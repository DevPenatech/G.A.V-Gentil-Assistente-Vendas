# arquivo: IA/db/database.py
"""Módulo de acesso ao banco de dados com segurança aprimorada"""

import os
import sys
from pathlib import Path
import logging
import psycopg2
from psycopg2.extras import DictCursor, RealDictCursor
from dotenv import load_dotenv
from typing import Union, List, Dict
import time
import decimal

# Adiciona utils ao path se não estiver
caminho_utils = Path(__file__).resolve().parent.parent / "utils"
if str(caminho_utils) not in sys.path:
    sys.path.insert(0, str(caminho_utils))

from busca_aproximada import busca_aproximada_produtos, MotorBuscaAproximada
from gav_logger import obter_logger, log_database_query, log_error, log_warning, log_info, log_debug

load_dotenv(dotenv_path='.env')  # Garante que o .env da pasta IA seja lido

# Cache simples em memória para consultas repetidas
_cache_consultas: Dict = {}

def cache_query(ttl: int = 300):
    """Decorator para cachear resultados de consultas ao banco."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            chave = (func.__name__, args, frozenset(kwargs.items()))
            agora = time.time()
            if chave in _cache_consultas:
                resultado, timestamp = _cache_consultas[chave]
                if agora - timestamp < ttl:
                    logging.debug(f"[CACHE_DB] Hit para {func.__name__}: {chave}")
                    return resultado
            resultado = func(*args, **kwargs)
            _cache_consultas[chave] = (resultado, agora)
            return resultado
        return wrapper
    return decorator

def validar_configuracao_banco():
    """Valida configuração crítica do banco no startup"""
    variaveis_obrigatorias = {
        "DB_NAME": "Nome do banco de dados",
        "DB_USERNAME": "Usuário do banco",
        "DB_PASSWORD": "Senha do banco", 
        "DB_HOST": "Host do banco",
        "DB_PORT": "Porta do banco"
    }
    
    variaveis_ausentes = []
    for nome_var, descricao in variaveis_obrigatorias.items():
        if not os.getenv(nome_var):
            variaveis_ausentes.append(f"{nome_var} ({descricao})")
    
    if variaveis_ausentes:
        raise ValueError(f"Variáveis de ambiente obrigatórias ausentes:\n" + 
                        "\n".join(f"- {var}" for var in variaveis_ausentes))

def obter_url_banco_segura():
    """Constrói URL do banco sem expor credenciais"""
    validar_configuracao_banco()
    
    variaveis_necessarias = {
        'dbname': os.getenv("DB_NAME"),
        'user': os.getenv("DB_USERNAME"),
        'password': os.getenv("DB_PASSWORD"),
        'host': os.getenv("DB_HOST"),
        'port': os.getenv("DB_PORT")
    }
    
    # Constrói URL sem logging das credenciais
    return " ".join([f"{k}='{v}'" for k, v in variaveis_necessarias.items()])

# Variáveis de configuração
NOME_BANCO = os.getenv("DB_NAME")
USUARIO_BANCO = os.getenv("DB_USERNAME")
SENHA_BANCO = os.getenv("DB_PASSWORD")
HOST_BANCO = os.getenv("DB_HOST")
PORTA_BANCO = os.getenv("DB_PORT")

try:
    URL_BANCO_DADOS = obter_url_banco_segura()
except ValueError as e:
    logging.error(f"Erro na configuração do banco: {e}")
    raise

def obter_conexao():
    """Estabelece uma conexão com o PostgreSQL, com uma lógica de retry.

    Returns:
        A conexão com o banco de dados.
    """
    log_debug("Tentando obter conexão com o banco de dados", categoria="DATABASE_CONNECTION")
    tentativas = 5
    atraso = 3
    for i in range(tentativas):
        try:
            inicio = time.time()
            conexao = psycopg2.connect(URL_BANCO_DADOS)
            tempo_conexao = time.time() - inicio
            log_database_query("CONNECTION", tempo_conexao, categoria="DATABASE_CONNECTION")
            log_debug("Conexão com o banco de dados estabelecida com sucesso", categoria="DATABASE_CONNECTION")
            return conexao
        except psycopg2.OperationalError as e:
            log_warning(f"Conexão falhou na tentativa {i+1}/{tentativas}: {str(e)}. Tentando novamente em {atraso}s...", 
                       categoria="DATABASE_CONNECTION", tentativa=i+1)
            time.sleep(atraso)
    
    log_error("Não foi possível conectar ao banco de dados após várias tentativas", categoria="DATABASE_CONNECTION")
    raise Exception("Não foi possível conectar ao banco de dados.")

def _converter_linha_para_dicionario(linha: DictCursor) -> Dict:
    """Converte uma linha do cursor para um dicionário, tratando Decimals.

    Args:
        linha: A linha do cursor.

    Returns:
        Um dicionário com os dados da linha.
    """
    if not linha:
        return None
    dicionario_linha = dict(linha)
    for chave, valor in dicionario_linha.items():
        if isinstance(valor, decimal.Decimal):
            dicionario_linha[chave] = float(valor)
    return dicionario_linha

@cache_query()
def encontrar_cliente_por_cnpj(cnpj: str) -> Union[Dict, None]:
    """Busca um cliente pelo CNPJ.

    Args:
        cnpj: O CNPJ do cliente.

    Returns:
        Um dicionário com os dados do cliente ou None se não encontrado.
    """
    logging.debug(f"Buscando cliente por CNPJ: {cnpj}")
    sql = "SELECT cnpj, nome FROM clientes WHERE cnpj = %(cnpj)s;"
    params = {'cnpj': cnpj}
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultado = cursor.fetchone()
                if resultado:
                    logging.debug(f"Cliente encontrado para o CNPJ {cnpj}: {resultado}")
                else:
                    logging.debug(f"Nenhum cliente encontrado para o CNPJ {cnpj}")
                return _converter_linha_para_dicionario(resultado) if resultado else None
    except Exception as e:
        logging.error(f"Erro ao buscar cliente por CNPJ {cnpj}: {e}")
        return None

@cache_query()
def obter_produtos_mais_vendidos(limite: int = 10, offset: int = 0, filial: int = 17) -> List[Dict]:
    """Busca os produtos mais vendidos com base no histórico de orçamentos.

    Args:
        limite: O número máximo de produtos a serem retornados.
        offset: O deslocamento para paginação.
        filial: O ID da filial.

    Returns:
        Uma lista de dicionários com os produtos mais vendidos.
    """
    logging.debug(f"Buscando os {limite} produtos mais vendidos com offset {offset} para a filial {filial}.")
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.unidade_venda,
        p.preco_varejo,
        p.preco_atacado,
        p.quantidade_atacado,
        COALESCE(SUM(oi.quantidade), 0) AS total_vendido
    FROM produtos p
    LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
    WHERE p.status = 'ativo'
    GROUP BY p.codprod, p.descricao, p.unidade_venda, p.preco_varejo, p.preco_atacado, p.quantidade_atacado
    ORDER BY total_vendido DESC, p.descricao ASC
    LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'limit': limite, 'offset': offset}
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                logging.debug(f"Encontrados {len(resultados)} produtos mais vendidos.")
                return [_converter_linha_para_dicionario(linha) for linha in resultados]
    except Exception as e:
        logging.error(f"Erro ao buscar produtos mais vendidos: {e}")
        return []

@cache_query()
def obter_produtos_mais_vendidos_por_nome(nome_produto: str, limite: int = 10, offset: int = 0) -> List[Dict]:
    """Busca produtos por nome com ranking de vendas.

    Args:
        nome_produto: O nome do produto a ser buscado.
        limite: O número máximo de produtos a serem retornados.
        offset: O deslocamento para paginação.

    Returns:
        Uma lista de dicionários com os produtos encontrados.
    """
    logging.debug(f"Buscando os {limite} produtos mais vendidos por nome '{nome_produto}' com offset {offset}.")
    if not nome_produto or len(nome_produto.strip()) < 2:
        logging.debug("Nome do produto inválido para busca.")
        return []
    
    padrao_busca = f"%{nome_produto.strip().lower()}%"
    
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.unidade_venda,
        p.preco_varejo,
        p.preco_atacado,
        p.quantidade_atacado,
        COALESCE(SUM(oi.quantidade), 0) AS total_vendido
    FROM produtos p
    LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
    WHERE p.status = 'ativo' 
        AND LOWER(p.descricao) ILIKE %(pattern)s
    GROUP BY p.codprod, p.descricao, p.unidade_venda, p.preco_varejo, p.preco_atacado, p.quantidade_atacado
    ORDER BY total_vendido DESC, p.descricao ASC
    LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'pattern': padrao_busca, 'limit': limite, 'offset': offset}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                logging.debug(f"Encontrados {len(resultados)} produtos para o nome '{nome_produto}'.")
                return [_converter_linha_para_dicionario(linha) for linha in resultados]
    except Exception as e:
        logging.error(f"Erro ao buscar produtos por nome '{nome_produto}': {e}")
        return []

def pesquisar_produtos_com_sugestoes(nome_produto: str, limite: int = 10, offset: int = 0) -> Dict:
    """Busca produtos com sugestões inteligentes e busca aproximada.

    Args:
        nome_produto: O nome do produto a ser buscado.
        limite: O número máximo de produtos a serem retornados.
        offset: O deslocamento para paginação.

    Returns:
        Um dicionário com os produtos, sugestões e qualidade da busca.
    """
    logging.debug(f"Pesquisando produtos com sugestões para '{nome_produto}'.")
    if not nome_produto or len(nome_produto.strip()) < 2:
        logging.debug("Nome do produto inválido para pesquisa com sugestões.")
        return {"products": [], "suggestions": [], "search_quality": "invalid"}
    
    produtos_exatos = obter_produtos_mais_vendidos_por_nome(nome_produto, limite, offset)
    
    if produtos_exatos:
        logging.debug(f"Encontrados {len(produtos_exatos)} produtos exatos para '{nome_produto}'.")
        return {
            "products": produtos_exatos,
            "suggestions": [],
            "search_quality": "exact"
        }
    
    produtos_fuzzy = busca_aproximada_produtos(nome_produto, limite)
    
    if produtos_fuzzy:
        logging.debug(f"Encontrados {len(produtos_fuzzy)} produtos por busca aproximada para '{nome_produto}'.")
        return {
            "products": produtos_fuzzy,
            "suggestions": [],
            "search_quality": "fuzzy"
        }
    
    sugestoes = []
    motor_busca = MotorBuscaAproximada()
    termo_corrigido = motor_busca.aplicar_correcoes(nome_produto)
    
    if termo_corrigido != nome_produto.lower().strip():
        produtos_corrigidos = obter_produtos_mais_vendidos_por_nome(termo_corrigido, 3)
        if produtos_corrigidos:
            sugestoes.append(termo_corrigido)
    
    sinonimos = motor_busca.expandir_com_sinonimos(nome_produto)
    for sinonimo in sinonimos[:2]:
        if sinonimo != nome_produto.lower():
            sugestoes.append(sinonimo)
    
    logging.debug(f"Nenhum produto encontrado para '{nome_produto}'. Sugestões: {sugestoes}")
    return {
        "products": [],
        "suggestions": sugestoes[:3],
        "search_quality": "no_results"
    }

def obter_produto_por_codprod(codprod: int) -> Union[Dict, None]:
    """Busca um produto específico pelo código.

    Args:
        codprod: O código do produto.

    Returns:
        Um dicionário com os dados do produto ou None se não encontrado.
    """
    logging.debug(f"Buscando produto por codprod: {codprod}")
    if not codprod or codprod <= 0:
        logging.debug("codprod inválido.")
        return None
    
    sql = """
    SELECT 
        codprod,
        descricao,
        unidade_venda,
        preco_varejo,
        preco_atacado,
        quantidade_atacado,
        status
    FROM produtos 
    WHERE codprod = %(codprod)s AND status = 'ativo';
    """
    params = {'codprod': codprod}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultado = cursor.fetchone()
                if resultado:
                    logging.debug(f"Produto encontrado para o codprod {codprod}: {resultado}")
                else:
                    logging.debug(f"Nenhum produto encontrado para o codprod {codprod}")
                return _converter_linha_para_dicionario(resultado) if resultado else None
    except Exception as e:
        logging.error(f"Erro ao buscar produto por código {codprod}: {e}")
        return None

def obter_detalhes_produto_fuzzy(termo_busca: str) -> List[Dict]:
    """Busca produtos com detalhes usando busca aproximada avançada.

    Args:
        termo_busca: O termo de busca.

    Returns:
        Uma lista de dicionários com os produtos encontrados.
    """
    logging.debug(f"Buscando detalhes do produto por busca aproximada para '{termo_busca}'.")
    if not termo_busca or len(termo_busca.strip()) < 2:
        logging.debug("Termo de busca inválido.")
        return []
    
    resultados_exatos = obter_produtos_mais_vendidos_por_nome(termo_busca, 10)
    if resultados_exatos:
        logging.debug(f"Encontrados {len(resultados_exatos)} produtos exatos para '{termo_busca}'.")
        return resultados_exatos
    
    resultados_fuzzy = busca_aproximada_produtos(termo_busca, 10)
    logging.debug(f"Encontrados {len(resultados_fuzzy)} produtos por busca aproximada para '{termo_busca}'.")
    return resultados_fuzzy

def obter_todos_produtos_ativos() -> List[Dict]:
    """Retorna todos os produtos ativos para geração da base de conhecimento.

    Returns:
        Uma lista de dicionários com todos os produtos ativos.
    """
    logging.debug("Buscando todos os produtos ativos.")
    sql = """
    SELECT 
        codprod,
        descricao,
        unidade_venda,
        preco_varejo,
        preco_atacado,
        quantidade_atacado,
        status
    FROM produtos 
    WHERE status = 'ativo'
    ORDER BY descricao ASC;
    """
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                resultados = cursor.fetchall()
                logging.debug(f"Encontrados {len(resultados)} produtos ativos.")
                return [_converter_linha_para_dicionario(linha) for linha in resultados]
    except Exception as e:
        logging.error(f"Erro ao buscar todos os produtos ativos: {e}")
        return []

def adicionar_estatistica_busca(termo_busca: str, fonte_resultado: str, codprod_sugerido: int = None, feedback: str = "sem_feedback"):
    """Adiciona uma estatística de busca com mais detalhes.

    Args:
        termo_busca: O termo de busca.
        fonte_resultado: A fonte do resultado (ex: 'exact', 'fuzzy').
        codprod_sugerido: O código do produto sugerido.
        feedback: O feedback do usuário.
    """
    logging.debug(f"Adicionando estatística de busca para '{termo_busca}'. Fonte: {fonte_resultado}, Produto sugerido: {codprod_sugerido}, Feedback: {feedback}")
    if not termo_busca:
        logging.debug("Termo de busca inválido para adicionar estatística.")
        return
        
    sql = """
    INSERT INTO estatisticas_busca 
    (termo_busca, fonte_resultado, codprod_sugerido, feedback_usuario, timestamp) 
    VALUES (%(term)s, %(source)s, %(codprod)s, %(feedback)s, NOW());
    """
    params = {
        'term': termo_busca[:255],
        'source': fonte_resultado,
        'codprod': codprod_sugerido,
        'feedback': feedback
    }
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
                conexao.commit()
                logging.debug(f"Estatística de busca adicionada com sucesso para '{termo_busca}'.")
    except Exception as e:
        logging.error(f"Erro ao adicionar estatística de busca: {e}")

def atualizar_feedback_busca(id_estatistica: int, feedback: str):
    """Atualiza o feedback de uma busca específica.

    Args:
        id_estatistica: O ID da estatística de busca.
        feedback: O feedback do usuário.
    """
    logging.debug(f"Atualizando feedback da busca {id_estatistica} para '{feedback}'.")
    if not id_estatistica: 
        logging.debug("ID da estatística inválido.")
        return
        
    sql = "UPDATE estatisticas_busca SET feedback_usuario = %(feedback)s WHERE id_estatistica = %(id)s;"
    params = {'feedback': feedback, 'id': id_estatistica}
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
                conexao.commit()
                logging.debug(f"Feedback da busca {id_estatistica} atualizado com sucesso.")
    except Exception as e:
        logging.error(f"Falha ao atualizar feedback de busca: {e}")

def obter_estatisticas_busca(dias: int = 7) -> List[Dict]:
    """Retorna as estatísticas de busca dos últimos N dias.

    Args:
        dias: O número de dias a serem considerados.

    Returns:
        Uma lista de dicionários com as estatísticas de busca.
    """
    logging.debug(f"Buscando estatísticas de busca dos últimos {dias} dias.")
    sql = """
    SELECT 
        termo_busca,
        fonte_resultado,
        COUNT(*) as total_buscas,
        COUNT(CASE WHEN feedback_usuario = 'acerto' THEN 1 END) as acertos,
        COUNT(CASE WHEN feedback_usuario = 'recusa' THEN 1 END) as recusas,
        MAX(timestamp) as ultima_busca
    FROM estatisticas_busca 
    WHERE timestamp >= NOW() - INTERVAL %(days)s DAY
    GROUP BY termo_busca, fonte_resultado
    ORDER BY total_buscas DESC, ultima_busca DESC
    LIMIT 50;
    """
    params = {'days': dias}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                logging.debug(f"Encontradas {len(resultados)} estatísticas de busca.")
                return [_converter_linha_para_dicionario(linha) for linha in resultados]
    except Exception as e:
        logging.error(f"Erro ao buscar estatísticas: {e}")
        return []

def criar_orcamento(cnpj_cliente: str, id_loja: int = 1) -> Union[int, None]:
    """Cria um novo orçamento e retorna o ID.

    Args:
        cnpj_cliente: O CNPJ do cliente.
        id_loja: O ID da loja.

    Returns:
        O ID do orçamento criado ou None em caso de erro.
    """
    logging.debug(f"Criando orçamento para o cliente CNPJ {cnpj_cliente} na loja {id_loja}.")
    sql = """
    INSERT INTO orcamentos (cnpj_cliente, id_loja, status, created_at) 
    VALUES (%(cnpj)s, %(loja)s, 'aberto', NOW())
    RETURNING id_orcamento;
    """
    params = {'cnpj': cnpj_cliente, 'loja': id_loja}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
                resultado = cursor.fetchone()
                conexao.commit()
                id_orcamento = resultado[0] if resultado else None
                logging.debug(f"Orçamento criado com ID: {id_orcamento}")
                return id_orcamento
    except Exception as e:
        logging.error(f"Erro ao criar orçamento: {e}")
        return None

def adicionar_item_orcamento(id_orcamento: int, codprod: int, quantidade: float, tipo_preco: str = 'varejo'):
    """Adiciona um item ao orçamento.

    Args:
        id_orcamento: O ID do orçamento.
        codprod: O código do produto.
        quantidade: A quantidade do produto.
        tipo_preco: O tipo de preço a ser aplicado (varejo ou atacado).

    Returns:
        True se o item foi adicionado com sucesso, False caso contrário.
    """
    logging.debug(f"Adicionando item {codprod} (quantidade: {quantidade}, tipo_preco: {tipo_preco}) ao orçamento {id_orcamento}.")
    produto = obter_produto_por_codprod(codprod)
    if not produto:
        logging.warning(f"Produto {codprod} não encontrado para adicionar ao orçamento.")
        return False
    
    preco_unitario = produto.get('preco_atacado' if tipo_preco == 'atacado' else 'preco_varejo', 0.0)
    
    sql = """
    INSERT INTO orcamento_itens 
    (id_orcamento, codprod, quantidade, tipo_preco_aplicado, preco_unitario_gravado) 
    VALUES (%(orcamento)s, %(codprod)s, %(qt)s, %(tipo)s, %(preco)s);
    """
    params = {
        'orcamento': id_orcamento,
        'codprod': codprod,
        'qt': quantidade,
        'tipo': tipo_preco,
        'preco': preco_unitario
    }
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
                conexao.commit()
                logging.debug(f"Item {codprod} adicionado ao orçamento {id_orcamento} com sucesso.")
                return True
    except Exception as e:
        logging.error(f"Erro ao adicionar item ao orçamento: {e}")
        return False

def finalizar_orcamento(id_orcamento: int) -> bool:
    """Finaliza um orçamento calculando o valor total.

    Args:
        id_orcamento: O ID do orçamento.

    Returns:
        True se o orçamento foi finalizado com sucesso, False caso contrário.
    """
    logging.debug(f"Finalizando orçamento {id_orcamento}.")
    sql_total = """
    SELECT SUM(quantidade * preco_unitario_gravado) as total
    FROM orcamento_itens 
    WHERE id_orcamento = %(id)s;
    """
    
    sql_update = """
    UPDATE orcamentos 
    SET valor_total = %(total)s, status = 'finalizado', finalizado_em = NOW()
    WHERE id_orcamento = %(id)s;
    """
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql_total, {'id': id_orcamento})
                resultado = cursor.fetchone()
                total = resultado[0] if resultado and resultado[0] else 0.0
                
                cursor.execute(sql_update, {'id': id_orcamento, 'total': total})
                conexao.commit()
                
                logging.info(f"Orçamento {id_orcamento} finalizado com total: R$ {total:.2f}")
                return True
                
    except Exception as e:
        logging.error(f"Erro ao finalizar orçamento {id_orcamento}: {e}")
        return False

def obter_termos_busca_populares(limite: int = 10) -> List[Dict]:
    """Retorna os termos de busca mais populares.

    Args:
        limite: O número máximo de termos a serem retornados.

    Returns:
        Uma lista de dicionários com os termos de busca populares.
    """
    logging.debug(f"Buscando os {limite} termos de busca mais populares.")
    sql = """
    SELECT 
        termo_busca,
        COUNT(*) as total_buscas,
        COUNT(CASE WHEN feedback_usuario = 'acerto' THEN 1 END) as taxa_acerto,
        MAX(timestamp) as ultima_busca
    FROM estatisticas_busca 
    WHERE timestamp >= NOW() - INTERVAL 30 DAY
    GROUP BY termo_busca
    HAVING COUNT(*) >= 2
    ORDER BY total_buscas DESC, taxa_acerto DESC
    LIMIT %(limit)s;
    """
    params = {'limit': limite}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                logging.debug(f"Encontrados {len(resultados)} termos de busca populares.")
                return [_converter_linha_para_dicionario(linha) for linha in resultados]
    except Exception as e:
        logging.error(f"Erro ao buscar termos populares: {e}")
        return []

def obter_estatisticas_performance_produto(dias: int = 30) -> List[Dict]:
    """Retorna as estatísticas de performance dos produtos.

    Args:
        dias: O número de dias a serem considerados.

    Returns:
        Uma lista de dicionários com as estatísticas de performance dos produtos.
    """
    logging.debug(f"Buscando estatísticas de performance dos produtos dos últimos {dias} dias.")
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        COUNT(DISTINCT e.id_estatistica) as buscas_recentes,
        COUNT(DISTINCT o.id_orcamento) as vendas_recentes,
        AVG(oi.quantidade) as quantidade_media_vendida,
        SUM(oi.quantidade * oi.preco_unitario_gravado) as receita_recente
    FROM produtos p
    LEFT JOIN estatisticas_busca e ON p.codprod = e.codprod_sugerido 
        AND e.timestamp >= NOW() - INTERVAL %(days)s DAY
    LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento 
        AND o.created_at >= NOW() - INTERVAL %(days)s DAY
    WHERE p.status = 'ativo'
    GROUP BY p.codprod, p.descricao
    HAVING COUNT(DISTINCT e.id_estatistica) > 0 OR COUNT(DISTINCT o.id_orcamento) > 0
    ORDER BY receita_recente DESC, buscas_recentes DESC
    LIMIT 20;
    """
    params = {'days': dias}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                logging.debug(f"Encontradas {len(resultados)} estatísticas de performance de produtos.")
                return [_converter_linha_para_dicionario(linha) for linha in resultados]
    except Exception as e:
        logging.error(f"Erro ao buscar estatísticas de performance: {e}")
        return []

