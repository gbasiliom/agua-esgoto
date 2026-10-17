from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/auth", tags=["autenticacao"])


@router.post("/registrar", response_model=schemas.Token)
def registrar(dados: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    """Cadastro público — SEMPRE cria um usuário do tipo "cliente". Contas da
    equipe (admin, operador, técnico, químico) só são criadas por um admin
    logado, em POST /usuarios/."""
    if dados.localidade and dados.localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Localidade inválida")

    if auth.usuario_duplicado(db, dados.email, dados.telefone):
        raise HTTPException(status_code=400, detail="Já existe usuário com este e-mail/telefone")

    novo = models.Usuario(
        nome=dados.nome,
        email=dados.email,
        telefone=dados.telefone,
        senha_hash=auth.hash_senha(dados.senha),
        tipo="cliente",
        localidade=dados.localidade,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)

    token = auth.criar_token(novo.id, novo.tipo)
    return schemas.Token(access_token=token, tipo_usuario=novo.tipo)


@router.post("/login", response_model=schemas.Token)
def login(dados: schemas.UsuarioLogin, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(
        or_(models.Usuario.email == dados.identificador, models.Usuario.telefone == dados.identificador)
    ).first()

    if not usuario or not auth.verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail/telefone ou senha incorretos")

    token = auth.criar_token(usuario.id, usuario.tipo)
    return schemas.Token(access_token=token, tipo_usuario=usuario.tipo)
