-- Sistema de Gestão de Água e Esgoto
-- Schema PostgreSQL

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE,
    telefone VARCHAR(20) UNIQUE,
    senha_hash VARCHAR(255) NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('admin', 'operador', 'tecnico', 'cliente')),
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id),
    nome VARCHAR(150) NOT NULL,
    documento VARCHAR(20),
    endereco VARCHAR(255),
    bairro VARCHAR(100),
    cidade VARCHAR(100),
    hidrometro VARCHAR(50),
    categoria VARCHAR(20) CHECK (categoria IN ('residencial', 'comercial', 'industrial')),
    ativo BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS leituras (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER REFERENCES clientes(id),
    data_leitura DATE NOT NULL,
    leitura_m3 NUMERIC(10,2) NOT NULL,
    consumo_m3 NUMERIC(10,2),
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS faturas (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER REFERENCES clientes(id),
    leitura_id INTEGER REFERENCES leituras(id),
    competencia VARCHAR(7),
    valor_agua NUMERIC(10,2),
    valor_esgoto NUMERIC(10,2),
    valor_total NUMERIC(10,2),
    vencimento DATE,
    status VARCHAR(20) DEFAULT 'aberto' CHECK (status IN ('aberto', 'pago', 'vencido')),
    pago_em TIMESTAMP
);

-- Módulo de chamados (substitui/expande "ordens_servico")
CREATE TABLE IF NOT EXISTS chamados (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER REFERENCES clientes(id) NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('vazamento', 'manutencao', 'religacao', 'vistoria', 'outro')),
    descricao_problema TEXT NOT NULL,
    prioridade VARCHAR(10) DEFAULT 'normal' CHECK (prioridade IN ('baixa', 'normal', 'alta', 'urgente')),
    origem VARCHAR(10) NOT NULL CHECK (origem IN ('app', 'whatsapp', 'telefone')),
    status VARCHAR(20) DEFAULT 'aberto' CHECK (status IN ('aberto', 'atribuido', 'em_andamento', 'concluido', 'cancelado')),
    tecnico_id INTEGER REFERENCES usuarios(id),
    descricao_solucao TEXT,
    abertura TIMESTAMP DEFAULT NOW(),
    atribuicao TIMESTAMP,
    conclusao TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chamado_fotos (
    id SERIAL PRIMARY KEY,
    chamado_id INTEGER REFERENCES chamados(id) NOT NULL,
    caminho_arquivo VARCHAR(255) NOT NULL,
    tipo VARCHAR(10) CHECK (tipo IN ('abertura', 'fechamento')),
    enviado_em TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chamados_status ON chamados(status);
CREATE INDEX IF NOT EXISTS idx_chamados_tecnico ON chamados(tecnico_id);
CREATE INDEX IF NOT EXISTS idx_leituras_cliente ON leituras(cliente_id);
CREATE INDEX IF NOT EXISTS idx_faturas_cliente ON faturas(cliente_id);
