from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt, JWTError
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import seguranca as seg

router = APIRouter(prefix="/auth", tags=["autenticacao"])

# Quantas senhas erradas seguidas travam a conta, e por quanto tempo.
FALHAS_PARA_BLOQUEAR = 5
BLOQUEIO_MIN = 15
MSG_CREDENCIAIS = "E-mail/telefone ou senha incorretos"
MSG_ESQUECI = ("Se existir uma conta com esse e-mail ou telefone e ela tiver e-mail cadastrado, "
               "enviamos um código de 6 dígitos. Se não chegar em alguns minutos, procure o administrador.")


def _buscar_por_identificador(db: Session, identificador: str):
    ident = (identificador or "").strip()
    if not ident:
        return None
    return db.query(models.Usuario).filter(
        or_(func.lower(models.Usuario.email) == ident.lower(), models.Usuario.telefone == ident)
    ).first()


def _emitir_tokens(db: Session, usuario: models.Usuario, request: Request) -> schemas.Token:
    usuario.ultimo_login_em = seg.agora_utc()
    usuario.falhas_login = 0
    usuario.bloqueado_ate = None
    db.commit()
    refresh = seg.criar_sessao(db, usuario, seg.ip_do_cliente(request), request.headers.get("user-agent"))
    return schemas.Token(
        access_token=auth.criar_token(usuario), refresh_token=refresh,
        tipo_usuario=usuario.tipo, trocar_senha=bool(usuario.trocar_senha),
    )


