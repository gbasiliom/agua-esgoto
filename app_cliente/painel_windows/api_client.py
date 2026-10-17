import requests
from config import API_BASE_URL


class ApiError(Exception):
    pass


class ApiClient:
    """Fala com a API FastAPI. Guarda o token depois do login."""

    def __init__(self):
        self.token = None
        self.tipo_usuario = None
        # Sessão reaproveitada entre chamadas — evita reabrir conexão TCP
        # toda vez (isso sozinho já deixa cada chamada bem mais rápida).
        self._sessao = requests.Session()

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, identificador: str, senha: str):
        resp = self._sessao.post(
            f"{API_BASE_URL}/auth/login",
            json={"identificador": identificador, "senha": senha},
            timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Falha no login"))
        dados = resp.json()
        self.token = dados["access_token"]
        self.tipo_usuario = dados["tipo_usuario"]
        return dados

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

    def listar_analises_eta(self, apenas_nao_conformes=False):
        params = {"apenas_nao_conformes": apenas_nao_conformes} if apenas_nao_conformes else {}
        resp = self._sessao.get(f"{API_BASE_URL}/analise-eta/", params=params, headers=self._headers(), timeout=10)
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar as análises da ETA")
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
    def cadastrar_usuario_login(self, nome, telefone, senha, tipo, localidade=None):
        resp = self._sessao.post(
            f"{API_BASE_URL}/usuarios/",
            json={"nome": nome, "telefone": telefone, "senha": senha, "tipo": tipo, "localidade": localidade},
            headers=self._headers(), timeout=10,
        )
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível cadastrar o usuário"))
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
