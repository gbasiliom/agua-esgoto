"""
Peças de segurança do SIGA: política de senha, limite de tentativas, códigos de
6 dígitos, envio de e-mail e trilha de auditoria.

Variáveis de ambiente (todas opcionais — no .env da pasta backend):
  SIGA_ENV                 producao | desenvolvimento (padrão). Em produção /docs some.
  SIGA_MODO_TESTE          1 = não obriga trocar senhas fracas de teste (123456 etc.). Só para testes!
  SIGA_2FA_ADMIN           auto (padrão: liga se o e-mail estiver configurado) | 1 | 0
  SIGA_PROXY_CONFIAVEL     1 = confia no cabeçalho X-Forwarded-For (só atrás de proxy seu, tipo nginx)
  SIGA_MAX_UPLOAD_MB       tamanho máximo de upload (padrão 15)
  SIGA_CORS_ORIGENS        lista separada por vírgula (padrão: nenhuma; apps nativos não precisam)
  E-mail (escolha UM):
    RESEND_API_KEY + EMAIL_REMETENTE   (ex.: SIGA <nao-responda@seudominio.com.br>)
    SMTP_HOST, SMTP_PORT, SMTP_USUARIO, SMTP_SENHA, EMAIL_REMETENTE
  Sem nenhum dos dois, o código aparece só no console do servidor (modo desenvolvimento).
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import threading
import time
import urllib.request
import urllib.error
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.message import EmailMessage

from fastapi import HTTPException, Request

import models

log = logging.getLogger("siga.seguranca")


def _env_bool(nome, padrao=False):
    v = os.getenv(nome)
    if v is None:
        return padrao
    return v.strip().lower() in ("1", "true", "sim", "yes", "on")


def agora_utc() -> datetime:
    return datetime.utcnow()


# --------------------------------------------------------------------------
# Política de senha
# --------------------------------------------------------------------------
SENHA_MIN = 8
SENHA_MAX = 72  # limite do bcrypt: acima disso os bytes extras seriam ignorados em silêncio

_SENHAS_FRACAS = {
    "12345678", "123456789", "1234567890", "password", "password1", "senha123", "senha1234",
    "123456a", "abc12345", "qwerty123", "11111111", "00000000", "admin123", "admin1234",
    "siga1234", "saae1234", "chale123", "teste123", "mudar123", "trocar123", "123mudar",
    "senha@123", "brasil123", "brasil2026", "q1w2e3r4", "1q2w3e4r", "iloveyou1",
}


def problemas_senha(senha: str, *contexto: str):
    """Lista de motivos pelos quais a senha NÃO serve (lista vazia = senha aceita)."""
    erros = []
    if senha is None or len(senha) < SENHA_MIN:
        erros.append(f"ter pelo menos {SENHA_MIN} caracteres")
        return erros
    if len(senha.encode("utf-8")) > SENHA_MAX:
        erros.append(f"ter no máximo {SENHA_MAX} caracteres")
    if not re.search(r"[A-Za-zÀ-ÿ]", senha):
        erros.append("ter pelo menos uma letra")
    if not re.search(r"\d", senha):
        erros.append("ter pelo menos um número")
    baixa = senha.lower()
    if baixa in _SENHAS_FRACAS or len(set(baixa)) <= 2:
        erros.append("evitar senhas comuns ou repetitivas")
    digitos_senha = re.sub(r"\D", "", baixa)
    for c in contexto:
        if not c:
            continue
        c = c.strip().lower()
        achou = False
        if "@" in c:
            local = c.split("@")[0]
            achou = len(local) >= 4 and local in baixa
        elif re.fullmatch(r"[\d\s()+\-.]+", c):
            fone = re.sub(r"\D", "", c)
            achou = len(fone) >= 6 and (fone in digitos_senha or fone[-6:] in digitos_senha)
        else:
            achou = any(len(p) >= 4 and p in baixa for p in re.split(r"\s+", c))
        if achou:
            erros.append("evitar seu nome, e-mail ou telefone")
            break
    return erros


def validar_senha(senha: str, *contexto: str):
    erros = problemas_senha(senha, *contexto)
    if erros:
        raise HTTPException(status_code=400, detail="A senha precisa " + "; ".join(erros) + ".")


def senha_e_fraca(senha: str) -> bool:
    return bool(problemas_senha(senha))


def modo_teste() -> bool:
    return _env_bool("SIGA_MODO_TESTE", False)


def gerar_senha_provisoria(tamanho: int = 10) -> str:
    """Senha provisória legível (sem 0/O, 1/l/I) que sempre passa na política."""
    letras = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
    numeros = "23456789"
    while True:
        s = "".join(secrets.choice(letras + numeros) for _ in range(tamanho))
        if re.search(r"[a-zA-Z]", s) and re.search(r"\d", s) and not problemas_senha(s):
            return s


# --------------------------------------------------------------------------
# Limite de tentativas (janela deslizante, em memória)
# --------------------------------------------------------------------------
_lock = threading.Lock()
_eventos = defaultdict(deque)


def limites_ativos() -> bool:
    return not _env_bool("SIGA_LIMITES_DESLIGADOS", False)


def resetar_limites():
    with _lock:
        _eventos.clear()


def checar_limite(chave: str, maximo: int, janela_s: int, mensagem: str = None):
    """Registra uma tentativa e levanta 429 se passou do máximo na janela."""
    if not limites_ativos():
        return
    agora = time.monotonic()
    with _lock:
        fila = _eventos[chave]
        while fila and agora - fila[0] > janela_s:
            fila.popleft()
        if len(fila) >= maximo:
            espera = max(1, int(janela_s - (agora - fila[0])))
            minutos = max(1, (espera + 59) // 60)
            raise HTTPException(
                status_code=429,
                detail=mensagem or f"Muitas tentativas. Aguarde {minutos} minuto(s) e tente de novo.",
                headers={"Retry-After": str(espera)},
            )
        fila.append(agora)


def limpar_limite(chave: str):
    with _lock:
        _eventos.pop(chave, None)


def ip_do_cliente(request: Request) -> str:
    if _env_bool("SIGA_PROXY_CONFIAVEL", False):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "desconhecido")[:64]


def normalizar_identificador(ident: str) -> str:
    return (ident or "").strip().lower()


# --------------------------------------------------------------------------
# Códigos de 6 dígitos
# --------------------------------------------------------------------------
CODIGO_VALIDADE_MIN = 10
CODIGO_MAX_TENTATIVAS = 5


def _chave_hmac() -> bytes:
    import auth
    return auth.SECRET_KEY.encode()


def _hmac_codigo(usuario_id: int, finalidade: str, codigo: str) -> str:
    msg = f"{usuario_id}:{finalidade}:{codigo}".encode()
    return hmac.new(_chave_hmac(), msg, hashlib.sha256).hexdigest()


def gerar_codigo(db, usuario: models.Usuario, finalidade: str) -> str:
    """Cria um código novo (invalida os anteriores da mesma finalidade) e devolve o texto de 6 dígitos."""
    db.query(models.CodigoSeguranca).filter(
        models.CodigoSeguranca.usuario_id == usuario.id,
        models.CodigoSeguranca.finalidade == finalidade,
        models.CodigoSeguranca.usado == False,  # noqa: E712
    ).update({"usado": True})
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    agora = agora_utc()
    db.add(models.CodigoSeguranca(
        usuario_id=usuario.id, finalidade=finalidade,
        codigo_hmac=_hmac_codigo(usuario.id, finalidade, codigo),
        criado_em=agora, expira_em=agora + timedelta(minutes=CODIGO_VALIDADE_MIN),
    ))
    db.commit()
    return codigo


def conferir_codigo(db, usuario: models.Usuario, finalidade: str, codigo: str) -> bool:
    """True e consome o código se estiver certo, dentro do prazo e das tentativas. Conta erros."""
    reg = db.query(models.CodigoSeguranca).filter(
        models.CodigoSeguranca.usuario_id == usuario.id,
        models.CodigoSeguranca.finalidade == finalidade,
        models.CodigoSeguranca.usado == False,  # noqa: E712
    ).order_by(models.CodigoSeguranca.id.desc()).first()
    if not reg:
        return False
    if reg.expira_em < agora_utc() or reg.tentativas >= CODIGO_MAX_TENTATIVAS:
        reg.usado = True
        db.commit()
        return False
    codigo = re.sub(r"\D", "", codigo or "")
    certo = hmac.compare_digest(reg.codigo_hmac, _hmac_codigo(usuario.id, finalidade, codigo))
    if certo:
        reg.usado = True
    else:
        reg.tentativas += 1
        if reg.tentativas >= CODIGO_MAX_TENTATIVAS:
            reg.usado = True
    db.commit()
    return certo


# --------------------------------------------------------------------------
# Tokens de renovação (refresh)
# --------------------------------------------------------------------------
REFRESH_DIAS = 30


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def criar_sessao(db, usuario: models.Usuario, ip: str, aparelho: str = None) -> str:
    token = secrets.token_urlsafe(48)
    agora = agora_utc()
    db.add(models.SessaoRefresh(
        usuario_id=usuario.id, token_hash=hash_token(token), criado_em=agora,
        expira_em=agora + timedelta(days=REFRESH_DIAS), ip=ip, aparelho=(aparelho or "")[:200],
    ))
    db.commit()
    return token


def revogar_sessoes(db, usuario_id: int):
    db.query(models.SessaoRefresh).filter(
        models.SessaoRefresh.usuario_id == usuario_id, models.SessaoRefresh.revogado == False  # noqa: E712
    ).update({"revogado": True})
    db.commit()


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------
def auditar(db, acao: str, usuario: models.Usuario = None, identificador: str = None, detalhe: str = None, ip: str = None):
    try:
        db.add(models.Auditoria(
            quando=agora_utc(), usuario_id=usuario.id if usuario else None,
            identificador=(identificador or "")[:150] or None, acao=acao,
            detalhe=(detalhe or "")[:300] or None, ip=ip,
        ))
        db.commit()
    except Exception:  # auditoria nunca pode derrubar a ação principal
        db.rollback()
        log.exception("Falha ao gravar auditoria")


# --------------------------------------------------------------------------
# E-mail
# --------------------------------------------------------------------------
def email_configurado() -> bool:
    return bool(os.getenv("RESEND_API_KEY") or os.getenv("SMTP_HOST"))


def mascarar_email(email: str) -> str:
    try:
        nome, dom = email.split("@", 1)
    except ValueError:
        return "***"
    return f"{nome[:1]}{'•' * max(2, len(nome) - 1)}@{dom}"


def enviar_email(para: str, assunto: str, texto: str) -> bool:
    """Envia por Resend ou SMTP; sem nenhum configurado, imprime no console do servidor
    (modo desenvolvimento). Devolve True se saiu/foi impresso, False se falhou."""
    remetente = os.getenv("EMAIL_REMETENTE", "SIGA <nao-responda@localhost>")
    html = "<div style='font-family:Arial,sans-serif;font-size:15px;color:#1e293b'>" + \
           texto.replace("\n", "<br>") + "</div>"
    try:
        if os.getenv("RESEND_API_KEY"):
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps({"from": remetente, "to": [para], "subject": assunto, "text": texto, "html": html}).encode(),
                headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return 200 <= r.status < 300
        if os.getenv("SMTP_HOST"):
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = remetente, para, assunto
            msg.set_content(texto)
            msg.add_alternative(html, subtype="html")
            porta = int(os.getenv("SMTP_PORT", "587"))
            with smtplib.SMTP(os.environ["SMTP_HOST"], porta, timeout=15) as s:
                s.starttls()
                if os.getenv("SMTP_USUARIO"):
                    s.login(os.environ["SMTP_USUARIO"], os.environ.get("SMTP_SENHA", ""))
                s.send_message(msg)
            return True
    except (urllib.error.URLError, smtplib.SMTPException, OSError, ValueError):
        log.exception("Falha ao enviar e-mail")
        return False
    # Modo desenvolvimento: sem provedor de e-mail configurado
    print("\n" + "=" * 60)
    print(f"[E-MAIL DE TESTE — nenhum provedor configurado]\nPara: {para}\nAssunto: {assunto}\n\n{texto}")
    print("=" * 60 + "\n", flush=True)
    return True


def enviar_codigo(usuario: models.Usuario, codigo: str, finalidade: str) -> bool:
    if finalidade == "recuperacao":
        assunto = "SIGA — código para redefinir sua senha"
        corpo = (f"Olá, {usuario.nome.split()[0]}.\n\nSeu código para redefinir a senha do SIGA é:\n\n"
                 f"    {codigo}\n\nEle vale por {CODIGO_VALIDADE_MIN} minutos e só pode ser usado uma vez.\n"
                 "Se não foi você que pediu, ignore este e-mail: sua senha continua a mesma.\n"
                 "Nunca passe este código para ninguém, nem para quem disser que é do suporte.")
    else:
        assunto = "SIGA — código de verificação de acesso"
        corpo = (f"Olá, {usuario.nome.split()[0]}.\n\nSeu código de verificação para entrar no painel do SIGA é:\n\n"
                 f"    {codigo}\n\nEle vale por {CODIGO_VALIDADE_MIN} minutos. Se não foi você que tentou entrar, "
                 "troque sua senha imediatamente.")
    return enviar_email(usuario.email, assunto, corpo)


def avisar_senha_alterada(usuario: models.Usuario):
    if usuario.email:
        enviar_email(
            usuario.email, "SIGA — sua senha foi alterada",
            f"Olá, {usuario.nome.split()[0]}.\n\nA senha da sua conta no SIGA acabou de ser alterada. "
            "Se foi você, não precisa fazer nada. Se NÃO foi, avise o administrador do sistema agora.",
        )


def e_mail_valido(email: str) -> bool:
    return bool(email) and len(email) <= 150 and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email) is not None


def doisfa_admin_ativo() -> bool:
    v = os.getenv("SIGA_2FA_ADMIN", "auto").strip().lower()
    if v == "auto":
        return email_configurado()
    return v in ("1", "true", "sim", "yes", "on")
