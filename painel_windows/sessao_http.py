"""Sessão HTTP com renovação automática do login — usada pelos apps e pelo painel.

Por que existe: o servidor agora entrega um token de acesso CURTO (30 min) e um token de renovação.
Quando uma chamada volta 401 (token vencido), esta camada troca o token de renovação por um par novo
e repete a chamada, sem o usuário perceber. Só se a renovação também falhar (sessão derrubada,
senha trocada em outro aparelho, etc.) é que o app volta para a tela de login.

Uso nos apps (substitui `import requests`, mantém `requests.get(...)`, `requests.exceptions...`):

    import sessao_http as requests
    ...
    sessao_http.definir_tokens(dados["access_token"], dados.get("refresh_token"), base_url)

Uso no painel (que usa requests.Session): `self._sessao = sessao_http.SessaoRequests(base_url)`.
"""
import threading

import requests as _requests
from requests import exceptions  # noqa: F401  (reexportado: código antigo faz requests.exceptions.RequestException)


class GerenciadorSessao:
    def __init__(self, base_url=None):
        self.base_url = (base_url or "").rstrip("/")
        self.access = None
        self.refresh = None
        self.ao_renovar = None          # f(access, refresh): para quem quiser guardar o par novo
        self.ao_perder_sessao = None    # f(): chamado quando não dá mais para renovar (voltar ao login)
        self._lock = threading.RLock()

    # --- estado ---
    def definir_tokens(self, access, refresh=None, base_url=None):
        with self._lock:
            self.access = access
            self.refresh = refresh
            if base_url:
                self.base_url = base_url.rstrip("/")

    def limpar(self):
        with self._lock:
            self.access = None
            self.refresh = None

    # --- renovação ---
    def _renovar(self):
        """True se conseguiu um par novo. Chamar SEMPRE com o lock preso (o servidor derruba a conta se
        o mesmo token de renovação for usado duas vezes)."""
        if not self.refresh or not self.base_url:
            return False
        try:
            r = _requests.post(f"{self.base_url}/auth/refresh", json={"refresh_token": self.refresh}, timeout=15)
        except _requests.exceptions.RequestException:
            return None  # sem rede agora: não é motivo para deslogar
        if r.status_code != 200:
            return False
        d = r.json()
        self.access, self.refresh = d["access_token"], d.get("refresh_token") or self.refresh
        if self.ao_renovar:
            try:
                self.ao_renovar(self.access, self.refresh)
            except Exception:
                pass
        return True

    def _perdeu(self):
        self.limpar()
        if self.ao_perder_sessao:
            try:
                self.ao_perder_sessao()
            except Exception:
                pass

    # --- chamada com repetição ---
    def enviar(self, enviar_fn, metodo, url, **kw):
        """`enviar_fn(metodo, url, **kw)` faz a chamada de verdade (requests.request ou Session.request)."""
        headers = dict(kw.pop("headers", None) or {})
        usou_token = None
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer ") and self.access:
            usou_token = self.access
            headers["Authorization"] = f"Bearer {self.access}"  # sempre o token mais novo
        resp = enviar_fn(metodo, url, headers=headers, **kw)
        if resp.status_code != 401 or usou_token is None or "/auth/" in url:
            return resp
        with self._lock:
            if self.access != usou_token:
                renovado = True  # outra thread já renovou enquanto esta esperava
            else:
                renovado = self._renovar()
            if renovado is False:
                self._perdeu()
                return resp
            if renovado is None:
                return resp
            headers["Authorization"] = f"Bearer {self.access}"
        self._rebobinar(kw)
        return enviar_fn(metodo, url, headers=headers, **kw)

    @staticmethod
    def _rebobinar(kw):
        """Arquivos (fotos) já lidos na 1ª tentativa precisam voltar ao início antes da 2ª."""
        arquivos = kw.get("files")
        itens = arquivos.values() if isinstance(arquivos, dict) else (arquivos or [])
        for item in itens:
            f = item[1] if isinstance(item, tuple) and len(item) > 1 else item
            if isinstance(f, tuple) and len(f) > 1:
                f = f[1]
            if hasattr(f, "seek"):
                try:
                    f.seek(0)
                except Exception:
                    pass


# --------------------------------------------------------------------------------------
# Versão "módulo" para os apps (drop-in de `requests`)
# --------------------------------------------------------------------------------------
padrao = GerenciadorSessao()


def definir_tokens(access, refresh=None, base_url=None):
    padrao.definir_tokens(access, refresh, base_url)


def limpar():
    padrao.limpar()


def ao_perder_sessao(funcao):
    padrao.ao_perder_sessao = funcao


def request(metodo, url, **kw):
    return padrao.enviar(_requests.request, metodo, url, **kw)


def get(url, **kw):
    return request("GET", url, **kw)


def post(url, **kw):
    return request("POST", url, **kw)


def put(url, **kw):
    return request("PUT", url, **kw)


def patch(url, **kw):
    return request("PATCH", url, **kw)


def delete(url, **kw):
    return request("DELETE", url, **kw)


# --------------------------------------------------------------------------------------
# Versão Session para o painel Windows
# --------------------------------------------------------------------------------------
class SessaoRequests(_requests.Session):
    def __init__(self, base_url=None):
        super().__init__()
        self.gerenciador = GerenciadorSessao(base_url)

    def request(self, method, url, **kw):  # noqa: D401
        return self.gerenciador.enviar(super().request, method, url, **kw)
