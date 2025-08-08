-- init.sql
-- Este script será executado automaticamente pelo contêiner do PostgreSQL na primeira inicialização.

-- Tabela para cadastrar as lojas/filiais
CREATE TABLE lojas (
    id_loja SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    endereco TEXT,
    status VARCHAR(20) DEFAULT 'ativa',
    ultima_sincronizacao TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para os clientes do bot
CREATE TABLE clientes (
    cnpj VARCHAR(18) PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    numero_whatsapp VARCHAR(50) NOT NULL UNIQUE,
    id_loja_preferida INTEGER, -- Referência a lojas(id_loja)
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela para o catálogo de produtos (sincronizado do Oracle)
CREATE TABLE produtos (
    codprod INTEGER PRIMARY KEY,
    descricao TEXT NOT NULL,
    unidade_venda VARCHAR(20),
    preco_varejo NUMERIC(10, 2),
    preco_atacado NUMERIC(10, 2),
    quantidade_atacado INTEGER,
    status VARCHAR(20) DEFAULT 'ativo',
    ultima_sincronizacao TIMESTAMPTZ
);

-- Tabela para os orçamentos/carrinhos de compra
CREATE TABLE orcamentos (
    id_orcamento SERIAL PRIMARY KEY,
    cnpj_cliente VARCHAR(18) NOT NULL, -- Referência a clientes(cnpj)
    id_loja INTEGER NOT NULL, -- Referência a lojas(id_loja)
    status VARCHAR(20) DEFAULT 'aberto',
    valor_total NUMERIC(12, 2),
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ
);

-- Tabela para os itens de cada orçamento
CREATE TABLE orcamento_itens (
    id_item SERIAL PRIMARY KEY,
    id_orcamento INTEGER NOT NULL, -- Referência a orcamentos(id_orcamento)
    codprod INTEGER NOT NULL, -- Referência a produtos(codprod)
    quantidade INTEGER NOT NULL,
    tipo_preco_aplicado VARCHAR(10), -- 'varejo' ou 'atacado'
    preco_unitario_gravado NUMERIC(10, 2)
);

CREATE TABLE estatisticas_busca (
    id_estatistica SERIAL PRIMARY KEY,
    termo_busca TEXT NOT NULL,
    fonte_resultado VARCHAR(20), -- 'knowledge_base' ou 'db_fallback'
    codprod_sugerido INTEGER,
    feedback_usuario VARCHAR(20), -- 'acerto', 'recusa', 'sem_feedback'
    timestamp TIMESTAMPTZ DEFAULT NOW()
);


-- Adiciona alguns dados de exemplo para teste inicial
INSERT INTO lojas (nome, endereco) VALUES ('Comercial Esperança - Filial 17', 'Endereço da Filial 17');
INSERT INTO produtos (codprod, descricao, unidade_venda, preco_varejo, preco_atacado, quantidade_atacado, status) VALUES 
(13700, 'REFRIG.COCA-COLA PET 2L', 'UN', 8.50, 7.99, 6, 'ativo'),
(8130, 'REFRIG.COCA-COLA LT 350ML', 'UN', 4.20, 3.90, 12, 'ativo'),
(52638, 'DT.PO OMO LAVAGEM PERFEITA 1.6KG', 'CX', 25.90, 24.50, 3, 'ativo');

