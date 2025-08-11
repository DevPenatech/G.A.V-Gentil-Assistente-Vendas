# file: session_manager.py
import json
import logging
import os
import re
from typing import List, Dict

import redis


# Inicializa o cliente Redis somente com senha se ela estiver configurada de fato
_redis_password = os.getenv("REDIS_PASSWORD")
_redis_config = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": 0,
    "decode_responses": True,
}

# Alguns ambientes definem REDIS_PASSWORD com valores fictícios como '<password>'.
# Isso faz com que o cliente envie um comando AUTH desnecessário e o Redis
# responda com erro, impedindo o carregamento/salvamento da sessão. Ao tratar
# valores vazios ou placeholders, evitamos a autenticação quando ela não é
# exigida.
if _redis_password and _redis_password != "<password>":
    _redis_config["password"] = _redis_password

redis_client = redis.Redis(**_redis_config)


def save_session(session_id: str, data: Dict):
    """Salva os dados da sessão no Redis com TTL de 1 hora e fallback para arquivo."""
    if not session_id or not data:
        logging.warning("[SESSION] Tentativa de salvar sessão com dados inválidos")
        return
        
    try:
        client = get_redis_client()
        if client:
            client.set(session_id, json.dumps(data), ex=3600)
            logging.debug(f"[SESSION] Sessão salva no Redis: {session_id}")
        else:
            # Fallback para arquivo se Redis não estiver disponível
            _save_session_to_file(session_id, data)
            
    except Exception as e:
        logging.error(f"[SESSION] Erro ao salvar sessão no Redis: {e}")
        # Fallback para arquivo
        _save_session_to_file(session_id, data)


def load_session(session_id: str) -> Dict:
    """Carrega os dados da sessão do Redis com fallback para arquivo."""
    if not session_id:
        logging.warning("[SESSION] Tentativa de carregar sessão sem ID")
        return {}
        
    try:
        client = get_redis_client()
        if client:
            raw = client.get(session_id)
            if raw:
                data = json.loads(raw)
                logging.debug(f"[SESSION] Sessão carregada do Redis: {session_id}")
                return data
        
        # Fallback para arquivo se não encontrar no Redis
        return _load_session_from_file(session_id)
        
    except Exception as e:
        logging.error(f"[SESSION] Erro ao carregar sessão do Redis: {e}")
        # Fallback para arquivo
        return _load_session_from_file(session_id)


def clear_session(session_id: str):
    """Remove os dados da sessão do Redis e arquivo."""
    if not session_id:
        return
        
    try:
        client = get_redis_client()
        if client:
            client.delete(session_id)
            logging.debug(f"[SESSION] Sessão removida do Redis: {session_id}")
        
        # Remove também do arquivo
        _clear_session_file(session_id)
        
    except Exception as e:
        logging.error(f"[SESSION] Erro ao limpar sessão: {e}")
        # Tenta remover do arquivo mesmo se Redis falhar
        _clear_session_file(session_id)

# Funções de fallback para arquivo
def _get_session_file_path(session_id: str) -> str:
    """Retorna caminho do arquivo de sessão."""
    # Sanitiza o session_id para nome de arquivo seguro
    safe_id = re.sub(r'[^\w\-_.]', '_', session_id)
    return f"data/session_{safe_id}.json"

def _save_session_to_file(session_id: str, data: Dict):
    """Salva sessão em arquivo como fallback."""
    try:
        os.makedirs("data", exist_ok=True)
        file_path = _get_session_file_path(session_id)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logging.info(f"[SESSION] Sessão salva em arquivo (fallback): {file_path}")
        
    except Exception as e:
        logging.error(f"[SESSION] Erro ao salvar sessão em arquivo: {e}")

def _load_session_from_file(session_id: str) -> Dict:
    """Carrega sessão de arquivo como fallback."""
    try:
        file_path = _get_session_file_path(session_id)
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logging.info(f"[SESSION] Sessão carregada de arquivo (fallback): {file_path}")
            return data
            
    except Exception as e:
        logging.error(f"[SESSION] Erro ao carregar sessão de arquivo: {e}")
    
    return {}

def _clear_session_file(session_id: str):
    """Remove arquivo de sessão."""
    try:
        file_path = _get_session_file_path(session_id)
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.debug(f"[SESSION] Arquivo de sessão removido: {file_path}")
    except Exception as e:
        logging.error(f"[SESSION] Erro ao remover arquivo de sessão: {e}")
    
def format_product_list_for_display(products: List[Dict], title: str, has_more: bool, offset: int = 0) -> str:
    if not products:
        return f"🤖 {title}\nNenhum produto encontrado com esse critério."
    
    response = f"🤖 {title}\n"
    for i, p in enumerate(products, 1 + offset):
        price = p.get('pvenda') or 0.0
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # 🆕 CORREÇÃO: Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')
        
        response += f"{i}. {product_name} - {price_str}\n"
    
    response += "Me diga o nome ou o número do item que deseja adicionar.\n"
    if has_more:
        response += "Ou digite 'mais' para ver outros resultados!"
    return response

def format_cart_for_display(cart: List[Dict]) -> str:
    if not cart:
        return "🤖 Seu carrinho de compras está vazio."
    
    response = "🛒 Seu Carrinho de Compras:\n"
    total = 0.0
    for item in cart:
        price = item.get('pvenda') or 0.0
        qt = item.get('qt', 0)
        subtotal = price * qt
        total += subtotal
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # 🆕 CORREÇÃO: Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = item.get('descricao') or item.get('canonical_name', 'Produto sem nome')
        
        response += f"- {product_name} (Qtd: {qt}) - Unit: {price_str} - Subtotal: {subtotal_str}\n"
    
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"-----------------------------------\nTOTAL DO PEDIDO: {total_str}"
    return response