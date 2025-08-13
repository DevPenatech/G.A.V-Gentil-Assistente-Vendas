# file: IA/core/session_manager.py
"""
Gerenciador de Sessão - Versão 2.0
Com Sistema de Contexto Completo e Histórico Conversacional
"""

import json
import os
import logging
import re
from typing import Dict, List, Union
from datetime import datetime
from utils.quantity_extractor import detect_quantity_modifiers

# Diretório para armazenar sessões
SESSION_DIR = "data"
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# ================================================================================
# GESTÃO DE SESSÕES
# ================================================================================

def get_session_file_path(sender_phone: str) -> str:
    """Retorna o caminho do arquivo de sessão para um número de telefone."""
    safe_phone = re.sub(r'\W+', '', sender_phone)
    return os.path.join(SESSION_DIR, f"session_{safe_phone}.json")


def load_session(sender_phone: str) -> Dict:
    """Carrega sessão do usuário ou cria uma nova."""
    session_file = get_session_file_path(sender_phone)
    
    try:
        if os.path.exists(session_file):
            with open(session_file, 'r', encoding='utf-8') as f:
                session = json.load(f)
                logging.debug(f"[SESSION] Sessão carregada do arquivo: {session_file}")
                
                # Garante que campos essenciais existam
                if "conversation_history" not in session:
                    session["conversation_history"] = []
                if "conversation_summary" not in session:
                    session["conversation_summary"] = ""
                
                return session
    except Exception as e:
        logging.error(f"[SESSION] Erro ao carregar sessão: {e}")
    
    # Cria nova sessão
    new_session = {
        "sender_phone": sender_phone,
        "customer_context": None,
        "shopping_cart": [],
        "last_search_type": None,
        "last_search_params": {},
        "current_offset": 0,
        "last_shown_products": [],
        "last_bot_action": None,
        "pending_action": None,
        "last_kb_search_term": None,
        "conversation_history": [],
        "conversation_summary": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "purchase_stage": "greeting"
    }
    
    logging.info(f"[SESSION] Nova sessão criada para: {sender_phone}")
    return new_session


def save_session(sender_phone: str, session_data: Dict) -> bool:
    """Salva sessão do usuário em arquivo."""
    session_file = get_session_file_path(sender_phone)
    
    try:
        session_data["updated_at"] = datetime.now().isoformat()
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        logging.debug(f"[SESSION] Sessão salva no arquivo: {session_file}")
        return True
    except Exception as e:
        logging.error(f"[SESSION] Erro ao salvar sessão: {e}")
        return False


def clear_session(sender_phone: str) -> bool:
    """Limpa completamente a sessão de um usuário."""
    session_file = get_session_file_path(sender_phone)
    
    try:
        if os.path.exists(session_file):
            os.remove(session_file)
            logging.info(f"[SESSION] Sessão removida para: {sender_phone}")
        return True
    except Exception as e:
        logging.error(f"[SESSION] Erro ao limpar sessão: {e}")
        return False


def update_session_context(session_data: Dict, updates: Dict) -> None:
    """Atualiza contexto da sessão com novos dados."""
    for key, value in updates.items():
        session_data[key] = value
    session_data["updated_at"] = datetime.now().isoformat()

# ================================================================================
# GESTÃO DE HISTÓRICO CONVERSACIONAL
# ================================================================================

def _summarize_old_messages(session_data: Dict, max_history: int = 20, keep_recent: int = 10):
    """Resumir mensagens antigas para manter contexto sem sobrecarregar."""
    history = session_data.get("conversation_history", [])
    if len(history) <= max_history:
        return

    old_messages = history[:-keep_recent]

    summary_lines = []
    for msg in old_messages:
        role = "Cliente" if msg.get("role") == "user" else "G.A.V."
        content = msg.get("message", "").replace("\n", " ")[:100]
        summary_lines.append(f"{role}: {content}")

    new_summary = " | ".join(summary_lines)
    existing_summary = session_data.get("conversation_summary", "")

    combined = (existing_summary + " | " + new_summary).strip(" |") if existing_summary else new_summary
    session_data["conversation_summary"] = combined[-1000:]

    session_data["conversation_history"] = history[-keep_recent:]


