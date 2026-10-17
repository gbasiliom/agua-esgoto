from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/faturamento", tags=["faturamento"])


# --- Tarifas ---

@router.get("/tarifas", response_model=List[schemas.TarifaFaixaOut])
def listar_tarifas(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.usuario_atual),
):
    return (
        db.query(models.TarifaFaixa)
        .filter(models.TarifaFaixa.ativo == True)
        .order_by(models.TarifaFaixa.consumo_min)
        .all()
    )


@router.post("/tarifas", response_model=schemas.TarifaFaixaOut)
def criar_tarifa(
    dados: schemas.TarifaFaixaCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    faixa = models.TarifaFaixa(**dados.model_dump())
    db.add(faixa)
    db.commit()
    db.refresh(faixa)
    return faixa


@router.patch("/tarifas/{faixa_id}", response_model=schemas.TarifaFaixaOut)
def atualizar_tarifa(
    faixa_id: int,
    dados: schemas.TarifaFaixaCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    faixa = db.query(models.TarifaFaixa).filter(models.TarifaFaixa.id == faixa_id).first()
    if not faixa:
        raise HTTPException(status_code=404, detail="Faixa de tarifa não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(faixa, campo, valor)
    db.commit()
    db.refresh(faixa)
    return faixa


@router.patch("/tarifas/{faixa_id}/desativar", response_model=schemas.TarifaFaixaOut)
def desativar_tarifa(
    faixa_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    faixa = db.query(models.TarifaFaixa).filter(models.TarifaFaixa.id == faixa_id).first()
    if not faixa:
        raise HTTPException(status_code=404, detail="Faixa de tarifa não encontrada")
    faixa.ativo = False
    db.commit()
    db.refresh(faixa)
    return faixa


def calcular_valor_agua(consumo_m3: float, faixas: list) -> float:
    """
    Cálculo progressivo: cada faixa cobra só a parte do consumo que cai
    dentro dela (igual tabela de imposto de renda), não o valor da faixa
    mais alta aplicado em cima do consumo inteiro.
    """
    faixas_ordenadas = sorted(faixas, key=lambda f: float(f.consumo_min))
    valor_total = 0.0
    restante = consumo_m3

    for faixa in faixas_ordenadas:
        if restante <= 0:
            break
        minimo = float(faixa.consumo_min)
        maximo = float(faixa.consumo_max) if faixa.consumo_max is not None else None
        largura_faixa = (maximo - minimo) if maximo is not None else restante
        quantidade_nesta_faixa = min(restante, largura_faixa)
        if quantidade_nesta_faixa > 0:
            valor_total += quantidade_nesta_faixa * float(faixa.valor_m3)
            restante -= quantidade_nesta_faixa

    return valor_total


def gerar_fatura_da_leitura(db: Session, leitura: "models.LeituraHidrometro"):
    """Chamada automaticamente quando uma leitura é aprovada."""
    ja_tem_fatura = db.query(models.Fatura).filter(models.Fatura.leitura_id == leitura.id).first()
    if ja_tem_fatura:
        return ja_tem_fatura

    leitura_anterior = (
        db.query(models.LeituraHidrometro)
        .filter(
            models.LeituraHidrometro.cliente_id == leitura.cliente_id,
            models.LeituraHidrometro.status == "aprovada",
            models.LeituraHidrometro.id != leitura.id,
            models.LeituraHidrometro.criado_em < leitura.criado_em,
        )
        .order_by(models.LeituraHidrometro.criado_em.desc())
        .first()
    )
    valor_anterior = float(leitura_anterior.valor_informado) if leitura_anterior else 0.0
    consumo = float(leitura.valor_informado) - valor_anterior
    if consumo < 0:
        # Hidrômetro trocado/zerado — não dá pra calcular direito, fica pendente de ajuste manual
        consumo = 0.0

    faixas = db.query(models.TarifaFaixa).filter(models.TarifaFaixa.ativo == True).all()
    valor_agua = calcular_valor_agua(consumo, faixas) if faixas else 0.0
    percentual_esgoto = float(faixas[0].percentual_esgoto) / 100 if faixas else 0.8
    valor_esgoto = valor_agua * percentual_esgoto
    valor_total = valor_agua + valor_esgoto

    fatura = models.Fatura(
        cliente_id=leitura.cliente_id,
        leitura_id=leitura.id,
        competencia=leitura.competencia,
        consumo_m3=consumo,
        valor_agua=valor_agua,
        valor_esgoto=valor_esgoto,
        valor_total=valor_total,
        vencimento=datetime.utcnow() + timedelta(days=10),
        status="aberto",
    )
    db.add(fatura)
    db.commit()
    db.refresh(fatura)
    return fatura


# --- Faturas ---

@router.get("/faturas", response_model=List[schemas.FaturaOut])
def listar_faturas(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.Fatura)
    if status:
        query = query.filter(models.Fatura.status == status)
    return query.order_by(models.Fatura.criado_em.desc()).all()


@router.get("/faturas/minhas", response_model=List[schemas.FaturaOut])
def minhas_faturas(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        return []
    return (
        db.query(models.Fatura)
        .filter(models.Fatura.cliente_id == cliente.id)
        .order_by(models.Fatura.criado_em.desc())
        .all()
    )


@router.patch("/faturas/{fatura_id}/marcar-paga", response_model=schemas.FaturaOut)
def marcar_paga(
    fatura_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    fatura = db.query(models.Fatura).filter(models.Fatura.id == fatura_id).first()
    if not fatura:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    fatura.status = "pago"
    fatura.pago_em = datetime.utcnow()
    db.commit()
    db.refresh(fatura)
    return fatura


@router.get("/faturas/{fatura_id}/pdf")
def fatura_pdf(
    fatura_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.usuario_atual),
):
    from fastapi.responses import Response
    from pdf_fatura import gerar_pdf_fatura

    fatura = db.query(models.Fatura).filter(models.Fatura.id == fatura_id).first()
    if not fatura:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")

    # Fatura é dado financeiro: cliente só baixa a própria; técnico/operador de ETA/químico não têm por que ver.
    if usuario.tipo == "cliente":
        dono = db.query(models.Cliente).filter(models.Cliente.id == fatura.cliente_id, models.Cliente.usuario_id == usuario.id).first()
        if not dono:
            raise HTTPException(status_code=404, detail="Fatura não encontrada")
    elif usuario.tipo not in ("admin", "operador"):
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")

    cliente = db.query(models.Cliente).filter(models.Cliente.id == fatura.cliente_id).first()
    pdf_bytes = gerar_pdf_fatura(fatura, cliente)

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=fatura_{fatura_id}.pdf"},
    )
