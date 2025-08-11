# file: session_manager.py
import json
import logging
import os
import re
from typing import List, Dict

import redis


redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD"),
    db=0,
    decode_responses=True,
)

def save_session(session_id: str, data: Dict):
    """Salva os dados da sessão no Redis com TTL de 1 hora."""
    try:
        redis_client.set(session_id, json.dumps(data), ex=3600)
    except Exception as e:
        logging.error("Erro ao salvar sessão: %s", e)
        return {}


def load_session(session_id: str) -> Dict:
    """Carrega os dados da sessão do Redis."""
    try:
        raw = redis_client.get(session_id)
        if raw:
            return json.loads(raw)
        return {}
    except Exception as e:
        logging.error("Erro ao carregar sessão: %s", e)
        return {}


def clear_session(session_id: str):
    """Remove os dados da sessão do Redis."""
    try:
        redis_client.delete(session_id)
    except Exception as e:
        logging.error("Erro ao limpar sessão: %s", e)
        return {}
    
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