def limpar_estatisticas_antigas(dias: int = 90):
    """Remove estatísticas antigas para manter a performance.

    Args:
        dias: O número de dias a serem considerados.
    """
    logging.debug(f"Limpando estatísticas de busca com mais de {dias} dias.")
    sql = "DELETE FROM estatisticas_busca WHERE timestamp < NOW() - INTERVAL %(days)s DAY;"
    params = {'days': dias}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, params)
                contagem_deletados = cursor.rowcount
                conexao.commit()
                logging.info(f"Removidas {contagem_deletados} estatísticas antigas (>{dias} dias)")
                return contagem_deletados
    except Exception as e:
        logging.error(f"Erro ao limpar estatísticas antigas: {e}")
        return 0

def otimizar_banco_dados():
    """Executa otimizações básicas no banco de dados."""
    logging.debug("Otimizando o banco de dados.")
    queries_otimizacao = [
        "VACUUM ANALYZE produtos;",
        "VACUUM ANALYZE estatisticas_busca;",
        "VACUUM ANALYZE orcamentos;",
        "VACUUM ANALYZE orcamento_itens;",
    ]
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                for query in queries_otimizacao:
                    logging.debug(f"Executando otimização: {query}")
                    cursor.execute(query)
                conexao.commit()
                logging.info("Otimização do banco de dados concluída")
                return True
    except Exception as e:
        logging.error(f"Erro na otimização do banco: {e}")
        return False

