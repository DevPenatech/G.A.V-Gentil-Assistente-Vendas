# file: IA/app.py
"""
G.A.V. (Gentil Assistente de Vendas) - Aplicação Principal
Sistema completo de vendas via WhatsApp com IA integrada
"""

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
from typing import Dict, List, Tuple, Union, Optional
from datetime import datetime
import re
import json
import os

# Importações dos módulos do projeto
from db import database
from ai_llm import llm_interface
from knowledge import knowledge
from utils import logger_config
from core.session_manager import (
    load_session, save_session, clear_session,
    format_product_list_for_display, format_cart_for_display,
    add_message_to_history, get_conversation_context,
    detect_user_intent_type, format_quick_actions, get_session_stats,
    update_session_context
)
from utils.quantity_extractor import extract_quantity, is_valid_quantity
from communication import twilio_client

# Importações específicas para funcionalidades avançadas
from db.database import (
    search_products_with_suggestions, 
    get_product_details_fuzzy,
    get_product_by_codprod,
    get_all_active_products
)
from knowledge.knowledge import (
    find_product_in_kb_with_analysis,
    search_kb_with_suggestions,
    update_kb,
    get_kb_statistics
)

app = Flask(__name__)
logger_config.setup_logger()

# ================================================================================
# UTILITÁRIOS BÁSICOS
# ================================================================================

def get_product_name(product: Dict) -> str:
    """Extrai o nome do produto, compatível com produtos do banco (descricao) e da KB (canonical_name)."""
    return product.get('descricao') or product.get('canonical_name', 'Produto sem nome')

def format_price(price: float) -> str:
    """Formata preço no padrão brasileiro."""
    return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def sanitize_message(message: str) -> str:
    """Sanitiza mensagem do usuário removendo caracteres problemáticos."""
    if not message:
        return ""
    # Remove quebras de linha excessivas e espaços
    return re.sub(r'\s+', ' ', message.strip())

def format_options_menu(options: List[str], max_options: int = 3) -> str:
    """Formata um menu de opções numeradas."""
    if not options:
        return ""
    
    limited_options = options[:max_options]
    menu = ""
    for i, option in enumerate(limited_options, 1):
        menu += f"[{i} {option}] "
    return menu.strip()

# ================================================================================
# FORMATAÇÃO DE PRODUTOS E CARRINHO
# ================================================================================

def format_product_selection(products: List[Dict], title: str = "Opções encontradas", has_more: bool = False) -> str:
    """Formata lista de produtos para seleção com estilo direto e objetivo."""
    if not products:
        return "Não achei esse item. Posso sugerir similares?"
    
    # Limita a 3 produtos conforme especificação
    limited_products = products[:3]
    
    response = f"{title}:\n"
    for i, product in enumerate(limited_products, 1):
        price = product.get('pvenda') or product.get('preco_varejo', 0.0)
        price_str = format_price(price)
        product_name = get_product_name(product)
        response += f"{i}. {product_name} — {price_str}\n"
    
    response += "Qual você quer? Responda 1, 2 ou 3."
    
    if has_more:
        response += "\nOu digite 'mais' para ver outros resultados!"
    
    return response

def format_checkout_summary(cart: List[Dict], customer_context: Dict = None) -> str:
    """Formata resumo final do pedido com estilo objetivo."""
    if not cart:
        return "Carrinho vazio — nenhum pedido para finalizar."
    
    summary = "🛍️ **RESUMO DO PEDIDO:**\n"
    summary += "=" * 30 + "\n"
    total = 0.0
    
    for i, item in enumerate(cart, 1):
        price = item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        subtotal = price * qt
        total += subtotal
        
        product_name = get_product_name(item)
        price_str = format_price(price)
        subtotal_str = format_price(subtotal)
        
        # Formata quantidade para exibição
        if isinstance(qt, float):
            qty_display = f"{qt:.1f}".rstrip('0').rstrip('.')
        else:
            qty_display = str(qt)
        
        summary += f"{i}. {product_name}\n"
        summary += f"   Qtd: {qty_display} × {price_str} = {subtotal_str}\n"
    
    summary += "=" * 30 + "\n"
    total_str = format_price(total)
    summary += f"**TOTAL: {total_str}**\n\n"
    
    # Adiciona informações do cliente se disponível
    if customer_context:
        customer_name = customer_context.get('name', 'Cliente')
        summary += f"Cliente: {customer_name}\n"
    
    summary += "Confirma o pedido? [1 Sim] [2 Alterar] [3 Cancelar]"
    return summary

