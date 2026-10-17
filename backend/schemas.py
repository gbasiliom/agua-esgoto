from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


LOCALIDADES = ["sede", "penha_do_coco", "bananal", "agua_limpa"]


class EstoqueItemCreate(BaseModel):
    nome: str
    unidade_medida: str = "un"
    valor_unitario: float = 0
    estoque_minimo: float = 0


class EstoqueItemOut(BaseModel):
    id: int
    nome: str
    unidade_medida: str
    valor_unitario: float
    estoque_minimo: float
    ativo: bool
    saldo_total: float = 0
    valor_total: float = 0

    class Config:
        from_attributes = True


class MovimentacaoCreate(BaseModel):
    item_id: int
    tipo: str  # entrada, saida, transferencia, ajuste
    quantidade: float
    origem_tipo: Optional[str] = None  # sede, unidade, tecnico
    origem_valor: Optional[str] = None
    destino_tipo: Optional[str] = None
    destino_valor: Optional[str] = None
    observacao: Optional[str] = None


class SaldoOut(BaseModel):
    item_id: int
    nome_item: str
    unidade_medida: str
    localizacao_tipo: str
    localizacao_valor: str
    quantidade: float

    class Config:
        from_attributes = True


class MaterialUsadoInput(BaseModel):
    item_id: int
    quantidade: float


class SolicitacaoCreate(BaseModel):
    item_id: int
    quantidade: float
    chamado_id: Optional[int] = None
    observacao: Optional[str] = None


class SolicitacaoOut(BaseModel):
    id: int
    tecnico_id: int
    item_id: int
    quantidade: float
    chamado_id: Optional[int]
    status: str
    modo_aprovacao: Optional[str] = None
    fornecedor_id: Optional[int] = None
    valor_compra: Optional[float] = None
    nota_fiscal_foto: Optional[str] = None
    nota_fiscal_enviada_em: Optional[datetime] = None
    observacao: Optional[str]
    criado_em: datetime
    respondida_em: Optional[datetime]

    class Config:
        from_attributes = True


class ComprovanteCompraDireta(BaseModel):
    fornecedor_id: int
    valor_compra: float


class FuncionarioCreate(BaseModel):
    nome: str
    cargo: Optional[str] = None
    telefone: Optional[str] = None
    localidade: Optional[str] = None


class FuncionarioOut(BaseModel):
    id: int
    nome: str
    cargo: Optional[str]
    telefone: Optional[str]
    localidade: Optional[str]
    ativo: bool

    class Config:
        from_attributes = True


class LeituraOut(BaseModel):
    id: int
    cliente_id: int
    competencia: str
    valor_informado: float
    foto_caminho: str
    valor_ocr: Optional[float] = None
    ocr_confere: Optional[bool] = None
    status: str
    observacao: Optional[str] = None
    criado_em: datetime
    validado_em: Optional[datetime] = None

    class Config:
        from_attributes = True


class RejeitarLeitura(BaseModel):
    observacao: str


class TarifaFaixaCreate(BaseModel):
    consumo_min: float
    consumo_max: Optional[float] = None
    valor_m3: float
    percentual_esgoto: float = 80


class TarifaFaixaOut(BaseModel):
    id: int
    consumo_min: float
    consumo_max: Optional[float]
    valor_m3: float
    percentual_esgoto: float
    ativo: bool

    class Config:
        from_attributes = True


class FaturaOut(BaseModel):
    id: int
    cliente_id: int
    leitura_id: Optional[int]
    competencia: str
    consumo_m3: float
    valor_agua: float
    valor_esgoto: float
    valor_total: float
    vencimento: datetime
    status: str
    pago_em: Optional[datetime] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class EmpresaConfigUpdate(BaseModel):
    nome_fantasia: Optional[str] = None
    razao_social: Optional[str] = None
    cnpj: Optional[str] = None
    endereco: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None


class EmpresaConfigOut(BaseModel):
    id: int
    nome_fantasia: Optional[str]
    razao_social: Optional[str]
    cnpj: Optional[str]
    endereco: Optional[str]
    telefone: Optional[str]
    email: Optional[str]

    class Config:
        from_attributes = True


class FornecedorCreate(BaseModel):
    nome: str
    documento: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    endereco: Optional[str] = None


class FornecedorOut(BaseModel):
    id: int
    nome: str
    documento: Optional[str]
    telefone: Optional[str]
    email: Optional[str]
    endereco: Optional[str]
    ativo: bool

    class Config:
        from_attributes = True


class ContaPagarCreate(BaseModel):
    fornecedor_id: Optional[int] = None
    descricao: str
    valor: float
    vencimento: datetime