@cache_query()
def obter_produtos_por_categoria(categoria: str, limite: int = 10, offset: int = 0, marca_priorizada: str = None) -> List[Dict]:
    """Busca produtos por categoria ordenados por vendas, com opção de priorizar marca específica.

    Args:
        categoria: A categoria dos produtos.
        limite: O número máximo de produtos a serem retornados.
        offset: O deslocamento para paginação.
        marca_priorizada: Marca específica para priorizar nos resultados.

    Returns:
        Uma lista de dicionários com os produtos encontrados.
    """
    logging.debug(f"Buscando produtos por categoria '{categoria}' com limite {limite}, offset {offset} e marca priorizada '{marca_priorizada}'.")
    if not categoria or len(categoria.strip()) < 2:
        logging.debug("Categoria inválida para busca.")
        return []
    
    # Se há marca priorizada, ordena colocando essa marca primeiro
    if marca_priorizada:
        sql = """
        SELECT 
            p.codprod,
            p.descricao,
            p.categoria,
            p.marca,
            p.unidade_venda,
            p.preco_varejo,
            p.preco_atacado,
            p.quantidade_atacado,
            COALESCE(SUM(oi.quantidade), 0) AS total_vendido,
            CASE 
                WHEN LOWER(p.marca) LIKE LOWER(%(marca_priorizada)s) 
                     OR LOWER(p.descricao) LIKE LOWER(%(marca_priorizada)s) 
                THEN 1 
                ELSE 0 
            END AS marca_match
        FROM produtos p
        LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
        LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
        WHERE p.status = 'ativo' 
            AND LOWER(p.categoria) = LOWER(%(category)s)
        GROUP BY p.codprod, p.descricao, p.categoria, p.marca, p.unidade_venda, 
                 p.preco_varejo, p.preco_atacado, p.quantidade_atacado
        ORDER BY marca_match DESC, total_vendido DESC, p.descricao ASC
        LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {
            'category': categoria.strip(), 
            'limit': limite, 
            'offset': offset,
            'marca_priorizada': f'%{marca_priorizada.strip()}%'
        }
        logging.info(f"[DB_BUSCA] Priorizando marca '{marca_priorizada}' na categoria '{categoria}'")
    else:
        sql = """
        SELECT 
            p.codprod,
            p.descricao,
            p.categoria,
            p.marca,
            p.unidade_venda,
            p.preco_varejo,
            p.preco_atacado,
            p.quantidade_atacado,
            COALESCE(SUM(oi.quantidade), 0) AS total_vendido
        FROM produtos p
        LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
        LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
        WHERE p.status = 'ativo' 
            AND LOWER(p.categoria) = LOWER(%(category)s)
        GROUP BY p.codprod, p.descricao, p.categoria, p.marca, p.unidade_venda, 
                 p.preco_varejo, p.preco_atacado, p.quantidade_atacado
        ORDER BY total_vendido DESC, p.descricao ASC
        LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {'category': categoria.strip(), 'limit': limite, 'offset': offset}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                produtos = [_converter_linha_para_dicionario(linha) for linha in resultados]
                
                logging.info(f"Encontrados {len(produtos)} produtos na categoria '{categoria}'" + 
                           (f" (priorizando marca '{marca_priorizada}')" if marca_priorizada else ""))
                return produtos
                
    except Exception as e:
        logging.error(f"Erro ao buscar produtos da categoria '{categoria}': {e}")
        return []

