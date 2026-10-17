from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, ForeignKey, Text, text
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator
from database import Base
from criptografia import criptografar, descriptografar


class TextoCriptografado(TypeDecorator):
    """
    Coluna que criptografa (AES-256-GCM) automaticamente ao salvar e
    descriptografa ao ler — nenhum outro lugar do código precisa saber
    que o dado está cifrado no banco.
    """
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return criptografar(value)

    def process_result_value(self, value, dialect):
        return descriptografar(value)


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(150), unique=True)
    telefone = Column(String(20), unique=True)
    senha_hash = Column(String(255), nullable=False)
    tipo = Column(String(20), nullable=False)  # admin, operador, tecnico, quimico, operador_eta, cliente
    localidade = Column(String(30))  # sede, penha_do_coco, bananal, agua_limpa — unidade do técnico
    criado_em = Column(DateTime, server_default=func.now())
    # --- segurança de conta ---
    token_versao = Column(Integer, nullable=False, default=0, server_default=text("0"))  # sobe a cada troca de senha/logout geral: invalida tokens antigos
    trocar_senha = Column(Boolean, nullable=False, default=False, server_default=text("0"))  # True = só consegue trocar a senha antes de usar o sistema
    falhas_login = Column(Integer, nullable=False, default=0, server_default=text("0"))
    bloqueado_ate = Column(DateTime)  # horário (UTC, sem fuso) até quando a conta fica travada por excesso de tentativas
    senha_alterada_em = Column(DateTime)
    ultimo_login_em = Column(DateTime)


class CodigoSeguranca(Base):
    """Códigos de 6 dígitos enviados por e-mail (recuperação de senha e 2ª etapa do admin).
    Só o HMAC do código fica salvo — nunca o código em si."""
    __tablename__ = "codigos_seguranca"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    finalidade = Column(String(20), nullable=False)  # recuperacao, 2fa
    codigo_hmac = Column(String(64), nullable=False)
    criado_em = Column(DateTime, nullable=False)
    expira_em = Column(DateTime, nullable=False)
    tentativas = Column(Integer, nullable=False, default=0)
    usado = Column(Boolean, nullable=False, default=False)


class SessaoRefresh(Base):
    """Uma linha por aparelho/login. O token de renovação é guardado só como hash e é trocado
    a cada uso; se um token já usado aparecer de novo (roubo), todas as sessões da conta caem."""
    __tablename__ = "sessoes_refresh"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    criado_em = Column(DateTime, nullable=False)
    expira_em = Column(DateTime, nullable=False)
    revogado = Column(Boolean, nullable=False, default=False)
    substituido_por = Column(Integer)
    ip = Column(String(64))
    aparelho = Column(String(200))


class Auditoria(Base):
    """Trilha de quem fez o quê em segurança: logins, falhas, bloqueios, trocas e resets de senha."""
    __tablename__ = "auditoria"
    id = Column(Integer, primary_key=True)
    quando = Column(DateTime, nullable=False)
    usuario_id = Column(Integer, index=True)
    identificador = Column(String(150))
    acao = Column(String(40), nullable=False, index=True)
    detalhe = Column(String(300))
    ip = Column(String(64))


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    nome = Column(String(150), nullable=False)
    documento = Column(TextoCriptografado(255))  # CPF/CNPJ — criptografado no banco (AES-256)
    endereco = Column(String(255))
    bairro = Column(String(100))
    cidade = Column(String(100))
    hidrometro = Column(String(50))
    categoria = Column(String(20))
    localidade = Column(String(30))  # sede, penha_do_coco, bananal, agua_limpa
    status_cadastro = Column(String(15), default="aprovado")  # pendente, aprovado
    ativo = Column(Boolean, default=True)


class Chamado(Base):
    __tablename__ = "chamados"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    tipo = Column(String(20), nullable=False)
    local_atendimento = Column(String(30))  # sede, penha_do_coco, bananal, agua_limpa
    descricao_problema = Column(Text, nullable=False)
    prioridade = Column(String(10), default="normal")
    origem = Column(String(10), nullable=False)  # app, whatsapp, telefone
    status = Column(String(20), default="aberto")
    tecnico_id = Column(Integer, ForeignKey("usuarios.id"))
    descricao_solucao = Column(Text)
    checklist = Column(Text)  # JSON: situação encontrada (itens marcados)
    materiais_utilizados = Column(Text)  # JSON: lista de materiais gastos no atendimento
    abertura = Column(DateTime, server_default=func.now())
    atribuicao = Column(DateTime)
    conclusao = Column(DateTime)


