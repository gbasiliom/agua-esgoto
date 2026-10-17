"""
Criptografia de dados sensíveis em repouso (no banco).

Usa AES-256-GCM (autenticado — detecta se o dado foi adulterado, não só
embaralha) via a biblioteca `cryptography`, o mesmo padrão usado por bancos
e serviços financeiros. Cada valor criptografado usa um "nonce" (número
aleatório) diferente, então o mesmo CPF criptografado duas vezes gera
textos cifrados diferentes — impossível de comparar/rastrear no banco.

A chave (256 bits = 32 bytes) fica só na variável de ambiente
CHAVE_CRIPTOGRAFIA, nunca no código-fonte nem no banco.
"""
import os
import sys
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CHAVE_ENV = os.getenv("CHAVE_CRIPTOGRAFIA")


def _pasta_persistente():
    """
    Onde salvar arquivos que precisam sobreviver entre execuções.
    Empacotado (.exe): ao lado do executável de verdade — NUNCA a pasta
    temporária que o PyInstaller usa por baixo dos panos (essa é apagada
    quando o programa fecha, e perder a chave = perder os CPFs salvos).
    Rodando via código-fonte: a própria pasta do backend.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


_ARQUIVO_CHAVE_RESERVA = os.path.join(_pasta_persistente(), ".chave_criptografia_local")


def _obter_chave():
    """
    Prioridade: 1) variável de ambiente CHAVE_CRIPTOGRAFIA (recomendado em
    produção). 2) Se não tiver, usa/gera um arquivo local pra chave nunca
    mudar sozinha entre reinícios — perder a chave = perder o CPF salvo
    pra sempre (criptografia não tem "esqueci minha senha").
    """
    if CHAVE_ENV:
        return base64.urlsafe_b64decode(CHAVE_ENV)

    if os.path.exists(_ARQUIVO_CHAVE_RESERVA):
        with open(_ARQUIVO_CHAVE_RESERVA, "rb") as f:
            return base64.urlsafe_b64decode(f.read())

    print(
        "⚠ AVISO DE SEGURANÇA: CHAVE_CRIPTOGRAFIA não definida no .env — "
        f"gerando e salvando uma chave local em {_ARQUIVO_CHAVE_RESERVA}. "
        "Pra produção de verdade, defina CHAVE_CRIPTOGRAFIA no .env e nunca "
        "perca essa chave (sem ela, os CPFs salvos não podem ser recuperados)."
    )
    chave_nova = AESGCM.generate_key(bit_length=256)
    with open(_ARQUIVO_CHAVE_RESERVA, "wb") as f:
        f.write(base64.urlsafe_b64encode(chave_nova))
    return chave_nova


_CHAVE = _obter_chave()
_aesgcm = AESGCM(_CHAVE)


def criptografar(texto_puro: str) -> str:
    if texto_puro is None:
        return None
    nonce = os.urandom(12)  # 96 bits, recomendado pelo padrão GCM
    cifrado = _aesgcm.encrypt(nonce, texto_puro.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + cifrado).decode("ascii")


def descriptografar(texto_cifrado: str) -> str:
    if texto_cifrado is None:
        return None
    bruto = base64.urlsafe_b64decode(texto_cifrado.encode("ascii"))
    nonce, cifrado = bruto[:12], bruto[12:]
    return _aesgcm.decrypt(nonce, cifrado, None).decode("utf-8")


def gerar_chave_nova() -> str:
    """Gera uma chave de 256 bits nova, pronta pra colar no .env como CHAVE_CRIPTOGRAFIA."""
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")


if __name__ == "__main__":
    print("Nova chave de 256 bits (cole no .env como CHAVE_CRIPTOGRAFIA):")
    print(gerar_chave_nova())