def add_message_to_history(session_data: Dict, role: str, message: str, action_type: str = ""):
    """Adiciona mensagem ao histórico da conversa com contexto aprimorado."""
    if "conversation_history" not in session_data:
        session_data["conversation_history"] = []
    
    session_data["conversation_history"].append({
        "role": role,
        "message": message[:500],
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type
    })

    _summarize_old_messages(session_data)


def get_conversation_context(session_data: Dict, max_messages: int = 10) -> str:
    """Retorna contexto da conversa incluindo sumário e últimas mensagens."""
    history = session_data.get("conversation_history", [])
    summary = session_data.get("conversation_summary")

    if not history and not summary:
        return "Primeira interação com o cliente."

    parts = []
    if summary:
        parts.append(f"RESUMO ANTERIOR:\n{summary}")

    if history:
        recent_history = history[-max_messages:]
        context_lines = []
        
        for msg in recent_history:
            role = "Cliente" if msg['role'] == 'user' else "G.A.V."
            message = msg['message'][:200]
            action = f" [{msg.get('action_type')}]" if msg.get('action_type') else ""
            context_lines.append(f"{role}: {message}{action}")
        
        if context_lines:
            parts.append("HISTÓRICO RECENTE:\n" + "\n".join(context_lines))

    return "\n\n".join(parts)

# ================================================================================
# DETECÇÃO E ANÁLISE DE INTENÇÕES
# ================================================================================

def detect_cart_clear_commands(message: str) -> bool:
    """Detecta comandos específicos de limpeza de carrinho."""
    message_lower = message.lower().strip()
    
    clear_commands = [
        'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
        'resetar carrinho', 'apagar carrinho', 'deletar carrinho',
        'esvaziar tudo', 'limpar tudo', 'zerar tudo',
        'apagar tudo', 'deletar tudo', 'remover tudo',
        'começar de novo', 'recomeçar', 'reiniciar',
        'do zero', 'novo pedido', 'nova compra',
        'limpa carrinho', 'esvazia carrinho', 'zera carrinho',
        'cancela tudo', 'cancelar pedido', 'cancelar compra'
    ]
    
    if message_lower in clear_commands:
        return True
    
    clear_patterns = [
        r'\b(esvaziar|limpar|zerar|apagar|deletar|remover)\s+(o\s+)?carrinho\b',
        r'\b(carrinho|tudo)\s+(vazio|limpo|zerado)\b',
        r'\bcomeca\w*\s+de\s+novo\b',
        r'\bdo\s+zero\b',
        r'\breinicia\w*\s+(carrinho|tudo|compra)\b',
        r'\b(esvazia|limpa|zera)\s+(carrinho|tudo)?\b',
        r'\b(cancela|cancelar)\s+(tudo|pedido|compra)\b'
    ]
    
    for pattern in clear_patterns:
        if re.search(pattern, message_lower):
            return True
    
    return False


def detect_checkout_context(session_data: Dict) -> Dict:
    """Detecta se estamos em contexto de checkout."""
    context = {
        "checkout_initiated": False,
        "awaiting_cnpj": False,
        "can_checkout": False
    }
    
    history = session_data.get("conversation_history", [])
    if history:
        recent_messages = history[-5:]
        
        for msg in recent_messages:
            content = msg.get("message", "").lower()
            action = msg.get("action_type", "")
            
            if action == "REQUEST_CNPJ" or any(phrase in content for phrase in [
                "preciso do seu cnpj",
                "informe seu cnpj",
                "qual seu cnpj",
                "digite seu cnpj"
            ]):
                context["awaiting_cnpj"] = True
            
            if any(word in content for word in ["finalizar", "checkout", "fechar pedido", "concluir"]):
                context["checkout_initiated"] = True
    
    context["can_checkout"] = (
        len(session_data.get("shopping_cart", [])) > 0 and
        bool(session_data.get("customer_context"))
    )
    
    return context