class ChamadoFoto(Base):
    __tablename__ = "chamado_fotos"
    id = Column(Integer, primary_key=True)
    chamado_id = Column(Integer, ForeignKey("chamados.id"), nullable=False)
    caminho_arquivo = Column(String(255), nullable=False)
    tipo = Column(String(10))  # abertura, fechamento
    enviado_em = Column(DateTime, server_default=func.now())


class EstoqueItem(Base):
    __tablename__ = "estoque_itens"
    id = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    unidade_medida = Column(String(10), default="un")  # un, m, kg, l...
    valor_unitario = Column(Numeric(10, 2), default=0)
    estoque_minimo = Column(Numeric(10, 2), default=0)
    ativo = Column(Boolean, default=True)


class EstoqueSaldo(Base):
    """Saldo atual de um item numa localização (sede, uma unidade, ou um técnico)."""
    __tablename__ = "estoque_saldo"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("estoque_itens.id"), nullable=False)
    localizacao_tipo = Column(String(10), nullable=False)  # sede, unidade, tecnico
    localizacao_valor = Column(String(50), nullable=False)  # nome da unidade ou id do técnico (string)
    quantidade = Column(Numeric(10, 2), default=0)


class EstoqueMovimentacao(Base):
    """Livro-razão: toda entrada/saída/transferência/baixa fica registrada aqui, rastreável."""
    __tablename__ = "estoque_movimentacoes"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("estoque_itens.id"), nullable=False)
    tipo = Column(String(15), nullable=False)  # entrada, saida, transferencia, ajuste, baixa_os
    quantidade = Column(Numeric(10, 2), nullable=False)
    origem_tipo = Column(String(10))  # sede, unidade, tecnico (None = entrada externa/compra)
    origem_valor = Column(String(50))
    destino_tipo = Column(String(10))  # sede, unidade, tecnico (None = saída final/consumo)
    destino_valor = Column(String(50))
    chamado_id = Column(Integer, ForeignKey("chamados.id"))  # preenchido só em baixa_os
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))  # quem registrou
    observacao = Column(Text)
    criado_em = Column(DateTime, server_default=func.now())


