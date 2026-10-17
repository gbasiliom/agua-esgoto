"""Testes do módulo de qualidade da água e da correção do cadastro público.
Rodar (dentro da pasta backend):  python -m pytest tests -q
Usa um banco SQLite temporário e chaves de teste — não toca no siga.db."""
import base64
import os
import sys
import tempfile
from datetime import date, datetime, timedelta

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/teste.db"
os.environ["CHAVE_CRIPTOGRAFIA"] = base64.urlsafe_b64encode(b"k" * 32).decode()
os.environ["SECRET_KEY"] = "chave-de-teste"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import auth  # noqa: E402
import models  # noqa: E402
from database import SessionLocal  # noqa: E402
import qualidade_regras as nr  # noqa: E402
from routers import qualidade_router  # noqa: E402

qualidade_router.PASTA_LAUDOS = os.path.join(_tmp, "laudos")
client = TestClient(main.app)


def _criar_usuario(tipo, tel, localidade=None):
    db = SessionLocal()
    u = models.Usuario(nome=f"{tipo} teste", telefone=tel, senha_hash=auth.hash_senha("senha123"), tipo=tipo, localidade=localidade)
    db.add(u); db.commit(); db.close()
    r = client.post("/auth/login", json={"identificador": tel, "senha": "senha123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def H():
    return {
        "admin": _criar_usuario("admin", "1000"),
        "quimico": _criar_usuario("quimico", "2000"),
        "tecnico": _criar_usuario("tecnico", "3000", "sede"),
        "operador": _criar_usuario("operador", "4000"),
    }


# ---------------- Fase 0: cadastro público ----------------

def test_registro_publico_nunca_cria_admin():
    r = client.post("/auth/registrar", json={"nome": "Intruso", "email": "intruso@exemplo.com", "telefone": "9999", "senha": "Zq83pLm2x", "tipo": "admin"})
    assert r.status_code == 200
    assert r.json()["tipo_usuario"] == "cliente"
    tok = r.json()["access_token"]
    r2 = client.get("/usuarios/eu", headers={"Authorization": f"Bearer {tok}"})
    assert r2.json()["tipo"] == "cliente"
    # e não consegue listar clientes (rota de equipe)
    assert client.get("/clientes/", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_registro_duplicado_e_localidade_invalida():
    assert client.post("/auth/registrar", json={"nome": "A", "email": "a@exemplo.com", "telefone": "9999", "senha": "Segura2026a"}).status_code == 400
    assert client.post("/auth/registrar", json={"nome": "B", "email": "b@exemplo.com", "telefone": "8888", "senha": "Segura2026b", "localidade": "marte"}).status_code == 400


def test_somente_admin_cria_usuario_interno(H):
    corpo = {"nome": "Novo Químico", "telefone": "5000", "senha": "Quimic0Forte", "tipo": "quimico"}
    assert client.post("/usuarios/", json=corpo).status_code == 401
    assert client.post("/usuarios/", json=corpo, headers=H["operador"]).status_code == 403
    assert client.post("/usuarios/", json=corpo, headers=H["quimico"]).status_code == 403
    r = client.post("/usuarios/", json=corpo, headers=H["admin"])
    assert r.status_code == 200 and r.json()["tipo"] == "quimico"
    assert client.post("/usuarios/", json={**corpo, "telefone": "5001", "tipo": "root"}, headers=H["admin"]).status_code == 400
    assert client.post("/usuarios/", json={**corpo, "telefone": "5002", "tipo": "tecnico"}, headers=H["admin"]).status_code == 400  # sem localidade
    assert client.post("/usuarios/", json=corpo, headers=H["admin"]).status_code == 400  # duplicado


# ---------------- Regras puras ----------------

def test_regras_padrao_superficial_lenta_pop_pequena():
    regras, avisos = nr.gerar_regras_padrao(1500, "superficial", "lenta")
    por_grupo = {r["grupo"]: r for r in regras}
    assert por_grupo["fq_saida"]["quantidade"] == 12 and por_grupo["fq_saida"]["periodo"] == "dia"
    assert por_grupo["turbidez_filtro"]["quantidade"] == 1 and por_grupo["turbidez_filtro"]["periodo"] == "dia"
    assert por_grupo["bact_saida"]["quantidade"] == 2 and por_grupo["bact_saida"]["periodo"] == "semana"
    assert por_grupo["bact_rede"]["quantidade"] == 5 and por_grupo["bact_rede"]["periodo"] == "mes"
    assert por_grupo["ecoli_captacao"]["periodo"] == "mes"
    assert por_grupo["agua_bruta_semestral"]["periodo"] == "semestre"
    assert avisos == []


def test_regras_faixas_e_populacao_grande():
    assert nr.minimo_bacteriologico_rede(4999) == 5
    assert nr.minimo_bacteriologico_rede(5000) == 10
    assert nr.minimo_bacteriologico_rede(10000) == 10
    assert nr.minimo_bacteriologico_rede(10001) is None
    regras, avisos = nr.gerar_regras_padrao(30000, "superficial", "rapida", numero_filtros=2)
    assert "bact_rede" not in {r["grupo"] for r in regras} and avisos
    assert {r["grupo"]: r for r in regras}["turbidez_filtro"]["quantidade"] == 24


def test_regras_subterraneo():
    regras, _ = nr.gerar_regras_padrao(800, "subterraneo", None)
    g = {r["grupo"]: r for r in regras}
    assert g["fq_saida"]["periodo"] == "semana" and g["bact_saida"]["quantidade"] == 1
    assert "ecoli_captacao" not in g and "cianobacterias" not in g and "turbidez_filtro" not in g


def test_avaliar_bacteriologia():
    assert nr.avaliar_bacteriologia("saida_eta", False, False)[0] is True
    c, al, rec = nr.avaliar_bacteriologia("saida_eta", True, False)
    assert c is False and rec is True and al
    c, al, rec = nr.avaliar_bacteriologia("rede", False, True)
    assert c is False and rec is True
    assert nr.avaliar_bacteriologia("captacao", True, True) == (None, [], False)


def test_avaliar_mes_rede():
    assert nr.avaliar_mes_rede(3000, 5, 0, 0)[0] == "ok"
    assert nr.avaliar_mes_rede(3000, 5, 1, 0)[0] == "atencao"
    assert nr.avaliar_mes_rede(3000, 5, 2, 0)[0] == "violacao"
    assert nr.avaliar_mes_rede(3000, 5, 0, 1)[0] == "violacao"
    assert nr.avaliar_mes_rede(25000, 100, 6, 0)[0] == "violacao"  # 94% ausência
    assert nr.avaliar_mes_rede(25000, 100, 5, 0)[0] == "ok"
    assert nr.avaliar_mes_rede(3000, 0, 0, 0)[0] == "sem_dados"


def test_media_geometrica_e_janelas():
    assert round(nr.media_geometrica([10, 1000]), 6) == 100.0
    assert nr.media_geometrica([0, 0]) == 1.0
    assert nr.media_geometrica([]) is None
    j = nr.janelas_da_regra("semana", 2026, 10, date(2026, 11, 15))
    assert len(j) == 4 and j[0][1].weekday() == 6 and all(x[2] for x in j)  # domingos de out/2026 = 4, 11, 18, 25
    assert [x[1].day for x in j] == [4, 11, 18, 25]
    assert len(nr.janelas_da_regra("dia", 2026, 10, date(2026, 10, 10))) == 10
    assert nr.janelas_da_regra("semestre", 2026, 10, date(2026, 10, 10))[0][:2] == (date(2026, 7, 1), date(2026, 12, 31))
    assert nr.janelas_da_regra("mes", 2026, 12, date(2027, 1, 5))[0] == (date(2026, 12, 1), date(2026, 12, 31), True)


# ---------------- API: config, pontos, regras ----------------

def test_config_regras_pontos(H):
    L = "bananal"
    assert client.get(f"/qualidade/config/{L}", headers=H["quimico"]).status_code == 404
    corpo = {"populacao_abastecida": 1200, "manancial": "superficial", "filtracao": "lenta", "numero_filtros": 1}
    assert client.put(f"/qualidade/config/{L}", json=corpo, headers=H["quimico"]).status_code == 403
    assert client.put(f"/qualidade/config/{L}", json={**corpo, "filtracao": None}, headers=H["admin"]).status_code == 400
    assert client.put(f"/qualidade/config/{L}", json=corpo, headers=H["admin"]).status_code == 200
    r = client.post(f"/qualidade/regras/gerar/{L}", headers=H["admin"])
    assert r.status_code == 200 and len(r.json()["regras"]) == 7
    # editar regra marca como manual e sobrevive a nova geração
    regra = next(x for x in r.json()["regras"] if x["grupo"] == "bact_rede")
    e = client.patch(f"/qualidade/regras/{regra['id']}", json={"quantidade": 8}, headers=H["admin"])
    assert e.json()["quantidade"] == 8 and e.json()["manual"] is True
    r2 = client.post(f"/qualidade/regras/gerar/{L}", headers=H["admin"])
    assert next(x for x in r2.json()["regras"] if x["grupo"] == "bact_rede")["quantidade"] == 8
    assert len(r2.json()["regras"]) == 7
    assert client.post("/qualidade/pontos", json={"localidade": L, "tipo": "lua", "nome": "x"}, headers=H["admin"]).status_code == 400
    assert client.post("/qualidade/pontos", json={"localidade": L, "tipo": "rede", "nome": "x"}, headers=H["tecnico"]).status_code == 403


def _montar_localidade(H, L, pop=3000):
    client.put(f"/qualidade/config/{L}", json={"populacao_abastecida": pop, "manancial": "superficial", "filtracao": "lenta", "numero_filtros": 1}, headers=H["admin"])
    client.post(f"/qualidade/regras/gerar/{L}", headers=H["admin"])
    ids = {}
    for tipo, nome in (("captacao", "Captação rio"), ("saida_eta", "Saída ETA"), ("rede", "Rede - ponta"), ("reservatorio", "Reservatório")):
        r = client.post("/qualidade/pontos", json={"localidade": L, "tipo": tipo, "nome": nome}, headers=H["quimico"])
        if r.status_code == 400:  # já existe (helper reutilizado na mesma localidade)
            existentes = client.get(f"/qualidade/pontos?localidade={L}&tipo={tipo}", headers=H["quimico"]).json()
            ids[tipo] = next(p["id"] for p in existentes if p["nome"] == nome)
            continue
        assert r.status_code == 200, r.text
        ids[tipo] = r.json()["id"]
    return ids


def test_fluxo_positivo_gera_recoleta_na_rede(H):
    P = _montar_localidade(H, "sede")
    agora = datetime.now()
    a = client.post("/qualidade/amostras", json={"ponto_id": P["rede"], "grupo": "bact_rede", "cloro_residual": 0.6, "cor_aparente": 3, "turbidez": 0.8}, headers=H["quimico"])
    assert a.status_code == 200, a.text
    am = a.json()
    assert am["codigo"].startswith("SED") and am["status"] == "coletada"
    # grupo errado para o tipo de ponto
    assert client.post("/qualidade/amostras", json={"ponto_id": P["saida_eta"], "grupo": "bact_rede"}, headers=H["quimico"]).status_code == 400
    # resultado exige os dois organismos
    assert client.post(f"/qualidade/amostras/{am['id']}/resultado", json={"e_coli_presente": False}, headers=H["quimico"]).status_code == 400
    r = client.post(f"/qualidade/amostras/{am['id']}/resultado", json={"coliformes_totais_presente": True, "e_coli_presente": False, "metodo": "Colilert", "lote_kit": "L1"}, headers=H["quimico"])
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["resultado"]["conforme"] is False
    assert len(corpo["recoletas_criadas"]) == 3
    assert {x["posicao_recoleta"] for x in corpo["recoletas_criadas"]} == {"mesmo_ponto", "montante", "jusante"}
    assert all(x["status"] == "pendente" and x["recoleta_de_id"] == am["id"] for x in corpo["recoletas_criadas"])
    assert any("POSITIVO" in t for t in corpo["alertas"])
    # não permite lançar duas vezes
    assert client.post(f"/qualidade/amostras/{am['id']}/resultado", json={"coliformes_totais_presente": False, "e_coli_presente": False}, headers=H["quimico"]).status_code == 409
    # recoleta pendente não aceita resultado antes da coleta
    rec = corpo["recoletas_criadas"][0]
    assert client.post(f"/qualidade/amostras/{rec['id']}/resultado", json={"coliformes_totais_presente": False, "e_coli_presente": False}, headers=H["quimico"]).status_code == 400
    c = client.patch(f"/qualidade/amostras/{rec['id']}/coleta", json={"cloro_residual": 0.8, "cor_aparente": 2, "turbidez": 0.5}, headers=H["quimico"])
    assert c.status_code == 200 and c.json()["status"] == "coletada"
    r = client.post(f"/qualidade/amostras/{rec['id']}/resultado", json={"coliformes_totais_presente": False, "e_coli_presente": False}, headers=H["quimico"])
    assert r.json()["resultado"]["conforme"] is True and r.json()["recoletas_criadas"] == []
    # alerta de medições faltando (sem cloro/cor/turbidez)
    a2 = client.post("/qualidade/amostras", json={"ponto_id": P["saida_eta"], "grupo": "bact_saida"}, headers=H["quimico"]).json()
    r = client.post(f"/qualidade/amostras/{a2['id']}/resultado", json={"coliformes_totais_presente": False, "e_coli_presente": False}, headers=H["quimico"])
    assert any("Art. 44" in t for t in r.json()["alertas"])
    # E. coli na saída => recoleta única no mesmo ponto
    a3 = client.post("/qualidade/amostras", json={"ponto_id": P["saida_eta"], "grupo": "bact_saida", "cloro_residual": 1, "cor_aparente": 1, "turbidez": 1}, headers=H["admin"]).json()
    r = client.post(f"/qualidade/amostras/{a3['id']}/resultado", json={"coliformes_totais_presente": False, "e_coli_presente": True}, headers=H["admin"])
    assert len(r.json()["recoletas_criadas"]) == 1 and r.json()["recoletas_criadas"][0]["posicao_recoleta"] == "mesmo_ponto"
    # técnico e operador não lançam
    assert client.post("/qualidade/amostras", json={"ponto_id": P["rede"], "grupo": "bact_rede"}, headers=H["tecnico"]).status_code == 403
    assert client.post("/qualidade/amostras", json={"ponto_id": P["rede"], "grupo": "bact_rede"}, headers=H["operador"]).status_code == 403
    assert client.get("/qualidade/amostras", headers=H["operador"]).status_code == 200
    assert client.get("/qualidade/amostras", headers=H["tecnico"]).status_code == 403


def test_conformidade_e_pdf(H):
    L = "penha_do_coco"
    P = _montar_localidade(H, L, pop=2000)
    hoje = date.today()
    # 3 de 5 amostras de rede (rotina) neste mês; 1 com coliformes
    for i in range(3):
        a = client.post("/qualidade/amostras", json={"ponto_id": P["rede"], "grupo": "bact_rede", "cloro_residual": 0.5, "cor_aparente": 1, "turbidez": 1}, headers=H["quimico"]).json()
        client.post(f"/qualidade/amostras/{a['id']}/resultado", json={"coliformes_totais_presente": i == 0, "e_coli_presente": False}, headers=H["quimico"])
    # análises diárias de ETA pelo químico (informando localidade)
    for h in (6, 8, 10):
        r = client.post("/analise-eta/", json={"coletado_em": datetime.combine(hoje, datetime.min.time()).replace(hour=h).isoformat(), "localidade": L, "turbidez_filtrada": 0.4, "cloro_residual": 1.0}, headers=H["quimico"])
        assert r.status_code == 200, r.text
    assert client.post("/analise-eta/", json={"coletado_em": datetime.now().isoformat()}, headers=H["quimico"]).status_code == 400  # sem localidade
    mes = f"{hoje.year}-{hoje.month:02d}"
    # consulta como se fosse o último dia do mês, para fechar as janelas
    fim = date(hoje.year + (hoje.month == 12), (hoje.month % 12) + 1, 1)  # 1º do mês seguinte: tudo encerrado
    r = client.get(f"/qualidade/conformidade?localidade={L}&mes={mes}&ate={fim.isoformat()}", headers=H["operador"])
    assert r.status_code == 200
    d = r.json()
    por = {x["grupo"]: x for x in d["regras"]}
    assert por["bact_rede"]["exigido"] == 5 and por["bact_rede"]["realizado"] == 3 and por["bact_rede"]["status"] == "deficit"
    assert por["bact_saida"]["status"] == "deficit"
    assert por["fq_saida"]["realizado"] == 3 and por["fq_saida"]["status"] == "deficit"
    assert por["turbidez_filtro"]["realizado"] == 1 and por["turbidez_filtro"]["realizado_bruto"] == 3  # exigido 1/dia: excedente não compensa outros dias
    assert d["rede"]["status"] == "atencao" and d["rede"]["amostras_analisadas"] == 3
    assert len(d["recoletas_pendentes"]) == 3
    # estando no meio do mês, deficit vira "em_andamento" para a rede
    r2 = client.get(f"/qualidade/conformidade?localidade={L}&mes={mes}&ate={date(hoje.year, hoje.month, 1).isoformat()}", headers=H["admin"]).json()
    assert {x["grupo"]: x for x in r2["regras"]}["bact_rede"]["status"] == "em_andamento"
    # PDF
    p = client.get(f"/qualidade/relatorio-mensal-pdf?localidade={L}&mes={mes}", headers=H["quimico"])
    assert p.status_code == 200 and p.content[:4] == b"%PDF"
    assert client.get(f"/qualidade/conformidade?localidade=marte", headers=H["admin"]).status_code == 400
    assert client.get(f"/qualidade/conformidade?localidade={L}&mes=2026-13", headers=H["admin"]).status_code == 400


def test_ecoli_captacao_cianobacterias_e_laudo(H):
    L = "agua_limpa"
    P = _montar_localidade(H, L, pop=900)
    # E. coli 5000 NMP e 2000 NMP => média geométrica ~3162 >= 1000
    for v in (5000, 2000):
        a = client.post("/qualidade/amostras", json={"ponto_id": P["captacao"], "grupo": "ecoli_captacao"}, headers=H["quimico"]).json()
        assert client.post(f"/qualidade/amostras/{a['id']}/resultado", json={"coliformes_totais_nmp": 9999, "e_coli_presente": True}, headers=H["quimico"]).status_code == 400  # exige NMP
        r = client.post(f"/qualidade/amostras/{a['id']}/resultado", json={"e_coli_nmp": v}, headers=H["quimico"])
        assert r.status_code == 200 and r.json()["resultado"]["conforme"] is None and r.json()["recoletas_criadas"] == []
    assert any("1.000" in t or "1000" in t for t in r.json()["alertas"])
    s = client.get(f"/qualidade/ecoli-captacao/{L}", headers=H["operador"]).json()
    assert s["acima_do_limite"] is True and round(s["media_geometrica_12m"]) == 3162 and len(s["medicoes"]) == 2
    # cianobactérias > 10.000 vira semanal; > 20.000 alerta de cianotoxinas
    a = client.post("/qualidade/amostras", json={"ponto_id": P["captacao"], "grupo": "cianobacterias"}, headers=H["quimico"]).json()
    r = client.post(f"/qualidade/amostras/{a['id']}/resultado", json={"cianobacterias_cel_ml": 25000}, headers=H["quimico"])
    assert any("cianotoxinas" in t for t in r.json()["alertas"])
    hoje = date.today()
    d = client.get(f"/qualidade/conformidade?localidade={L}", headers=H["admin"]).json()
    cian = next(x for x in d["regras"] if x["grupo"] == "cianobacterias")
    assert cian["periodo"] == "semana" and cian["nota"]
    assert any("20.000" in t for t in d["alertas"])
    # laudo externo (Viçosa) com arquivo; contagem da regra semestral
    arq = ("laudo.pdf", b"%PDF-1.4 teste", "application/pdf")
    dados = {"localidade": L, "tipo": "agua_bruta_semestral", "laboratorio": "Lab Viçosa", "data_coleta": hoje.isoformat(), "numero_laudo": "123/2026", "conforme": "true"}
    assert client.post("/qualidade/laudos", data=dados, files={"arquivo": arq}, headers=H["tecnico"]).status_code == 403
    r = client.post("/qualidade/laudos", data=dados, files={"arquivo": arq}, headers=H["quimico"])
    assert r.status_code == 200, r.text
    laudo = r.json()
    assert laudo["tem_arquivo"] is True
    assert client.get(f"/qualidade/laudos/{laudo['id']}/arquivo").status_code == 401  # só com login
    dl = client.get(f"/qualidade/laudos/{laudo['id']}/arquivo", headers=H["operador"])
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF")
    assert client.post("/qualidade/laudos", data=dados, files={"arquivo": ("x.exe", b"MZ", "application/octet-stream")}, headers=H["quimico"]).status_code == 400
    assert client.post("/qualidade/laudos", data={**dados, "tipo": "outro2"}, headers=H["quimico"]).status_code == 400
    d = client.get(f"/qualidade/conformidade?localidade={L}", headers=H["admin"]).json()
    assert next(x for x in d["regras"] if x["grupo"] == "agua_bruta_semestral")["realizado"] == 1
    assert len(client.get(f"/qualidade/laudos?localidade={L}", headers=H["operador"]).json()) == 1
    # a pasta de laudos NÃO é servida publicamente
    assert client.get("/uploads/../dados_laudos/x").status_code in (404, 400)


def test_encaminhar_amostra(H):
    P = _montar_localidade(H, "sede")  # reaproveita config; cria pontos novos
    a = client.post("/qualidade/amostras", json={"ponto_id": P["captacao"], "grupo": "agua_bruta_semestral"}, headers=H["quimico"]).json()
    assert client.post(f"/qualidade/amostras/{a['id']}/resultado", json={}, headers=H["quimico"]).status_code == 400  # só por laudo
    e = client.post(f"/qualidade/amostras/{a['id']}/encaminhar", headers=H["quimico"])
    assert e.status_code == 200 and e.json()["status"] == "encaminhada"


# ---------------- Operador de ETA ----------------

def test_operador_eta(H):
    corpo = {"nome": "Op ETA Bananal", "telefone": "6000", "senha": "OperEta2026", "tipo": "operador_eta"}
    assert client.post("/usuarios/", json=corpo, headers=H["admin"]).status_code == 400  # exige localidade
    r = client.post("/usuarios/", json={**corpo, "localidade": "bananal"}, headers=H["admin"])
    assert r.status_code == 200 and r.json()["tipo"] == "operador_eta"
    login = client.post("/auth/login", json={"identificador": "6000", "senha": "OperEta2026"}).json()
    assert login["trocar_senha"] is True  # conta criada pelo admin: troca obrigatória no 1º acesso
    tok = client.post("/auth/trocar-senha", json={"senha_atual": "OperEta2026", "nova_senha": "OperEta2027"},
                      headers={"Authorization": f"Bearer {login['access_token']}"}).json()["access_token"]
    HE = {"Authorization": f"Bearer {tok}"}
    a = client.post("/analise-eta/", json={"coletado_em": datetime.now().isoformat(), "turbidez_filtrada": 0.3, "cloro_residual": 1.1}, headers=HE)
    assert a.status_code == 200, a.text
    assert client.get("/analise-eta/minhas", headers=HE).status_code == 200
    # não acessa a qualidade (químico) nem usuários
    assert client.get("/qualidade/amostras", headers=HE).status_code == 403
    assert client.post("/qualidade/pontos", json={"localidade": "bananal", "tipo": "rede", "nome": "x"}, headers=HE).status_code == 403
    assert client.post("/usuarios/", json={**corpo, "telefone": "6001", "localidade": "sede"}, headers=HE).status_code == 403


def test_ponto_duplicado_recusado(H):
    corpo = {"localidade": "bananal", "tipo": "rede", "nome": "Escola Duplicada"}
    assert client.post("/qualidade/pontos", json=corpo, headers=H["quimico"]).status_code == 200
    assert client.post("/qualidade/pontos", json={**corpo, "nome": "  escola duplicada "}, headers=H["quimico"]).status_code == 400
    assert client.post("/qualidade/pontos", json={**corpo, "nome": "   "}, headers=H["quimico"]).status_code == 400
    assert client.post("/qualidade/pontos", json={**corpo, "tipo": "reservatorio"}, headers=H["quimico"]).status_code == 200