def format_search_suggestions(term: str, suggestions: List[str]) -> str:
    """Formata sugestões de busca quando não encontra produtos."""
    if not suggestions:
        return f"Não encontrei '{term}'. Tente outro termo ou navegue pelos produtos disponíveis."
    
    response = f"Não encontrei '{term}'. Você quis dizer:\n"
    for i, suggestion in enumerate(suggestions[:3], 1):
        response += f"{i}. {suggestion}\n"
    
    response += "Escolha uma opção (1-3) ou digite outro termo."
    return response

# ================================================================================
# GESTÃO DE CARRINHO
# ================================================================================

def add_item_to_cart_with_quantity(cart: List[Dict], product: Dict, quantity: Union[int, float]) -> Tuple[bool, str, List[Dict]]:
    """Adiciona item ao carrinho com quantidade especificada."""
    if not product or not is_valid_quantity(quantity):
        return False, "Dados inválidos para adicionar ao carrinho.", cart
    
    codprod = product.get('codprod')
    if not codprod:
        return False, "Produto inválido.", cart
    
    # Verifica se já existe no carrinho
    for item in cart:
        if item.get('codprod') == codprod:
            item['qt'] += quantity
            product_name = get_product_name(item)
            
            # Formata quantidade para exibição
            total_qty = item['qt']
            if isinstance(total_qty, float):
                qty_display = f"{total_qty:.1f}".rstrip('0').rstrip('.')
            else:
                qty_display = str(total_qty)
            
            cart_display = format_cart_for_display(cart)
            return True, f"Quantidade de {product_name} atualizada para {qty_display}.\n\n{cart_display}", cart
    
    # Adiciona novo item
    new_item = product.copy()
    new_item['qt'] = quantity
    cart.append(new_item)
    
    product_name = get_product_name(new_item)
    
    # Formata quantidade para exibição
    if isinstance(quantity, float):
        qty_display = f"{quantity:.1f}".rstrip('0').rstrip('.')
    else:
        qty_display = str(quantity)
    
    cart_display = format_cart_for_display(cart)
    return True, f"{product_name} ({qty_display} un.) adicionado ao carrinho.\n\n{cart_display}", cart

def handle_numeric_selection_with_quantity(user_message: str, last_shown_products: List[Dict], session_id: str) -> Tuple[bool, str]:
    """Gerencia seleção numérica de produtos com extração de quantidade."""
    try:
        # Extrai seleção e quantidade da mensagem
        selection_match = re.search(r'([123])', user_message)
        if not selection_match:
            return False, ""
        
        selection = int(selection_match.group(1)) - 1
        
        if 0 <= selection < len(last_shown_products):
            selected_product = last_shown_products[selection]
            
            # Extrai quantidade da mensagem (padrão: 1)
            quantity = extract_quantity(user_message)
            if not is_valid_quantity(quantity):
                quantity = 1
            
            # Adiciona ao carrinho
            state = load_session(session_id)
            cart = state.get("shopping_cart", [])
            
            success, message, updated_cart = add_item_to_cart_with_quantity(cart, selected_product, quantity)
            
            if success:
                state["shopping_cart"] = updated_cart
                state["last_shown_products"] = []  # Limpa produtos mostrados
                save_session(session_id, state)
                
                product_name = get_product_name(selected_product)
                
                # Formata quantidade para exibição
                if isinstance(quantity, float):
                    qty_display = f"{quantity:.1f}".rstrip('0').rstrip('.')
                else:
                    qty_display = str(quantity)
                
                response = f"✅ {product_name} ({qty_display} un.) adicionado!\n\n"
                response += "O que prefere agora?\n"
                response += format_quick_actions(has_cart=True)
                
                return True, response
            
        return False, ""
    except (ValueError, IndexError):
        return False, ""

