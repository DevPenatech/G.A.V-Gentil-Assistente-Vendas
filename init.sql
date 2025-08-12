-- ================================================================
-- G.A.V. (Gentil Assistente de Vendas) - Database Schema
-- ================================================================
-- Script de inicialização do banco de dados PostgreSQL
-- Executado automaticamente na primeira inicialização do container

-- Configurações iniciais
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- ========================
-- Funções Utilitárias
-- ========================

-- Função para atualizar timestamp automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Função para normalizar texto (remove acentos)
CREATE OR REPLACE FUNCTION normalize_text(text)
RETURNS TEXT AS $$
BEGIN
    RETURN lower(unaccent($1));
END;
$$ LANGUAGE 'plpgsql' IMMUTABLE;

-- ========================
-- Tabelas Principais
-- ========================

-- Tabela para cadastrar as lojas/filiais
CREATE TABLE lojas (
    id_loja SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    endereco TEXT,
    telefone VARCHAR(20),
    email VARCHAR(100),
    status VARCHAR(20) DEFAULT 'ativa' CHECK (status IN ('ativa', 'inativa', 'manutencao')),
    configuracoes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    ultima_sincronizacao TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para os clientes do bot
CREATE TABLE clientes (
    cnpj VARCHAR(18) PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    nome_fantasia VARCHAR(255),
    numero_whatsapp VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100),
    endereco TEXT,
    cidade VARCHAR(100),
    estado VARCHAR(2),
    cep VARCHAR(10),
    id_loja_preferida INTEGER REFERENCES lojas(id_loja),
    limite_credito NUMERIC(12, 2) DEFAULT 0.00,
    status VARCHAR(20) DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo', 'bloqueado')),
    observacoes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    ultimo_acesso TIMESTAMPTZ,
    total_pedidos INTEGER DEFAULT 0,
    valor_total_compras NUMERIC(12, 2) DEFAULT 0.00
);

