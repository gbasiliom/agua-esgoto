import os
from api_base import ApiBase, ApiError, ErroConexao, ErroSessao  # noqa: F401

TIPOS_ACEITOS = ("quimico",)


class ApiClient(ApiBase):
    def login(self, identificador, senha, tipos_aceitos=TIPOS_ACEITOS):
        return super().login(identificador, senha, tipos_aceitos)

    def conformidade(self, localidade, mes=None):
        p = {"localidade": localidade}
        if mes:
            p["mes"] = mes
        return self._json("GET", "/qualidade/conformidade", params=p)

    def pontos(self, localidade):
        return self._json("GET", "/qualidade/pontos", params={"localidade": localidade})

    def criar_ponto(self, localidade, tipo, nome, descricao=None):
        return self._json("POST", "/qualidade/pontos", json={"localidade": localidade, "tipo": tipo, "nome": nome, "descricao": descricao})

    def amostras(self, localidade, status=None):
        p = {"localidade": localidade}
        if status:
            p["status"] = status
        return self._json("GET", "/qualidade/amostras", params=p)

    def criar_amostra(self, payload):
        return self._json("POST", "/qualidade/amostras", json=payload)

    def registrar_coleta(self, amostra_id, payload):
        return self._json("PATCH", f"/qualidade/amostras/{amostra_id}/coleta", json=payload)

    def lancar_resultado(self, amostra_id, payload):
        return self._json("POST", f"/qualidade/amostras/{amostra_id}/resultado", json=payload)

    def encaminhar(self, amostra_id):
        return self._json("POST", f"/qualidade/amostras/{amostra_id}/encaminhar")

    def laudos(self, localidade):
        return self._json("GET", "/qualidade/laudos", params={"localidade": localidade})

    def enviar_laudo(self, campos, caminho_arquivo=None):
        dados = {k: str(v) for k, v in campos.items() if v not in (None, "")}
        if caminho_arquivo:
            if not os.path.exists(caminho_arquivo):
                raise ApiError("Arquivo não encontrado.")
            with open(caminho_arquivo, "rb") as f:
                return self._json("POST", "/qualidade/laudos", data=dados, files={"arquivo": (os.path.basename(caminho_arquivo), f)}, timeout=60)
        return self._json("POST", "/qualidade/laudos", data=dados, timeout=60)

    def analises_ao_vivo(self, apos_analise=0, apos_lavagem=0):
        return self._json("GET", "/analise-eta/ao-vivo", params={"apos_analise": apos_analise, "apos_lavagem": apos_lavagem}, timeout=10)