def update_cart_item_quantity(cart: List[Dict], index: int, new_qty: Union[int, float]) -> Tuple[bool, str, List[Dict]]:
    """Atualiza a quantidade de um item do carrinho."""
    if not cart:
        return False, "Seu carrinho está vazio.", cart
    
    if not (1 <= index <= len(cart)):
        return False, f"Número inválido. Escolha entre 1 e {len(cart)}.", cart
    
    if not is_valid_quantity(new_qty):
        return False, f"Quantidade inválida: {new_qty}", cart
    
    cart[index - 1]['qt'] = new_qty
    product_name = get_product_name(cart[index - 1])
    
    # Formata quantidade para exibição
    if isinstance(new_qty, float):
        qty_display = f"{new_qty:.1f}".rstrip('0').rstrip('.')
    else:
        qty_display = str(new_qty)
    
    cart_display = format_cart_for_display(cart)
    message = f"Quantidade de {product_name} atualizada para {qty_display}.\n\n{cart_display}"
    
    return True, message, cart

def handle_cart_operations(cart: List[Dict], operation: str, parameters: Dict) -> Tuple[bool, str, List[Dict]]:
    """Gerencia operações no carrinho (remover, atualizar, limpar)."""
    operation = operation.lower()
    
    if operation == 'clear':
        if not cart:
            return False, "Carrinho já está vazio.", cart
        cart.clear()
        return True, "Carrinho esvaziado com sucesso.", cart
    
    elif operation == 'remove':
        if not cart:
            return False, "Seu carrinho está vazio.", cart
        
        index = parameters.get('index')
        if index and 1 <= index <= len(cart):
            removed = cart.pop(index - 1)
            product_name = get_product_name(removed)
            return True, f"{product_name} removido do carrinho.", cart
        
        return False, f"Número inválido. Use um número entre 1 e {len(cart)}.", cart
    
    elif operation == 'update_quantity':
        index = parameters.get('index')
        quantity = parameters.get('quantity')
        
        if index and quantity is not None:
            return update_cart_item_quantity(cart, index, quantity)
        
        return False, "Parâmetros inválidos para atualização.", cart
    
    return False, "Operação não reconhecida.", cart

# ================================================================================
# BUSCA INTELIGENTE DE PRODUTOS
# ================================================================================

def search_products_intelligent(term: str, session_data: Dict) -> Tuple[List[Dict], Dict]:
    """
    Busca inteligente de produtos combinando banco de dados e knowledge base.
    Retorna produtos encontrados e análise de qualidade.
    """
    search_results = {
        "products": [],
        "analysis": {
            "search_quality": "unknown",
            "source": "none",
            "suggestions": [],
            "corrected_term": None
        }
    }
    
    # 1. Busca na Knowledge Base com análise
    try:
        kb_products, kb_analysis = find_product_in_kb_with_analysis(term)
        if kb_products:
            search_results["products"] = kb_products
            search_results["analysis"] = kb_analysis
            search_results["analysis"]["source"] = "knowledge_base"
            logging.info(f"Busca KB bem-sucedida para '{term}': {len(kb_products)} produtos")
            return search_results["products"], search_results["analysis"]
    except Exception as e:
        logging.warning(f"Erro na busca KB para '{term}': {e}")
    
    # 2. Busca no banco de dados com sugestões
    try:
        db_products = search_products_with_suggestions(term)
        if db_products:
            search_results["products"] = db_products
            search_results["analysis"]["source"] = "database"
            search_results["analysis"]["search_quality"] = "good" if len(db_products) > 0 else "poor"
            logging.info(f"Busca DB bem-sucedida para '{term}': {len(db_products)} produtos")
            return search_results["products"], search_results["analysis"]
    except Exception as e:
        logging.warning(f"Erro na busca DB para '{term}': {e}")
    
    # 3. Busca fuzzy no banco como fallback
    try:
        fuzzy_products = get_product_details_fuzzy(term)
        if fuzzy_products:
            search_results["products"] = fuzzy_products
            search_results["analysis"]["source"] = "database_fuzzy"
            search_results["analysis"]["search_quality"] = "fair"
            logging.info(f"Busca fuzzy bem-sucedida para '{term}': {len(fuzzy_products)} produtos")
            return search_results["products"], search_results["analysis"]
    except Exception as e:
        logging.warning(f"Erro na busca fuzzy para '{term}': {e}")
    
    # 4. Gera sugestões se não encontrou nada
    try:
        kb_suggestions = search_kb_with_suggestions(term)
        if kb_suggestions.get("suggestions"):
            search_results["analysis"]["suggestions"] = kb_suggestions["suggestions"]
            search_results["analysis"]["search_quality"] = "no_results_with_suggestions"
    except Exception as e:
        logging.warning(f"Erro ao gerar sugestões para '{term}': {e}")
    
    search_results["analysis"]["search_quality"] = "no_results"
    return [], search_results["analysis"]

