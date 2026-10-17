"""Chamadas de senha/sessão que não dependem de tela (usadas pelos apps Kivy):
esqueci minha senha → código por e-mail → nova senha; troca de senha; sair.
Os erros viram `ErroFluxo` com texto pronto para mostrar ao usuário."""
import re

import requests as _rq

import sessao_http


class ErroFluxo(Exception):
    pass


def _texto_erro(resp, padrao):
    try:
        det = resp.json().get("detail")
    except Exception:
        det = None
    if isinstance(det, list):
        det = "; ".join(str(d.get("msg", d)) for d in det)
    return det or padrao


def _chamar(base, caminho, corpo, autenticado=False):
    url = f"{base.rstrip('/')}{caminho}"
    try:
        if autenticado:
            resp = sessao_http.post(url, json=corpo, headers={"Authorization": "Bearer x"}, timeout=20)
        else:
            resp = _rq.post(url, json=corpo, timeout=20)
    except _rq.exceptions.RequestException:
        raise ErroFluxo("Sem conexão com o servidor. Confira a internet e o endereço do servidor.")
    if resp.status_code >= 400:
        raise ErroFluxo(_texto_erro(resp, f"Erro {resp.status_code}"))
    return resp.json()


def problemas_senha(nova, repetir=None):
    """Confere no aparelho (o servidor confere de novo): devolve a lista do que está faltando."""
    erros = []
    if len(nova or "") < 8:
        erros.append("pelo menos 8 caracteres")
    if not re.search(r"[A-Za-zÀ-ÿ]", nova or ""):
        erros.append("pelo menos uma letra")
    if not re.search(r"\d", nova or ""):
        erros.append("pelo menos um número")
    if repetir is not None and nova != repetir:
        return ["as duas senhas iguais"]
    return erros


def texto_problemas(erros):
    return "A senha precisa ter " + ", ".join(erros) + "." if erros else ""


def esqueci_senha(base, identificador):
    return _chamar(base, "/auth/esqueci-senha", {"identificador": identificador.strip()}).get("detail", "")


def redefinir_senha(base, identificador, codigo, nova_senha):
    return _chamar(base, "/auth/redefinir-senha", {
        "identificador": identificador.strip(), "codigo": re.sub(r"\D", "", codigo or ""), "nova_senha": nova_senha,
    }).get("detail", "Senha redefinida.")


def trocar_senha(base, senha_atual, nova_senha):
    """Logado: troca a senha e já guarda o par de tokens novo (os antigos deixaram de valer)."""
    d = _chamar(base, "/auth/trocar-senha", {"senha_atual": senha_atual, "nova_senha": nova_senha}, autenticado=True)
    sessao_http.definir_tokens(d["access_token"], d.get("refresh_token"), base)
    return d


def sair(base):
    """Encerra a sessão no servidor (best effort) e esquece os tokens daqui."""
    refresh = sessao_http.padrao.refresh
    sessao_http.limpar()
    if refresh:
        try:
            _rq.post(f"{base.rstrip('/')}/auth/logout", json={"refresh_token": refresh}, timeout=5)
        except _rq.exceptions.RequestException:
            pass
