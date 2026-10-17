"""Configuração comum dos testes: banco temporário e sem limites de tentativas (os testes de
segurança ligam os limites de propósito)."""
import base64
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/teste.db")
os.environ.setdefault("CHAVE_CRIPTOGRAFIA", base64.urlsafe_b64encode(b"k" * 32).decode())
os.environ.setdefault("SECRET_KEY", "chave-de-teste")
os.environ["SIGA_LIMITES_DESLIGADOS"] = "1"
os.environ["SIGA_MODO_TESTE"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
