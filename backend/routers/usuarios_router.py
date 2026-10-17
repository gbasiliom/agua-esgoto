from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import seguranca as seg

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("/", response_model=schemas.UsuarioCriadoOut)
def criar_usuario_interno(
    dados: schemas.UsuarioInternoCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin")),
):
    """Cria login da equipe (admin, operador, técnico, químico, operador de ETA). Só admin."""
    if dados.tipo not in schemas.TIPOS_USUARIO_INTERNO:
        raise HTTPException(status_code=400, detail="Tipo de usuário inválido")
    if dados.tipo in ("tecnico", "operador_eta") and dados.localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Informe uma localidade válida (obrigatória para técnico e operador de ETA)")
    if dados.localidade and dados.localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Localidade inválida")
    if not dados.email and not dados.telefone:
        raise HTTPException(status_code=400, detail="Informe e-mail ou telefone (será o login)")
    email = dados.email.strip().lower() if dados.email else None
    if email and not seg.e_mail_valido(email):
        raise HTTPException(status_code=400, detail="E-mail inválido")
    if dados.tipo == "admin" and not email:
        raise HTTPException(status_code=400, detail="Administrador precisa de e-mail (recuperação de senha e código de verificação)")
    gerada = None
    senha = dados.senha
    if not senha:
        senha = gerada = seg.gerar_senha_provisoria()
    else:
        seg.validar_senha(senha, dados.nome, email, dados.telefone)
    if auth.usuario_duplicado(db, email, dados.telefone):
        raise HTTPException(status_code=400, detail="Já existe usuário com este e-mail/telefone")

    # A senha inicial quem escolheu foi o admin (ou o servidor): o próprio funcionário é obrigado a trocar no primeiro acesso.
    novo = models.Usuario(
        nome=dados.nome, email=email, telefone=dados.telefone,
        senha_hash=auth.hash_senha(senha), tipo=dados.tipo, localidade=dados.localidade,
        trocar_senha=True, senha_alterada_em=seg.agora_utc(),
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    seg.auditar(db, "usuario_criado", usuario, detalhe=f"criou {novo.tipo} id={novo.id}", ip=seg.ip_do_cliente(request))
    saida = schemas.UsuarioCriadoOut.model_validate(novo)
    saida.senha_provisoria = gerada
    return saida


@router.get("/", response_model=List[schemas.UsuarioListaOut])
def listar_usuarios(
    tipo: str = None,
    busca: str = None,
    limite: int = 300,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(auth.exigir_tipo("admin")),
):
    """Contas de acesso (equipe e moradores) para o admin gerenciar: ver quem precisa trocar a senha,
    quem está bloqueado e resetar a senha de quem perdeu o acesso."""
    q = db.query(models.Usuario)
    if tipo:
        q = q.filter(models.Usuario.tipo == tipo)
    if busca and busca.strip():
        like = f"%{busca.strip().lower()}%"
        q = q.filter(or_(func.lower(models.Usuario.nome).like(like), func.lower(models.Usuario.email).like(like),
                         models.Usuario.telefone.like(like)))
    agora = seg.agora_utc()
    saida = []
    for u in q.order_by(models.Usuario.tipo, models.Usuario.nome).limit(max(1, min(limite, 1000))).all():
        item = schemas.UsuarioListaOut.model_validate(u)
        item.trocar_senha = bool(u.trocar_senha)
        item.bloqueado = bool(u.bloqueado_ate and u.bloqueado_ate > agora)
        saida.append(item)
    return saida


@router.post("/{usuario_id}/resetar-senha", response_model=schemas.ResetSenhaOut)
def resetar_senha(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(auth.exigir_tipo("admin")),
):
    """Admin gera uma senha provisória (mostrada UMA vez) para quem não tem e-mail ou perdeu o acesso.
    A pessoa é obrigada a trocá-la no primeiro login, e todas as sessões dela caem agora."""
    alvo = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    provisoria = seg.gerar_senha_provisoria()
    alvo.senha_hash = auth.hash_senha(provisoria)
    alvo.trocar_senha = True
    alvo.falhas_login = 0
    alvo.bloqueado_ate = None
    alvo.token_versao = (alvo.token_versao or 0) + 1
    alvo.senha_alterada_em = seg.agora_utc()
    db.commit()
    seg.revogar_sessoes(db, alvo.id)
    seg.auditar(db, "senha_resetada_por_admin", admin, detalhe=f"alvo id={alvo.id} ({alvo.tipo})", ip=seg.ip_do_cliente(request))
    return schemas.ResetSenhaOut(
        senha_provisoria=provisoria,
        detail=f"Senha provisória de {alvo.nome} gerada. Entregue-a pessoalmente; ela será obrigada a trocar no primeiro acesso.",
    )


@router.get("/auditoria", response_model=List[schemas.AuditoriaOut])
def ver_auditoria(
    acao: str = None,
    limite: int = 200,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(auth.exigir_tipo("admin")),
):
    """Últimos eventos de segurança (logins, falhas, bloqueios, trocas e resets de senha)."""
    q = db.query(models.Auditoria)
    if acao:
        q = q.filter(models.Auditoria.acao == acao)
    return q.order_by(models.Auditoria.id.desc()).limit(max(1, min(limite, 1000))).all()


@router.get("/tecnicos", response_model=List[schemas.UsuarioOut])
def listar_tecnicos(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Usado pelo painel Windows pra popular a lista de técnicos ao atribuir um chamado."""
    return db.query(models.Usuario).filter(models.Usuario.tipo == "tecnico").all()


@router.get("/eu", response_model=schemas.UsuarioOut)
def meus_dados(usuario: models.Usuario = Depends(auth.usuario_atual_livre)):
    """Usado pelo app do técnico logo após o login, pra saber seu próprio id."""
    return usuario
