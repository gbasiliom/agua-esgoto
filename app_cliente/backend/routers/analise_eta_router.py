import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/analise-eta", tags=["analise-eta"])


def _localidade_do_lancamento(usuario: models.Usuario, localidade_informada: Optional[str]) -> str:
    """Técnico lança na própria localidade. Químico (que atende todas) informa qual."""
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
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico", "quimico")),
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
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.AnaliseEta)
    if localidade:
        query = query.filter(models.AnaliseEta.localidade == localidade)
    if apenas_nao_conformes:
        query = query.filter(models.AnaliseEta.conforme == False)
    return query.order_by(models.AnaliseEta.coletado_em.desc()).all()


@router.get("/minhas", response_model=List[schemas.AnaliseEtaOut])
def minhas_analises(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico", "quimico")),
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
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico", "quimico")),
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
    usuario: models.Usuario = Depends(auth.usuario_atual),
):
    query = db.query(models.LavagemFiltro)
    if localidade:
        query = query.filter(models.LavagemFiltro.localidade == localidade)
    return query.order_by(models.LavagemFiltro.hora.desc()).limit(100).all()