class ChamadoMaterialUsado(Base):
    """Vínculo estruturado entre um chamado e os itens de estoque consumidos nele."""
    __tablename__ = "chamado_materiais_usados"
    id = Column(Integer, primary_key=True)
    chamado_id = Column(Integer, ForeignKey("chamados.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("estoque_itens.id"), nullable=False)
    quantidade = Column(Numeric(10, 2), nullable=False)


class LeituraHidrometro(Base):
    """Leitura mensal do hidrômetro enviada pelo cliente (número + foto)."""
    __tablename__ = "leituras_hidrometro"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    competencia = Column(String(7), nullable=False)  # "2026-07"
    valor_informado = Column(Numeric(10, 2), nullable=False)
    foto_caminho = Column(String(255), nullable=False)
    foto_hash = Column(String(64), nullable=False, index=True)  # SHA-256 — detecta foto reciclada
    valor_ocr = Column(Numeric(10, 2))  # melhor esforço, pode ficar vazio se Tesseract não estiver instalado
    ocr_confere = Column(Boolean)  # None = não foi possível checar; True/False = checou e bateu ou não
    status = Column(String(15), default="pendente")  # pendente, aprovada, rejeitada
    observacao = Column(Text)
    criado_em = Column(DateTime, server_default=func.now())
    validado_em = Column(DateTime)
    validado_por = Column(Integer, ForeignKey("usuarios.id"))


class TarifaFaixa(Base):
    """Faixa de tarifação progressiva (tipo imposto de renda): cada faixa de
    consumo tem seu próprio valor por m³. Editável pelo painel — os valores
    aqui são só ponto de partida pra testes."""
    __tablename__ = "tarifa_faixas"
    id = Column(Integer, primary_key=True)
    consumo_min = Column(Numeric(10, 2), nullable=False)  # ex: 0
    consumo_max = Column(Numeric(10, 2))  # None = sem limite superior (última faixa)
    valor_m3 = Column(Numeric(10, 2), nullable=False)
    percentual_esgoto = Column(Numeric(5, 2), default=80)  # % do valor da água cobrado como esgoto
    ativo = Column(Boolean, default=True)


class Fatura(Base):
    """Conta de água gerada automaticamente quando uma leitura é aprovada."""
    __tablename__ = "faturas"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    leitura_id = Column(Integer, ForeignKey("leituras_hidrometro.id"))
    competencia = Column(String(7), nullable=False)
    consumo_m3 = Column(Numeric(10, 2), nullable=False)
    valor_agua = Column(Numeric(10, 2), nullable=False)
    valor_esgoto = Column(Numeric(10, 2), nullable=False)
    valor_total = Column(Numeric(10, 2), nullable=False)
    vencimento = Column(DateTime, nullable=False)
    status = Column(String(15), default="aberto")  # aberto, pago, vencido
    pago_em = Column(DateTime)
    criado_em = Column(DateTime, server_default=func.now())


class SolicitacaoMaterial(Base):
    """Técnico pede material (pra reparo ou insumo de ETA); admin/operador aprova ou nega."""
    __tablename__ = "solicitacoes_material"
    id = Column(Integer, primary_key=True)
    tecnico_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("estoque_itens.id"), nullable=False)
    quantidade = Column(Numeric(10, 2), nullable=False)
    chamado_id = Column(Integer, ForeignKey("chamados.id"))  # opcional: vinculada a um chamado específico
    status = Column(String(15), default="pendente")  # pendente, aprovada, negada
    modo_aprovacao = Column(String(15))  # estoque (transferência normal) ou compra_direta
    fornecedor_id = Column(Integer, ForeignKey("fornecedores.id"))  # preenchido quando o técnico envia o comprovante
    valor_compra = Column(Numeric(10, 2))  # valor gasto, informado junto com o comprovante
    nota_fiscal_foto = Column(String(255))  # caminho da foto da nota fiscal
    nota_fiscal_enviada_em = Column(DateTime)
    observacao = Column(Text)
    criado_em = Column(DateTime, server_default=func.now())
    respondida_em = Column(DateTime)


class Funcionario(Base):
    """Cadastro de funcionários — inclui quem não necessariamente loga no sistema
    (ex: quem instala hidrômetro), separado dos usuários com login."""
    __tablename__ = "funcionarios"
    id = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    cargo = Column(String(100))
    telefone = Column(String(20))
    localidade = Column(String(30))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))  # opcional: se ele também tem login
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class EmpresaConfig(Base):
    """Dados da empresa/prefeitura que está usando o sistema — cadastro único
    (sempre id=1), pra fins fiscais e pra aparecer o nome dela no sistema."""
    __tablename__ = "empresa_config"
    id = Column(Integer, primary_key=True)
    nome_fantasia = Column(String(150))
    razao_social = Column(String(150))
    cnpj = Column(TextoCriptografado(255))  # dado fiscal sensível — criptografado, igual o CPF do cliente
    endereco = Column(String(255))
    telefone = Column(String(20))
    email = Column(String(150))
    atualizado_em = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Fornecedor(Base):
    __tablename__ = "fornecedores"
    id = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    documento = Column(TextoCriptografado(255))  # CNPJ/CPF — criptografado
    telefone = Column(String(20))
    email = Column(String(150))
    endereco = Column(String(255))
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class ContaPagar(Base):
    __tablename__ = "contas_pagar"
    id = Column(Integer, primary_key=True)
    fornecedor_id = Column(Integer, ForeignKey("fornecedores.id"))
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    vencimento = Column(DateTime, nullable=False)
    status = Column(String(15), default="aberto")  # aberto, pago, vencido
    pago_em = Column(DateTime)
    criado_em = Column(DateTime, server_default=func.now())


