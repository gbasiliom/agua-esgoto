import os

PADRAO = "http://192.168.0.115:8000"   # troque pelo endereço do servidor (ou use o campo "Servidor" no login)
_ARQ = "servidor.txt"                  # gravado na pasta de dados do app


def carregar_url(pasta_dados):
    try:
        with open(os.path.join(pasta_dados, _ARQ), encoding="utf-8") as f:
            url = f.read().strip()
            if url:
                return url
    except OSError:
        pass
    return os.getenv("API_BASE_URL", PADRAO)


def salvar_url(pasta_dados, url):
    url = (url or "").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("O endereço deve começar com http:// ou https://")
    os.makedirs(pasta_dados, exist_ok=True)
    with open(os.path.join(pasta_dados, _ARQ), "w", encoding="utf-8") as f:
        f.write(url)
    return url