@cache_query()
def obter_produtos_promocionais_por_categoria(categoria: str, limite: int = 5, offset: int = 0) -> List[Dict]:
    """Busca produtos promocionais ativos por categoria.

    Args:
        categoria: A categoria dos produtos.
        limite: O número máximo de promoções a serem retornadas.
        offset: O deslocamento para paginação.

    Returns:
        Uma lista de dicionários com os produtos promocionais encontrados.
    """
    logging.debug(f"Buscando produtos promocionais por categoria '{categoria}' com limite {limite} e offset {offset}.")
    if not categoria or len(categoria.strip()) < 2:
        logging.debug("Categoria inválida para busca de promoções.")
        return []
    
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.categoria,
        p.marca,
        p.unidade_venda,
        p.preco_varejo,
        p.preco_atacado,
        p.quantidade_atacado,
        p.preco_promocional,
        p.data_inicio_promocao,
        p.data_fim_promocao,
        COALESCE(SUM(oi.quantidade), 0) AS total_vendido,
        ROUND(((p.preco_varejo - p.preco_promocional) / p.preco_varejo * 100), 1) AS desconto_percentual
    FROM produtos p
    LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
    WHERE p.status = 'ativo' 
        AND LOWER(p.categoria) = LOWER(%(category)s)
        AND p.preco_promocional IS NOT NULL
        AND p.preco_promocional > 0
        AND (p.data_inicio_promocao IS NULL OR p.data_inicio_promocao <= CURRENT_DATE)
        AND (p.data_fim_promocao IS NULL OR p.data_fim_promocao >= CURRENT_DATE)
    GROUP BY p.codprod, p.descricao, p.categoria, p.marca, p.unidade_venda,
             p.preco_varejo, p.preco_atacado, p.quantidade_atacado,
             p.preco_promocional, p.data_inicio_promocao, p.data_fim_promocao
    ORDER BY desconto_percentual DESC, total_vendido DESC, p.descricao ASC
    LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'category': categoria.strip(), 'limit': limite, 'offset': offset}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                promocoes = [_converter_linha_para_dicionario(linha) for linha in resultados]
                
                logging.info(f"Encontradas {len(promocoes)} promoções na categoria '{categoria}'")
                return promocoes
                
    except Exception as e:
        logging.error(f"Erro ao buscar promoções da categoria '{categoria}': {e}")
        return []