def handle_search_request(term: str, session_data: Dict, offset: int = 0) -> Tuple[str, Dict]:
    """Processa solicitação de busca e retorna resposta formatada."""
    if not term or len(term.strip()) < 2:
        return "Digite pelo menos 2 caracteres para buscar produtos.", session_data
    
    # Busca inteligente
    products, analysis = search_products_intelligent(term, session_data)
    
    # Atualiza sessão com resultados da busca
    session_data["last_search_term"] = term
    session_data["last_search_results"] = products
    session_data["last_search_analysis"] = analysis
    session_data["current_offset"] = offset
    
    # Se encontrou produtos
    if products:
        # Mostra produtos encontrados
        has_more = len(products) > 3
        session_data["last_shown_products"] = products[:3]
        
        title = "Produtos encontrados"
        if analysis.get("source") == "knowledge_base":
            title = "Encontrei estes produtos"
        elif analysis.get("corrected_term"):
            title = f"Resultados para '{analysis['corrected_term']}'"
        
        response = format_product_list_for_display(
            products[:3], 
            title, 
            has_more, 
            offset
        )
        
        # Adiciona ações rápidas
        response += f"\n\n{format_quick_actions(has_products=True)}"
        
        return response, session_data
    
    # Se não encontrou produtos
    else:
        session_data["last_shown_products"] = []
        
        # Verifica se há sugestões
        suggestions = analysis.get("suggestions", [])
        if suggestions:
            response = format_search_suggestions(term, suggestions)
            session_data["last_search_suggestions"] = suggestions
        else:
            response = f"Não encontrei produtos para '{term}'. "
            response += "Tente usar palavras diferentes ou navegue pelos produtos disponíveis.\n\n"
            response += format_quick_actions()
        
        return response, session_data

# ================================================================================
# PROCESSAMENTO DE MENSAGENS COM IA
# ================================================================================

def generate_ai_response(user_message: str, session_data: Dict) -> str:
    """Gera resposta usando IA quando necessário."""
    try:
        # Prepara contexto para a IA
        conversation_context = get_conversation_context(session_data)
        user_intent = detect_user_intent_type(user_message, session_data)
        session_stats = get_session_stats(session_data)
        
        # Contexto do sistema
        system_context = {
            "conversation_history": conversation_context,
            "user_intent": user_intent,
            "cart_items": session_stats.get("cart_items", 0),
            "cart_total": session_stats.get("cart_total_value", 0),
            "last_action": session_stats.get("last_action", "NONE")
        }
        
        # Gera resposta com IA
        ai_response = llm_interface.generate_response(
            user_message=user_message,
            system_context=system_context,
            max_tokens=200
        )
        
        return ai_response if ai_response else "Desculpe, não entendi. Pode reformular?"
        
    except Exception as e:
        logging.error(f"Erro ao gerar resposta IA: {e}")
        return "Desculpe, houve um problema. Como posso ajudar?"

def handle_greeting_message(user_message: str, session_data: Dict) -> str:
    """Processa mensagens de saudação."""
    customer_context = session_data.get("customer_context", {})
    customer_name = customer_context.get("name", "")
    
    greeting_response = "Olá"
    if customer_name:
        greeting_response += f", {customer_name}"
    
    greeting_response += "! Bem-vindo ao nosso atendimento. "
    
    cart = session_data.get("shopping_cart", [])
    if cart:
        greeting_response += f"Vi que você já tem {len(cart)} item(ns) no carrinho. "
        greeting_response += "Quer continuar comprando ou finalizar o pedido?\n\n"
        greeting_response += format_quick_actions(has_cart=True)
    else:
        greeting_response += "Como posso ajudar você hoje?\n\n"
        greeting_response += format_quick_actions()
    
    return greeting_response

