import requests


class ApiError(Exception):
    pass


class ErroConexao(ApiError):
    """Sem internet / servidor fora do ar — decide quando cair para o modo offline."""


class ErroSessao(ApiError):
    """Token expirado/inválido — o item NÃO deve ser descartado da fila."""


class ApiBase:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.token = None
        self.tipo_usuario = None
        self.usuario_id = None
        self.nome = None
        self.localidade = None

    # ---- infraestrutura ----
    def _h(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _req(self, metodo, caminho, timeout=15, **kw):
        try:
            resp = requests.request(metodo, f"{self.url}{caminho}", headers=self._h(), timeout=timeout, **kw)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code == 401 and self.token:
            raise ErroSessao("Sessão expirada. Saia e entre de novo.")
        if resp.status_code >= 400:
            try:
                det = resp.json().get("detail")
            except Exception:
                det = None
            if isinstance(det, list):  # erro de validação do FastAPI
                det = "; ".join(str(d.get("msg", d)) for d in det)
            raise ApiError(det or f"Erro {resp.status_code}")
        return resp

    def _json(self, metodo, caminho, **kw):
        return self._req(metodo, caminho, **kw).json()

    # ---- login ----
    def login(self, identificador, senha, tipos_aceitos):
        try:
            resp = requests.post(f"{self.url}/auth/login", json={"identificador": identificador, "senha": senha}, timeout=15)
        except requests.exceptions.RequestException:
            raise ErroConexao("Não foi possível conectar ao servidor. Confira o endereço e a internet.")
        if resp.status_code != 200:
            try:
                raise ApiError(resp.json().get("detail", "Falha no login"))
            except ValueError:
                raise ApiError("Falha no login")
        dados = resp.json()
        if dados["tipo_usuario"] not in tipos_aceitos:
            raise ApiError("Este app é para outro perfil de usuário.")
        self.token = dados["access_token"]
        self.tipo_usuario = dados["tipo_usuario"]
        eu = self._json("GET", "/usuarios/eu")
        self.usuario_id, self.nome, self.localidade = eu["id"], eu["nome"], eu.get("localidade")
        return eu
