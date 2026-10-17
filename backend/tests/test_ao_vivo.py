"""Testes do acompanhamento ao vivo das análises da ETA (químico recebe o que o operador lança).
Rodar (dentro da pasta backend):  python -m pytest tests -q"""
import base64
import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/teste_vivo.db")
os.environ.setdefault("CHAVE_CRIPTOGRAFIA", base64.urlsafe_b64encode(b"k" * 32).decode())
os.environ.setdefault("SECRET_KEY", "chave-de-teste")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import auth  # noqa: E402
import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from routers import analise_eta_router as ar  # noqa: E402

client = TestClient(main.app)


def _login(tipo, tel, localidade=None):
    db = SessionLocal()
    db.add(models.Usuario(nome=f"{tipo} vivo", telefone=tel, senha_hash=auth.hash_senha("senha123"), tipo=tipo, localidade=localidade))
    db.commit(); db.close()
    r = client.post("/auth/login", json={"identificador": tel, "senha": "senha123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def H():
    yield _usuarios()
    # limpa o que este arquivo lançou, para não alterar as contagens dos outros testes (banco compartilhado)
    db = SessionLocal()
    ids = [u.id for u in db.query(models.Usuario).filter(models.Usuario.telefone.like("319000001%")).all()]
    db.query(models.AnaliseEta).filter(models.AnaliseEta.tecnico_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.LavagemFiltro).filter(models.LavagemFiltro.tecnico_id.in_(ids)).delete(synchronize_session=False)
    db.commit(); db.close()


def _usuarios():
    return {
        "eta_pc": _login("operador_eta", "31900000101", "penha_do_coco"),
        "eta_ba": _login("operador_eta", "31900000102", "bananal"),
        "quimico": _login("quimico", "31900000103"),
        "cliente": _login("cliente", "31900000104"),
        "tecnico": _login("tecnico", "31900000105", "sede"),
    }


def _analise(h, quando, **kw):
    r = client.post("/analise-eta/", json={"coletado_em": quando.isoformat(), **kw}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_primeira_carga_e_incremental(H):
    q = H["quimico"]
    r0 = client.get("/analise-eta/ao-vivo", headers=q).json()
    assert r0["primeira_carga"] is True
    assert r0["analises"] == [] and r0["ultimo_id_analise"] == 0
    assert {l["localidade"] for l in r0["localidades"]} == {"sede", "penha_do_coco", "bananal", "agua_limpa"}
    assert all(l["tem_dados"] is False and l["atrasada"] is False for l in r0["localidades"])

    agora = ar.agora_brasilia()
    a1 = _analise(H["eta_pc"], agora, turbidez_filtrada=0.3, ph_tratada=7.2, cloro_residual=1.0)
    r1 = client.get("/analise-eta/ao-vivo", headers=q).json()
    assert [a["id"] for a in r1["analises"]] == [a1["id"]]

    # segunda chamada só traz o que for novo
    r2 = client.get("/analise-eta/ao-vivo", params={"apos_analise": r1["ultimo_id_analise"], "apos_lavagem": r1["ultimo_id_lavagem"]}, headers=q).json()
    assert r2["primeira_carga"] is False and r2["analises"] == []
    assert r2["ultimo_id_analise"] == r1["ultimo_id_analise"]

    fora = _analise(H["eta_pc"], agora, turbidez_filtrada=1.8, cloro_residual=0.05)
    assert fora["conforme"] is False
    r3 = client.get("/analise-eta/ao-vivo", params={"apos_analise": r1["ultimo_id_analise"]}, headers=q).json()
    assert [a["id"] for a in r3["analises"]] == [fora["id"]]
    assert r3["analises"][0]["conforme"] is False
    pc = next(l for l in r3["localidades"] if l["localidade"] == "penha_do_coco")
    assert pc["tem_dados"] and pc["ultima_conforme"] is False and len(pc["ultimos_alertas"]) >= 2


def test_lavagem_aparece_e_filtro_de_localidade(H):
    q = H["quimico"]
    base = client.get("/analise-eta/ao-vivo", headers=q).json()
    r = client.post("/analise-eta/lavagem-filtro", json={"hora": ar.agora_brasilia().isoformat(), "tempo_gasto_min": 12, "volume_gasto": 3.5}, headers=H["eta_ba"])
    assert r.status_code == 200
    novo = client.get("/analise-eta/ao-vivo", params={"apos_analise": base["ultimo_id_analise"], "apos_lavagem": base["ultimo_id_lavagem"]}, headers=q).json()
    assert len(novo["lavagens"]) == 1 and novo["lavagens"][0]["localidade"] == "bananal"
    so_pc = client.get("/analise-eta/ao-vivo", params={"localidade": "penha_do_coco", "apos_lavagem": base["ultimo_id_lavagem"]}, headers=q).json()
    assert so_pc["lavagens"] == [] and len(so_pc["localidades"]) == 1
    assert client.get("/analise-eta/ao-vivo", params={"localidade": "marte"}, headers=q).status_code == 400


def test_permissoes(H):
    assert client.get("/analise-eta/ao-vivo").status_code in (401, 403)
    for quem in ("cliente", "tecnico", "eta_pc"):
        assert client.get("/analise-eta/ao-vivo", headers=H[quem]).status_code == 403


def test_atraso_so_no_turno_e_com_tolerancia():
    db = SessionLocal()
    try:
        u = db.query(models.Usuario).filter(models.Usuario.telefone == "31900000102").first()
        db.add(models.AnaliseEta(tecnico_id=u.id, localidade="bananal", coletado_em=datetime(2026, 10, 14, 10, 0), conforme=True))
        db.commit()
        dia = lambda h, m=0: datetime(2026, 10, 14, h, m)
        s = ar.situacao_localidade(db, "bananal", dia(12, 0))   # 2h00 depois — dentro do prazo
        assert s["atrasada"] is False and s["minutos_desde_ultima"] == 120
        s = ar.situacao_localidade(db, "bananal", dia(12, 19))  # dentro da tolerância
        assert s["atrasada"] is False
        s = ar.situacao_localidade(db, "bananal", dia(12, 41))  # 2h41 -> atrasada em 41 min
        assert s["atrasada"] is True and s["minutos_atraso"] == 41
        s = ar.situacao_localidade(db, "bananal", dia(23, 0))   # fora do turno: nunca "atrasada"
        assert s["atrasada"] is False and s["no_turno"] is False
        # começo do turno: última análise é de ontem, mas a contagem parte das 06:00
        db.add(models.AnaliseEta(tecnico_id=u.id, localidade="agua_limpa", coletado_em=datetime(2026, 10, 13, 18, 0), conforme=True))
        db.commit()
        assert ar.situacao_localidade(db, "agua_limpa", dia(7, 0))["atrasada"] is False
        assert ar.situacao_localidade(db, "agua_limpa", dia(8, 30))["atrasada"] is True
    finally:
        db.close()
