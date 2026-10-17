import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
import models

import sys
import secrets


def _pasta_persistente():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


_ARQUIVO_SECRET_KEY_RESERVA = os.path.join(_pasta_persistente(), ".secret_key_local")



def _obter_secret_key():
    """Mesma lógica da chave de criptografia: variável de ambiente tem
    prioridade; sem ela, usa/gera um arquivo local — nunca uma string fixa
    e previsível, que é uma porta aberta pra forjar tokens de login."""
    valor_env = os.getenv("SECRET_KEY")
    if valor_env:
        return valor_env
    if os.path.exists(_ARQUIVO_SECRET_KEY_RESERVA):
        with open(_ARQUIVO_SECRET_KEY_RESERVA) as f:
            return f.read().strip()
    nova_chave = secrets.token_urlsafe(64)
    with open(_ARQUIVO_SECRET_KEY_RESERVA, "w") as f:
        f.write(nova_chave)
    return nova_chave


SECRET_KEY = _obter_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("SIGA_ACCESS_MINUTOS", "30"))  # curto de propósito: quem mantém a sessão é o token de renovação

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Hash de mentirinha: usado quando o login é de uma conta que não existe, só para gastar o mesmo tempo.
HASH_FALSO = pwd_context.hash("senha-que-ninguem-usa-0")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def criar_token(usuario: "models.Usuario") -> str:
    """Token de acesso (curto). Leva a "versão" da conta: trocar a senha ou sair de todos os
    aparelhos sobe a versão no banco e todos os tokens antigos deixam de valer na hora."""
    expira = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(usuario.id), "tipo": usuario.tipo, "tv": usuario.token_versao or 0, "exp": expira}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _usuario_do_token(token: str, db: Session) -> models.Usuario:
    excecao = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id = payload.get("sub")
        if usuario_id is None:
            raise excecao
    except JWTError:
        raise excecao

    usuario = db.query(models.Usuario).filter(models.Usuario.id == int(usuario_id)).first()
    if usuario is None or (payload.get("tv", 0) != (usuario.token_versao or 0)):
        raise excecao
    return usuario


def usuario_atual_livre(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Usuario:
    """Usuário logado, SEM exigir que a senha provisória já tenha sido trocada
    (usado só em /auth/trocar-senha, /auth/logout e /usuarios/eu)."""
    return _usuario_do_token(token, db)


def usuario_atual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Usuario:
    usuario = _usuario_do_token(token, db)
    if usuario.trocar_senha:
        raise HTTPException(status_code=403, detail="TROCA_SENHA_OBRIGATORIA")
    return usuario


def usuario_duplicado(db: Session, email, telefone):
    """True se já existe usuário com o mesmo e-mail ou telefone. Só compara
    os campos preenchidos (comparar com None bateria com qualquer usuário sem
    e-mail)."""
    from sqlalchemy import or_
    condicoes = []
    if email:
        condicoes.append(models.Usuario.email == email)
    if telefone:
        condicoes.append(models.Usuario.telefone == telefone)
    if not condicoes:
        return False
    return db.query(models.Usuario).filter(or_(*condicoes)).first() is not None


def exigir_tipo(*tipos_permitidos):
    def verificador(usuario: models.Usuario = Depends(usuario_atual)):
        if usuario.tipo not in tipos_permitidos:
            raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
        return usuario
    return verificador


def exigir_equipe():
    """Qualquer usuário LOGADO que não seja cliente (admin, operador, técnico, químico, operador de ETA).
    Usado em telas internas que o morador nunca precisa ver."""
    def verificador(usuario: models.Usuario = Depends(usuario_atual)):
        if usuario.tipo == "cliente":
            raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
        return usuario
    return verificador
