from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/licitacoes", tags=["licitacoes"])

TRANSICOES_VALIDAS = {
    "rascunho": {"publicada", "cancelada"},
    "publicada": {"em_analise", "cancelada"},
    "em_analise": {"homologada", "fracassada", "cancelada"},
    "homologada": set(),  # estado final
    "fracassada": set(),  # estado final
    "cancelada": set(),  # estado final
}


@router.post("/", response_model=schemas.LicitacaoOut)
def criar_licitacao(
    dados: schemas.LicitacaoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    licitacao = models.Licitacao(status="rascunho", **dados.model_dump())
    db.add(licitacao)
    db.commit()
    db.refresh(licitacao)
    return licitacao


@router.get("/", response_model=List[schemas.LicitacaoOut])
def listar_licitacoes(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.Licitacao)
    if status:
        query = query.filter(models.Licitacao.status == status)
    return query.order_by(models.Licitacao.criado_em.desc()).all()


@router.patch("/{licitacao_id}", response_model=schemas.LicitacaoOut)
def atualizar_licitacao(
    licitacao_id: int,
    dados: schemas.LicitacaoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Edita os dados gerais (modalidade, objeto, valor estimado etc) — não muda o status."""
    licitacao = db.query(models.Licitacao).filter(models.Licitacao.id == licitacao_id).first()
    if not licitacao:
        raise HTTPException(status_code=404, detail="Licitação não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(licitacao, campo, valor)
    db.commit()
    db.refresh(licitacao)
    return licitacao


@router.patch("/{licitacao_id}/status", response_model=schemas.LicitacaoOut)
def mudar_status_licitacao(
    licitacao_id: int,
    dados: schemas.LicitacaoStatusUpdate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """
    Segue o fluxo: rascunho → publicada → em_analise → homologada/fracassada/cancelada.
    Não deixa pular etapa nem voltar — se errou, cancela e cria outra.
    """
    licitacao = db.query(models.Licitacao).filter(models.Licitacao.id == licitacao_id).first()
    if not licitacao:
        raise HTTPException(status_code=404, detail="Licitação não encontrada")

    permitido = TRANSICOES_VALIDAS.get(licitacao.status, set())
    if dados.status not in permitido:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível ir de '{licitacao.status}' pra '{dados.status}'. "
                   f"A partir de '{licitacao.status}' só pode ir pra: {', '.join(permitido) or '(nenhum — status final)'}",
        )

    licitacao.status = dados.status
    if dados.status == "homologada":
        licitacao.vencedor = dados.vencedor
        licitacao.fornecedor_id = dados.fornecedor_id
        licitacao.valor_final = dados.valor_final

    db.commit()
    db.refresh(licitacao)
    return licitacao
