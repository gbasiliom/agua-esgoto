import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/analise-eta", tags=["analise-eta"])


def _localidade_do_lancamento(usuario: models.Usuario, localidade_informada: Optional[str]) -> str:
    """Técnico e operador de ETA lançam na própria localidade. Químico (que atende todas) informa qual."""
    if usuario.tipo == "quimico":
        if localidade_informada not in schemas.LOCALIDADES:
            raise HTTPException(status_code=400, detail="Informe a localidade da análise")
        return localidade_informada
    return usuario.localidade or "sede"


def avaliar_conformidade(dados: schemas.AnaliseEtaCreate):
    """
    Confere os parâmetros informados contra os Valores Máximos Permitidos
    (VMP) da Portaria GM/MS nº 888/2021. Só sinaliza os parâmetros que têm
    um limite oficial — os demais (bruta, dosagem) são só operacionais,
    sem padrão de potabilidade fixo.
    """
    alertas = []

    if dados.turbidez_filtrada is not None and dados.turbidez_filtrada > 1.0:
        alertas.append(f"Turbidez filtrada {dados.turbidez_filtrada} NTU acima do máximo de 1,0 NTU")
    elif dados.turbidez_filtrada is not None and dados.turbidez_filtrada > 0.5:
        alertas.append(f"Turbidez filtrada {dados.turbidez_filtrada} NTU acima da meta de 0,5 NTU (atenção)")

    if dados.turbidez_tratada is not None and dados.turbidez_tratada > 5.0:
        alertas.append(f"Turbidez tratada {dados.turbidez_tratada} NTU acima do máximo de 5,0 NTU")

    if dados.ph_tratada is not None and not (6.0 <= dados.ph_tratada <= 9.5):
        alertas.append(f"pH tratada {dados.ph_tratada} fora da faixa 6,0–9,5")

    if dados.cloro_residual is not None and not (0.2 <= dados.cloro_residual <= 5.0):
        alertas.append(f"Cloro residual {dados.cloro_residual} mg/L fora da faixa 0,2–5,0 mg/L")

    if dados.cor_tratada is not None and dados.cor_tratada > 15:
        alertas.append(f"Cor tratada {dados.cor_tratada} UC acima do máximo de 15 UC")

    conforme = len(alertas) == 0
    return conforme, alertas


@router.post("/", response_model=schemas.AnaliseEtaOut)
def registrar_analise(
    dados: schemas.AnaliseEtaCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico", "quimico", "operador_eta")),
):
    conforme, alertas = avaliar_conformidade(dados)

    campos = dados.model_dump()
    localidade = _localidade_do_lancamento(usuario, campos.pop("localidade", None))
    analise = models.AnaliseEta(
        tecnico_id=usuario.id,
        localidade=localidade,
        conforme=conforme,
        alertas=json.dumps(alertas, ensure_ascii=False) if alertas else None,
        **campos,
    )
    db.add(analise)
    db.commit()
    db.refresh(analise)
    return analise


@router.get("/", response_model=List[schemas.AnaliseEtaOut])
def listar_analises(
    localidade: Optional[str] = None,
    apenas_nao_conformes: bool = False,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador", "quimico")),
):
    query = db.query(models.AnaliseEta)
    if localidade:
        query = query.filter(models.AnaliseEta.localidade == localidade)
    if apenas_nao_conformes:
        query = query.filter(models.AnaliseEta.conforme == False)
    return query.order_by(models.AnaliseEta.coletado_em.desc()).all()


# --- Acompanhamento ao vivo (químico / painel) ---
# O químico e o painel consultam este endpoint a cada ~15 s e recebem só o que é novo.

INTERVALO_ANALISE_MIN = 120   # o SAAE pede uma análise a cada 2 horas
TOLERANCIA_MIN = 20           # só avisa "atrasada" depois de 2h20 sem coleta
TURNO_INICIO_H = int(os.getenv("ETA_TURNO_INICIO", "6"))   # fora do turno não existe "atrasada"
TURNO_FIM_H = int(os.getenv("ETA_TURNO_FIM", "20"))
LIMITE_ENTRADA_INICIAL = 30   # na primeira consulta (sem "apos_*") devolve só os últimos lançamentos


def agora_brasilia() -> datetime:
    """Hora de Brasília (UTC-3, sem horário de verão) sem fuso — o mesmo "relógio" dos celulares dos operadores,
    independente do fuso do servidor (PythonAnywhere/VPS costumam rodar em UTC)."""
    return (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)


def _alertas_lista(texto):
    if not texto:
        return []
    try:
        return json.loads(texto)
    except ValueError:
        return [texto]