class ContaReceberOutras(Base):
    """Contas a receber que NÃO vieram de leitura de hidrômetro (ex: taxa de
    religação, multa) — as faturas de água/esgoto já são contas a receber
    por si, geradas automaticamente; isso aqui complementa."""
    __tablename__ = "contas_receber_outras"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    descricao = Column(String(255), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    vencimento = Column(DateTime, nullable=False)
    status = Column(String(15), default="aberto")  # aberto, pago, vencido
    pago_em = Column(DateTime)
    criado_em = Column(DateTime, server_default=func.now())


class ManutencaoEta(Base):
    """Registro de manutenção na Estação de Tratamento de Água — limpeza de
    tanque, verificação de cloro, etc. Cada técnico cuida da ETA da própria
    localidade."""
    __tablename__ = "manutencoes_eta"
    id = Column(Integer, primary_key=True)
    tecnico_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    localidade = Column(String(30), nullable=False)
    tipo = Column(String(30), nullable=False)  # limpeza_tanque, verificacao_cloro, manutencao_bomba, outro
    descricao = Column(Text, nullable=False)
    criado_em = Column(DateTime, server_default=func.now())


class Licitacao(Base):
    __tablename__ = "licitacoes"
    id = Column(Integer, primary_key=True)
    numero_processo = Column(String(50))
    modalidade = Column(String(50), nullable=False)  # pregao_eletronico, pregao_presencial, concorrencia, tomada_precos, convite, dispensa, inexigibilidade
    objeto = Column(Text, nullable=False)
    valor_estimado = Column(Numeric(12, 2))
    valor_final = Column(Numeric(12, 2))
    data_abertura = Column(DateTime, nullable=False)
    vencedor = Column(String(150))
    fornecedor_id = Column(Integer, ForeignKey("fornecedores.id"))  # opcional, se o vencedor já é um fornecedor cadastrado
    status = Column(String(15), default="rascunho")  # rascunho, publicada, em_analise, homologada, fracassada, cancelada
    observacoes = Column(Text)
    criado_em = Column(DateTime, server_default=func.now())
    atualizado_em = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AnaliseEta(Base):
    """Relatório diário de análises da ETA (vazão, turbidez, pH, cloro, cor
    etc) — digitaliza o boletim de papel do SAAE. Validado automaticamente
    contra os limites da Portaria GM/MS nº 888/2021."""
    __tablename__ = "analises_eta"
    id = Column(Integer, primary_key=True)
    tecnico_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    localidade = Column(String(30), nullable=False)
    coletado_em = Column(DateTime, nullable=False)  # horário da coleta (o técnico escolhe: 06:00, 08:00 etc)

    vazao_ls = Column(Numeric(10, 2))

    turbidez_bruta = Column(Numeric(10, 2))
    turbidez_filtrada = Column(Numeric(10, 2))
    turbidez_tratada = Column(Numeric(10, 2))

    ph_bruta = Column(Numeric(10, 2))
    ph_tratada = Column(Numeric(10, 2))

    sulfato_dosagem = Column(Numeric(10, 2))

    cloro_dosagem = Column(Numeric(10, 2))
    cloro_residual = Column(Numeric(10, 2))

    cor_bruta = Column(Numeric(10, 2))
    cor_tratada = Column(Numeric(10, 2))

    observacoes = Column(Text)

    conforme = Column(Boolean)  # False se algum parâmetro estourou o VMP da portaria
    alertas = Column(Text)  # JSON: lista de textos descrevendo o que estourou

    criado_em = Column(DateTime, server_default=func.now())


class LavagemFiltro(Base):
    """Registro de lavagem de filtro da ETA (hora, tempo gasto, volume gasto) — a mesma tabelinha do boletim de papel."""
    __tablename__ = "lavagens_filtro"
    id = Column(Integer, primary_key=True)
    tecnico_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    localidade = Column(String(30), nullable=False)
    hora = Column(DateTime, nullable=False)
    tempo_gasto_min = Column(Numeric(10, 1))
    volume_gasto = Column(Numeric(10, 2))
    criado_em = Column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Qualidade da água (módulo do químico) — Portaria GM/MS nº 888/2021
# ---------------------------------------------------------------------------

class ConfigSistemaAgua(Base):
    """Parâmetros de cada sistema de abastecimento (uma localidade = um
    sistema, com ETA e captação próprias). Servem para gerar o plano mínimo
    de amostragem da norma."""
    __tablename__ = "config_sistema_agua"
    id = Column(Integer, primary_key=True)
    localidade = Column(String(30), unique=True, nullable=False)
    populacao_abastecida = Column(Integer, nullable=False, default=0)
    manancial = Column(String(12), nullable=False, default="superficial")  # superficial, subterraneo
    filtracao = Column(String(10), default="lenta")  # lenta, rapida (só para manancial superficial)
    numero_filtros = Column(Integer, default=1)
    atualizado_em = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PontoColeta(Base):
    __tablename__ = "pontos_coleta"
    id = Column(Integer, primary_key=True)
    localidade = Column(String(30), nullable=False)
    tipo = Column(String(15), nullable=False)  # captacao, saida_eta, reservatorio, rede
    nome = Column(String(120), nullable=False)
    descricao = Column(Text)
    estrategico = Column(Boolean, default=False)  # hospital, creche, ponta de rede etc. (Art. 44 §1 II)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class RegraAmostragem(Base):
    """Uma linha do plano de amostragem: 'N amostras do grupo G por período'."""
    __tablename__ = "regras_amostragem"
    id = Column(Integer, primary_key=True)
    localidade = Column(String(30), nullable=False)
    grupo = Column(String(30), nullable=False)
    ponto_tipo = Column(String(15), nullable=False)
    quantidade = Column(Integer, nullable=False)
    periodo = Column(String(10), nullable=False)  # dia, semana, mes, trimestre, semestre
    norma = Column(String(40))
    observacao = Column(Text)
    manual = Column(Boolean, default=False)  # editada à mão: o gerador automático não sobrescreve
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class Amostra(Base):
    """Uma amostra de água: do planejamento (pendente) até o laudo."""
    __tablename__ = "amostras"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(30), unique=True)
    localidade = Column(String(30), nullable=False)
    ponto_id = Column(Integer, ForeignKey("pontos_coleta.id"), nullable=False)
    grupo = Column(String(30), nullable=False)
    status = Column(String(20), default="coletada")  # pendente, coletada, analisada, encaminhada, laudo_recebido, cancelada
    data_prevista = Column(Date)
    coletado_em = Column(DateTime)
    coletor_id = Column(Integer, ForeignKey("usuarios.id"))
    # Medidos na hora da coleta (Art. 44 §3: cor, turbidez e residual de desinfetante em toda amostra bacteriológica)
    cloro_residual = Column(Numeric(10, 2))
    cor_aparente = Column(Numeric(10, 2))
    turbidez = Column(Numeric(10, 2))
    ph = Column(Numeric(10, 2))
    # Recoleta (Art. 27)
    recoleta_de_id = Column(Integer, ForeignKey("amostras.id"))
    posicao_recoleta = Column(String(12))  # mesmo_ponto, montante, jusante
    observacoes = Column(Text)
    criado_em = Column(DateTime, server_default=func.now())


