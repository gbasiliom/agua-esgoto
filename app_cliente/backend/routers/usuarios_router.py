from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("/", response_model=schemas.UsuarioOut)
def criar_usuario_interno(
    dados: schemas.UsuarioInternoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin")),
):
    """Cria login da equipe (admin, operador, técnico, químico). Só admin."""
    if dados.tipo not in schemas.TIPOS_USUARIO_INTERNO:
        raise HTTPException(status_code=400, detail="Tipo de usuário inválido")
    if dados.tipo == "tecnico" and dados.localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Informe uma localidade válida para o técnico")
    if dados.localidade and dados.localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Localidade inválida")
    if not dados.email and not dados.telefone:
        raise HTTPException(status_code=400, detail="Informe e-mail ou telefone (será o login)")
    if auth.usuario_duplicado(db, dados.email, dados.telefone):
        raise HTTPException(status_code=400, detail="Já existe usuário com este e-mail/telefone")

    novo = models.Usuario(
        nome=dados.nome, email=dados.email, telefone=dados.telefone,
        senha_hash=auth.hash_senha(dados.senha), tipo=dados.tipo, localidade=dados.localidade,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.get("/tecnicos", response_model=List[schemas.UsuarioOut])
def listar_tecnicos(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Usado pelo painel Windows pra popular a lista de técnicos ao atribuir um chamado."""
    return db.query(models.Usuario).filter(models.Usuario.tipo == "tecnico").all()


@router.get("/eu", response_model=schemas.UsuarioOut)
def meus_dados(usuario: models.Usuario = Depends(auth.usuario_atual)):
    """Usado pelo app do técnico logo após o login, pra saber seu próprio id."""
    return usuario