def handle_help_message(session_data: Dict) -> str:
    """Processa solicitações de ajuda."""
    help_response = "🤖 **COMO POSSO AJUDAR:**\n\n"
    help_response += "📍 **Para buscar produtos:**\n"
    help_response += "   Digite o nome do produto (ex: 'coca cola')\n\n"
    help_response += "📍 **Para ver seu carrinho:**\n"
    help_response += "   Digite 'carrinho' ou 'ver carrinho'\n\n"
    help_response += "📍 **Para finalizar pedido:**\n"
    help_response += "   Digite 'finalizar' ou 'fechar pedido'\n\n"
    help_response += "📍 **Para adicionar quantidade:**\n"
    help_response += "   Digite '2 coca cola' (quantidade + produto)\n\n"
    
    cart = session_data.get("shopping_cart", [])
    if cart:
        help_response += f"Você tem {len(cart)} item(ns) no carrinho.\n\n"
        help_response += format_quick_actions(has_cart=True)
    else:
        help_response += format_quick_actions()
    
    return help_response

# ================================================================================
# PROCESSAMENTO PRINCIPAL DE MENSAGENS
# ================================================================================

def process_message_async(session_id: str, user_message: str):
    """Processa mensagem de forma assíncrona com lógica completa."""
    try:
        # Sanitiza mensagem
        user_message = sanitize_message(user_message)
        if not user_message:
            return
        
        # Carrega estado da sessão
        state = load_session(session_id)
        
        # Variáveis de sessão
        customer_context = state.get("customer_context")
        shopping_cart = state.get("shopping_cart", [])
        last_search_type = state.get("last_search_type")
        last_search_params = state.get("last_search_params", {})
        current_offset = state.get("current_offset", 0)
        last_shown_products = state.get("last_shown_products", [])
        last_bot_action = state.get("last_bot_action")
        pending_action = state.get("pending_action")
        last_search_suggestions = state.get("last_search_suggestions", [])
        
        response_text = ""
        user_lower = user_message.lower().strip()
        
        # Detecta intenção do usuário
        user_intent = detect_user_intent_type(user_message, state)
        
        # =====================================================================
        # PRIORIDADE 1: Seleção numérica de produtos (1, 2, 3)
        # =====================================================================
        if last_shown_products and re.match(r'^\s*[123]\s*$', user_message.strip()):
            handled, response = handle_numeric_selection_with_quantity(user_message, last_shown_products, session_id)
            if handled:
                add_message_to_history(state, 'user', user_message, 'NUMERIC_SELECTION')
                add_message_to_history(state, 'assistant', response, 'ITEM_ADDED_WITH_OPTIONS')
                save_session(session_id, state)
                twilio_client.send_message(session_id, response)
                logging.info(f"THREAD: Seleção numérica processada para '{user_message}'")
                return
        
        # =====================================================================
        # PRIORIDADE 2: Comandos diretos de carrinho
        # =====================================================================
        
        # Comando: esvaziar carrinho
        if any(cmd in user_lower for cmd in ['esvaziar carrinho', 'limpar carrinho', 'zerar carrinho']):
            success, message, new_cart = handle_cart_operations(shopping_cart, 'clear', {})
            if success:
                state["shopping_cart"] = new_cart
                state["last_bot_action"] = "CART_CLEARED"
                save_session(session_id, state)
                response_text = message + " Posso ajudar com mais alguma coisa?\n\n" + format_quick_actions()
        
        # Comando: ver carrinho
        elif any(cmd in user_lower for cmd in ['carrinho', 'ver carrinho', 'mostrar carrinho']):
            if shopping_cart:
                cart_display = format_cart_for_display(shopping_cart)
                response_text = cart_display + "\n\n"
                response_text += "O que gostaria de fazer?\n"
                response_text += format_quick_actions(has_cart=True)
                state["last_bot_action"] = "CART_DISPLAYED"
            else:
                response_text = "Seu carrinho está vazio. Vamos adicionar alguns produtos?\n\n"
                response_text += format_quick_actions()
                state["last_bot_action"] = "EMPTY_CART_DISPLAYED"
        
        # Comando: finalizar pedido
        elif any(cmd in user_lower for cmd in ['finalizar', 'fechar pedido', 'checkout', 'finalizar pedido']):
            if shopping_cart:
                checkout_summary = format_checkout_summary(shopping_cart, customer_context)
                response_text = checkout_summary
                state["last_bot_action"] = "CHECKOUT_INITIATED"
                state["pending_action"] = "CHECKOUT_CONFIRMATION"
            else:
                response_text = "Seu carrinho está vazio. Adicione alguns produtos primeiro!\n\n"
                response_text += format_quick_actions()
                state["last_bot_action"] = "EMPTY_CART_CHECKOUT_ATTEMPT"
        
        # =====================================================================
        # PRIORIDADE 3: Confirmação de checkout
        # =====================================================================
        elif pending_action == "CHECKOUT_CONFIRMATION":
            if re.match(r'^\s*1\s*$', user_message.strip()) or 'sim' in user_lower:
                # Confirma pedido
                total_value = sum(
                    (item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)) * item.get('qt', 0)
                    for item in shopping_cart
                )
                
                order_id = f"PED{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                response_text = f"🎉 **PEDIDO CONFIRMADO!**\n\n"
                response_text += f"Número: {order_id}\n"
                response_text += f"Total: {format_price(total_value)}\n\n"
                response_text += "Obrigado pela preferência! Seu pedido foi registrado.\n\n"
                response_text += "Precisa de mais alguma coisa?"
                
                # Limpa carrinho e sessão após confirmar pedido
                state["shopping_cart"] = []
                state["pending_action"] = None
                state["last_bot_action"] = "ORDER_CONFIRMED"
                
            elif re.match(r'^\s*[23]\s*$', user_message.strip()) or 'não' in user_lower or 'cancelar' in user_lower:
                response_text = "Pedido cancelado. Seu carrinho permanece como estava.\n\n"
                if shopping_cart:
                    response_text += format_quick_actions(has_cart=True)
                else:
                    response_text += format_quick_actions()
                
                state["pending_action"] = None
                state["last_bot_action"] = "ORDER_CANCELLED"
            else:
                response_text = "Por favor, confirme o pedido:\n"
                response_text += "[1 Sim] [2 Alterar] [3 Cancelar]"
        
        # =====================================================================
        # PRIORIDADE 4: Seleção de sugestões de busca
        # =====================================================================
        elif last_search_suggestions and re.match(r'^\s*[123]\s*$', user_message.strip()):
            selection = int(user_message.strip()) - 1
            if 0 <= selection < len(last_search_suggestions):
                suggested_term = last_search_suggestions[selection]
                response_text, state = handle_search_request(suggested_term, state)
                state["last_search_suggestions"] = []
                state["last_bot_action"] = "SUGGESTION_SELECTED"
        
        # =====================================================================
        # PRIORIDADE 5: Comando "mais" para ver mais resultados
        # =====================================================================
        elif user_lower == 'mais' and last_search_type:
            # Implementa paginação dos resultados
            current_offset = state.get("current_offset", 0) + 3
            last_search_term = state.get("last_search_term", "")
            
            if last_search_term:
                response_text, state = handle_search_request(last_search_term, state, current_offset)
                state["last_bot_action"] = "MORE_RESULTS_REQUESTED"
        
        # =====================================================================
        # PRIORIDADE 6: Saudações
        # =====================================================================
        elif user_intent == "GREETING":
            response_text = handle_greeting_message(user_message, state)
            state["last_bot_action"] = "GREETING_RESPONDED"
        
        # =====================================================================
        # PRIORIDADE 7: Pedidos de ajuda
        # =====================================================================
        elif any(word in user_lower for word in ['ajuda', 'help', 'como funciona', 'comandos']):
            response_text = handle_help_message(state)
            state["last_bot_action"] = "HELP_PROVIDED"
        
        # =====================================================================
        # PRIORIDADE 8: Busca de produtos (com extração de quantidade)
        # =====================================================================
        elif user_intent in ["SEARCH_PRODUCT", "GENERAL"] or len(user_message.strip()) > 2:
            # Extrai quantidade da mensagem se presente
            extracted_qty = extract_quantity(user_message)
            search_term = re.sub(r'\b\d+(\.\d+)?\b', '', user_message).strip()
            
            if len(search_term) >= 2:
                # Busca produtos
                response_text, state = handle_search_request(search_term, state)
                state["last_bot_action"] = "PRODUCT_SEARCH"
                
                # Se extraiu quantidade, armazena para uso posterior
                if extracted_qty and is_valid_quantity(extracted_qty):
                    state["pending_quantity"] = extracted_qty
            else:
                response_text = "Digite pelo menos 2 caracteres para buscar produtos.\n\n"
                response_text += format_quick_actions()
                state["last_bot_action"] = "INVALID_SEARCH_TERM"
        
        # =====================================================================
        # FALLBACK: IA para casos não cobertos
        # =====================================================================
        else:
            response_text = generate_ai_response(user_message, state)
            state["last_bot_action"] = "AI_RESPONSE"
        
        # =====================================================================
        # Salva sessão e envia resposta
        # =====================================================================
        if response_text:
            # Adiciona mensagens ao histórico
            add_message_to_history(state, 'user', user_message, user_intent)
            add_message_to_history(state, 'assistant', response_text, state.get("last_bot_action", "UNKNOWN"))
            
            # Atualiza contexto da sessão
            update_session_context(state, state)
            
            # Salva sessão
            save_session(session_id, state)
            
            # Envia resposta
            twilio_client.send_message(session_id, response_text)
            
            logging.info(f"THREAD: Processamento completo para '{user_message[:50]}...' - Ação: {state.get('last_bot_action')}")
        else:
            logging.warning(f"THREAD: Nenhuma resposta gerada para '{user_message}'")
            
    except Exception as e:
        logging.error(f"THREAD: Erro no processamento assíncrono: {e}")
        
        # Resposta de erro para o usuário
        error_response = "Desculpe, houve um problema técnico. Tente novamente em alguns segundos."
        try:
            twilio_client.send_message(session_id, error_response)
        except:
            pass