-- Tabela para o catálogo de produtos (sincronizado do sistema principal)
CREATE TABLE produtos (
    codprod INTEGER PRIMARY KEY,
    descricao TEXT NOT NULL,
    descricao_completa TEXT,
    categoria VARCHAR(100),
    subcategoria VARCHAR(100),
    marca VARCHAR(100),
    codigo_barras VARCHAR(50),
    unidade_venda VARCHAR(20) DEFAULT 'UN',
    preco_varejo NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    preco_atacado NUMERIC(10, 2) DEFAULT 0.00,
    quantidade_atacado INTEGER DEFAULT 1,
    preco_promocional NUMERIC(10, 2),
    data_inicio_promocao DATE,
    data_fim_promocao DATE,
    estoque_disponivel INTEGER DEFAULT 0,
    estoque_minimo INTEGER DEFAULT 0,
    peso_kg NUMERIC(8, 3),
    dimensoes VARCHAR(50),
    status VARCHAR(20) DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo', 'descontinuado')),
    destaque BOOLEAN DEFAULT FALSE,
    tags TEXT[], -- Array de tags para busca
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    ultima_sincronizacao TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para os orçamentos/carrinhos de compra
CREATE TABLE orcamentos (
    id_orcamento SERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE,
    cnpj_cliente VARCHAR(18) REFERENCES clientes(cnpj),
    numero_whatsapp VARCHAR(50), -- Para clientes não cadastrados
    id_loja INTEGER NOT NULL REFERENCES lojas(id_loja),
    status VARCHAR(20) DEFAULT 'aberto' CHECK (status IN ('aberto', 'finalizado', 'cancelado', 'expirado')),
    tipo_orcamento VARCHAR(20) DEFAULT 'varejo' CHECK (tipo_orcamento IN ('varejo', 'atacado', 'misto')),
    valor_subtotal NUMERIC(12, 2) DEFAULT 0.00,
    valor_desconto NUMERIC(12, 2) DEFAULT 0.00,
    valor_total NUMERIC(12, 2) DEFAULT 0.00,
    observacoes TEXT,
    data_vencimento DATE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ,
    cancelado_em TIMESTAMPTZ,
    total_itens INTEGER DEFAULT 0
);

-- Tabela para os itens de cada orçamento
CREATE TABLE orcamento_itens (
    id_item SERIAL PRIMARY KEY,
    id_orcamento INTEGER NOT NULL REFERENCES orcamentos(id_orcamento) ON DELETE CASCADE,
    codprod INTEGER NOT NULL REFERENCES produtos(codprod),
    quantidade NUMERIC(10, 3) NOT NULL CHECK (quantidade > 0),
    tipo_preco_aplicado VARCHAR(10) DEFAULT 'varejo' CHECK (tipo_preco_aplicado IN ('varejo', 'atacado', 'promocional')),
    preco_unitario_gravado NUMERIC(10, 2) NOT NULL,
    valor_desconto_item NUMERIC(10, 2) DEFAULT 0.00,
    valor_total_item NUMERIC(10, 2) NOT NULL,
    observacoes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    posicao INTEGER DEFAULT 1 -- Ordem dos itens no orçamento
);

-- ========================
-- Tabelas de Análise e BI
-- ========================

-- Tabela para estatísticas de busca e uso
CREATE TABLE estatisticas_busca (
    id_estatistica SERIAL PRIMARY KEY,
    session_id VARCHAR(100),
    numero_whatsapp VARCHAR(50),
    termo_busca TEXT NOT NULL,
    termo_normalizado TEXT, -- Termo após normalização
    fonte_resultado VARCHAR(30) CHECK (fonte_resultado IN ('knowledge_base', 'db_fallback', 'fuzzy_search', 'no_results')),
    codprod_sugerido INTEGER REFERENCES produtos(codprod),
    produtos_encontrados INTEGER DEFAULT 0,
    tempo_resposta_ms INTEGER,
    qualidade_busca VARCHAR(20) CHECK (qualidade_busca IN ('excellent', 'good', 'fair', 'poor', 'no_results')),
    feedback_usuario VARCHAR(20) DEFAULT 'sem_feedback' CHECK (feedback_usuario IN ('acerto', 'recusa', 'sem_feedback', 'produto_adicionado')),
    metadata JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para sessões de conversa
CREATE TABLE sessoes_conversa (
    id_sessao SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    numero_whatsapp VARCHAR(50) NOT NULL,
    cnpj_cliente VARCHAR(18) REFERENCES clientes(cnpj),
    status VARCHAR(20) DEFAULT 'ativa' CHECK (status IN ('ativa', 'encerrada', 'expirada')),
    contexto_atual VARCHAR(50),
    carrinho_ativo INTEGER REFERENCES orcamentos(id_orcamento),
    total_mensagens INTEGER DEFAULT 0,
    total_produtos_buscados INTEGER DEFAULT 0,
    total_produtos_adicionados INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    ultima_atividade TIMESTAMPTZ DEFAULT NOW(),
    tempo_total_sessao INTERVAL
);

-- Tabela para histórico de mensagens (log detalhado)
CREATE TABLE historico_mensagens (
    id_mensagem SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    numero_whatsapp VARCHAR(50) NOT NULL,
    tipo_mensagem VARCHAR(20) CHECK (tipo_mensagem IN ('user', 'assistant', 'system', 'error')),
    conteudo TEXT NOT NULL,
    tool_executada VARCHAR(50),
    tempo_processamento_ms INTEGER,
    sucesso BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- ========================
-- Tabelas de Configuração
-- ========================

-- Tabela para configurações do sistema
CREATE TABLE configuracoes (
    id SERIAL PRIMARY KEY,
    chave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT,
    tipo VARCHAR(20) DEFAULT 'string' CHECK (tipo IN ('string', 'number', 'boolean', 'json')),
    descricao TEXT,
    categoria VARCHAR(50),
    editavel BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para templates de mensagens
CREATE TABLE templates_mensagem (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) UNIQUE NOT NULL,
    categoria VARCHAR(50),
    template TEXT NOT NULL,
    variaveis JSON DEFAULT '[]',
    ativo BOOLEAN DEFAULT TRUE,
    descricao TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ========================
-- Tabelas de Log e Auditoria
-- ========================

-- Tabela para logs de sistema
CREATE TABLE logs_sistema (
    id SERIAL PRIMARY KEY,
    nivel VARCHAR(20) NOT NULL CHECK (nivel IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    modulo VARCHAR(100),
    mensagem TEXT NOT NULL,
    contexto JSONB DEFAULT '{}',
    stack_trace TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para auditoria de ações
CREATE TABLE auditoria (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100),
    session_id VARCHAR(100),
    acao VARCHAR(100) NOT NULL,
    tabela_afetada VARCHAR(100),
    registro_id VARCHAR(100),
    dados_anteriores JSONB,
    dados_novos JSONB,
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- ========================
-- Índices para Performance
-- ========================

-- Índices para clientes
CREATE INDEX idx_clientes_whatsapp ON clientes(numero_whatsapp);
CREATE INDEX idx_clientes_status ON clientes(status);
CREATE INDEX idx_clientes_loja ON clientes(id_loja_preferida);
CREATE INDEX idx_clientes_ultimo_acesso ON clientes(ultimo_acesso);

-- Índices para produtos
CREATE INDEX idx_produtos_status ON produtos(status);
CREATE INDEX idx_produtos_categoria ON produtos(categoria);
CREATE INDEX idx_produtos_marca ON produtos(marca);
CREATE INDEX idx_produtos_destaque ON produtos(destaque);
CREATE INDEX idx_produtos_promocao ON produtos(data_inicio_promocao, data_fim_promocao) WHERE preco_promocional IS NOT NULL;

-- Índice de busca textual para produtos (GIN com pg_trgm)
CREATE INDEX idx_produtos_busca_texto ON produtos USING GIN (
    (normalize_text(descricao) || ' ' || 
     COALESCE(normalize_text(categoria), '') || ' ' || 
     COALESCE(normalize_text(marca), '')) gin_trgm_ops
);

-- Índice para tags de produtos
CREATE INDEX idx_produtos_tags ON produtos USING GIN (tags);

-- Índices para orçamentos
CREATE INDEX idx_orcamentos_cliente ON orcamentos(cnpj_cliente);
CREATE INDEX idx_orcamentos_whatsapp ON orcamentos(numero_whatsapp);
CREATE INDEX idx_orcamentos_status ON orcamentos(status);
CREATE INDEX idx_orcamentos_data ON orcamentos(created_at);
CREATE INDEX idx_orcamentos_loja ON orcamentos(id_loja);

-- Índices para itens de orçamento
CREATE INDEX idx_orcamento_itens_orcamento ON orcamento_itens(id_orcamento);
CREATE INDEX idx_orcamento_itens_produto ON orcamento_itens(codprod);

-- Índices para estatísticas
CREATE INDEX idx_estatisticas_termo ON estatisticas_busca(termo_busca);
CREATE INDEX idx_estatisticas_whatsapp ON estatisticas_busca(numero_whatsapp);
CREATE INDEX idx_estatisticas_timestamp ON estatisticas_busca(timestamp);
CREATE INDEX idx_estatisticas_fonte ON estatisticas_busca(fonte_resultado);
CREATE INDEX idx_estatisticas_qualidade ON estatisticas_busca(qualidade_busca);

-- Índices para sessões
CREATE INDEX idx_sessoes_session_id ON sessoes_conversa(session_id);
CREATE INDEX idx_sessoes_whatsapp ON sessoes_conversa(numero_whatsapp);
CREATE INDEX idx_sessoes_status ON sessoes_conversa(status);
CREATE INDEX idx_sessoes_ultima_atividade ON sessoes_conversa(ultima_atividade);

-- Índices para histórico
CREATE INDEX idx_historico_session ON historico_mensagens(session_id);
CREATE INDEX idx_historico_whatsapp ON historico_mensagens(numero_whatsapp);
CREATE INDEX idx_historico_timestamp ON historico_mensagens(timestamp);
CREATE INDEX idx_historico_tool ON historico_mensagens(tool_executada);

-- ========================
-- Triggers para Auditoria
-- ========================

-- Trigger para atualizar timestamp
CREATE TRIGGER trigger_update_lojas_updated_at
    BEFORE UPDATE ON lojas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_update_clientes_updated_at
    BEFORE UPDATE ON clientes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_update_produtos_updated_at
    BEFORE UPDATE ON produtos
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_update_orcamentos_updated_at
    BEFORE UPDATE ON orcamentos
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_update_sessoes_updated_at
    BEFORE UPDATE ON sessoes_conversa
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ========================
-- Views Úteis
-- ========================

-- View para produtos em promoção
CREATE VIEW produtos_promocao AS
SELECT 
    p.*,
    CASE 
        WHEN p.preco_promocional IS NOT NULL 
        AND CURRENT_DATE BETWEEN p.data_inicio_promocao AND p.data_fim_promocao
        THEN p.preco_promocional
        ELSE p.preco_varejo
    END AS preco_atual,
    CASE 
        WHEN p.preco_promocional IS NOT NULL 
        AND CURRENT_DATE BETWEEN p.data_inicio_promocao AND p.data_fim_promocao
        THEN ROUND(((p.preco_varejo - p.preco_promocional) / p.preco_varejo * 100), 2)
        ELSE 0
    END AS percentual_desconto
FROM produtos p
WHERE p.status = 'ativo';

-- View para estatísticas de vendas por produto
CREATE VIEW vendas_por_produto AS
SELECT 
    p.codprod,
    p.descricao,
    p.categoria,
    p.marca,
    COUNT(oi.id_item) as total_vendas,
    SUM(oi.quantidade) as quantidade_vendida,
    SUM(oi.valor_total_item) as valor_total_vendido,
    AVG(oi.preco_unitario_gravado) as preco_medio,
    MAX(o.created_at) as ultima_venda
FROM produtos p
LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
WHERE o.status = 'finalizado'
GROUP BY p.codprod, p.descricao, p.categoria, p.marca;

-- View para clientes mais ativos
CREATE VIEW clientes_ativos AS
SELECT 
    c.*,
    COUNT(o.id_orcamento) as total_orcamentos,
    SUM(o.valor_total) as valor_total_compras_calc,
    AVG(o.valor_total) as ticket_medio,
    MAX(o.created_at) as ultimo_orcamento
FROM clientes c
LEFT JOIN orcamentos o ON c.cnpj = o.cnpj_cliente
WHERE c.status = 'ativo'
GROUP BY c.cnpj;

-- ========================
-- Dados Iniciais
-- ========================

-- Inserir loja padrão
INSERT INTO lojas (nome, endereco, telefone, email) VALUES 
('Comercial Esperança - Filial Principal', 'Endereço da Filial Principal', '(11) 1234-5678', 'contato@comercial-esperanca.com');

-- Inserir configurações padrão
INSERT INTO configuracoes (chave, valor, tipo, descricao, categoria) VALUES
('sistema.versao', '1.0.0', 'string', 'Versão atual do sistema', 'sistema'),
('whatsapp.rate_limit', '10', 'number', 'Limite de mensagens por minuto', 'whatsapp'),
('ia.timeout', '30', 'number', 'Timeout para requisições IA em segundos', 'ia'),
('carrinho.timeout', '3600', 'number', 'Timeout do carrinho em segundos', 'vendas'),
('sistema.manutencao', 'false', 'boolean', 'Sistema em manutenção', 'sistema'),
('vendas.desconto_maximo', '20', 'number', 'Desconto máximo permitido (%)', 'vendas');

-- Inserir produtos de exemplo
INSERT INTO produtos (codprod, descricao, categoria, marca, unidade_venda, preco_varejo, preco_atacado, quantidade_atacado, status, tags) VALUES 
(13700, 'REFRIG.COCA-COLA PET 2L', 'Bebidas', 'Coca-Cola', 'UN', 8.50, 7.99, 6, 'ativo', ARRAY['refrigerante', 'coca', 'cola', '2l', 'pet']),
(8130, 'REFRIG.COCA-COLA LT 350ML', 'Bebidas', 'Coca-Cola', 'UN', 4.20, 3.90, 12, 'ativo', ARRAY['refrigerante', 'coca', 'cola', 'lata', '350ml']),
(52638, 'DT.PO OMO LAVAGEM PERFEITA 1.6KG', 'Limpeza', 'Omo', 'CX', 25.90, 24.50, 3, 'ativo', ARRAY['detergente', 'sabao', 'po', 'omo', '1.6kg']);

-- Templates de mensagem padrão
INSERT INTO templates_mensagem (nome, categoria, template, descricao) VALUES
('saudacao_inicial', 'sistema', 'Olá! Sou o G.A.V., seu assistente virtual do Comercial Esperança. Como posso ajudar você hoje?', 'Mensagem de saudação inicial'),
('produto_adicionado', 'vendas', 'Produto {{nome_produto}} adicionado ao carrinho! Quantidade: {{quantidade}}', 'Confirmação de produto adicionado'),
('carrinho_vazio', 'vendas', 'Seu carrinho está vazio. Que tal ver nossos produtos em destaque?', 'Mensagem para carrinho vazio'),
('pedido_finalizado', 'vendas', 'Pedido finalizado com sucesso! Total: R$ {{total}}. Em breve entraremos em contato.', 'Confirmação de pedido finalizado');

-- ========================
-- Funções de Análise
-- ========================

-- Função para calcular estatísticas de vendas
CREATE OR REPLACE FUNCTION calcular_estatisticas_vendas(periodo_dias INTEGER DEFAULT 30)
RETURNS TABLE(
    total_orcamentos BIGINT,
    valor_total NUMERIC,
    ticket_medio NUMERIC,
    produtos_mais_vendidos TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(o.id_orcamento) as total_orcamentos,
        COALESCE(SUM(o.valor_total), 0) as valor_total,
        COALESCE(AVG(o.valor_total), 0) as ticket_medio,
        STRING_AGG(p.descricao, ', ') as produtos_mais_vendidos
    FROM orcamentos o
    LEFT JOIN orcamento_itens oi ON o.id_orcamento = oi.id_orcamento
    LEFT JOIN produtos p ON oi.codprod = p.codprod
    WHERE o.status = 'finalizado'
    AND o.created_at >= NOW() - INTERVAL '1 day' * periodo_dias;
END;
$$ LANGUAGE plpgsql;

-- ========================
-- Políticas de Segurança (RLS)
-- ========================

-- Habilita Row Level Security (descomentado em ambiente multi-tenant)
-- ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE orcamentos ENABLE ROW LEVEL SECURITY;

-- ========================
-- Comentários nas Tabelas
-- ========================

COMMENT ON TABLE lojas IS 'Cadastro de lojas/filiais da empresa';
COMMENT ON TABLE clientes IS 'Cadastro de clientes do sistema WhatsApp';
COMMENT ON TABLE produtos IS 'Catálogo de produtos sincronizado do sistema principal';
COMMENT ON TABLE orcamentos IS 'Orçamentos/carrinhos de compra dos clientes';
COMMENT ON TABLE orcamento_itens IS 'Itens de cada orçamento';
COMMENT ON TABLE estatisticas_busca IS 'Estatísticas de buscas realizadas pelos usuários';
COMMENT ON TABLE sessoes_conversa IS 'Sessões ativas de conversa via WhatsApp';
COMMENT ON TABLE historico_mensagens IS 'Log detalhado de todas as mensagens';
COMMENT ON TABLE configuracoes IS 'Configurações gerais do sistema';
COMMENT ON TABLE templates_mensagem IS 'Templates de mensagens padronizadas';

-- ========================
-- Validações Finais
-- ========================

-- Verifica se todas as tabelas foram criadas
DO $$
DECLARE
    tabelas_esperadas TEXT[] := ARRAY[
        'lojas', 'clientes', 'produtos', 'orcamentos', 'orcamento_itens',
        'estatisticas_busca', 'sessoes_conversa', 'historico_mensagens',
        'configuracoes', 'templates_mensagem', 'logs_sistema', 'auditoria'
    ];
    tabela TEXT;
    tabelas_criadas INTEGER := 0;
BEGIN
    FOREACH tabela IN ARRAY tabelas_esperadas
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = tabela) THEN
            tabelas_criadas := tabelas_criadas + 1;
            RAISE NOTICE 'Tabela % criada com sucesso', tabela;
        ELSE
            RAISE WARNING 'Tabela % não foi criada', tabela;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Database G.A.V. inicializado: % de % tabelas criadas', tabelas_criadas, array_length(tabelas_esperadas, 1);
END $$;

-- Log de inicialização
INSERT INTO logs_sistema (nivel, modulo, mensagem, contexto) VALUES 
('INFO', 'database', 'Database G.A.V. inicializado com sucesso', '{"timestamp": "' || NOW() || '", "version": "1.0.0"}');

-- Concede permissões (ajustar conforme necessário)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gavuser;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO gavuser;