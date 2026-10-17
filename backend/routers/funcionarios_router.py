from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/funcionarios", tags=["funcionarios"])


@router.post("/", response_model=schemas.FuncionarioOut)
def cadastrar_funcionario(
    dados: schemas.FuncionarioCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    funcionario = models.Funcionario(**dados.model_dump())
    db.add(funcionario)
    db.commit()
    db.refresh(funcionario)
    return funcionario


@router.get("/", response_model=List[schemas.FuncionarioOut])
def listar_funcionarios(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    return db.query(models.Funcionario).filter(models.Funcionario.ativo == True).all()


@router.patch("/{funcionario_id}", response_model=schemas.FuncionarioOut)
def atualizar_funcionario(
    funcionario_id: int,
    dados: schemas.FuncionarioCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Atualiza dados do funcionário — útil quando ele muda de cargo/localidade."""
    funcionario = db.query(models.Funcionario).filter(models.Funcionario.id == funcionario_id).first()
    if not funcionario:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    for campo, valor in dados.model_dump().items():
        setattr(funcionario, campo, valor)
    db.commit()
    db.refresh(funcionario)
    return funcionario


@router.patch("/{funcionario_id}/desativar", response_model=schemas.FuncionarioOut)
def desativar_funcionario(
    funcionario_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    funcionario = db.query(models.Funcionario).filter(models.Funcionario.id == funcionario_id).first()
    if not funcionario:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    funcionario.ativo = False
    db.commit()
    db.refresh(funcionario)
    return funcionario