@cache_query()
def obter_todas_promocoes_ativas(limite: int = 20, offset: int = 0) -> List[Dict]:
    """Busca todas as promoções ativas independente de categoria.

    Args:
        limite: O número máximo de promoções a serem retornadas.
        offset: O deslocamento para paginação.

    Returns:
        Uma lista de dicionários com todas as promoções ativas.
    """
    logging.debug(f"Buscando todas as promoções ativas com limite {limite} e offset {offset}.")
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.categoria,
        p.marca,
        p.unidade_venda,
        p.preco_varejo,
        p.preco_atacado,
        p.quantidade_atacado,
        p.preco_promocional,
        p.data_inicio_promocao,
        p.data_fim_promocao,
        COALESCE(SUM(oi.quantidade), 0) AS total_vendido,
        ROUND(((p.preco_varejo - p.preco_promocional) / p.preco_varejo * 100), 1) AS desconto_percentual
    FROM produtos p
    LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
    WHERE p.status = 'ativo' 
        AND p.preco_promocional IS NOT NULL
        AND p.preco_promocional > 0
        AND (p.data_inicio_promocao IS NULL OR p.data_inicio_promocao <= CURRENT_DATE)
        AND (p.data_fim_promocao IS NULL OR p.data_fim_promocao >= CURRENT_DATE)
    GROUP BY p.codprod, p.descricao, p.categoria, p.marca, p.unidade_venda,
             p.preco_varejo, p.preco_atacado, p.quantidade_atacado,
             p.preco_promocional, p.data_inicio_promocao, p.data_fim_promocao
    ORDER BY desconto_percentual DESC, total_vendido DESC, p.descricao ASC
    LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'limit': limite, 'offset': offset}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                promocoes = [_converter_linha_para_dicionario(linha) for linha in resultados]
                
                logging.info(f"Encontradas {len(promocoes)} promoções ativas no total")
                return promocoes
                
    except Exception as e:
        logging.error(f"Erro ao buscar todas as promoções ativas: {e}")
        return []