class ContaPagarOut(BaseModel):
    id: int
    fornecedor_id: Optional[int]
    descricao: str
    valor: float
    vencimento: datetime
    status: str
    pago_em: Optional[datetime] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class ContaReceberCreate(BaseModel):
    cliente_id: Optional[int] = None
    descricao: str
    valor: float
    vencimento: datetime


class ContaReceberOut(BaseModel):
    id: int
    cliente_id: Optional[int]
    descricao: str
    valor: float
    vencimento: datetime
    status: str
    pago_em: Optional[datetime] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class ManutencaoEtaCreate(BaseModel):
    tipo: str
    descricao: str


class ManutencaoEtaOut(BaseModel):
    id: int
    tecnico_id: int
    localidade: str
    tipo: str
    descricao: str
    criado_em: datetime

    class Config:
        from_attributes = True


class LicitacaoCreate(BaseModel):
    numero_processo: Optional[str] = None
    modalidade: str
    objeto: str
    valor_estimado: Optional[float] = None
    data_abertura: datetime
    observacoes: Optional[str] = None


class LicitacaoStatusUpdate(BaseModel):
    status: str
    vencedor: Optional[str] = None
    fornecedor_id: Optional[int] = None
    valor_final: Optional[float] = None


class LicitacaoOut(BaseModel):
    id: int
    numero_processo: Optional[str]
    modalidade: str
    objeto: str
    valor_estimado: Optional[float]
    valor_final: Optional[float]
    data_abertura: datetime
    vencedor: Optional[str]
    fornecedor_id: Optional[int]
    status: str
    observacoes: Optional[str]
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


class AnaliseEtaCreate(BaseModel):
    coletado_em: datetime
    localidade: Optional[str] = None  # só o químico informa (o técnico usa a localidade do próprio cadastro)
    vazao_ls: Optional[float] = None
    turbidez_bruta: Optional[float] = None
    turbidez_filtrada: Optional[float] = None
    turbidez_tratada: Optional[float] = None
    ph_bruta: Optional[float] = None
    ph_tratada: Optional[float] = None
    sulfato_dosagem: Optional[float] = None
    cloro_dosagem: Optional[float] = None
    cloro_residual: Optional[float] = None
    cor_bruta: Optional[float] = None
    cor_tratada: Optional[float] = None
    observacoes: Optional[str] = None


class AnaliseEtaOut(BaseModel):
    id: int
    tecnico_id: int
    localidade: str
    coletado_em: datetime
    vazao_ls: Optional[float] = None
    turbidez_bruta: Optional[float] = None
    turbidez_filtrada: Optional[float] = None
    turbidez_tratada: Optional[float] = None
    ph_bruta: Optional[float] = None
    ph_tratada: Optional[float] = None
    sulfato_dosagem: Optional[float] = None
    cloro_dosagem: Optional[float] = None
    cloro_residual: Optional[float] = None
    cor_bruta: Optional[float] = None
    cor_tratada: Optional[float] = None
    observacoes: Optional[str] = None
    conforme: Optional[bool] = None
    alertas: Optional[str] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class LavagemFiltroCreate(BaseModel):
    hora: datetime
    localidade: Optional[str] = None  # só o químico informa
    tempo_gasto_min: Optional[float] = None
    volume_gasto: Optional[float] = None


class LavagemFiltroOut(BaseModel):
    id: int
    tecnico_id: int
    localidade: str
    hora: datetime
    tempo_gasto_min: Optional[float]
    volume_gasto: Optional[float]
    criado_em: datetime

    class Config:
        from_attributes = True


class UsuarioCreate(BaseModel):
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    senha: str
    tipo: str  # admin, operador, tecnico, cliente
    localidade: Optional[str] = None  # sede, penha_do_coco, bananal, agua_limpa (pro técnico)


class UsuarioRegistro(BaseModel):
    """Cadastro PÚBLICO (/auth/registrar): sempre cria um cliente. O tipo de
    usuário nunca vem do cliente da API — senão qualquer pessoa se cadastrava
    como admin. O e-mail é obrigatório: é por ele que o cliente recupera a senha."""
    nome: str
    email: str
    telefone: Optional[str] = None
    senha: str
    localidade: Optional[str] = None


TIPOS_USUARIO_INTERNO = ["admin", "operador", "tecnico", "quimico", "operador_eta"]


class UsuarioInternoCreate(BaseModel):
    """Cadastro de usuário da equipe (/usuarios/) — só admin pode chamar."""
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    senha: Optional[str] = None  # vazio = o servidor gera uma senha provisória e devolve uma única vez
    tipo: str  # admin, operador, tecnico, quimico, operador_eta
    localidade: Optional[str] = None


