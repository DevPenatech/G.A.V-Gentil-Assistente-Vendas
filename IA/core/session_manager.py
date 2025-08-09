# file: session_manager.py
import json
import logging
import os
from typing import List, Dict, Union

SESSION_FILE = "session.json"

def save_session(session_data: Dict):
    """Salva os dados da sessão atual em um arquivo JSON."""
    logging.info(f"Salvando sessão: {session_data}")
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=4, ensure_ascii=False)

def load_session() -> Dict:
    """Carrega os dados da sessão de um arquivo JSON, retornando um dicionário vazio se não existir."""
    if os.path.exists(SESSION_FILE):
        logging.info("Arquivo de sessão encontrado. Carregando.")
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Erro ao decodificar o arquivo de sessão. Iniciando uma nova.")
                return {}
    logging.info("Nenhum arquivo de sessão encontrado. Iniciando uma nova.")
    return {}

def clear_session():
    """Remove o arquivo de sessão."""
    if os.path.exists(SESSION_FILE):
        logging.info("Limpando sessão (removendo arquivo).")
        os.remove(SESSION_FILE)

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