class ResultadoAnalise(Base):
    """Resultado do laboratório PRÓPRIO (kit/estufa) para uma amostra. O laudo
    oficial do laboratório externo fica em LaudoExterno."""
    __tablename__ = "resultados_analise"
    id = Column(Integer, primary_key=True)
    amostra_id = Column(Integer, ForeignKey("amostras.id"), unique=True, nullable=False)
    analista_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    metodo = Column(String(80))
    lote_kit = Column(String(40))
    validade_kit = Column(Date)
    incubacao_inicio = Column(DateTime)
    incubacao_fim = Column(DateTime)
    incubacao_temp_c = Column(Numeric(5, 1))
    coliformes_totais_presente = Column(Boolean)
    e_coli_presente = Column(Boolean)
    coliformes_totais_nmp = Column(Numeric(14, 2))  # NMP/100 mL (água bruta)
    e_coli_nmp = Column(Numeric(14, 2))  # NMP/100 mL (água bruta, Art. 29)
    cianobacterias_cel_ml = Column(Numeric(14, 2))
    conforme = Column(Boolean)  # None na água bruta
    alertas = Column(Text)  # JSON
    observacoes = Column(Text)
    criado_em = Column(DateTime, server_default=func.now())


class LaudoExterno(Base):
    """Laudo do laboratório externo (ex.: Viçosa) — o arquivo fica numa pasta
    PRIVADA (não é servido por URL pública), baixado só com login."""
    __tablename__ = "laudos_externos"
    id = Column(Integer, primary_key=True)
    localidade = Column(String(30), nullable=False)
    ponto_id = Column(Integer, ForeignKey("pontos_coleta.id"))
    amostra_id = Column(Integer, ForeignKey("amostras.id"))
    tipo = Column(String(25), nullable=False)  # agua_bruta_semestral, bacteriologico, outro
    laboratorio = Column(String(120), nullable=False)
    numero_laudo = Column(String(60))
    data_coleta = Column(Date, nullable=False)
    data_emissao = Column(Date)
    parametros_resumo = Column(Text)
    conforme = Column(Boolean)
    arquivo = Column(String(255))  # nome do arquivo na pasta privada
    observacoes = Column(Text)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    criado_em = Column(DateTime, server_default=func.now())
