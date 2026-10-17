import os
import re

import requests
import sessao_http
from config import API_BASE_URL


class ApiError(Exception):
    pass


def _texto_erro(resp, padrao):
    """Mensagem de erro da API pronta para mostrar (aceita o formato de validação do FastAPI)."""
    try:
        det = resp.json().get("detail")
    except Exception:
        det = None
    if isinstance(det, list):
        det = "; ".join(str(d.get("msg", d)) for d in det)
    return det or padrao


class ApiClient:
    """Fala com a API FastAPI. Guarda o token depois do login e o renova sozinho (sessao_http).

    Fluxo de entrada:  login() -> (se dados["requer_2fa"]) verificar_2fa(codigo)
                       -> (se trocar_senha_pendente) trocar_senha(atual, nova)
    """

    def __init__(self):
        self.token = None
        self.tipo_usuario = None
        self.nome = None
        self.trocar_senha_pendente = False  # senha provisória/fraca: só libera o painel depois de trocar
        self.sessao_perdida = False         # a renovação automática falhou (senha trocada em outro lugar...)
        self._desafio_2fa = None
        self.email_mascarado = None
        # Sessão reaproveitada entre chamadas (evita reabrir a conexão TCP a cada chamada) e que renova
        # o token de acesso sozinha quando ele vence (30 min).
        self._sessao = sessao_http.SessaoRequests(API_BASE_URL)
        self._sessao.gerenciador.ao_perder_sessao = self._marcar_sessao_perdida

    def _marcar_sessao_perdida(self):
        # Chamado de thread de fundo: só levanta a bandeira; a janela principal confere de tempos em tempos.
        self.sessao_perdida = True
        self.token = None

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # --- entrada / senha / saída ---
    def _aplicar_tokens(self, dados):
        self.token = dados["access_token"]
        self.tipo_usuario = dados["tipo_usuario"]
        self.trocar_senha_pendente = bool(dados.get("trocar_senha"))
        self.sessao_perdida = False
        self._desafio_2fa = None
        self._sessao.gerenciador.definir_tokens(self.token, dados.get("refresh_token"), API_BASE_URL)

    def login(self, identificador: str, senha: str):
        """Devolve o JSON do login. Se vier `requer_2fa`, falta chamar verificar_2fa (admin com e-mail configurado)."""
        resp = self._sessao.post(
            f"{API_BASE_URL}/auth/login",
            json={"identificador": identificador, "senha": senha},
            timeout=15,
        )
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Falha no login"))
        dados = resp.json()
        if dados.get("requer_2fa"):
            self._desafio_2fa = dados.get("desafio")
            self.email_mascarado = dados.get("email_mascarado")
            return dados
        self._aplicar_tokens(dados)
        return dados

    def verificar_2fa(self, codigo: str):
        if not self._desafio_2fa:
            raise ApiError("Verificação expirada. Entre de novo com e-mail e senha.")
        resp = self._sessao.post(
            f"{API_BASE_URL}/auth/verificar-2fa",
            json={"desafio": self._desafio_2fa, "codigo": re.sub(r"\D", "", codigo or "")},
            timeout=15,
        )
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Código incorreto ou expirado."))
        dados = resp.json()
        self._aplicar_tokens(dados)
        return dados

    def esqueci_senha(self, identificador: str):
        resp = self._sessao.post(f"{API_BASE_URL}/auth/esqueci-senha", json={"identificador": identificador.strip()}, timeout=20)
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível enviar o código."))
        return resp.json().get("detail", "")

    def redefinir_senha(self, identificador: str, codigo: str, nova_senha: str):
        resp = self._sessao.post(
            f"{API_BASE_URL}/auth/redefinir-senha",
            json={"identificador": identificador.strip(), "codigo": re.sub(r"\D", "", codigo or ""), "nova_senha": nova_senha},
            timeout=20,
        )
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível redefinir a senha."))
        return resp.json().get("detail", "Senha redefinida.")

    def trocar_senha(self, senha_atual: str, nova_senha: str):
        """Logado: troca a senha. Os tokens antigos deixam de valer, então já guarda o par novo."""
        resp = self._sessao.post(
            f"{API_BASE_URL}/auth/trocar-senha",
            json={"senha_atual": senha_atual, "nova_senha": nova_senha},
            headers=self._headers(), timeout=20,
        )
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível trocar a senha."))
        dados = resp.json()
        self._aplicar_tokens(dados)
        return dados

    def sair(self):
        """Encerra a sessão no servidor (melhor esforço) e esquece os tokens daqui."""
        refresh = self._sessao.gerenciador.refresh
        self._sessao.gerenciador.limpar()
        self.token = None
        if refresh:
            try:
                requests.post(f"{API_BASE_URL}/auth/logout", json={"refresh_token": refresh}, timeout=5)
            except requests.exceptions.RequestException:
                pass

    def meus_dados(self):
        resp = self._sessao.get(f"{API_BASE_URL}/usuarios/eu", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível identificar o usuário logado")
        dados = resp.json()
        self.nome = dados.get("nome")
        return dados

    # --- Segurança (só admin) ---
    def listar_usuarios(self, tipo=None, busca=None):
        params = {k: v for k, v in (("tipo", tipo), ("busca", busca)) if v}
        resp = self._sessao.get(f"{API_BASE_URL}/usuarios/", params=params, headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível carregar os usuários"))
        return resp.json()

    def resetar_senha_usuario(self, usuario_id: int):
        resp = self._sessao.post(f"{API_BASE_URL}/usuarios/{usuario_id}/resetar-senha", headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível resetar a senha"))
        return resp.json()

    def listar_auditoria(self, acao=None, limite=300):
        params = {"limite": limite}
        if acao:
            params["acao"] = acao
        resp = self._sessao.get(f"{API_BASE_URL}/usuarios/auditoria", params=params, headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível carregar a auditoria"))
        return resp.json()

    def listar_chamados(self, status: str = None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/chamados/", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os chamados")
        return resp.json()

    def listar_tecnicos(self):
        resp = self._sessao.get(f"{API_BASE_URL}/usuarios/tecnicos", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os técnicos")
        return resp.json()

    def atribuir_tecnico(self, chamado_id: int, tecnico_id: int):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/chamados/{chamado_id}/atribuir",
            json={"tecnico_id": tecnico_id},
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atribuir o técnico"))
        return resp.json()

    def relatorio_resumo(self):
        resp = self._sessao.get(f"{API_BASE_URL}/chamados/relatorio/resumo", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar o relatório")
        return resp.json()

    def baixar_relatorio_pdf(self, chamado_id: int):
        """Retorna os bytes do PDF do relatório de atendimento."""
        resp = self._sessao.get(
            f"{API_BASE_URL}/chamados/{chamado_id}/relatorio-pdf", headers=self._headers(), timeout=20
        )
        if resp.status_code != 200:
            raise ApiError("Não foi possível gerar o relatório em PDF")
        return resp.content

    # --- Estoque ---
    def listar_itens_estoque(self):
        resp = self._sessao.get(f"{API_BASE_URL}/estoque/itens", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar o estoque")
        return resp.json()

    def alerta_estoque_minimo(self):
        resp = self._sessao.get(f"{API_BASE_URL}/estoque/alerta-minimo", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os alertas")
        return resp.json()

    def criar_item_estoque(self, nome, unidade_medida, valor_unitario, estoque_minimo):
        resp = self._sessao.post(
            f"{API_BASE_URL}/estoque/itens",
            json={"nome": nome, "unidade_medida": unidade_medida,
                  "valor_unitario": valor_unitario, "estoque_minimo": estoque_minimo},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível cadastrar o item"))
        return resp.json()

    def atualizar_item_estoque(self, item_id, nome, unidade_medida, valor_unitario, estoque_minimo):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/estoque/itens/{item_id}",
            json={"nome": nome, "unidade_medida": unidade_medida,
                  "valor_unitario": valor_unitario, "estoque_minimo": estoque_minimo},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar o item"))
        return resp.json()

    def desativar_item_estoque(self, item_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/estoque/itens/{item_id}/desativar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível desativar o item"))
        return resp.json()

    def listar_manutencoes_eta(self):
        resp = self._sessao.get(f"{API_BASE_URL}/estoque/manutencao-eta", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as manutenções da ETA")
        return resp.json()

    def listar_analises_eta(self, apenas_nao_conformes=False, localidade=None):
        params = {"apenas_nao_conformes": apenas_nao_conformes} if apenas_nao_conformes else {}
        if localidade:
            params["localidade"] = localidade
        resp = self._sessao.get(f"{API_BASE_URL}/analise-eta/", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as análises da ETA")
        return resp.json()

    def analises_ao_vivo(self, apos_analise=0, apos_lavagem=0):
        """Só o que chegou depois dos ids informados + situação atual de cada ETA (usado pelo acompanhamento ao vivo)."""
        resp = self._sessao.get(f"{API_BASE_URL}/analise-eta/ao-vivo", headers=self._headers(), timeout=10,
                                params={"apos_analise": apos_analise, "apos_lavagem": apos_lavagem})
        if resp.status_code != 200:
            raise ApiError("Não foi possível atualizar o acompanhamento ao vivo")
        return resp.json()

    def listar_lavagens_filtro(self):
        resp = self._sessao.get(f"{API_BASE_URL}/analise-eta/lavagem-filtro", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as lavagens de filtro")
        return resp.json()

    # --- Licitações ---
    def listar_licitacoes(self, status=None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/licitacoes/", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as licitações")
        return resp.json()

    def criar_licitacao(self, numero_processo, modalidade, objeto, valor_estimado, data_abertura_iso, observacoes):
        resp = self._sessao.post(
            f"{API_BASE_URL}/licitacoes/",
            json={"numero_processo": numero_processo, "modalidade": modalidade, "objeto": objeto,
                  "valor_estimado": valor_estimado, "data_abertura": data_abertura_iso, "observacoes": observacoes},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível criar a licitação"))
        return resp.json()

    def atualizar_licitacao(self, licitacao_id, numero_processo, modalidade, objeto, valor_estimado, data_abertura_iso, observacoes):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/licitacoes/{licitacao_id}",
            json={"numero_processo": numero_processo, "modalidade": modalidade, "objeto": objeto,
                  "valor_estimado": valor_estimado, "data_abertura": data_abertura_iso, "observacoes": observacoes},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar a licitação"))
        return resp.json()

    def mudar_status_licitacao(self, licitacao_id, status, vencedor=None, fornecedor_id=None, valor_final=None):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/licitacoes/{licitacao_id}/status",
            json={"status": status, "vencedor": vencedor, "fornecedor_id": fornecedor_id, "valor_final": valor_final},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível mudar o status"))
        return resp.json()

    def movimentar_estoque(self, item_id, tipo, quantidade, origem_tipo=None, origem_valor=None,
                            destino_tipo=None, destino_valor=None, observacao=None):
        resp = self._sessao.post(
            f"{API_BASE_URL}/estoque/movimentar",
            json={"item_id": item_id, "tipo": tipo, "quantidade": quantidade,
                  "origem_tipo": origem_tipo, "origem_valor": origem_valor,
                  "destino_tipo": destino_tipo, "destino_valor": destino_valor,
                  "observacao": observacao},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível registrar a movimentação"))
        return resp.json()

    def consultar_saldo(self, localizacao_tipo=None, localizacao_valor=None):
        params = {}
        if localizacao_tipo:
            params["localizacao_tipo"] = localizacao_tipo
        if localizacao_valor:
            params["localizacao_valor"] = localizacao_valor
        resp = self._sessao.get(f"{API_BASE_URL}/estoque/saldo", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar o saldo")
        return resp.json()

    # --- Solicitações de material ---
    def listar_solicitacoes(self, status=None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/estoque/solicitacoes", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as solicitações")
        return resp.json()

    def aprovar_solicitacao(self, solicitacao_id, modo="estoque", origem_tipo="sede", origem_valor="sede"):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/estoque/solicitacoes/{solicitacao_id}/aprovar",
            params={"modo": modo, "origem_tipo": origem_tipo, "origem_valor": origem_valor},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível aprovar"))
        return resp.json()

    def negar_solicitacao(self, solicitacao_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/estoque/solicitacoes/{solicitacao_id}/negar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível negar"))
        return resp.json()

    # --- Funcionários ---
    def listar_funcionarios(self):
        resp = self._sessao.get(f"{API_BASE_URL}/funcionarios/", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os funcionários")
        return resp.json()

    def cadastrar_funcionario(self, nome, cargo, telefone, localidade):
        resp = self._sessao.post(
            f"{API_BASE_URL}/funcionarios/",
            json={"nome": nome, "cargo": cargo, "telefone": telefone, "localidade": localidade},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível cadastrar o funcionário"))
        return resp.json()

    def atualizar_funcionario(self, funcionario_id, nome, cargo, telefone, localidade):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/funcionarios/{funcionario_id}",
            json={"nome": nome, "cargo": cargo, "telefone": telefone, "localidade": localidade},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar o funcionário"))
        return resp.json()

    def desativar_funcionario(self, funcionario_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/funcionarios/{funcionario_id}/desativar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível desativar o funcionário"))
        return resp.json()

    # --- Leituras de hidrômetro ---
    def listar_leituras(self, status=None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/leituras/", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as leituras")
        return resp.json()

    def aprovar_leitura(self, leitura_id):
        resp = self._sessao.patch(f"{API_BASE_URL}/leituras/{leitura_id}/aprovar", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível aprovar a leitura"))
        return resp.json()

    def rejeitar_leitura(self, leitura_id, observacao):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/leituras/{leitura_id}/rejeitar", json={"observacao": observacao},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível rejeitar a leitura"))
        return resp.json()

    def baixar_foto_leitura(self, caminho_arquivo):
        resp = self._sessao.get(f"{API_BASE_URL}/{caminho_arquivo}", headers=self._headers(), timeout=20)
        if resp.status_code != 200:
            raise ApiError("Não foi possível baixar a foto")
        return resp.content

    # --- Faturamento: tarifas ---
    def listar_tarifas(self):
        resp = self._sessao.get(f"{API_BASE_URL}/faturamento/tarifas", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as tarifas")
        return resp.json()

    def criar_tarifa(self, consumo_min, consumo_max, valor_m3, percentual_esgoto):
        resp = self._sessao.post(
            f"{API_BASE_URL}/faturamento/tarifas",
            json={"consumo_min": consumo_min, "consumo_max": consumo_max,
                  "valor_m3": valor_m3, "percentual_esgoto": percentual_esgoto},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível cadastrar a tarifa"))
        return resp.json()

    def atualizar_tarifa(self, faixa_id, consumo_min, consumo_max, valor_m3, percentual_esgoto):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/faturamento/tarifas/{faixa_id}",
            json={"consumo_min": consumo_min, "consumo_max": consumo_max,
                  "valor_m3": valor_m3, "percentual_esgoto": percentual_esgoto},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar a tarifa"))
        return resp.json()

    def desativar_tarifa(self, faixa_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/faturamento/tarifas/{faixa_id}/desativar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível desativar a tarifa"))
        return resp.json()

    # --- Faturamento: faturas ---
    def listar_faturas(self, status=None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/faturamento/faturas", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as faturas")
        return resp.json()

    def marcar_fatura_paga(self, fatura_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/faturamento/faturas/{fatura_id}/marcar-paga", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível marcar como paga"))
        return resp.json()

    def baixar_fatura_pdf(self, fatura_id):
        resp = self._sessao.get(f"{API_BASE_URL}/faturamento/faturas/{fatura_id}/pdf", headers=self._headers(), timeout=20)
        if resp.status_code != 200:
            raise ApiError("Não foi possível gerar o PDF da fatura")
        return resp.content

    # --- Financeiro: empresa ---
    def obter_empresa(self):
        resp = self._sessao.get(f"{API_BASE_URL}/financeiro/empresa", timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os dados da empresa")
        return resp.json()

    def atualizar_empresa(self, nome_fantasia, razao_social, cnpj, endereco, telefone, email):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/financeiro/empresa",
            json={"nome_fantasia": nome_fantasia, "razao_social": razao_social, "cnpj": cnpj,
                  "endereco": endereco, "telefone": telefone, "email": email},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar a empresa"))
        return resp.json()

    # --- Financeiro: fornecedores ---
    def listar_fornecedores(self):
        resp = self._sessao.get(f"{API_BASE_URL}/financeiro/fornecedores", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os fornecedores")
        return resp.json()

    def cadastrar_fornecedor(self, nome, documento, telefone, email, endereco):
        resp = self._sessao.post(
            f"{API_BASE_URL}/financeiro/fornecedores",
            json={"nome": nome, "documento": documento, "telefone": telefone, "email": email, "endereco": endereco},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível cadastrar o fornecedor"))
        return resp.json()

    def atualizar_fornecedor(self, fornecedor_id, nome, documento, telefone, email, endereco):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/financeiro/fornecedores/{fornecedor_id}",
            json={"nome": nome, "documento": documento, "telefone": telefone, "email": email, "endereco": endereco},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar o fornecedor"))
        return resp.json()

    def desativar_fornecedor(self, fornecedor_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/financeiro/fornecedores/{fornecedor_id}/desativar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível desativar o fornecedor"))
        return resp.json()

    # --- Financeiro: contas a pagar ---
    def listar_contas_pagar(self, status=None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/financeiro/contas-pagar", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as contas a pagar")
        return resp.json()

    def criar_conta_pagar(self, fornecedor_id, descricao, valor, vencimento_iso):
        resp = self._sessao.post(
            f"{API_BASE_URL}/financeiro/contas-pagar",
            json={"fornecedor_id": fornecedor_id, "descricao": descricao, "valor": valor, "vencimento": vencimento_iso},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível criar a conta"))
        return resp.json()

    def marcar_conta_pagar_paga(self, conta_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/financeiro/contas-pagar/{conta_id}/marcar-paga", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível marcar como paga"))
        return resp.json()

    # --- Financeiro: contas a receber (fora do faturamento de água) ---
    def listar_contas_receber(self, status=None):
        params = {"status": status} if status else {}
        resp = self._sessao.get(f"{API_BASE_URL}/financeiro/contas-receber", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as contas a receber")
        return resp.json()

    def criar_conta_receber(self, cliente_id, descricao, valor, vencimento_iso):
        resp = self._sessao.post(
            f"{API_BASE_URL}/financeiro/contas-receber",
            json={"cliente_id": cliente_id, "descricao": descricao, "valor": valor, "vencimento": vencimento_iso},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível criar a conta"))
        return resp.json()

    def marcar_conta_receber_paga(self, conta_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/financeiro/contas-receber/{conta_id}/marcar-paga", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível marcar como paga"))
        return resp.json()

    def resumo_financeiro(self):
        resp = self._sessao.get(f"{API_BASE_URL}/financeiro/resumo", headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar o resumo financeiro")
        return resp.json()

    # --- Cadastro de usuários com login (técnico/químico/operador) — só admin ---
    def cadastrar_usuario_login(self, nome, telefone, senha, tipo, localidade=None, email=None):
        """`senha` vazia = o servidor gera uma provisória e devolve em `senha_provisoria` (mostrada uma vez)."""
        corpo = {"nome": nome, "telefone": telefone or None, "email": email or None, "tipo": tipo, "localidade": localidade}
        if senha:
            corpo["senha"] = senha
        resp = self._sessao.post(f"{API_BASE_URL}/usuarios/", json=corpo, headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise ApiError(_texto_erro(resp, "Não foi possível cadastrar o usuário"))
        return resp.json()

    # --- Cadastro de clientes direto pelo painel ---
    def cadastrar_cliente(self, nome, documento, endereco, bairro, cidade, hidrometro, categoria, localidade):
        resp = self._sessao.post(
            f"{API_BASE_URL}/clientes/",
            json={"nome": nome, "documento": documento, "endereco": endereco, "bairro": bairro,
                  "cidade": cidade, "hidrometro": hidrometro, "categoria": categoria, "localidade": localidade},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível cadastrar o cliente"))
        return resp.json()

    def listar_clientes(self, status_cadastro=None):
        params = {"status_cadastro": status_cadastro} if status_cadastro else {}
        resp = self._sessao.get(f"{API_BASE_URL}/clientes/", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os clientes")
        return resp.json()

    def aprovar_cliente(self, cliente_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/clientes/{cliente_id}/aprovar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível aprovar o cliente"))
        return resp.json()

    def atualizar_cliente(self, cliente_id, nome, documento, endereco, bairro, cidade, hidrometro, categoria, localidade):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/clientes/{cliente_id}",
            json={"nome": nome, "documento": documento, "endereco": endereco, "bairro": bairro,
                  "cidade": cidade, "hidrometro": hidrometro, "categoria": categoria, "localidade": localidade},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível atualizar o cliente"))
        return resp.json()

    def desativar_cliente(self, cliente_id):
        resp = self._sessao.patch(
            f"{API_BASE_URL}/clientes/{cliente_id}/desativar", headers=self._headers(), timeout=10
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível desativar o cliente"))
        return resp.json()

    # --- Qualidade da água (Portaria GM/MS 888/2021) ---
    def _qualidade_get(self, caminho, params=None, erro="Não foi possível carregar os dados de qualidade", timeout=15):
        resp = self._sessao.get(
            f"{API_BASE_URL}/qualidade{caminho}", params=params, headers=self._headers(), timeout=timeout
        )
        if resp.status_code != 200:
            try:
                detalhe = resp.json().get("detail", erro)
            except Exception:
                detalhe = erro
            raise ApiError(detalhe if isinstance(detalhe, str) else erro)
        return resp

    def _qualidade_enviar(self, metodo, caminho, erro, **kwargs):
        resp = self._sessao.request(
            metodo, f"{API_BASE_URL}/qualidade{caminho}", headers=self._headers(), timeout=20, **kwargs
        )
        if resp.status_code != 200:
            try:
                detalhe = resp.json().get("detail", erro)
            except Exception:
                detalhe = erro
            raise ApiError(detalhe if isinstance(detalhe, str) else erro)
        return resp.json()

    def qualidade_conformidade(self, localidade, mes=None):
        params = {"localidade": localidade}
        if mes:
            params["mes"] = mes
        return self._qualidade_get("/conformidade", params).json()

    def qualidade_relatorio_pdf(self, localidade, mes=None):
        params = {"localidade": localidade}
        if mes:
            params["mes"] = mes
        return self._qualidade_get(
            "/relatorio-mensal-pdf", params, "Não foi possível gerar o relatório mensal", timeout=30
        ).content

    def qualidade_listar_amostras(self, localidade, mes=None, status=None):
        params = {"localidade": localidade}
        if mes:
            params["mes"] = mes
        if status:
            params["status"] = status
        return self._qualidade_get("/amostras", params).json()

    def qualidade_ver_resultado(self, amostra_id):
        return self._qualidade_get(f"/amostras/{amostra_id}/resultado", erro="Resultado ainda não lançado").json()

    def qualidade_listar_pontos(self, localidade, incluir_inativos=True):
        return self._qualidade_get(
            "/pontos", {"localidade": localidade, "incluir_inativos": str(bool(incluir_inativos)).lower()}
        ).json()

    def qualidade_criar_ponto(self, localidade, tipo, nome, descricao=None, estrategico=False):
        return self._qualidade_enviar(
            "POST", "/pontos", "Não foi possível cadastrar o ponto de coleta",
            json={"localidade": localidade, "tipo": tipo, "nome": nome,
                  "descricao": descricao or None, "estrategico": estrategico},
        )

    def qualidade_editar_ponto(self, ponto_id, **campos):
        return self._qualidade_enviar("PATCH", f"/pontos/{ponto_id}", "Não foi possível atualizar o ponto", json=campos)

    def qualidade_listar_regras(self, localidade):
        return self._qualidade_get("/regras", {"localidade": localidade}).json()

    def qualidade_editar_regra(self, regra_id, **campos):
        return self._qualidade_enviar("PATCH", f"/regras/{regra_id}", "Não foi possível atualizar a regra", json=campos)

    def qualidade_gerar_regras(self, localidade):
        return self._qualidade_enviar("POST", f"/regras/gerar/{localidade}", "Não foi possível gerar o plano")

    def qualidade_ver_config(self, localidade):
        return self._qualidade_get(f"/config/{localidade}", erro="Localidade ainda não configurada").json()

    def qualidade_salvar_config(self, localidade, populacao_abastecida, manancial, filtracao, numero_filtros):
        return self._qualidade_enviar(
            "PUT", f"/config/{localidade}", "Não foi possível salvar a configuração",
            json={"populacao_abastecida": populacao_abastecida, "manancial": manancial,
                  "filtracao": filtracao, "numero_filtros": numero_filtros},
        )

    def qualidade_listar_laudos(self, localidade):
        return self._qualidade_get("/laudos", {"localidade": localidade}).json()

    def qualidade_baixar_laudo(self, laudo_id):
        return self._qualidade_get(f"/laudos/{laudo_id}/arquivo", erro="Arquivo do laudo indisponível").content

    def qualidade_registrar_laudo(self, dados: dict, caminho_arquivo=None):
        dados = {k: v for k, v in dados.items() if v not in (None, "")}
        arquivos = None
        if caminho_arquivo:
            arquivos = {"arquivo": (os.path.basename(caminho_arquivo), open(caminho_arquivo, "rb"))}
        try:
            return self._qualidade_enviar(
                "POST", "/laudos", "Não foi possível registrar o laudo", data=dados, files=arquivos
            )
        finally:
            if arquivos:
                arquivos["arquivo"][1].close()