def detect_user_intent_type(message: str, session_data: Dict) -> str:
    """Detecta tipo de intenção do usuário para melhor contexto."""
    message_lower = message.lower().strip()
    
    # PRIORIDADE MÁXIMA: Comandos de limpeza
    if detect_cart_clear_commands(message):
        logging.info(f"[INTENT] Comando de limpeza detectado: '{message}'")
        return "CLEAR_CART"
    
    # Comandos numéricos diretos
    if re.match(r'^\s*[123]\s*$', message_lower):
        return "NUMERIC_SELECTION"
    
    # Comandos de carrinho
    cart_commands = ['carrinho', 'ver carrinho', 'mostrar carrinho', 'meu carrinho']
    if any(cmd in message_lower for cmd in cart_commands):
        return "VIEW_CART"
    
    # Comandos de finalização
    checkout_commands = ['finalizar', 'fechar pedido', 'checkout', 'comprar', 'concluir']
    if any(cmd in message_lower for cmd in checkout_commands):
        return "CHECKOUT"
    
    # Comandos de busca
    if any(word in message_lower for word in ['quero', 'buscar', 'procurar', 'produto', 'tem']):
        return "SEARCH_PRODUCT"

    # Saudações
    greetings = ['oi', 'olá', 'ola', 'boa', 'bom dia', 'boa tarde', 'boa noite', 'e aí', 'e ai']
    if any(greeting in message_lower for greeting in greetings):
        return "GREETING"

    # Remover itens do carrinho
    modifiers = detect_quantity_modifiers(message_lower)
    if modifiers.get('action') == 'remove':
        return "REMOVE_CART_ITEM"

    # Quantidades
    if re.search(r'\d+', message) and len(session_data.get("last_shown_products", [])) > 0:
        return "QUANTITY_SPECIFICATION"
    
    # CNPJ
    cnpj_pattern = re.compile(r'\d{14}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')
    if cnpj_pattern.search(message):
        return "CNPJ_PROVIDED"
    
    return "GENERAL"

# ================================================================================
# FORMATAÇÃO DE CONTEXTO PARA LLM
# ================================================================================

def format_cart_context(cart: List[Dict]) -> str:
    """Formata contexto do carrinho para o LLM."""
    if not cart:
        return "Vazio (0 itens)"
    
    items = []
    total = 0.0
    
    for item in cart[:5]:
        name = item.get('descricao', item.get('canonical_name', 'Produto'))
        qt = item.get('qt', 0)
        price = item.get('pvenda', item.get('preco_varejo', 0))
        total += price * qt
        items.append(f"{name} x{qt}")
    
    result = f"{len(cart)} itens: {', '.join(items)}"
    if len(cart) > 5:
        result += f" (+{len(cart)-5} mais)"
    result += f" | Total: R$ {total:.2f}"
    
    return result


def format_customer_context(customer: Union[Dict, None]) -> str:
    """Formata contexto do cliente para o LLM."""
    if not customer:
        return "Não identificado"
    
    return f"{customer.get('nome', 'Cliente')} (CNPJ: {customer.get('cnpj', 'N/A')})"


def format_products_context(products: List[Dict]) -> str:
    """Formata produtos mostrados para o LLM."""
    if not products:
        return "Nenhum produto mostrado recentemente"
    
    items = []
    for i, p in enumerate(products[:3], 1):
        name = p.get('descricao', p.get('canonical_name', 'Produto'))
        codprod = p.get('codprod', 'N/A')
        price = p.get('pvenda', p.get('preco_varejo', 0))
        items.append(f"{i}. {name} (cod: {codprod}, R$ {price:.2f})")
    
    return " | ".join(items)

# ================================================================================
# ESTATÍSTICAS E MÉTRICAS
# ================================================================================

def get_session_stats(session_data: Dict) -> Dict:
    """Retorna estatísticas da sessão atual."""
    stats = {
        "cart_items": len(session_data.get("shopping_cart", [])),
        "conversation_length": len(session_data.get("conversation_history", [])),
        "customer_identified": bool(session_data.get("customer_context")),
        "last_action": session_data.get("last_bot_action", "NONE"),
        "has_pending_selection": bool(session_data.get("last_shown_products")),
        "has_pending_quantity": bool(session_data.get("pending_product_selection")),
        "purchase_stage": session_data.get("purchase_stage", "greeting")
    }
    
    cart = session_data.get("shopping_cart", [])
    total_value = 0.0
    for item in cart:
        price = item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        total_value += price * qt
    
    stats["cart_total_value"] = total_value
    
    return stats

# ================================================================================
# AÇÕES RÁPIDAS E MENUS
# ================================================================================

