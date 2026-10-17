"""
Ponto de entrada "silencioso" pro backend — sem janela preta, só um
ícone perto do relógio (bandeja do sistema). Clique com o botão direito
nele pra abrir a documentação da API ou sair.

Como não tem mais tela pra mostrar erro, TUDO que seria print() agora
vai pro arquivo siga_backend_log.txt, do lado do .exe — se algo der
errado, é lá que se olha.
"""
import os
import sys
import threading
import traceback
from datetime import datetime


def pasta_do_executavel():
    """Onde o .exe de verdade está — usado pros dados que precisam persistir (log, banco)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def pasta_de_assets_embutidos():
    """Onde os arquivos empacotados junto (tipo o ícone) ficam ao rodar — só leitura."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return pasta_do_executavel()


PASTA_BASE = pasta_do_executavel()
os.chdir(PASTA_BASE)

ARQUIVO_LOG = os.path.join(PASTA_BASE, "siga_backend_log.txt")
_arquivo_log = open(ARQUIVO_LOG, "a", encoding="utf-8", buffering=1)
sys.stdout = _arquivo_log
sys.stderr = _arquivo_log


def registrar(mensagem):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _arquivo_log.write(f"[{agora}] {mensagem}\n")
    _arquivo_log.flush()


def rodar_backend():
    try:
        import uvicorn
        from main import app

        registrar("Backend iniciando...")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        registrar("Backend encerrado normalmente.")
    except Exception:
        registrar("ERRO ao iniciar o backend:\n" + traceback.format_exc())


def abrir_documentacao(icon, item):
    import webbrowser
    webbrowser.open("http://localhost:8000/docs")


def sair(icon, item):
    registrar("Encerrado pelo usuário (menu da bandeja).")
    icon.stop()
    os._exit(0)


def criar_icone_bandeja():
    import pystray
    from PIL import Image

    caminho_icone = os.path.join(pasta_de_assets_embutidos(), "icone.ico")
    if os.path.exists(caminho_icone):
        imagem = Image.open(caminho_icone)
    else:
        imagem = Image.new("RGB", (64, 64), "#0891b2")  # quadrado azul, só de reserva

    menu = pystray.Menu(
        pystray.MenuItem("SIGA — Backend rodando", None, enabled=False),
        pystray.MenuItem("Abrir documentação da API", abrir_documentacao),
        pystray.MenuItem("Sair", sair),
    )
    return pystray.Icon("SIGA-Backend", imagem, "SIGA — Backend", menu)


if __name__ == "__main__":
    registrar("=" * 40)
    registrar("Aplicativo iniciado.")

    thread_servidor = threading.Thread(target=rodar_backend, daemon=True)
    thread_servidor.start()

    icone = criar_icone_bandeja()
    icone.run()