@cache_query()
def obter_produtos_promocionais_por_termo(termo: str, limite: int = 10, offset: int = 0) -> List[Dict]:
    """Busca produtos promocionais por termo (marca, nome, etc) na tabela produtos_promocao.
    
    Args:
        termo: Termo de busca (marca ou nome do produto).
        limite: O número máximo de produtos a serem retornados.
        offset: O deslocamento para paginação.
    
    Returns:
        Uma lista de dicionários com os produtos promocionais encontrados.
    """
    logging.debug(f"Buscando produtos promocionais por termo '{termo}' com limite {limite} e offset {offset}.")
    if not termo or len(termo.strip()) < 2:
        logging.debug("Termo de busca inválido para promoções.")
        return []
    
    termo_busca = f"%{termo.strip().lower()}%"
    
    sql = """
    SELECT 
        pp.codprod,
        pp.descricao,
        pp.categoria,
        pp.marca,
        pp.unidade_venda,
        pp.preco_varejo,
        pp.preco_atacado,
        pp.quantidade_atacado,
        pp.preco_promocional,
        pp.preco_atual,
        pp.percentual_desconto,
        pp.data_inicio_promocao,
        pp.data_fim_promocao,
        COALESCE(SUM(oi.quantidade), 0) AS total_vendido
    FROM produtos_promocao pp
    LEFT JOIN orcamento_itens oi ON pp.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
    WHERE pp.status = 'ativo' 
        AND (
            LOWER(pp.descricao) LIKE %(termo)s 
            OR LOWER(pp.marca) LIKE %(termo)s
            OR LOWER(pp.categoria) LIKE %(termo)s
        )
        AND (pp.data_inicio_promocao IS NULL OR pp.data_inicio_promocao <= CURRENT_DATE)
        AND (pp.data_fim_promocao IS NULL OR pp.data_fim_promocao >= CURRENT_DATE)
    GROUP BY pp.codprod, pp.descricao, pp.categoria, pp.marca, pp.unidade_venda,
             pp.preco_varejo, pp.preco_atacado, pp.quantidade_atacado,
             pp.preco_promocional, pp.preco_atual, pp.percentual_desconto,
             pp.data_inicio_promocao, pp.data_fim_promocao
    ORDER BY pp.percentual_desconto DESC, total_vendido DESC, pp.descricao ASC
    LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'termo': termo_busca, 'limit': limite, 'offset': offset}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                promocoes = [_converter_linha_para_dicionario(linha) for linha in resultados]
                
                logging.info(f"Encontradas {len(promocoes)} promoções para termo '{termo}'")
                return promocoes
                
    except Exception as e:
        logging.error(f"Erro ao buscar promoções por termo '{termo}': {e}")
        return []

@cache_query()
def obter_categorias_disponiveis() -> List[str]:
    """Retorna todas as categorias disponíveis no banco de dados.

    Returns:
        Uma lista de strings com as categorias.
    """
    logging.debug("Buscando todas as categorias disponíveis.")
    sql = """
    SELECT DISTINCT LOWER(categoria) as categoria
    FROM produtos 
    WHERE status = 'ativo' 
        AND categoria IS NOT NULL 
        AND TRIM(categoria) != ''
    ORDER BY categoria ASC;
    """
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql)
                resultados = cursor.fetchall()
                categorias = [linha[0] for linha in resultados if linha[0]]
                
                logging.info(f"Encontradas {len(categorias)} categorias no banco de dados")
                return categorias
                
    except Exception as e:
        logging.error(f"Erro ao buscar categorias disponíveis: {e}")
        return []

def validar_datas_promocionais():
    """Valida e corrige datas promocionais inconsistentes."""
    logging.debug("Validando datas promocionais.")
    estatisticas_validacao = {
        "total_promocoes": 0,
        "datas_invalidas_corrigidas": 0,
        "promocoes_expiradas_encontradas": 0,
        "promocoes_ativas": 0
    }
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM produtos 
                    WHERE preco_promocional IS NOT NULL AND preco_promocional > 0;
                """)
                estatisticas_validacao["total_promocoes"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    UPDATE produtos 
                    SET data_fim_promocao = NULL 
                    WHERE preco_promocional IS NOT NULL 
                        AND data_inicio_promocao IS NOT NULL 
                        AND data_fim_promocao IS NOT NULL
                        AND data_inicio_promocao > data_fim_promocao;
                """)
                estatisticas_validacao["datas_invalidas_corrigidas"] = cursor.rowcount
                
                cursor.execute("""
                    SELECT COUNT(*) FROM produtos 
                    WHERE preco_promocional IS NOT NULL 
                        AND preco_promocional > 0
                        AND data_fim_promocao IS NOT NULL
                        AND data_fim_promocao < CURRENT_DATE;
                """)
                estatisticas_validacao["promocoes_expiradas_encontradas"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM produtos 
                    WHERE preco_promocional IS NOT NULL 
                        AND preco_promocional > 0
                        AND (data_inicio_promocao IS NULL OR data_inicio_promocao <= CURRENT_DATE)
                        AND (data_fim_promocao IS NULL OR data_fim_promocao >= CURRENT_DATE);
                """)
                estatisticas_validacao["promocoes_ativas"] = cursor.fetchone()[0]
                
                conexao.commit()
                logging.info(f"Validação promocional concluída: {estatisticas_validacao}")
                
    except Exception as e:
        logging.error(f"Erro na validação de datas promocionais: {e}")
        estatisticas_validacao["error"] = str(e)
    
    return estatisticas_validacao