def format_quick_actions(has_cart: bool = False, has_products: bool = False) -> str:
    """Gera menu de ações rápidas baseado no contexto atual."""
    actions = []
    
    if has_cart:
        actions.append("🛒 Digite *carrinho* para ver seus itens")
        actions.append("✅ Digite *finalizar* para concluir")
        actions.append("🗑️ Digite *limpar carrinho* para recomeçar")
    else:
        actions.append("🔍 Digite o nome do produto")
        actions.append("📦 Digite *produtos* para ver os mais vendidos")
    
    actions.append("❓ Digite *ajuda* para mais opções")
    
    return "\n".join(actions)

# ================================================================================
# FORMATAÇÃO DE DISPLAYS
# ================================================================================

def format_product_list_for_display(products: List[Dict], offset: int = 0, limit: int = 3) -> str:
    """Formata lista de produtos para exibição no WhatsApp."""
    if not products:
        return "🤖 Nenhum produto encontrado."
    
    response = "📦 *Produtos encontrados:*\n\n"
    
    for i, product in enumerate(products[offset:offset+limit], 1):
        name = product.get('descricao', product.get('canonical_name', 'Produto'))
        price = product.get('pvenda', product.get('preco_varejo', 0))
        unit = product.get('unidade_venda', 'UN')
        
        price_str = f"R$ {price:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        response += f"*{i}.* {name}\n"
        response += f"    💰 {price_str}/{unit}\n"
        
        # Adiciona informação de atacado se disponível
        if product.get('preco_atacado') and product.get('quantidade_atacado'):
            atacado_price = product.get('preco_atacado')
            atacado_qt = product.get('quantidade_atacado')
            atacado_str = f"R$ {atacado_price:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            response += f"    📦 Atacado: {atacado_str} (a partir de {atacado_qt} {unit})\n"
        
        response += "\n"
    
    response += "Digite o *número* do produto desejado (1, 2 ou 3)"
    
    if offset + limit < len(products):
        response += "\n📄 Digite *mais* para ver outros produtos"
    
    return response


def format_cart_for_display(cart: List[Dict]) -> str:
    """Formata carrinho para exibição no WhatsApp."""
    if not cart:
        return "🛒 Seu carrinho está vazio."
    
    response = "🛒 *SEU CARRINHO:*\n"
    response += "━━━━━━━━━━━━━━━━\n\n"
    
    total = 0.0
    
    for i, item in enumerate(cart, 1):
        name = item.get('descricao', item.get('canonical_name', 'Produto'))
        price = item.get('pvenda', item.get('preco_varejo', 0))
        qt = item.get('qt', 0)
        subtotal = price * qt
        total += subtotal
        
        price_str = f"R$ {price:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        subtotal_str = f"R$ {subtotal:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        response += f"{i}. {name}\n"
        response += f"   {qt} x {price_str} = {subtotal_str}\n\n"
    
    response += "━━━━━━━━━━━━━━━━\n"
    total_str = f"R$ {total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    response += f"*TOTAL: {total_str}*\n\n"
    
    response += "✅ Digite *finalizar* para concluir\n"
    response += "➕ Digite o nome de um produto para adicionar\n"
    response += "🗑️ Digite *limpar carrinho* para recomeçar"
    
    return response

# ================================================================================
# VALIDAÇÕES E CORREÇÕES
# ================================================================================

def validate_and_correct_session(session_data: Dict) -> Dict:
    """Valida e corrige dados da sessão."""
    # Garante campos essenciais
    essential_fields = {
        "sender_phone": "",
        "customer_context": None,
        "shopping_cart": [],
        "last_search_type": None,
        "last_search_params": {},
        "current_offset": 0,
        "last_shown_products": [],
        "last_bot_action": None,
        "pending_action": None,
        "last_kb_search_term": None,
        "conversation_history": [],
        "conversation_summary": "",
        "purchase_stage": "greeting"
    }
    
    for field, default_value in essential_fields.items():
        if field not in session_data:
            session_data[field] = default_value
    
    # Valida tipos de dados
    if not isinstance(session_data.get("shopping_cart"), list):
        session_data["shopping_cart"] = []
    
    if not isinstance(session_data.get("conversation_history"), list):
        session_data["conversation_history"] = []
    
    if not isinstance(session_data.get("last_shown_products"), list):
        session_data["last_shown_products"] = []
    
    return session_data