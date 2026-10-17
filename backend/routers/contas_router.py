from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


# --- Cadastro da empresa (fiscal) ---

@router.get("/empresa", response_model=schemas.EmpresaConfigOut)
def obter_empresa(db: Session = Depends(get_db)):
    """Sem exigir login — o nome da empresa precisa aparecer antes mesmo do login, nas telas dos apps."""
    empresa = db.query(models.EmpresaConfig).filter(models.EmpresaConfig.id == 1).first()
    if not empresa:
        empresa = models.EmpresaConfig(id=1, nome_fantasia="SIGA")
        db.add(empresa)
        db.commit()
        db.refresh(empresa)
    return empresa


@router.patch("/empresa", response_model=schemas.EmpresaConfigOut)
def atualizar_empresa(
    dados: schemas.EmpresaConfigUpdate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin")),
):
    empresa = db.query(models.EmpresaConfig).filter(models.EmpresaConfig.id == 1).first()
    if not empresa:
        empresa = models.EmpresaConfig(id=1)
        db.add(empresa)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(empresa, campo, valor)
    db.commit()
    db.refresh(empresa)
    return empresa


# --- Fornecedores ---

@router.post("/fornecedores", response_model=schemas.FornecedorOut)
def cadastrar_fornecedor(
    dados: schemas.FornecedorCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    fornecedor = models.Fornecedor(ativo=True, **dados.model_dump())
    db.add(fornecedor)
    db.commit()
    db.refresh(fornecedor)
    return fornecedor


@router.get("/fornecedores", response_model=List[schemas.FornecedorOut])
def listar_fornecedores(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador", "tecnico")),
):
    return db.query(models.Fornecedor).filter(models.Fornecedor.ativo == True).all()


@router.patch("/fornecedores/{fornecedor_id}", response_model=schemas.FornecedorOut)
def atualizar_fornecedor(
    fornecedor_id: int,
    dados: schemas.FornecedorCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    fornecedor = db.query(models.Fornecedor).filter(models.Fornecedor.id == fornecedor_id).first()
    if not fornecedor:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    for campo, valor in dados.model_dump().items():
        setattr(fornecedor, campo, valor)
    db.commit()
    db.refresh(fornecedor)
    return fornecedor


@router.patch("/fornecedores/{fornecedor_id}/desativar", response_model=schemas.FornecedorOut)
def desativar_fornecedor(
    fornecedor_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    fornecedor = db.query(models.Fornecedor).filter(models.Fornecedor.id == fornecedor_id).first()
    if not fornecedor:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    fornecedor.ativo = False
    db.commit()
    db.refresh(fornecedor)
    return fornecedor


# --- Contas a pagar ---

@router.post("/contas-pagar", response_model=schemas.ContaPagarOut)
def criar_conta_pagar(
    dados: schemas.ContaPagarCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    conta = models.ContaPagar(status="aberto", **dados.model_dump())
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return conta


@router.get("/contas-pagar", response_model=List[schemas.ContaPagarOut])
def listar_contas_pagar(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.ContaPagar)
    if status:
        query = query.filter(models.ContaPagar.status == status)
    return query.order_by(models.ContaPagar.vencimento).all()


@router.patch("/contas-pagar/{conta_id}/marcar-paga", response_model=schemas.ContaPagarOut)
def marcar_conta_pagar_paga(
    conta_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    conta = db.query(models.ContaPagar).filter(models.ContaPagar.id == conta_id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    conta.status = "pago"
    conta.pago_em = datetime.utcnow()
    db.commit()
    db.refresh(conta)
    return conta


# --- Contas a receber (fora do faturamento de água — ex: taxa, multa) ---

@router.post("/contas-receber", response_model=schemas.ContaReceberOut)
def criar_conta_receber(
    dados: schemas.ContaReceberCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    conta = models.ContaReceberOutras(status="aberto", **dados.model_dump())
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return conta


@router.get("/contas-receber", response_model=List[schemas.ContaReceberOut])
def listar_contas_receber(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.ContaReceberOutras)
    if status:
        query = query.filter(models.ContaReceberOutras.status == status)
    return query.order_by(models.ContaReceberOutras.vencimento).all()


@router.patch("/contas-receber/{conta_id}/marcar-paga", response_model=schemas.ContaReceberOut)
def marcar_conta_receber_paga(
    conta_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    conta = db.query(models.ContaReceberOutras).filter(models.ContaReceberOutras.id == conta_id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    conta.status = "pago"
    conta.pago_em = datetime.utcnow()
    db.commit()
    db.refresh(conta)
    return conta


# --- Resumo (dashboard do financeiro) ---

@router.get("/resumo")
def resumo_financeiro(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    total_pagar = sum(
        float(c.valor) for c in db.query(models.ContaPagar).filter(models.ContaPagar.status == "aberto").all()
    )
    total_receber_faturas = sum(
        float(f.valor_total) for f in db.query(models.Fatura).filter(models.Fatura.status == "aberto").all()
    )
    total_receber_outras = sum(
        float(c.valor) for c in db.query(models.ContaReceberOutras).filter(models.ContaReceberOutras.status == "aberto").all()
    )
    total_receber = total_receber_faturas + total_receber_outras

    return {
        "total_a_pagar": total_pagar,
        "total_a_receber": total_receber,
        "total_a_receber_faturas_agua": total_receber_faturas,
        "total_a_receber_outras": total_receber_outras,
        "saldo_projetado": total_receber - total_pagar,
    }
