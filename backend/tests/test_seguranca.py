"""Testes de segurança: login, bloqueio, recuperação de senha por código, troca obrigatória,
renovação de sessão, 2FA do admin, permissões e proteção contra acesso a dados de outros.
Rodar (dentro da pasta backend):  python -m pytest tests -q"""
import os
import re
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import auth  # noqa: E402
import models  # noqa: E402
import seguranca as seg  # noqa: E402
from database import SessionLocal  # noqa: E402

client = TestClient(main.app)
EMAILS = []  # e-mails "enviados" durante o teste


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    EMAILS.clear()
    monkeypatch.setattr(seg, "enviar_email", lambda para, assunto, texto: (EMAILS.append((para, assunto, texto)) or True))
    seg.resetar_limites()
    yield
    seg.resetar_limites()


def _criar(tel, tipo="tecnico", senha="Forte2026ab", email=None, localidade="sede", trocar=False):
    db = SessionLocal()
    u = db.query(models.Usuario).filter(models.Usuario.telefone == tel).first()
    if u:
        db.delete(u); db.commit()
    u = models.Usuario(nome=f"Pessoa {tel}", telefone=tel, email=email, senha_hash=auth.hash_senha(senha),
                       tipo=tipo, localidade=localidade, trocar_senha=trocar)
    db.add(u); db.commit(); uid = u.id; db.close()
    return uid


def _login(ident, senha):
    return client.post("/auth/login", json={"identificador": ident, "senha": senha})