@router.post("/registrar", response_model=schemas.Token)
def registrar(dados: schemas.UsuarioRegistro, request: Request, db: Session = Depends(get_db)):
    """Cadastro público — SEMPRE cria um usuário do tipo "cliente". Contas da
    equipe (admin, operador, técnico, químico) só são criadas por um admin
    logado, em POST /usuarios/."""
    ip = seg.ip_do_cliente(request)
    seg.checar_limite(f"registro:{ip}", 5, 3600, "Muitos cadastros deste aparelho. Tente de novo mais tarde.")

    if dados.localidade and dados.localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail="Localidade inválida")
    email = dados.email.strip().lower()
    if not seg.e_mail_valido(email):
        raise HTTPException(status_code=400, detail="Informe um e-mail válido (é por ele que você recupera a senha).")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe seu nome")
    seg.validar_senha(dados.senha, dados.nome, email, dados.telefone)

    if auth.usuario_duplicado(db, email, dados.telefone):
        raise HTTPException(status_code=400, detail="Já existe usuário com este e-mail/telefone")

    novo = models.Usuario(
        nome=dados.nome.strip(), email=email, telefone=dados.telefone,
        senha_hash=auth.hash_senha(dados.senha), tipo="cliente", localidade=dados.localidade,
        senha_alterada_em=seg.agora_utc(),
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    seg.auditar(db, "registro", novo, ip=ip)
    return _emitir_tokens(db, novo, request)


@router.post("/login", response_model=schemas.Token)
def login(dados: schemas.UsuarioLogin, request: Request, db: Session = Depends(get_db)):
    ip = seg.ip_do_cliente(request)
    ident_norm = seg.normalizar_identificador(dados.identificador)
    # Dois freios independentes: por aparelho/rede (IP) e por conta alvo (mesmo se a conta nem existir,
    # pra não dar pista de quais e-mails/telefones estão cadastrados).
    seg.checar_limite(f"login-ip:{ip}", 20, 300)
    usuario = _buscar_por_identificador(db, dados.identificador)

    if usuario and usuario.bloqueado_ate and usuario.bloqueado_ate > seg.agora_utc():
        restante = int((usuario.bloqueado_ate - seg.agora_utc()).total_seconds() // 60) + 1
        seg.auditar(db, "login_bloqueado", usuario, ident_norm, ip=ip)
        raise HTTPException(status_code=429, detail=f"Muitas tentativas erradas. Tente de novo em {restante} minuto(s) ou use \"Esqueci minha senha\".")

    senha_ok = False
    if usuario:
        senha_ok = auth.verificar_senha(dados.senha, usuario.senha_hash)
    else:
        auth.verificar_senha(dados.senha, auth.HASH_FALSO)  # gasta o mesmo tempo, sem revelar que a conta não existe

    if not usuario or not senha_ok:
        if usuario:
            usuario.falhas_login = (usuario.falhas_login or 0) + 1
            if usuario.falhas_login >= FALHAS_PARA_BLOQUEAR:
                usuario.bloqueado_ate = seg.agora_utc() + timedelta(minutes=BLOQUEIO_MIN)
                usuario.falhas_login = 0
                seg.auditar(db, "conta_bloqueada", usuario, ident_norm, f"{FALHAS_PARA_BLOQUEAR} senhas erradas seguidas", ip)
            db.commit()
        seg.auditar(db, "login_falhou", usuario, ident_norm, ip=ip)
        seg.checar_limite(f"login-conta:{ident_norm}", 10, 900, "Muitas tentativas erradas. Aguarde alguns minutos.")
        raise HTTPException(status_code=401, detail=MSG_CREDENCIAIS)

    # Senha provisória/fraca (tipo 123456 dos testes): obriga trocar antes de usar o sistema.
    if not seg.modo_teste() and seg.senha_e_fraca(dados.senha) and not usuario.trocar_senha:
        usuario.trocar_senha = True
        db.commit()

    # 2ª etapa do administrador (código por e-mail), quando o e-mail do sistema está configurado.
    if usuario.tipo == "admin" and usuario.email and seg.doisfa_admin_ativo():
        codigo = seg.gerar_codigo(db, usuario, "2fa")
        seg.enviar_codigo(usuario, codigo, "2fa")
        desafio = jwt.encode(
            {"sub": str(usuario.id), "fin": "2fa", "exp": seg.agora_utc() + timedelta(minutes=seg.CODIGO_VALIDADE_MIN)},
            auth.SECRET_KEY, algorithm=auth.ALGORITHM,
        )
        seg.auditar(db, "2fa_enviado", usuario, ident_norm, ip=ip)
        return schemas.Token(requer_2fa=True, desafio=desafio, email_mascarado=seg.mascarar_email(usuario.email), tipo_usuario="admin")

    seg.limpar_limite(f"login-conta:{ident_norm}")
    seg.auditar(db, "login_ok", usuario, ident_norm, ip=ip)
    return _emitir_tokens(db, usuario, request)


@router.post("/verificar-2fa", response_model=schemas.Token)
def verificar_2fa(dados: schemas.Verificar2FA, request: Request, db: Session = Depends(get_db)):
    ip = seg.ip_do_cliente(request)
    seg.checar_limite(f"2fa-ip:{ip}", 15, 600)
    try:
        payload = jwt.decode(dados.desafio, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        if payload.get("fin") != "2fa":
            raise JWTError()
        usuario = db.query(models.Usuario).filter(models.Usuario.id == int(payload["sub"])).first()
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Verificação expirada. Entre de novo com e-mail e senha.")
    if not usuario or not seg.conferir_codigo(db, usuario, "2fa", dados.codigo):
        seg.auditar(db, "2fa_falhou", usuario, ip=ip)
        raise HTTPException(status_code=401, detail="Código incorreto ou expirado.")
    seg.auditar(db, "login_ok", usuario, detalhe="com 2FA", ip=ip)
    return _emitir_tokens(db, usuario, request)


@router.post("/refresh", response_model=schemas.Token)
def renovar(dados: schemas.RefreshIn, request: Request, db: Session = Depends(get_db)):
    """Troca o token de renovação por um par novo. O antigo deixa de valer. Se alguém tentar usar
    um token já trocado (sinal de roubo), TODAS as sessões da conta são derrubadas."""
    ip = seg.ip_do_cliente(request)
    seg.checar_limite(f"refresh-ip:{ip}", 60, 300)
    sessao = db.query(models.SessaoRefresh).filter(models.SessaoRefresh.token_hash == seg.hash_token(dados.refresh_token)).first()
    if not sessao:
        raise HTTPException(status_code=401, detail="Sessão inválida. Entre de novo.")
    usuario = db.query(models.Usuario).filter(models.Usuario.id == sessao.usuario_id).first()
    if sessao.revogado:
        if usuario:
            usuario.token_versao = (usuario.token_versao or 0) + 1
            db.commit()
            seg.revogar_sessoes(db, usuario.id)
            seg.auditar(db, "refresh_reutilizado", usuario, detalhe="token já usado reapareceu; sessões derrubadas", ip=ip)
        raise HTTPException(status_code=401, detail="Sessão inválida. Entre de novo.")
    if sessao.expira_em < seg.agora_utc() or not usuario:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre de novo.")

    sessao.revogado = True
    novo_refresh = seg.criar_sessao(db, usuario, ip, request.headers.get("user-agent"))
    nova = db.query(models.SessaoRefresh).filter(models.SessaoRefresh.token_hash == seg.hash_token(novo_refresh)).first()
    sessao.substituido_por = nova.id
    db.commit()
    return schemas.Token(
        access_token=auth.criar_token(usuario), refresh_token=novo_refresh,
        tipo_usuario=usuario.tipo, trocar_senha=bool(usuario.trocar_senha),
    )


@router.post("/logout", response_model=schemas.Mensagem)
def sair(dados: schemas.RefreshIn, request: Request, db: Session = Depends(get_db)):
    """Encerra este aparelho (invalida o token de renovação dele)."""
    sessao = db.query(models.SessaoRefresh).filter(models.SessaoRefresh.token_hash == seg.hash_token(dados.refresh_token)).first()
    if sessao and not sessao.revogado:
        sessao.revogado = True
        db.commit()
        usuario = db.query(models.Usuario).filter(models.Usuario.id == sessao.usuario_id).first()
        seg.auditar(db, "logout", usuario, ip=seg.ip_do_cliente(request))
    return schemas.Mensagem(detail="Sessão encerrada.")


@router.post("/logout-todos", response_model=schemas.Mensagem)
def sair_de_todos(request: Request, db: Session = Depends(get_db), usuario: models.Usuario = Depends(auth.usuario_atual_livre)):
    """Derruba todos os aparelhos logados nesta conta (inclusive este)."""
    usuario.token_versao = (usuario.token_versao or 0) + 1
    db.commit()
    seg.revogar_sessoes(db, usuario.id)
    seg.auditar(db, "logout_todos", usuario, ip=seg.ip_do_cliente(request))
    return schemas.Mensagem(detail="Todos os aparelhos foram desconectados.")


@router.post("/esqueci-senha", response_model=schemas.Mensagem)
def esqueci_senha(dados: schemas.EsqueciSenha, request: Request, db: Session = Depends(get_db)):
    """Manda um código de 6 dígitos para o e-mail da conta. A resposta é SEMPRE a mesma,
    exista a conta ou não, pra ninguém descobrir quem está cadastrado."""
    ip = seg.ip_do_cliente(request)
    ident_norm = seg.normalizar_identificador(dados.identificador)
    seg.checar_limite(f"esqueci-ip:{ip}", 8, 900)
    seg.checar_limite(f"esqueci-conta:{ident_norm}", 5, 3600, MSG_ESQUECI)
    usuario = _buscar_por_identificador(db, dados.identificador)
    if usuario and usuario.email:
        codigo = seg.gerar_codigo(db, usuario, "recuperacao")
        enviado = seg.enviar_codigo(usuario, codigo, "recuperacao")
        seg.auditar(db, "recuperacao_pedida", usuario, ident_norm, "e-mail enviado" if enviado else "FALHA no envio de e-mail", ip)
    else:
        seg.auditar(db, "recuperacao_sem_conta_ou_email", usuario, ident_norm, ip=ip)
    return schemas.Mensagem(detail=MSG_ESQUECI)


@router.post("/redefinir-senha", response_model=schemas.Mensagem)
def redefinir_senha(dados: schemas.RedefinirSenha, request: Request, db: Session = Depends(get_db)):
    ip = seg.ip_do_cliente(request)
    ident_norm = seg.normalizar_identificador(dados.identificador)
    seg.checar_limite(f"redef-ip:{ip}", 15, 900)
    seg.checar_limite(f"redef-conta:{ident_norm}", 10, 900)
    usuario = _buscar_por_identificador(db, dados.identificador)
    erro = HTTPException(status_code=400, detail="Código incorreto ou expirado. Peça um novo código.")
    if not usuario:
        raise erro
    # Confere a regra da senha ANTES de gastar o código: quem digitou o código certo mas escolheu
    # uma senha fraca não precisa pedir outro.
    seg.validar_senha(dados.nova_senha, usuario.nome, usuario.email, usuario.telefone)
    if not seg.conferir_codigo(db, usuario, "recuperacao", dados.codigo):
        seg.auditar(db, "recuperacao_codigo_errado", usuario, ident_norm, ip=ip)
        raise erro

    usuario.senha_hash = auth.hash_senha(dados.nova_senha)
    usuario.senha_alterada_em = seg.agora_utc()
    usuario.trocar_senha = False
    usuario.falhas_login = 0
    usuario.bloqueado_ate = None
    usuario.token_versao = (usuario.token_versao or 0) + 1  # derruba qualquer sessão antiga
    db.commit()
    seg.revogar_sessoes(db, usuario.id)
    seg.limpar_limite(f"login-conta:{ident_norm}")
    seg.auditar(db, "senha_redefinida", usuario, ident_norm, "por código de e-mail", ip)
    seg.avisar_senha_alterada(usuario)
    return schemas.Mensagem(detail="Senha redefinida. Entre com a nova senha.")


@router.post("/trocar-senha", response_model=schemas.Token)
def trocar_senha(dados: schemas.TrocarSenha, request: Request, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(auth.usuario_atual_livre)):
    """Troca a senha estando logado (e é também o passo obrigatório depois de uma senha provisória).
    Derruba os outros aparelhos e devolve um par de tokens novo pra este continuar logado."""
    ip = seg.ip_do_cliente(request)
    seg.checar_limite(f"trocar-conta:{usuario.id}", 8, 900)
    if not auth.verificar_senha(dados.senha_atual, usuario.senha_hash):
        seg.auditar(db, "troca_senha_falhou", usuario, ip=ip)
        raise HTTPException(status_code=400, detail="A senha atual está incorreta.")
    if dados.nova_senha == dados.senha_atual:
        raise HTTPException(status_code=400, detail="A nova senha precisa ser diferente da atual.")
    seg.validar_senha(dados.nova_senha, usuario.nome, usuario.email, usuario.telefone)

    usuario.senha_hash = auth.hash_senha(dados.nova_senha)
    usuario.senha_alterada_em = seg.agora_utc()
    usuario.trocar_senha = False
    usuario.token_versao = (usuario.token_versao or 0) + 1
    db.commit()
    seg.revogar_sessoes(db, usuario.id)
    seg.auditar(db, "senha_trocada", usuario, ip=ip)
    seg.avisar_senha_alterada(usuario)
    return _emitir_tokens(db, usuario, request)
