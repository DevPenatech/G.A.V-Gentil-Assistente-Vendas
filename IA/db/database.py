# file: IA/db/database.py
import os
import logging
import psycopg2
from psycopg2.extras import DictCursor, RealDictCursor
from dotenv import load_dotenv
from typing import Union, List, Dict
import time
import decimal

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
        SELECT p.codprod, p.descricao, p.preco_varejo as pvenda 
        FROM orcamento_itens oi 
        JOIN produtos p ON oi.codprod = p.codprod 
        JOIN orcamentos o ON oi.id_orcamento = o.id_orcamento 
        WHERE o.id_loja = %(id_loja)s AND p.status = 'ativo'
        GROUP BY p.codprod, p.descricao, p.preco_varejo 
        ORDER BY SUM(oi.quantidade) DESC 
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'limit': limit, 'offset': offset, 'id_loja': filial}
    products = []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall(): 
                    converted = _convert_row_to_dict(row)
                    if converted:
                        products.append(converted)
    except Exception as e:
        logging.error(f"Erro ao buscar produtos mais vendidos: {e}")
    return products

def get_top_selling_products_by_name(product_name: str, limit: int = 5, offset: int = 0) -> List[Dict]:
    """Busca produtos por nome ou termo relacionado."""
    if not product_name:
        return []
        
    search_term = f"%{product_name}%"
    sql = """
        SELECT p.codprod, p.descricao, p.preco_varejo as pvenda 
        FROM produtos p 
        WHERE p.descricao ILIKE %(search_term)s AND p.status = 'ativo' 
        ORDER BY p.descricao 
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    params = {'search_term': search_term, 'limit': limit, 'offset': offset}
    products = []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall(): 
                    converted = _convert_row_to_dict(row)
                    if converted:
                        products.append(converted)
    except Exception as e:
        logging.error(f"Erro ao buscar produtos por nome '{product_name}': {e}")
    return products

def get_product_by_codprod(codprod: int) -> Union[Dict, None]:
    """Busca um produto específico pelo código do produto."""
    if not codprod:
        return None
        
    sql = "SELECT codprod, descricao, preco_varejo as pvenda FROM produtos WHERE codprod = %(codprod)s AND status = 'ativo';"
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

def get_product_details(product_name: str) -> Union[Dict, None]:
    """Busca o produto mais similar ao nome fornecido."""
    if not product_name:
        return None
        
    search_term = f"%{product_name}%"
    sql = """
        SELECT codprod, descricao, preco_varejo as pvenda 
        FROM produtos 
        WHERE descricao ILIKE %(search_term)s AND status = 'ativo' 
        ORDER BY LENGTH(descricao) ASC 
        LIMIT 1;
    """
    params = {'search_term': search_term}
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                result = cursor.fetchone()
                return _convert_row_to_dict(result) if result else None
    except Exception as e:
        logging.error(f"Erro ao buscar detalhes do produto '{product_name}': {e}")
        return None

def get_last_order_items(cnpj: str) -> List[Dict]:
    """Busca os itens do último pedido finalizado de um cliente."""
    if not cnpj:
        return []
        
    sql = """
        SELECT p.codprod, p.descricao, oi.quantidade AS qt, oi.preco_unitario_gravado AS pvenda 
        FROM orcamento_itens oi 
        JOIN produtos p ON oi.codprod = p.codprod 
        WHERE oi.id_orcamento = (
            SELECT id_orcamento 
            FROM orcamentos 
            WHERE cnpj_cliente = %(cnpj)s AND status = 'finalizado' 
            ORDER BY finalizado_em DESC 
            LIMIT 1
        );
    """
    params = {'cnpj': cnpj}
    items = []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall(): 
                    converted = _convert_row_to_dict(row)
                    if converted:
                        items.append(converted)
    except Exception as e:
        logging.error(f"Erro ao buscar último pedido do cliente {cnpj}: {e}")
    return items

def search_products_by_category_terms(terms: List[str], limit: int = 5, offset: int = 0) -> List[Dict]:
    """
    Busca produtos cuja descrição contenha QUALQUER um dos termos fornecidos.
    """
    if not terms:
        return []
    
    where_clauses = " OR ".join([f"p.descricao ILIKE %(term_{i})s" for i in range(len(terms))])
    
    sql = f"""
        SELECT p.codprod, p.descricao, p.preco_varejo as pvenda
        FROM produtos p
        WHERE ({where_clauses}) AND p.status = 'ativo'
        ORDER BY p.descricao
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    
    params = {'limit': limit, 'offset': offset}
    for i, term in enumerate(terms):
        params[f'term_{i}'] = f'%{term}%'
        
    logging.info(f"Executando SQL de Categoria com Parâmetros: {params}")
    products = []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    converted = _convert_row_to_dict(row)
                    if converted:
                        products.append(converted)
    except Exception as e:
        logging.error(f"Erro ao buscar produtos por categoria {terms}: {e}")
    return products

def get_all_products() -> List[Dict]:
    """Busca todos os produtos ativos para geração da base de conhecimento."""
    sql = "SELECT codprod, descricao FROM produtos WHERE status = 'ativo' ORDER BY codprod;"
    products = []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                for row in cursor.fetchall():
                    converted = _convert_row_to_dict(row)
                    if converted:
                        products.append(converted)
    except Exception as e:
        logging.error(f"Erro ao buscar todos os produtos: {e}")
    return products

# --- Funções de Estatísticas ---

def log_search_event(termo_busca: str, fonte_resultado: str, codprod_sugerido: int) -> int:
    """Registra um evento de busca para análise posterior."""
    sql = """
        INSERT INTO estatisticas_busca (termo_busca, fonte_resultado, codprod_sugerido, feedback_usuario) 
        VALUES (%(termo)s, %(fonte)s, %(codprod)s, 'sem_feedback') 
        RETURNING id_estatistica;
    """
    params = {'termo': termo_busca, 'fonte': fonte_resultado, 'codprod': codprod_sugerido}
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                new_id = cursor.fetchone()[0]
                conn.commit()
                return new_id
    except Exception as e:
        logging.error(f"Falha ao registrar evento de busca: {e}")
        return None

def update_search_feedback(id_estatistica: int, feedback: str):
    """Atualiza o feedback de um evento de busca."""
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