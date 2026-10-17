import os

# Troque pelo IP/domínio do servidor onde a API estiver rodando.
# Ex: "http://192.168.1.10:8000" (rede local) ou "https://api.suaprefeitura.gov.br"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
