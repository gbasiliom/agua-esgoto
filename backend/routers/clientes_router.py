from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/clientes", tags=["clientes"])


def _campos(dados: schemas.ClienteAutoCadastro) -> dict:
    """Dados do cadastro prontos para gravar. Só a sede tem hidrômetro: nas outras localidades o campo é limpo."""
    d = dados.model_dump()
    if not schemas.localidade_tem_hidrometro(d.get("localidade")):
        d["hidrometro"] = None
    return d


@router.post("/", response_model=schemas.ClienteOut)
def cadastrar_cliente_admin(
    dados: schemas.ClienteAutoCadastro,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Operador cadastra um cliente diretamente (ex: atendimento por telefone),
    sem precisar que o cliente tenha o app instalado. Já nasce aprovado."""
    cliente = models.Cliente(ativo=True, status_cadastro="aprovado", **_campos(dados))
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.get("/", response_model=List[schemas.ClienteOut])
def listar_clientes(
    status_cadastro: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.Cliente).filter(models.Cliente.ativo == True)
    if status_cadastro:
        query = query.filter(models.Cliente.status_cadastro == status_cadastro)
    return query.all()


@router.patch("/{cliente_id}/aprovar", response_model=schemas.ClienteOut)
def aprovar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Homologa o cadastro que o cliente fez sozinho pelo app — libera ele pra abrir chamados."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    cliente.status_cadastro = "aprovado"
    db.commit()
    db.refresh(cliente)
    return cliente


# (precisa vir ANTES de /{cliente_id}, senão "eu" é tratado como id e o cliente leva 403)
@router.patch("/eu", response_model=schemas.ClienteOut)
def atualizar_meu_cadastro(
    dados: schemas.ClienteAutoCadastro,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Você ainda não completou seu cadastro")

    for campo, valor in _campos(dados).items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.patch("/{cliente_id}", response_model=schemas.ClienteOut)
def atualizar_cliente_admin(
    cliente_id: int,
    dados: schemas.ClienteAutoCadastro,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Operador edita/atualiza o cadastro de um cliente (registrado pelo app ou manualmente)."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    for campo, valor in _campos(dados).items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.patch("/{cliente_id}/desativar", response_model=schemas.ClienteOut)
def desativar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Usado pra 'apagar' cadastros duplicados sem perder o histórico (chamados antigos continuam ligados a ele)."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    cliente.ativo = False
    db.commit()
    db.refresh(cliente)
    return cliente


@router.post("/eu", response_model=schemas.ClienteOut)
def criar_meu_cadastro(
    dados: schemas.ClienteAutoCadastro,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    """O próprio cliente preenche seu cadastro (endereço, hidrômetro) na primeira vez que usa o app."""
    existente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if existente:
        raise HTTPException(status_code=400, detail="Você já tem um cadastro. Use PATCH /clientes/eu pra atualizar.")

    cliente = models.Cliente(usuario_id=usuario.id, ativo=True, status_cadastro="pendente", **_campos(dados))
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.get("/eu", response_model=schemas.ClienteOut)
def meu_cadastro(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Você ainda não completou seu cadastro")
    return cliente