def situacao_localidade(db: Session, localidade: str, agora: datetime) -> dict:
    ultima = (
        db.query(models.AnaliseEta)
        .filter(models.AnaliseEta.localidade == localidade)
        .order_by(models.AnaliseEta.coletado_em.desc(), models.AnaliseEta.id.desc())
        .first()
    )
    inicio_turno = agora.replace(hour=TURNO_INICIO_H, minute=0, second=0, microsecond=0)
    fim_turno = agora.replace(hour=TURNO_FIM_H, minute=0, second=0, microsecond=0)
    no_turno = inicio_turno <= agora <= fim_turno
    atrasada, minutos_atraso, minutos_desde = False, 0, None
    if ultima is not None:
        minutos_desde = max(0, int((agora - ultima.coletado_em).total_seconds() // 60))
        # no começo do turno a contagem parte das 06:00, não da última análise de ontem
        referencia = max(ultima.coletado_em, inicio_turno) if no_turno else ultima.coletado_em
        espera = int((agora - referencia).total_seconds() // 60)
        if no_turno and espera > INTERVALO_ANALISE_MIN + TOLERANCIA_MIN:
            atrasada, minutos_atraso = True, espera - INTERVALO_ANALISE_MIN
    return {
        "localidade": localidade,
        "tem_dados": ultima is not None,
        "ultima_coleta": ultima.coletado_em.isoformat() if ultima else None,
        "minutos_desde_ultima": minutos_desde,
        "ultima_conforme": ultima.conforme if ultima else None,
        "ultimos_alertas": _alertas_lista(ultima.alertas) if ultima else [],
        "atrasada": atrasada,
        "minutos_atraso": minutos_atraso,
        "no_turno": no_turno,
    }


@router.get("/ao-vivo")
def ao_vivo(
    apos_analise: int = 0,
    apos_lavagem: int = 0,
    localidade: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador", "quimico")),
):
    """Só o que chegou depois dos ids informados (use os `ultimo_id_*` da resposta anterior). Na primeira
    chamada (ids = 0) devolve os últimos lançamentos. `localidades` traz a situação atual de cada ETA."""
    if localidade is not None and localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Localidade inválida")

    def _novos(modelo, apos, ordem):
        q = db.query(modelo)
        if localidade:
            q = q.filter(modelo.localidade == localidade)
        if apos > 0:
            return q.filter(modelo.id > apos).order_by(modelo.id.asc()).limit(200).all()
        return list(reversed(q.order_by(modelo.id.desc()).limit(LIMITE_ENTRADA_INICIAL).all()))

    analises = _novos(models.AnaliseEta, apos_analise, None)
    lavagens = _novos(models.LavagemFiltro, apos_lavagem, None)
    agora = agora_brasilia()
    locais = [localidade] if localidade else list(schemas.LOCALIDADES)
    return {
        "agora": agora.isoformat(),
        "primeira_carga": apos_analise <= 0 and apos_lavagem <= 0,
        "analises": [schemas.AnaliseEtaOut.model_validate(a).model_dump(mode="json") for a in analises],
        "lavagens": [schemas.LavagemFiltroOut.model_validate(l).model_dump(mode="json") for l in lavagens],
        "ultimo_id_analise": max([apos_analise] + [a.id for a in analises]),
        "ultimo_id_lavagem": max([apos_lavagem] + [l.id for l in lavagens]),
        "localidades": [situacao_localidade(db, loc, agora) for loc in locais],
    }


@router.get("/minhas", response_model=List[schemas.AnaliseEtaOut])
def minhas_analises(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico", "quimico", "operador_eta")),
):
    return (
        db.query(models.AnaliseEta)
        .filter(models.AnaliseEta.tecnico_id == usuario.id)
        .order_by(models.AnaliseEta.coletado_em.desc())
        .limit(50)
        .all()
    )


# --- Lavagem de filtro ---

@router.post("/lavagem-filtro", response_model=schemas.LavagemFiltroOut)
def registrar_lavagem_filtro(
    dados: schemas.LavagemFiltroCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico", "quimico", "operador_eta")),
):
    campos = dados.model_dump()
    localidade = _localidade_do_lancamento(usuario, campos.pop("localidade", None))
    lavagem = models.LavagemFiltro(tecnico_id=usuario.id, localidade=localidade, **campos)
    db.add(lavagem)
    db.commit()
    db.refresh(lavagem)
    return lavagem


@router.get("/lavagem-filtro", response_model=List[schemas.LavagemFiltroOut])
def listar_lavagens_filtro(
    localidade: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_equipe()),
):
    query = db.query(models.LavagemFiltro)
    if localidade:
        query = query.filter(models.LavagemFiltro.localidade == localidade)
    return query.order_by(models.LavagemFiltro.hora.desc()).limit(100).all()
