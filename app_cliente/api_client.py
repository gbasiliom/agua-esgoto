import sessao_http as requests
from api_base import ApiBase, ApiError, ErroConexao, ErroSessao  # noqa: F401

TIPOS_ACEITOS = ("cliente",)


class ApiClient(ApiBase):
    """Fala com a API FastAPI, do ponto de vista do cliente/morador.
    (login, renovação automática do token e troca de senha vêm de ApiBase / sessao_http.)"""

    def _headers(self):
        return self._h()

    def login(self, identificador, senha, tipos_aceitos=TIPOS_ACEITOS):
        return super().login(identificador, senha, tipos_aceitos)

    def obter_empresa(self):
        """Não exige login — o nome da empresa aparece já na tela de login."""
        try:
            resp = requests.get(f"{self.url}/financeiro/empresa", timeout=10)
        except requests.exceptions.RequestException:
            return None
        if resp.status_code != 200:
            return None
        return resp.json()

    def _post(self, caminho, **kwargs):
        try:
            return requests.post(f"{self.url}{caminho}", headers=self._headers(), timeout=10, **kwargs)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem internet — a ação será guardada e enviada quando houver conexão.")

    def _get(self, caminho, **kwargs):
        try:
            return requests.get(f"{self.url}{caminho}", headers=self._headers(), timeout=10, **kwargs)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem internet.")

    def _patch(self, caminho, **kwargs):
        try:
            return requests.patch(f"{self.url}{caminho}", headers=self._headers(), timeout=10, **kwargs)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem internet.")

    def registrar(self, nome, email, telefone, senha):
        resp = self._post(
            "/auth/registrar",
            json={"nome": nome, "email": email, "telefone": telefone, "senha": senha},
        )
        if resp.status_code != 200:
            try:
                det = resp.json().get("detail")
            except Exception:
                det = None
            if isinstance(det, list):
                det = "; ".join(str(d.get("msg", d)) for d in det)
            raise ApiError(det or "Não foi possível criar sua conta")
        dados = resp.json()
        self.token = dados["access_token"]
        self.tipo_usuario = dados["tipo_usuario"]
        self.trocar_senha_pendente = bool(dados.get("trocar_senha"))
        requests.definir_tokens(self.token, dados.get("refresh_token"), self.url)
        return dados

    def meu_cadastro(self):
        """Retorna None se o cliente ainda não completou o cadastro (endereço etc)."""
        resp = self._get("/clientes/eu")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar seu cadastro")
        return resp.json()

    def criar_cadastro(self, nome, endereco, bairro, cidade, hidrometro, categoria, localidade=None):
        resp = self._post(
            "/clientes/eu",
            json={
                "nome": nome, "endereco": endereco, "bairro": bairro,
                "cidade": cidade, "hidrometro": hidrometro, "categoria": categoria,
                "localidade": localidade,
            },
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível salvar seu cadastro"))
        return resp.json()

    def abrir_chamado(self, tipo, descricao_problema, prioridade="normal"):
        resp = self._post(
            "/chamados/meu",
            json={"tipo": tipo, "descricao_problema": descricao_problema, "prioridade": prioridade, "origem": "app"},
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível abrir o chamado"))
        return resp.json()

    def meus_chamados(self):
        resp = self._get("/chamados/meus")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar seus chamados")
        return resp.json()

    def pendente_mes_leitura(self):
        resp = self._get("/leituras/pendente-mes")
        if resp.status_code != 200:
            raise ApiError("Não foi possível verificar a leitura do mês")
        return resp.json()

    def enviar_leitura(self, valor_informado, caminho_foto):
        with open(caminho_foto, "rb") as f:
            arquivos = {"foto": ("hidrometro.jpg", f, "image/jpeg")}
            resp = self._post_multipart("/leituras/", data={"valor_informado": valor_informado}, files=arquivos)
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível enviar a leitura"))
        return resp.json()

    def minhas_leituras(self):
        resp = self._get("/leituras/minhas")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar suas leituras")
        return resp.json()

    def ultima_leitura(self):
        resp = self._get("/leituras/ultima")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar a última leitura")
        return resp.json()

    def minhas_faturas(self):
        resp = self._get("/faturamento/faturas/minhas")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar suas faturas")
        return resp.json()

    def _post_multipart(self, caminho, data, files):
        try:
            return requests.post(f"{self.url}{caminho}", data=data, files=files, headers=self._headers(), timeout=30)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem internet — a ação será guardada e enviada quando houver conexão.")
