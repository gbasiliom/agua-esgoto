import json
import sessao_http as requests
from api_base import ApiBase, ApiError, ErroConexao, ErroSessao  # noqa: F401

TIPOS_ACEITOS = ("tecnico",)


class ApiClient(ApiBase):
    """Fala com a API FastAPI. Guarda o token e os dados do técnico logado.
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

    def meus_dados(self):
        try:
            resp = requests.get(f"{self.url}/usuarios/eu", headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Não foi possível conectar ao servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível identificar o usuário logado")
        dados = resp.json()
        self.usuario_id = dados["id"]
        self.nome = dados["nome"]
        return dados

    def listar_meus_chamados(self, status: str = None):
        params = {"tecnico_id": self.usuario_id}
        if status:
            params["status"] = status
        try:
            resp = requests.get(f"{self.url}/chamados/", params=params, headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar seus chamados")
        return resp.json()

    def iniciar_atendimento(self, chamado_id: int):
        try:
            resp = requests.patch(
                f"{self.url}/chamados/{chamado_id}/iniciar", headers=self._headers(), timeout=10
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível iniciar o atendimento"))
        return resp.json()

    def fechar_chamado(self, chamado_id: int, descricao_solucao: str, caminhos_fotos: list,
                        checklist: dict = None, materiais: str = None, itens_estoque_usados: list = None):
        arquivos = [
            ("fotos", (f"foto{i}.jpg", open(caminho, "rb"), "image/jpeg"))
            for i, caminho in enumerate(caminhos_fotos)
        ]
        dados_form = {"descricao_solucao": descricao_solucao}
        if checklist is not None:
            dados_form["checklist"] = json.dumps(checklist, ensure_ascii=False)
        if materiais is not None:
            dados_form["materiais_utilizados"] = materiais
        if itens_estoque_usados:
            dados_form["itens_estoque_usados"] = json.dumps(itens_estoque_usados, ensure_ascii=False)

        try:
            resp = requests.post(
                f"{self.url}/chamados/{chamado_id}/fechar",
                data=dados_form,
                files=arquivos,
                headers=self._headers(),
                timeout=30,
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        finally:
            for _, (_, f, _) in arquivos:
                f.close()

        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível fechar o chamado"))
        return resp.json()

    def meu_estoque(self):
        """
        O que o técnico vê como 'meu estoque': soma do que é só dele +
        o que é compartilhado da unidade dele (sede→unidade já basta,
        não precisa do passo extra unidade→técnico).
        """
        try:
            resp = requests.get(f"{self.url}/estoque/meu-estoque-completo", headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar seu estoque")
        return resp.json()

    def catalogo_estoque(self):
        """Lista TODOS os itens cadastrados no estoque (catálogo geral, pra solicitar)."""
        try:
            resp = requests.get(f"{self.url}/estoque/itens", headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar o catálogo de materiais")
        return resp.json()

    def solicitar_material(self, item_id: int, quantidade: float, chamado_id: int = None):
        try:
            resp = requests.post(
                f"{self.url}/estoque/solicitacoes",
                json={"item_id": item_id, "quantidade": quantidade, "chamado_id": chamado_id},
                headers=self._headers(), timeout=10,
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível enviar a solicitação"))
        return resp.json()

    def registrar_manutencao_eta(self, tipo: str, descricao: str):
        try:
            resp = requests.post(
                f"{self.url}/estoque/manutencao-eta",
                json={"tipo": tipo, "descricao": descricao},
                headers=self._headers(), timeout=10,
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível registrar a manutenção"))
        return resp.json()

    def minhas_manutencoes_eta(self):
        try:
            resp = requests.get(
                f"{self.url}/estoque/manutencao-eta", params={"minhas": True},
                headers=self._headers(), timeout=10,
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar o histórico de manutenções")
        return resp.json()

    def registrar_analise_eta(self, dados: dict):
        try:
            resp = requests.post(f"{self.url}/analise-eta/", json=dados, headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível registrar a análise"))
        return resp.json()

    def minhas_analises_eta(self):
        try:
            resp = requests.get(f"{self.url}/analise-eta/minhas", headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar suas análises")
        return resp.json()

    def registrar_lavagem_filtro(self, hora_iso: str, tempo_gasto_min: float, volume_gasto: float):
        try:
            resp = requests.post(
                f"{self.url}/analise-eta/lavagem-filtro",
                json={"hora": hora_iso, "tempo_gasto_min": tempo_gasto_min, "volume_gasto": volume_gasto},
                headers=self._headers(), timeout=10,
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível registrar a lavagem"))
        return resp.json()

    def minhas_solicitacoes(self):
        try:
            resp = requests.get(
                f"{self.url}/estoque/solicitacoes", params={"minhas": True},
                headers=self._headers(), timeout=10,
            )
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar suas solicitações")
        return resp.json()

    def listar_fornecedores(self):
        try:
            resp = requests.get(f"{self.url}/financeiro/fornecedores", headers=self._headers(), timeout=10)
        except requests.exceptions.RequestException:
            raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError("Não foi possível carregar os fornecedores")
        return resp.json()

    def enviar_comprovante_compra(self, solicitacao_id: int, fornecedor_id: int, valor_compra: float, caminho_foto: str):
        with open(caminho_foto, "rb") as f:
            arquivos = {"foto": ("nota_fiscal.jpg", f, "image/jpeg")}
            try:
                resp = requests.post(
                    f"{self.url}/estoque/solicitacoes/{solicitacao_id}/comprovante",
                    data={"fornecedor_id": fornecedor_id, "valor_compra": valor_compra},
                    files=arquivos, headers=self._headers(), timeout=30,
                )
            except requests.exceptions.RequestException:
                raise ErroConexao("Sem conexão com o servidor.")
        if resp.status_code != 200:
            raise ApiError(resp.json().get("detail", "Não foi possível enviar o comprovante"))
        return resp.json()
