from api_base import ApiBase, ApiError, ErroConexao, ErroSessao  # noqa: F401

TIPOS_ACEITOS = ("operador_eta",)


class ApiClient(ApiBase):
    def login(self, identificador, senha, tipos_aceitos=TIPOS_ACEITOS):
        return super().login(identificador, senha, tipos_aceitos)

    def enviar_analise(self, payload):
        return self._json("POST", "/analise-eta/", json=payload)

    def enviar_lavagem(self, payload):
        return self._json("POST", "/analise-eta/lavagem-filtro", json=payload)

    def minhas_analises(self):
        return self._json("GET", "/analise-eta/minhas")