# ================================================================================
# ROTA PRINCIPAL DO WEBHOOK
# ================================================================================

@app.route("/webhook", methods=["POST"])
def webhook():
    """Webhook principal para receber mensagens do Twilio."""
    try:
        # Extrai dados da requisição
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        
        if not incoming_msg or not from_number:
            logging.warning("Webhook recebido sem corpo da mensagem ou número de origem")
            return str(MessagingResponse())
        
        # Extrai número limpo para usar como session_id
        session_id = re.sub(r'[^\d]', '', from_number)
        
        logging.info(f"WEBHOOK: Mensagem recebida de {from_number}: '{incoming_msg[:100]}...'")
        
        # Resposta imediata para o Twilio
        response = MessagingResponse()
        
        # Processa mensagem em thread separada para não bloquear o webhook
        thread = threading.Thread(
            target=process_message_async,
            args=(session_id, incoming_msg),
            daemon=True
        )
        thread.start()
        
        return str(response)
        
    except Exception as e:
        logging.error(f"WEBHOOK: Erro crítico: {e}")
        
        # Resposta de erro mínima
        response = MessagingResponse()
        msg = response.message("Desculpe, houve um problema técnico. Tente novamente.")
        return str(response)

# ================================================================================
# ROTAS DE DIAGNÓSTICO E SAÚDE
# ================================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de verificação de saúde da aplicação."""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": "unknown",
                "twilio": "unknown",
                "knowledge_base": "unknown",
                "ai_llm": "unknown"
            }
        }
        
        # Verifica banco de dados
        try:
            products = get_all_active_products()
            health_status["services"]["database"] = "healthy" if products else "no_data"
        except Exception as e:
            health_status["services"]["database"] = f"error: {str(e)[:50]}"
        
        # Verifica Twilio
        try:
            twilio_health = twilio_client.get_client_health()
            health_status["services"]["twilio"] = "healthy" if twilio_health.get("client_healthy") else "unhealthy"
        except Exception as e:
            health_status["services"]["twilio"] = f"error: {str(e)[:50]}"
        
        # Verifica Knowledge Base
        try:
            kb_stats = get_kb_statistics()
            health_status["services"]["knowledge_base"] = "healthy" if kb_stats.get("total_entries", 0) > 0 else "no_data"
        except Exception as e:
            health_status["services"]["knowledge_base"] = f"error: {str(e)[:50]}"
        
        # Verifica AI/LLM
        try:
            test_response = llm_interface.generate_response("teste", {}, max_tokens=10)
            health_status["services"]["ai_llm"] = "healthy" if test_response else "no_response"
        except Exception as e:
            health_status["services"]["ai_llm"] = f"error: {str(e)[:50]}"
        
        # Status geral
        unhealthy_services = [k for k, v in health_status["services"].items() if not v.startswith("healthy")]
        if unhealthy_services:
            health_status["status"] = "degraded"
            health_status["issues"] = unhealthy_services
        
        return health_status, 200
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, 500