def _H(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _codigo_do_ultimo_email():
    assert EMAILS, "nenhum e-mail enviado"
    return re.search(r"\b(\d{6})\b", EMAILS[-1][2]).group(1)


# ------------------------------------------------------------------ login e sessão
def test_login_devolve_tokens_e_funciona():
    _criar("32000000001")
    r = _login("32000000001", "Forte2026ab")
    assert r.status_code == 200
    d = r.json()
    assert d["access_token"] and d["refresh_token"] and d["trocar_senha"] is False
    assert client.get("/usuarios/eu", headers=_H(d)).status_code == 200


def test_login_erro_e_igual_para_conta_inexistente_e_senha_errada():
    _criar("32000000002")
    a = _login("32000000002", "errada123A")
    b = _login("nao-existe@exemplo.com", "errada123A")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_bloqueio_depois_de_5_senhas_erradas():
    _criar("32000000003")
    for _ in range(5):
        assert _login("32000000003", "errada123A").status_code == 401
    r = _login("32000000003", "Forte2026ab")  # mesmo a senha certa fica travada
    assert r.status_code == 429
    db = SessionLocal()
    u = db.query(models.Usuario).filter(models.Usuario.telefone == "32000000003").first()
    u.bloqueado_ate = seg.agora_utc() - timedelta(minutes=1); db.commit(); db.close()
    assert _login("32000000003", "Forte2026ab").status_code == 200


def test_limite_por_aparelho_no_login(monkeypatch):
    monkeypatch.setenv("SIGA_LIMITES_DESLIGADOS", "0")
    codigos = {_login(f"inexistente{i}@x.com", "Qualquer123").status_code for i in range(25)}
    assert 429 in codigos


def test_senha_fraca_obriga_troca_antes_de_usar(monkeypatch):
    monkeypatch.setattr(seg, "modo_teste", lambda: False)
    _criar("32000000004", senha="123456")
    d = _login("32000000004", "123456").json()
    assert d["trocar_senha"] is True
    assert client.get("/chamados/", headers=_H(d)).json() == {"detail": "TROCA_SENHA_OBRIGATORIA"}
    assert client.get("/usuarios/eu", headers=_H(d)).status_code == 200  # a tela de troca precisa disso
    r = client.post("/auth/trocar-senha", json={"senha_atual": "123456", "nova_senha": "123456"}, headers=_H(d))
    assert r.status_code == 400
    r = client.post("/auth/trocar-senha", json={"senha_atual": "123456", "nova_senha": "NovaForte2026"}, headers=_H(d))
    assert r.status_code == 200 and r.json()["trocar_senha"] is False
    novo = r.json()
    assert client.get("/chamados/", headers=_H(novo)).status_code == 200
    assert client.get("/chamados/", headers=_H(d)).status_code == 401  # token antigo morreu
    assert _login("32000000004", "123456").status_code == 401
    assert EMAILS == []  # sem e-mail cadastrado: nada enviado


def test_troca_de_senha_exige_senha_atual_e_regra():
    _criar("32000000005")
    d = _login("32000000005", "Forte2026ab").json()
    assert client.post("/auth/trocar-senha", json={"senha_atual": "errada", "nova_senha": "OutraForte2026"}, headers=_H(d)).status_code == 400
    assert client.post("/auth/trocar-senha", json={"senha_atual": "Forte2026ab", "nova_senha": "curta1"}, headers=_H(d)).status_code == 400
    assert client.post("/auth/trocar-senha", json={"senha_atual": "Forte2026ab", "nova_senha": "somenteletras"}, headers=_H(d)).status_code == 400


def test_refresh_gira_e_reuso_derruba_tudo():
    _criar("32000000006")
    d = _login("32000000006", "Forte2026ab").json()
    r1 = client.post("/auth/refresh", json={"refresh_token": d["refresh_token"]})
    assert r1.status_code == 200
    novo = r1.json()
    assert novo["refresh_token"] != d["refresh_token"]
    assert client.get("/usuarios/eu", headers=_H(novo)).status_code == 200
    # reaproveitar o token antigo = sinal de roubo: tudo cai, inclusive o par novo
    assert client.post("/auth/refresh", json={"refresh_token": d["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": novo["refresh_token"]}).status_code == 401
    assert client.get("/usuarios/eu", headers=_H(novo)).status_code == 401


def test_logout_e_logout_de_todos():
    _criar("32000000007")
    d = _login("32000000007", "Forte2026ab").json()
    assert client.post("/auth/logout", json={"refresh_token": d["refresh_token"]}).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": d["refresh_token"]}).status_code == 401
    a = _login("32000000007", "Forte2026ab").json()
    b = _login("32000000007", "Forte2026ab").json()
    assert client.post("/auth/logout-todos", headers=_H(a)).status_code == 200
    assert client.get("/usuarios/eu", headers=_H(b)).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 401


# ------------------------------------------------------------------ recuperação por código
def test_esqueci_senha_resposta_igual_exista_ou_nao():
    _criar("32000000008", email="rec8@exemplo.com")
    a = client.post("/auth/esqueci-senha", json={"identificador": "rec8@exemplo.com"})
    b = client.post("/auth/esqueci-senha", json={"identificador": "ninguem@exemplo.com"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert len(EMAILS) == 1 and EMAILS[0][0] == "rec8@exemplo.com"


def test_recuperacao_completa_e_codigo_de_uso_unico():
    _criar("32000000009", email="rec9@exemplo.com", senha="Antiga2026zz")
    antigo = _login("32000000009", "Antiga2026zz").json()
    client.post("/auth/esqueci-senha", json={"identificador": "32000000009"})  # pode pedir pelo telefone também
    codigo = _codigo_do_ultimo_email()
    corpo = {"identificador": "rec9@exemplo.com", "codigo": codigo, "nova_senha": "Nova2026Segura"}
    assert client.post("/auth/redefinir-senha", json={**corpo, "nova_senha": "fraca"}).status_code == 400  # não gasta o código
    assert client.post("/auth/redefinir-senha", json=corpo).status_code == 200
    assert client.post("/auth/redefinir-senha", json=corpo).status_code == 400  # código já usado
    assert _login("32000000009", "Antiga2026zz").status_code == 401
    assert _login("32000000009", "Nova2026Segura").status_code == 200
    assert client.get("/usuarios/eu", headers=_H(antigo)).status_code == 401  # sessão antiga caiu
    assert any("alterada" in e[1] for e in EMAILS)  # avisou por e-mail que a senha mudou


def test_codigo_errado_queima_depois_de_5_tentativas():
    _criar("32000000010", email="rec10@exemplo.com")
    client.post("/auth/esqueci-senha", json={"identificador": "rec10@exemplo.com"})
    certo = _codigo_do_ultimo_email()
    errado = "000000" if certo != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/redefinir-senha", json={"identificador": "rec10@exemplo.com", "codigo": errado, "nova_senha": "Nova2026Segura"}).status_code == 400
    assert client.post("/auth/redefinir-senha", json={"identificador": "rec10@exemplo.com", "codigo": certo, "nova_senha": "Nova2026Segura"}).status_code == 400


def test_codigo_expirado_nao_vale():
    _criar("32000000011", email="rec11@exemplo.com")
    client.post("/auth/esqueci-senha", json={"identificador": "rec11@exemplo.com"})
    codigo = _codigo_do_ultimo_email()
    db = SessionLocal()
    db.query(models.CodigoSeguranca).update({"expira_em": seg.agora_utc() - timedelta(minutes=1)}); db.commit(); db.close()
    assert client.post("/auth/redefinir-senha", json={"identificador": "rec11@exemplo.com", "codigo": codigo, "nova_senha": "Nova2026Segura"}).status_code == 400


def test_codigo_novo_invalida_o_anterior():
    _criar("32000000012", email="rec12@exemplo.com")
    client.post("/auth/esqueci-senha", json={"identificador": "rec12@exemplo.com"})
    primeiro = _codigo_do_ultimo_email()
    client.post("/auth/esqueci-senha", json={"identificador": "rec12@exemplo.com"})
    segundo = _codigo_do_ultimo_email()
    if primeiro != segundo:
        assert client.post("/auth/redefinir-senha", json={"identificador": "rec12@exemplo.com", "codigo": primeiro, "nova_senha": "Nova2026Segura"}).status_code == 400
    assert client.post("/auth/redefinir-senha", json={"identificador": "rec12@exemplo.com", "codigo": segundo, "nova_senha": "Nova2026Segura"}).status_code == 200


def test_limite_de_pedidos_de_codigo(monkeypatch):
    monkeypatch.setenv("SIGA_LIMITES_DESLIGADOS", "0")
    _criar("32000000013", email="rec13@exemplo.com")
    for _ in range(5):
        assert client.post("/auth/esqueci-senha", json={"identificador": "rec13@exemplo.com"}).status_code == 200
    qtd = len(EMAILS)
    assert client.post("/auth/esqueci-senha", json={"identificador": "rec13@exemplo.com"}).status_code in (200, 429)
    assert len(EMAILS) == qtd  # o 6º pedido não gera e-mail


# ------------------------------------------------------------------ 2FA do admin
def test_admin_com_2fa(monkeypatch):
    monkeypatch.setattr(seg, "doisfa_admin_ativo", lambda: True)
    _criar("32000000014", tipo="admin", email="adm14@exemplo.com", localidade=None)
    r = _login("32000000014", "Forte2026ab")
    d = r.json()
    assert d["requer_2fa"] is True and d["access_token"] is None and d["desafio"]
    assert d["email_mascarado"].endswith("@exemplo.com")
    codigo = _codigo_do_ultimo_email()
    errado = "000000" if codigo != "000000" else "111111"
    assert client.post("/auth/verificar-2fa", json={"desafio": d["desafio"], "codigo": errado}).status_code == 401
    ok = client.post("/auth/verificar-2fa", json={"desafio": d["desafio"], "codigo": codigo})
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert client.post("/auth/verificar-2fa", json={"desafio": "lixo", "codigo": codigo}).status_code == 401


# ------------------------------------------------------------------ admin: reset e auditoria
def test_admin_reseta_senha_e_so_admin():
    admin = _login_tokens(_criar("32000000015", tipo="admin", localidade=None, email="adm15@exemplo.com"), "32000000015")
    alvo = _criar("32000000016")
    tec = _login("32000000016", "Forte2026ab").json()
    assert client.post(f"/usuarios/{alvo}/resetar-senha", headers=_H(tec)).status_code == 403
    r = client.post(f"/usuarios/{alvo}/resetar-senha", headers=_H(admin))
    assert r.status_code == 200
    prov = r.json()["senha_provisoria"]
    assert not seg.problemas_senha(prov)
    assert _login("32000000016", "Forte2026ab").status_code == 401
    d = _login("32000000016", prov).json()
    assert d["trocar_senha"] is True
    assert client.get("/usuarios/eu", headers=_H(tec)).status_code == 401  # sessão antiga caiu


def _login_tokens(_uid, tel, senha="Forte2026ab"):
    return _login(tel, senha).json()


def test_auditoria_so_admin_e_registra_falhas():
    admin = _login_tokens(_criar("32000000017", tipo="admin", localidade=None, email="adm17@exemplo.com"), "32000000017")
    _criar("32000000018")
    _login("32000000018", "errada123A")
    tec = _login("32000000018", "Forte2026ab").json()
    assert client.get("/usuarios/auditoria", headers=_H(tec)).status_code == 403
    ev = client.get("/usuarios/auditoria", headers=_H(admin)).json()
    acoes = {e["acao"] for e in ev}
    assert {"login_falhou", "login_ok"} <= acoes


def test_usuario_criado_pelo_admin_precisa_senha_forte_e_trocar():
    admin = _login_tokens(_criar("32000000019", tipo="admin", localidade=None, email="adm19@exemplo.com"), "32000000019")
    base = {"nome": "Fulano Tecnico", "telefone": "32000000020", "tipo": "tecnico", "localidade": "sede"}
    assert client.post("/usuarios/", json={**base, "senha": "123456"}, headers=_H(admin)).status_code == 400
    r = client.post("/usuarios/", json={**base, "senha": "Inicial2026xy"}, headers=_H(admin))
    assert r.status_code == 200
    assert _login("32000000020", "Inicial2026xy").json()["trocar_senha"] is True
    assert client.post("/usuarios/", json={**base, "telefone": "32000000021", "tipo": "admin", "senha": "Inicial2026xy"}, headers=_H(admin)).status_code == 400  # admin sem e-mail


def test_admin_cria_usuario_sem_senha_e_servidor_gera_provisoria():
    admin = _login_tokens(_criar("32000000091", tipo="admin", localidade=None, email="adm91@exemplo.com"), "32000000091")
    r = client.post("/usuarios/", json={"nome": "Beltrano Quimico", "telefone": "32000000092", "tipo": "quimico"}, headers=_H(admin))
    assert r.status_code == 200
    prov = r.json()["senha_provisoria"]
    assert prov and not seg.senha_e_fraca(prov)
    login = _login("32000000092", prov).json()
    assert login["trocar_senha"] is True


def test_lista_de_usuarios_so_admin_com_busca_e_estado():
    admin = _login_tokens(_criar("32000000093", tipo="admin", localidade=None, email="adm93@exemplo.com"), "32000000093")
    _criar("32000000094", trocar=True)
    tec = _login("32000000094", "Forte2026ab").json()
    assert client.get("/usuarios/", headers=_H(tec)).status_code == 403
    lista = client.get("/usuarios/", params={"busca": "32000000094"}, headers=_H(admin)).json()
    assert len(lista) == 1 and lista[0]["trocar_senha"] is True and lista[0]["bloqueado"] is False
    assert "senha_hash" not in lista[0]
    assert all(u["tipo"] == "admin" for u in client.get("/usuarios/", params={"tipo": "admin"}, headers=_H(admin)).json())


def test_registro_publico_exige_email_e_senha_forte():
    corpo = {"nome": "Maria Cliente", "email": "maria.cli@exemplo.com", "telefone": "32000000022", "senha": "Forte2026ab"}
    assert client.post("/auth/registrar", json={**corpo, "email": "sem-arroba"}).status_code == 400
    assert client.post("/auth/registrar", json={**corpo, "senha": "12345678"}).status_code == 400
    assert client.post("/auth/registrar", json={**corpo, "senha": "Maria2026xyz"}).status_code == 400  # contém o nome
    assert client.post("/auth/registrar", json=corpo).status_code == 200
    assert client.post("/auth/registrar", json=corpo).status_code == 400  # duplicado


# ------------------------------------------------------------------ acesso a dados de outros
def _cliente_com_dados(tel, email):
    uid = _criar(tel, tipo="cliente", email=email, localidade="sede")
    db = SessionLocal()
    c = models.Cliente(usuario_id=uid, nome=f"Cliente {tel}", endereco="Rua A", bairro="Centro", cidade="Chalé",
                       hidrometro=f"H{tel}", categoria="residencial", localidade="sede", status_cadastro="aprovado")
    db.add(c); db.commit()
    from datetime import datetime
    f = models.Fatura(cliente_id=c.id, competencia="2026-09", consumo_m3=10, valor_agua=50, valor_esgoto=40,
                      valor_total=90, vencimento=datetime(2026, 10, 10))
    db.add(f); db.commit()
    fid = f.id; cid = c.id; db.close()
    tok = _login_tokens(uid, tel)
    ch = client.post("/chamados/meu", json={"tipo": "falta_agua", "descricao_problema": "sem água"}, headers=_H(tok))
    assert ch.status_code == 200, ch.text
    return tok, fid, ch.json()["id"], cid


def test_cliente_nao_baixa_pdf_de_outro_cliente():
    tok_a, fatura_a, chamado_a, _ = _cliente_com_dados("32000000030", "a30@exemplo.com")
    tok_b, fatura_b, chamado_b, _ = _cliente_com_dados("32000000031", "b31@exemplo.com")
    assert client.get(f"/faturamento/faturas/{fatura_a}/pdf", headers=_H(tok_a)).status_code == 200
    assert client.get(f"/faturamento/faturas/{fatura_a}/pdf", headers=_H(tok_b)).status_code == 404
    assert client.get(f"/chamados/{chamado_a}/relatorio-pdf", headers=_H(tok_a)).status_code == 200
    assert client.get(f"/chamados/{chamado_a}/relatorio-pdf", headers=_H(tok_b)).status_code == 404


def test_cliente_nao_lista_chamados_nem_estoque_e_nao_abre_em_nome_de_outro():
    tok_a, _, _, cid_a = _cliente_com_dados("32000000032", "a32@exemplo.com")
    tok_b, _, _, cid_b = _cliente_com_dados("32000000033", "b33@exemplo.com")
    assert client.get("/chamados/", headers=_H(tok_a)).status_code == 403
    assert client.get("/estoque/itens", headers=_H(tok_a)).status_code == 403
    assert client.get("/estoque/saldo", headers=_H(tok_a)).status_code == 403
    assert client.get("/analise-eta/lavagem-filtro", headers=_H(tok_a)).status_code == 403
    r = client.post("/chamados/", json={"cliente_id": cid_b, "tipo": "vazamento", "descricao_problema": "x"}, headers=_H(tok_a))
    assert r.status_code == 403


def test_tecnico_so_ve_os_proprios_chamados():
    tok_c, _, chamado, _ = _cliente_com_dados("32000000034", "c34@exemplo.com")
    tec1 = _criar("32000000035"); tec2 = _criar("32000000036")
    t1 = _login_tokens(tec1, "32000000035"); t2 = _login_tokens(tec2, "32000000036")
    db = SessionLocal()
    db.query(models.Chamado).filter(models.Chamado.id == chamado).update({"tecnico_id": tec1}); db.commit(); db.close()
    ids1 = {c["id"] for c in client.get("/chamados/", headers=_H(t1)).json()}
    ids2 = {c["id"] for c in client.get(f"/chamados/?tecnico_id={tec1}", headers=_H(t2)).json()}  # tenta espiar o colega
    assert chamado in ids1 and chamado not in ids2
    assert client.get(f"/chamados/{chamado}/relatorio-pdf", headers=_H(t2)).status_code == 403
    assert client.get(f"/chamados/{chamado}/fotos", headers=_H(t2)).status_code == 403


def test_uploads_exigem_login_e_bloqueiam_caminho_fora_da_pasta():
    assert client.get("/uploads/chamados/qualquer.jpg").status_code == 401
    tec = _login_tokens(_criar("32000000037"), "32000000037")
    assert client.get("/uploads/../main.py", headers=_H(tec)).status_code == 404
    assert client.get("/uploads/%2e%2e/main.py", headers=_H(tec)).status_code == 404
    cli, _, _, _ = _cliente_com_dados("32000000038", "c38@exemplo.com")
    assert client.get("/uploads/chamados/x.jpg", headers=_H(cli)).status_code == 403


def test_cabecalhos_de_seguranca():
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


# ------------------------------------------------------------------ hidrômetro só na sede
def _cliente_em(tel, localidade, hidrometro="H-1"):
    uid = _criar(tel, tipo="cliente", localidade=localidade, email=f"c{tel}@exemplo.com")
    db = SessionLocal()
    db.add(models.Cliente(usuario_id=uid, nome=f"Cli {tel}", endereco="Rua", cidade="Chalé", hidrometro=hidrometro,
                          categoria="residencial", localidade=localidade, status_cadastro="aprovado"))
    db.commit(); db.close()
    return _login(tel, "Forte2026ab").json()


def test_hidrometro_so_na_sede_cadastro_limpa_campo_fora_da_sede():
    cli = _criar("32000000101", tipo="cliente", email="c101@exemplo.com", localidade=None)
    t = _login("32000000101", "Forte2026ab").json()
    corpo = {"nome": "Fulano", "endereco": "Rua A", "hidrometro": "H-99", "localidade": "bananal"}
    r = client.post("/clientes/eu", json=corpo, headers=_H(t))
    assert r.status_code == 200 and r.json()["hidrometro"] is None
    r = client.patch("/clientes/eu", json={**corpo, "localidade": "sede"}, headers=_H(t))
    assert r.status_code == 200, r.text
    assert r.json()["hidrometro"] == "H-99"
    r = client.patch("/clientes/eu", json={**corpo, "localidade": "agua_limpa"}, headers=_H(t))
    assert r.json()["hidrometro"] is None


def test_leitura_nao_existe_fora_da_sede():
    t = _cliente_em("32000000102", "penha_do_coco", hidrometro=None)
    r = client.post("/leituras/", data={"valor_informado": "10"}, files={"foto": ("h.jpg", b"x", "image/jpeg")}, headers=_H(t))
    assert r.status_code == 400 and "sede" in r.json()["detail"]
    assert client.get("/leituras/pendente-mes", headers=_H(t)).json()["aplica"] is False
    sede = _cliente_em("32000000103", "sede")
    assert client.get("/leituras/pendente-mes", headers=_H(sede)).json()["aplica"] is True
