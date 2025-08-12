# file: IA/db/database.py
import os, sys
from pathlib import Path
import logging
import psycopg2
from psycopg2.extras import DictCursor, RealDictCursor
from dotenv import load_dotenv
from typing import Union, List, Dict
import time
import decimal

# Adiciona utils ao path se não estiver
utils_path = Path(__file__).resolve().parent.parent / "utils"
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

from fuzzy_search import fuzzy_search_products, fuzzy_engine

load_dotenv(dotenv_path='.env') # Garante que o .env da pasta IA seja lido

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

DATABASE_URL = f"dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}' host='{DB_HOST}' port='{DB_PORT}'"

def get_connection():
    """Estabelece uma conexão com o PostgreSQL, com uma lógica de retry."""
    retries = 5
    delay = 3
    for i in range(retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except psycopg2.OperationalError as e:
            logging.warning(f"Conexão falhou: {e}. Tentando novamente em {delay}s...")
            time.sleep(delay)
    logging.error("Não foi possível conectar ao banco de dados após várias tentativas.")
    raise Exception("Não foi possível conectar ao banco de dados.")

def _convert_row_to_dict(row: DictCursor) -> Dict:
    """Converte uma linha do cursor para um dicionário, tratando Decimals."""
    if not row:
        return None
    row_dict = dict(row)
    for key, value in row_dict.items():
        if isinstance(value, decimal.Decimal):
            row_dict[key] = float(value)
    return row_dict

# --- Funções de Consulta ---

def find_customer_by_cnpj(cnpj: str) -> Union[Dict, None]:
    """Busca um cliente pelo CNPJ."""
    sql = "SELECT cnpj, nome FROM clientes WHERE cnpj = %(cnpj)s;"
    params = {'cnpj': cnpj}
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                result = cursor.fetchone()
                return _convert_row_to_dict(result) if result else None
    except Exception as e:
        logging.error(f"Erro ao buscar cliente por CNPJ {cnpj}: {e}")
        return None

def get_top_selling_products(limit: int = 5, offset: int = 0, filial: int = 17) -> List[Dict]:
    """Busca os produtos mais vendidos com base no histórico de orçamentos."""
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.unidade_venda,
        p.preco_varejo AS pvenda,
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
    params = {'limit': limit, 'offset': offset}
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                return [_convert_row_to_dict(row) for row in results]
    except Exception as e:
        logging.error(f"Erro ao buscar produtos mais vendidos: {e}")
        return []

def get_top_selling_products_by_name(product_name: str, limit: int = 5, offset: int = 0) -> List[Dict]:
    """Busca produtos por nome com ranking de vendas."""
    if not product_name or len(product_name.strip()) < 2:
        return []
    
    # Preparação da string de busca para ILIKE
    search_pattern = f"%{product_name.strip().lower()}%"
    
    sql = """
    SELECT 
        p.codprod,
        p.descricao,
        p.unidade_venda,
        p.preco_varejo AS pvenda,
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
    params = {'pattern': search_pattern, 'limit': limit, 'offset': offset}
    
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                return [_convert_row_to_dict(row) for row in results]
    except Exception as e:
        logging.error(f"Erro ao buscar produtos por nome '{product_name}': {e}")
        return []

def search_products_with_suggestions(product_name: str, limit: int = 5, offset: int = 0) -> Dict:
    """
    🆕 NOVA FUNÇÃO: Busca produtos com sugestões inteligentes e fuzzy search.
    
    Returns:
        Dict com 'products', 'suggestions', 'search_quality'
    """
    if not product_name or len(product_name.strip()) < 2:
        return {"products": [], "suggestions": [], "search_quality": "invalid"}
    
    # Etapa 1: Busca exata no banco
    exact_products = get_top_selling_products_by_name(product_name, limit, offset)
    
    if exact_products:
        return {
            "products": exact_products,
            "suggestions": [],
            "search_quality": "exact"
        }
    
    # Etapa 2: Busca fuzzy no banco
    fuzzy_products = fuzzy_search_products(product_name, limit)
    
    if fuzzy_products:
        return {
            "products": fuzzy_products,
            "suggestions": [],
            "search_quality": "fuzzy"
        }
    
    # Etapa 3: Gera sugestões de correção
    suggestions = []
    corrected_term = fuzzy_engine.apply_corrections(product_name)
    
    if corrected_term != product_name.lower().strip():
        # Testa termo corrigido
        corrected_products = get_top_selling_products_by_name(corrected_term, 3)
        if corrected_products:
            suggestions.append(corrected_term)
    
    # Sugestões baseadas em sinônimos
    synonyms = fuzzy_engine.expand_with_synonyms(product_name)
    for synonym in synonyms[:2]:  # Máximo 2 sugestões
        if synonym != product_name.lower():
            suggestions.append(synonym)
    
    return {
        "products": [],
        "suggestions": suggestions[:3],  # Máximo 3 conforme especificação
        "search_quality": "no_results"
    }

def get_product_by_codprod(codprod: int) -> Union[Dict, None]:
    """Busca um produto específico pelo código."""
    if not codprod or codprod <= 0:
        return None
    
    sql = """
    SELECT 
        codprod,
        descricao,
        unidade_venda,
        preco_varejo AS pvenda,
        preco_atacado,
        quantidade_atacado,
        status
    FROM produtos 
    WHERE codprod = %(codprod)s AND status = 'ativo';
    """
    params = {'codprod': codprod}
    
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                result = cursor.fetchone()
                return _convert_row_to_dict(result) if result else None
    except Exception as e:
        logging.error(f"Erro ao buscar produto por código {codprod}: {e}")
        return None

def get_product_details_fuzzy(search_term: str) -> List[Dict]:
    """
    🆕 NOVA FUNÇÃO: Busca produtos com detalhes usando fuzzy search avançado.
    """
    if not search_term or len(search_term.strip()) < 2:
        return []
    
    # Primeiro tenta busca exata
    exact_results = get_top_selling_products_by_name(search_term, 5)
    if exact_results:
        return exact_results
    
    # Usa fuzzy search como fallback
    return fuzzy_search_products(search_term, 5)

def get_all_active_products() -> List[Dict]:
    """Retorna todos os produtos ativos para geração da base de conhecimento."""
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
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
                return [_convert_row_to_dict(row) for row in results]
    except Exception as e:
        logging.error(f"Erro ao buscar todos os produtos ativos: {e}")
        return []

# --- Funções de Estatísticas e Análise ---

def add_search_statistic(search_term: str, result_source: str, suggested_codprod: int = None, feedback: str = "sem_feedback"):
    """
    🆕 FUNÇÃO APRIMORADA: Adiciona estatística de busca com mais detalhes.
    """
    if not search_term:
        return
        
    sql = """
    INSERT INTO estatisticas_busca 
    (termo_busca, fonte_resultado, codprod_sugerido, feedback_usuario, timestamp) 
    VALUES (%(term)s, %(source)s, %(codprod)s, %(feedback)s, NOW());
    """
    params = {
        'term': search_term[:255],  # Limita tamanho
        'source': result_source,
        'codprod': suggested_codprod,
        'feedback': feedback
    }
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                conn.commit()
                logging.debug(f"Estatística de busca adicionada: {search_term} -> {result_source}")
    except Exception as e:
        logging.error(f"Erro ao adicionar estatística de busca: {e}")

def update_search_feedback(id_estatistica: int, feedback: str):
    """Atualiza feedback de uma busca específica."""
    if not id_estatistica: 
        return
        
    sql = "UPDATE estatisticas_busca SET feedback_usuario = %(feedback)s WHERE id_estatistica = %(id)s;"
    params = {'feedback': feedback, 'id': id_estatistica}
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                conn.commit()
    except Exception as e:
        logging.error(f"Falha ao atualizar feedback de busca: {e}")

def get_search_statistics(days: int = 7) -> List[Dict]:
    """
    🆕 NOVA FUNÇÃO: Retorna estatísticas de busca dos últimos N dias.
    """
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
    params = {'days': days}
    
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                return [_convert_row_to_dict(row) for row in results]
    except Exception as e:
        logging.error(f"Erro ao buscar estatísticas: {e}")
        return []

# --- Funções de Orçamento/Carrinho ---

def create_orcamento(cnpj_cliente: str, id_loja: int = 1) -> Union[int, None]:
    """Cria um novo orçamento e retorna o ID."""
    sql = """
    INSERT INTO orcamentos (cnpj_cliente, id_loja, status, criado_em) 
    VALUES (%(cnpj)s, %(loja)s, 'aberto', NOW())
    RETURNING id_orcamento;
    """
    params = {'cnpj': cnpj_cliente, 'loja': id_loja}
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
    except Exception as e:
        logging.error(f"Erro ao criar orçamento: {e}")
        return None

def add_item_to_orcamento(id_orcamento: int, codprod: int, quantidade: float, tipo_preco: str = 'varejo'):
    """Adiciona item ao orçamento."""
    # Busca preço atual do produto
    product = get_product_by_codprod(codprod)
    if not product:
        return False
    
    preco_unitario = product.get('preco_atacado' if tipo_preco == 'atacado' else 'pvenda', 0.0)
    
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
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                conn.commit()
                return True
    except Exception as e:
        logging.error(f"Erro ao adicionar item ao orçamento: {e}")
        return False

def finalize_orcamento(id_orcamento: int) -> bool:
    """Finaliza um orçamento calculando o valor total."""
    # Calcula valor total
    sql_total = """
    SELECT SUM(quantidade * preco_unitario_gravado) as total
    FROM orcamento_itens 
    WHERE id_orcamento = %(id)s;
    """
    
    # Atualiza orçamento
    sql_update = """
    UPDATE orcamentos 
    SET valor_total = %(total)s, status = 'finalizado', finalizado_em = NOW()
    WHERE id_orcamento = %(id)s;
    """
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # Calcula total
                cursor.execute(sql_total, {'id': id_orcamento})
                result = cursor.fetchone()
                total = result[0] if result and result[0] else 0.0
                
                # Atualiza orçamento
                cursor.execute(sql_update, {'id': id_orcamento, 'total': total})
                conn.commit()
                
                logging.info(f"Orçamento {id_orcamento} finalizado com total: R$ {total:.2f}")
                return True
                
    except Exception as e:
        logging.error(f"Erro ao finalizar orçamento {id_orcamento}: {e}")
        return False

# --- Funções de Análise e Relatórios ---

def get_popular_search_terms(limit: int = 10) -> List[Dict]:
    """
    🆕 NOVA FUNÇÃO: Retorna termos de busca mais populares.
    """
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
    params = {'limit': limit}
    
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                return [_convert_row_to_dict(row) for row in results]
    except Exception as e:
        logging.error(f"Erro ao buscar termos populares: {e}")
        return []

def get_product_performance_stats(days: int = 30) -> List[Dict]:
    """
    🆕 NOVA FUNÇÃO: Retorna estatísticas de performance dos produtos.
    """
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
        AND o.criado_em >= NOW() - INTERVAL %(days)s DAY
    WHERE p.status = 'ativo'
    GROUP BY p.codprod, p.descricao
    HAVING COUNT(DISTINCT e.id_estatistica) > 0 OR COUNT(DISTINCT o.id_orcamento) > 0
    ORDER BY receita_recente DESC, buscas_recentes DESC
    LIMIT 20;
    """
    params = {'days': days}
    
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                return [_convert_row_to_dict(row) for row in results]
    except Exception as e:
        logging.error(f"Erro ao buscar estatísticas de performance: {e}")
        return []

# --- Funções de Manutenção ---

def cleanup_old_statistics(days: int = 90):
    """
    🆕 NOVA FUNÇÃO: Remove estatísticas antigas para manter performance.
    """
    sql = "DELETE FROM estatisticas_busca WHERE timestamp < NOW() - INTERVAL %(days)s DAY;"
    params = {'days': days}
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                deleted_count = cursor.rowcount
                conn.commit()
                logging.info(f"Removidas {deleted_count} estatísticas antigas (>{days} dias)")
                return deleted_count
    except Exception as e:
        logging.error(f"Erro ao limpar estatísticas antigas: {e}")
        return 0

def optimize_database():
    """
    🆕 NOVA FUNÇÃO: Executa otimizações básicas no banco.
    """
    optimization_queries = [
        "VACUUM ANALYZE produtos;",
        "VACUUM ANALYZE estatisticas_busca;",
        "VACUUM ANALYZE orcamentos;",
        "VACUUM ANALYZE orcamento_itens;",
    ]
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                for query in optimization_queries:
                    cursor.execute(query)
                conn.commit()
                logging.info("Otimização do banco de dados concluída")
                return True
    except Exception as e:
        logging.error(f"Erro na otimização do banco: {e}")
        return False

# --- Funções de Teste e Diagnóstico ---

def test_connection():
    """Testa a conexão com o banco de dados."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
                result = cursor.fetchone()
                logging.info("Conexão com banco de dados OK")
                return result[0] == 1
    except Exception as e:
        logging.error(f"Falha no teste de conexão: {e}")
        return False

def get_products_count() -> int:
    """Retorna o total de produtos ativos."""
    sql = "SELECT COUNT(*) FROM produtos WHERE status = 'ativo';"
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                result = cursor.fetchone()
                return result[0] if result else 0
    except Exception as e:
        logging.error(f"Erro ao contar produtos: {e}")
        return 0

def get_database_health() -> Dict:
    """
    🆕 NOVA FUNÇÃO: Retorna informações de saúde do banco de dados.
    """
    health_info = {
        "connection_ok": False,
        "total_products": 0,
        "recent_searches": 0,
        "recent_orders": 0,
        "database_size": "N/A"
    }
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                health_info["connection_ok"] = True
                
                # Total de produtos ativos
                cursor.execute("SELECT COUNT(*) FROM produtos WHERE status = 'ativo';")
                health_info["total_products"] = cursor.fetchone()[0]
                
                # Buscas recentes (último dia)
                cursor.execute("""
                    SELECT COUNT(*) FROM estatisticas_busca 
                    WHERE timestamp >= NOW() - INTERVAL 1 DAY;
                """)
                health_info["recent_searches"] = cursor.fetchone()[0]
                
                # Orçamentos recentes (último dia)
                cursor.execute("""
                    SELECT COUNT(*) FROM orcamentos 
                    WHERE criado_em >= NOW() - INTERVAL 1 DAY;
                """)
                health_info["recent_orders"] = cursor.fetchone()[0]
                
                # Tamanho do banco de dados
                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database()));
                """)
                health_info["database_size"] = cursor.fetchone()[0]
                
    except Exception as e:
        logging.error(f"Erro ao verificar saúde do banco: {e}")
        health_info["connection_ok"] = False
    
    return health_info

def run_database_diagnostics() -> Dict:
    """
    🆕 NOVA FUNÇÃO: Executa diagnósticos completos do banco.
    """
    diagnostics = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health": get_database_health(),
        "popular_terms": get_popular_search_terms(5),
        "top_products": get_product_performance_stats(7),
        "search_quality": {}
    }
    
    # Analisa qualidade das buscas
    try:
        stats = get_search_statistics(7)
        total_searches = sum(stat.get('total_buscas', 0) for stat in stats)
        total_hits = sum(stat.get('acertos', 0) for stat in stats)
        
        diagnostics["search_quality"] = {
            "total_searches_week": total_searches,
            "success_rate": (total_hits / total_searches * 100) if total_searches > 0 else 0,
            "knowledge_base_usage": len([s for s in stats if s.get('fonte_resultado') == 'knowledge_base']),
            "database_fallback_usage": len([s for s in stats if s.get('fonte_resultado') == 'db_fallback'])
        }
        
    except Exception as e:
        logging.error(f"Erro na análise de qualidade de buscas: {e}")
        diagnostics["search_quality"] = {"error": str(e)}
    
    return diagnostics