@app.route("/stats", methods=["GET"])
def get_stats():
    """Endpoint para estatísticas do sistema."""
    try:
        stats = {
            "timestamp": datetime.now().isoformat(),
            "database": {
                "active_products": 0,
                "total_products": 0
            },
            "knowledge_base": {},
            "twilio": {},
            "sessions": {
                "active_sessions": 0
            }
        }
        
        # Estatísticas do banco
        try:
            active_products = get_all_active_products()
            stats["database"]["active_products"] = len(active_products) if active_products else 0
        except Exception as e:
            stats["database"]["error"] = str(e)
        
        # Estatísticas da Knowledge Base
        try:
            stats["knowledge_base"] = get_kb_statistics()
        except Exception as e:
            stats["knowledge_base"]["error"] = str(e)
        
        # Estatísticas do Twilio
        try:
            twilio_health = twilio_client.get_client_health()
            stats["twilio"] = twilio_health.get("statistics", {})
        except Exception as e:
            stats["twilio"]["error"] = str(e)
        
        return stats, 200
        
    except Exception as e:
        return {"error": str(e)}, 500

# ================================================================================
# INICIALIZAÇÃO DA APLICAÇÃO
# ================================================================================

def initialize_application():
    """Inicializa componentes necessários da aplicação."""
    logging.info("=== INICIANDO G.A.V. (Gentil Assistente de Vendas) ===")
    
    # Verifica configurações essenciais
    required_env_vars = [
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "POSTGRES_HOST",
        "POSTGRES_DB"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logging.error(f"Variáveis de ambiente faltando: {missing_vars}")
        return False
    
    # Cria diretórios necessários
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Testa conexões principais
    try:
        # Testa banco de dados
        products = get_all_active_products()
        logging.info(f"✅ Banco de dados: {len(products) if products else 0} produtos ativos")
        
        # Testa Knowledge Base
        kb_stats = get_kb_statistics()
        logging.info(f"✅ Knowledge Base: {kb_stats.get('total_entries', 0)} entradas")
        
        # Testa Twilio
        twilio_health = twilio_client.get_client_health()
        logging.info(f"✅ Twilio: {'Conectado' if twilio_health.get('client_healthy') else 'Com problemas'}")
        
        logging.info("=== G.A.V. INICIALIZADO COM SUCESSO ===")
        return True
        
    except Exception as e:
        logging.error(f"❌ Erro na inicialização: {e}")
        return False

if __name__ == "__main__":
    # Inicializa aplicação
    if initialize_application():
        # Configurações do servidor
        host = os.getenv("FLASK_HOST", "0.0.0.0")
        port = int(os.getenv("FLASK_PORT", 8080))
        debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
        
        logging.info(f"🚀 Iniciando servidor Flask em {host}:{port} (debug={debug})")
        
        # Inicia servidor
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
    else:
        logging.error("❌ Falha na inicialização. Encerrando aplicação.")
        exit(1)