class UsuarioLogin(BaseModel):
    identificador: str  # email ou telefone
    senha: str


class Token(BaseModel):
    """Resposta de login. Normalmente traz access_token + refresh_token. Casos especiais:
    - requer_2fa=True: (admin) falta digitar o código enviado por e-mail; use `desafio` em /auth/verificar-2fa.
    - trocar_senha=True: senha provisória/fraca — o app deve mandar direto pra tela de troca de senha."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    tipo_usuario: Optional[str] = None
    trocar_senha: bool = False
    requer_2fa: bool = False
    desafio: Optional[str] = None
    email_mascarado: Optional[str] = None


class EsqueciSenha(BaseModel):
    identificador: str  # e-mail ou telefone


class RedefinirSenha(BaseModel):
    identificador: str
    codigo: str
    nova_senha: str


class TrocarSenha(BaseModel):
    senha_atual: str
    nova_senha: str


class RefreshIn(BaseModel):
    refresh_token: str


class Verificar2FA(BaseModel):
    desafio: str
    codigo: str


class Mensagem(BaseModel):
    detail: str


class ResetSenhaOut(BaseModel):
    senha_provisoria: str
    detail: str


class AuditoriaOut(BaseModel):
    id: int
    quando: datetime
    usuario_id: Optional[int] = None
    identificador: Optional[str] = None
    acao: str
    detalhe: Optional[str] = None
    ip: Optional[str] = None

    class Config:
        from_attributes = True


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: Optional[str]
    telefone: Optional[str]
    tipo: str
    localidade: Optional[str] = None

    class Config:
        from_attributes = True


class UsuarioCriadoOut(UsuarioOut):
    senha_provisoria: Optional[str] = None  # só vem quando o servidor gerou a senha


class UsuarioListaOut(UsuarioOut):
    """Linha da tela de usuários do painel (admin): inclui estado de segurança da conta."""
    trocar_senha: bool = False
    bloqueado: bool = False


class ClienteOut(BaseModel):
    id: int
    nome: str
    documento: Optional[str]
    endereco: Optional[str]
    bairro: Optional[str]
    cidade: Optional[str]
    hidrometro: Optional[str]
    categoria: Optional[str]
    localidade: Optional[str] = None
    status_cadastro: Optional[str] = "aprovado"
    ativo: bool

    class Config:
        from_attributes = True


LOCALIDADES_SEM_HIDROMETRO = ("penha_do_coco", "bananal", "agua_limpa")


def localidade_tem_hidrometro(localidade) -> bool:
    """Só a sede tem hidrômetro (leitura mensal e fatura). Penha do Coco, Bananal e Água Limpa não."""
    return localidade not in LOCALIDADES_SEM_HIDROMETRO


class ClienteAutoCadastro(BaseModel):
    nome: str
    documento: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    hidrometro: Optional[str] = None
    categoria: str = "residencial"
    localidade: Optional[str] = None  # sede, penha_do_coco, bananal, agua_limpa


class ChamadoCreateCliente(BaseModel):
    tipo: str
    descricao_problema: str
    prioridade: str = "normal"
    origem: str = "app"


class ChamadoCreate(BaseModel):
    cliente_id: int
    tipo: str
    descricao_problema: str
    prioridade: str = "normal"
    origem: str = "app"


class ChamadoAtribuir(BaseModel):
    tecnico_id: int


class ChamadoFechar(BaseModel):
    descricao_solucao: str


class ChamadoOut(BaseModel):
    id: int
    cliente_id: int
    tipo: str
    local_atendimento: Optional[str] = None
    descricao_problema: str
    prioridade: str
    origem: str
    status: str
    tecnico_id: Optional[int]
    descricao_solucao: Optional[str]
    checklist: Optional[str] = None
    materiais_utilizados: Optional[str] = None
    abertura: datetime
    atribuicao: Optional[datetime]
    conclusao: Optional[datetime]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Qualidade da água (módulo do químico)
# ---------------------------------------------------------------------------

class ConfigSistemaAguaIn(BaseModel):
    populacao_abastecida: int
    manancial: str = "superficial"  # superficial, subterraneo
    filtracao: Optional[str] = "lenta"  # lenta, rapida
    numero_filtros: int = 1


class ConfigSistemaAguaOut(ConfigSistemaAguaIn):
    id: int
    localidade: str

    class Config:
        from_attributes = True


class PontoColetaCreate(BaseModel):
    localidade: str
    tipo: str  # captacao, saida_eta, reservatorio, rede
    nome: str
    descricao: Optional[str] = None
    estrategico: bool = False


class PontoColetaUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    estrategico: Optional[bool] = None
    ativo: Optional[bool] = None


class PontoColetaOut(BaseModel):
    id: int
    localidade: str
    tipo: str
    nome: str
    descricao: Optional[str] = None
    estrategico: bool
    ativo: bool

    class Config:
        from_attributes = True


class RegraAmostragemUpdate(BaseModel):
    quantidade: Optional[int] = None
    periodo: Optional[str] = None
    observacao: Optional[str] = None
    ativo: Optional[bool] = None


class RegraAmostragemOut(BaseModel):
    id: int
    localidade: str
    grupo: str
    ponto_tipo: str
    quantidade: int
    periodo: str
    norma: Optional[str] = None
    observacao: Optional[str] = None
    manual: bool
    ativo: bool

    class Config:
        from_attributes = True


class GerarRegrasOut(BaseModel):
    regras: List[RegraAmostragemOut]
    avisos: List[str]


class AmostraCreate(BaseModel):
    ponto_id: int
    grupo: str
    coletado_em: Optional[datetime] = None  # vazio = agora
    data_prevista: Optional[date] = None  # se informada sem coletado_em, cria como pendente
    cloro_residual: Optional[float] = None
    cor_aparente: Optional[float] = None
    turbidez: Optional[float] = None
    ph: Optional[float] = None
    observacoes: Optional[str] = None


class AmostraColeta(BaseModel):
    """Registra a coleta de uma amostra pendente (ex.: uma recoleta)."""
    coletado_em: Optional[datetime] = None
    cloro_residual: Optional[float] = None
    cor_aparente: Optional[float] = None
    turbidez: Optional[float] = None
    ph: Optional[float] = None
    observacoes: Optional[str] = None


class AmostraOut(BaseModel):
    id: int
    codigo: Optional[str] = None
    localidade: str
    ponto_id: int
    grupo: str
    status: str
    data_prevista: Optional[date] = None
    coletado_em: Optional[datetime] = None
    coletor_id: Optional[int] = None
    cloro_residual: Optional[float] = None
    cor_aparente: Optional[float] = None
    turbidez: Optional[float] = None
    ph: Optional[float] = None
    recoleta_de_id: Optional[int] = None
    posicao_recoleta: Optional[str] = None
    observacoes: Optional[str] = None

    class Config:
        from_attributes = True


class ResultadoAnaliseCreate(BaseModel):
    metodo: Optional[str] = None
    lote_kit: Optional[str] = None
    validade_kit: Optional[date] = None
    incubacao_inicio: Optional[datetime] = None
    incubacao_fim: Optional[datetime] = None
    incubacao_temp_c: Optional[float] = None
    coliformes_totais_presente: Optional[bool] = None
    e_coli_presente: Optional[bool] = None
    coliformes_totais_nmp: Optional[float] = None
    e_coli_nmp: Optional[float] = None
    cianobacterias_cel_ml: Optional[float] = None
    observacoes: Optional[str] = None


class ResultadoAnaliseOut(BaseModel):
    id: int
    amostra_id: int
    analista_id: int
    metodo: Optional[str] = None
    lote_kit: Optional[str] = None
    validade_kit: Optional[date] = None
    incubacao_inicio: Optional[datetime] = None
    incubacao_fim: Optional[datetime] = None
    incubacao_temp_c: Optional[float] = None
    coliformes_totais_presente: Optional[bool] = None
    e_coli_presente: Optional[bool] = None
    coliformes_totais_nmp: Optional[float] = None
    e_coli_nmp: Optional[float] = None
    cianobacterias_cel_ml: Optional[float] = None
    conforme: Optional[bool] = None
    alertas: Optional[str] = None
    observacoes: Optional[str] = None

    class Config:
        from_attributes = True


class ResultadoComRecoletas(BaseModel):
    resultado: ResultadoAnaliseOut
    alertas: List[str]
    recoletas_criadas: List[AmostraOut]


class LaudoExternoOut(BaseModel):
    id: int
    localidade: str
    ponto_id: Optional[int] = None
    amostra_id: Optional[int] = None
    tipo: str
    laboratorio: str
    numero_laudo: Optional[str] = None
    data_coleta: date
    data_emissao: Optional[date] = None
    parametros_resumo: Optional[str] = None
    conforme: Optional[bool] = None
    tem_arquivo: bool = False
    observacoes: Optional[str] = None

    class Config:
        from_attributes = True