def testar_conexao():
    """Testa a conexão com o banco de dados.

    Returns:
        True se a conexão for bem-sucedida, False caso contrário.
    """
    logging.debug("Testando conexão com o banco de dados.")
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT 1;")
                resultado = cursor.fetchone()
                logging.info("Conexão com banco de dados OK")
                return resultado[0] == 1
    except Exception as e:
        logging.error(f"Falha no teste de conexão: {e}")
        return False

def obter_contagem_produtos() -> int:
    """Retorna o total de produtos ativos.

    Returns:
        O número total de produtos ativos.
    """
    logging.debug("Contando o número de produtos ativos.")
    sql = "SELECT COUNT(*) FROM produtos WHERE status = 'ativo';"
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql)
                resultado = cursor.fetchone()
                logging.debug(f"Total de produtos ativos: {resultado[0] if resultado else 0}")
                return resultado[0] if resultado else 0
    except Exception as e:
        logging.error(f"Erro ao contar produtos: {e}")
        return 0

def obter_saude_banco_dados() -> Dict:
    """Retorna informações de saúde do banco de dados.

    Returns:
        Um dicionário com as informações de saúde do banco de dados.
    """
    logging.debug("Verificando a saúde do banco de dados.")
    info_saude = {
        "conexao_ok": False,
        "total_produtos": 0,
        "buscas_recentes": 0,
        "pedidos_recentes": 0,
        "tamanho_banco_dados": "N/A"
    }
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                info_saude["conexao_ok"] = True
                
                cursor.execute("SELECT COUNT(*) FROM produtos WHERE status = 'ativo';")
                info_saude["total_produtos"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM estatisticas_busca 
                    WHERE timestamp >= NOW() - INTERVAL 1 DAY;
                """)
                info_saude["buscas_recentes"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM orcamentos 
                    WHERE created_at >= NOW() - INTERVAL 1 DAY;
                """)
                info_saude["pedidos_recentes"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database()));
                """)
                info_saude["tamanho_banco_dados"] = cursor.fetchone()[0]
                
    except Exception as e:
        logging.error(f"Erro ao verificar saúde do banco: {e}")
        info_saude["conexao_ok"] = False
    
    logging.debug(f"Saúde do banco de dados: {info_saude}")
    return info_saude

def executar_diagnosticos_banco_dados() -> Dict:
    """Executa diagnósticos completos do banco de dados.

    Returns:
        Um dicionário com os resultados dos diagnósticos.
    """
    logging.debug("Executando diagnósticos do banco de dados.")
    diagnosticos = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "saude": obter_saude_banco_dados(),
        "termos_populares": obter_termos_busca_populares(5),
        "produtos_top": obter_estatisticas_performance_produto(7),
        "qualidade_busca": {}
    }
    
    try:
        estatisticas = obter_estatisticas_busca(7)
        total_buscas = sum(stat.get('total_buscas', 0) for stat in estatisticas)
        total_acertos = sum(stat.get('acertos', 0) for stat in estatisticas)
        
        diagnosticos["qualidade_busca"] = {
            "total_buscas_semana": total_buscas,
            "taxa_sucesso": (total_acertos / total_buscas * 100) if total_buscas > 0 else 0,
            "uso_base_conhecimento": len([s for s in estatisticas if s.get('fonte_resultado') == 'knowledge_base']),
            "uso_fallback_banco_dados": len([s for s in estatisticas if s.get('fonte_resultado') == 'db_fallback'])
        }
        
    except Exception as e:
        logging.error(f"Erro na análise de qualidade de buscas: {e}")
        diagnosticos["qualidade_busca"] = {"error": str(e)}
    
    logging.debug(f"Diagnósticos do banco de dados: {diagnosticos}")
    return diagnosticos

def obter_promocoes_mais_baratas(limite: int = 10, offset: int = 0) -> List[Dict]:
    """Busca as promoções mais baratas por preço promocional.

    Args:
        limite: O número máximo de promoções a serem retornadas.
        offset: O deslocamento para paginação.

    Returns:
        Uma lista de dicionários com as promoções mais baratas.
    """
    logging.debug(f"Buscando as {limite} promoções mais baratas com offset {offset}.")
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.categoria,
        p.marca,
        p.unidade_venda,
        p.preco_varejo,
        p.preco_atacado,
        p.quantidade_atacado,
        p.preco_promocional,
        p.data_inicio_promocao,
        p.data_fim_promocao,
        COALESCE(SUM(oi.quantidade), 0) AS total_vendido,
        ROUND(((p.preco_varejo - p.preco_promocional) / p.preco_varejo * 100), 1) AS desconto_percentual
    FROM produtos p
    LEFT JOIN orcamento_itens oi ON p.codprod = oi.codprod
    LEFT JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento
    WHERE p.status = 'ativo' 
        AND p.preco_promocional IS NOT NULL
        AND p.preco_promocional > 0
        AND (p.data_inicio_promocao IS NULL OR p.data_inicio_promocao <= CURRENT_DATE)
        AND (p.data_fim_promocao IS NULL OR p.data_fim_promocao >= CURRENT_DATE)
    GROUP BY p.codprod, p.descricao, p.categoria, p.marca, p.unidade_venda,
             p.preco_varejo, p.preco_atacado, p.quantidade_atacado,
             p.preco_promocional, p.data_inicio_promocao, p.data_fim_promocao
    ORDER BY p.preco_promocional ASC, total_vendido DESC, p.descricao ASC
    LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'limit': limite, 'offset': offset}
    
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                resultados = cursor.fetchall()
                promocoes = [_converter_linha_para_dicionario(linha) for linha in resultados]
                
                logging.info(f"Encontradas {len(promocoes)} promoções mais baratas")
                return promocoes
                
    except Exception as e:
        logging.error(f"Erro ao buscar promoções mais baratas: {e}")
        return []

# ===== FUNÇÕES DE MANUTENÇÃO AUTOMÁTICA =====

def iniciar_manutencao_automatica():
    """Inicia tarefas de manutenção automática do banco"""
    try:
        # Limpeza semanal de estatísticas antigas
        schedule.every().sunday.at("02:00").do(limpar_estatisticas_antigas)
        
        # Otimização diária do banco
        schedule.every().day.at("03:00").do(otimizar_banco_dados)
        
        # Validação de promoções diária
        schedule.every().day.at("01:00").do(validar_datas_promocionais)
        
        # Diagnósticos semanais
        schedule.every().monday.at("04:00").do(executar_diagnosticos_banco_dados)
        
        def executar_agendador():
            """Executa o agendador em thread separada"""
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(3600)  # Verifica a cada hora
                except Exception as e:
                    logging.error(f"Erro no agendador de manutenção: {e}")
                    time.sleep(3600)  # Continua tentando após erro
        
        thread_agendador = threading.Thread(target=executar_agendador, daemon=True)
        thread_agendador.start()
        
        logging.info("Sistema de manutenção automática do banco iniciado com sucesso")
        return True
        
    except Exception as e:
        logging.error(f"Erro ao iniciar manutenção automática: {e}")
        return False

def executar_manutencao_completa():
    """Executa manutenção completa do banco de dados"""
    logging.info("Iniciando manutenção completa do banco de dados")
    
    resultados = {
        "limpeza_estatisticas": False,
        "otimizacao_banco": False, 
        "validacao_promocoes": False,
        "diagnosticos": None
    }
    
    try:
        # 1. Limpeza de estatísticas antigas
        estatisticas_removidas = limpar_estatisticas_antigas()
        if estatisticas_removidas >= 0:
            resultados["limpeza_estatisticas"] = True
            logging.info(f"Limpeza concluída: {estatisticas_removidas} registros removidos")
        
        # 2. Otimização do banco
        resultados["otimizacao_banco"] = otimizar_banco_dados()
        if resultados["otimizacao_banco"]:
            logging.info("Otimização do banco concluída")
        
        # 3. Validação de promoções
        validacao_resultado = validar_datas_promocionais()
        if not validacao_resultado.get("error"):
            resultados["validacao_promocoes"] = True
            logging.info("Validação de promoções concluída")
        
        # 4. Diagnósticos
        resultados["diagnosticos"] = executar_diagnosticos_banco_dados()
        
        logging.info(f"Manutenção completa finalizada: {resultados}")
        return resultados
        
    except Exception as e:
        logging.error(f"Erro durante manutenção completa: {e}")
        return resultados

def verificar_saude_sistema():
    """Verifica saúde geral do sistema de banco de dados"""
    try:
        saude = obter_saude_banco_dados()
        
        # Critérios de saúde
        problemas = []
        
        if not saude.get("conexao_ok"):
            problemas.append("Conexão com banco falhou")
        
        if saude.get("total_produtos", 0) < 10:
            problemas.append("Poucos produtos no banco")
        
        if saude.get("buscas_recentes", 0) == 0:
            problemas.append("Nenhuma busca recente registrada")
        
        status = "SAUDÁVEL" if not problemas else "COM PROBLEMAS"
        
        resultado = {
            "status": status,
            "problemas": problemas,
            "metricas": saude,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if problemas:
            logging.warning(f"Problemas de saúde detectados: {problemas}")
        else:
            logging.info("Sistema de banco de dados saudável")
        
        return resultado
        
    except Exception as e:
        logging.error(f"Erro ao verificar saúde do sistema: {e}")
        return {
            "status": "ERRO",
            "problemas": [f"Falha na verificação: {str(e)}"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }