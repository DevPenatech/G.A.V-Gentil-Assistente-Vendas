# file: IA/app.py
"""
Aplicação Principal G.A.V. - Versão 2.0
Com Sistema de Contexto Completo e Validações Aprimoradas
"""

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
import re
from typing import Dict, List, Tuple, Union
from datetime import datetime

# Imports dos módulos
from db import database
from ai_llm import llm_interface
from knowledge import knowledge
from utils import logger_config
from core.session_manager import (
    load_session,
    save_session,
    clear_session,
    format_product_list_for_display,
    format_cart_for_display,
    add_message_to_history,
    get_conversation_context,
    format_quick_actions,
    update_session_context,
    detect_user_intent_type,
    detect_cart_clear_commands,
    detect_checkout_context,
    format_cart_context,
    format_customer_context,
    format_products_context,
    get_session_stats,
    validate_and_correct_session
)
from utils.quantity_extractor import extract_quantity, is_valid_quantity
from communication import twilio_client
from db.database import search_products_with_suggestions, get_product_details_fuzzy
from knowledge.knowledge import find_product_in_kb_with_analysis

app = Flask(__name__)
logger_config.setup_logger()


# ================================================================================
# FUNÇÕES AUXILIARES
# ================================================================================

def get_product_name(product: Dict) -> str:
    """Extrai o nome do produto, compatível com produtos do banco e da KB."""
    return product.get("descricao") or product.get("canonical_name", "Produto sem nome")


def clear_cart_completely(shopping_cart: List[Dict]) -> Tuple[str, List]:
    """Limpa completamente o carrinho de compras."""
    items_count = len(shopping_cart)
    
    if items_count == 0:
        message = "🛒 Seu carrinho já está vazio.\n\n" + format_quick_actions(has_cart=False)
    else:
        message = (
            f"🗑️ Carrinho esvaziado! {items_count} {'item removido' if items_count == 1 else 'itens removidos'}.\n\n"
            + format_quick_actions(has_cart=False)
        )
    
    return message, []


def find_products_in_cart_by_name(cart: List[Dict], product_name: str) -> List[Tuple[int, Dict]]:
    """Encontra produtos no carrinho pelo nome (busca fuzzy)."""
    if not cart or not product_name:
        return []

    from utils.fuzzy_search import fuzzy_engine

    matches = []
    search_term = product_name.lower().strip()

    for i, item in enumerate(cart):
        item_name = get_product_name(item).lower()

        if search_term in item_name or item_name in search_term:
            matches.append((i, item))
            continue

        similarity = fuzzy_engine.calculate_similarity(search_term, item_name)
        if similarity >= 0.6:
            matches.append((i, item))

    return matches


def format_cart_with_indices(cart: List[Dict]) -> str:
    """Formata o carrinho com índices para facilitar seleção."""
    if not cart:
        return "🛒 Seu carrinho está vazio."

    response = "🛒 *SEU CARRINHO:*\n━━━━━━━━━━━━━━━━\n\n"
    total = 0.0

    for i, item in enumerate(cart, 1):
        price = item.get("pvenda") or item.get("preco_varejo", 0.0)
        qt = item.get("qt", 0)
        subtotal = price * qt
        total += subtotal

        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        product_name = get_product_name(item)

        response += f"{i}. {product_name}\n"
        response += f"   {qt} x {price_str} = {subtotal_str}\n\n"

    response += "━━━━━━━━━━━━━━━━\n"
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"*TOTAL: {total_str}*"

    return response


def generate_checkout_summary(cart: List[Dict], customer: Union[Dict, None] = None) -> str:
    """Gera resumo final do checkout."""
    if not cart:
        return "🛒 Carrinho vazio. Adicione produtos primeiro!"
    
    response = "✅ *PEDIDO FINALIZADO COM SUCESSO!*\n"
    response += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if customer:
        response += f"👤 *Cliente:* {customer.get('nome', 'N/A')}\n"
        response += f"📄 *CNPJ:* {customer.get('cnpj', 'N/A')}\n\n"
    
    response += format_cart_for_display(cart)
    response += "\n\n📞 Em breve entraremos em contato para confirmação.\n"
    response += "🚚 Prazo de entrega: 1 a 2 dias úteis.\n\n"
    response += "Obrigado pela preferência! 🎉"
    
    return response


def generate_continue_or_checkout_message(cart: List[Dict]) -> str:
    """Gera mensagem perguntando se continua comprando ou finaliza."""
    cart_summary = format_cart_for_display(cart)
    return (
        f"{cart_summary}\n\n"
        "➕ Digite o nome de um produto para continuar comprando\n"
        "✅ Digite *finalizar* para concluir o pedido"
    )


def validate_and_correct_intent(intent: Dict, message: str, session: Dict) -> Dict:
    """Validação final para garantir que comandos críticos sejam detectados."""
    message_lower = message.lower().strip()
    
    # Correção forçada para comandos de limpeza
    clear_phrases = [
        'limpar carrinho', 'esvaziar carrinho', 'zerar carrinho',
        'limpar tudo', 'esvaziar tudo', 'zerar tudo',
        'apagar carrinho', 'deletar carrinho', 'cancelar tudo'
    ]
    
    if any(phrase in message_lower for phrase in clear_phrases):
        if intent.get("tool_name") != "clear_cart":
            logging.warning(f"[VALIDATION] Corrigindo intent: deveria ser clear_cart, era {intent.get('tool_name')}")
            return {"tool_name": "clear_cart", "parameters": {}}
    
    # Correção para CNPJ em checkout
    checkout_ctx = detect_checkout_context(session)
    if checkout_ctx.get("awaiting_cnpj"):
        cnpj_match = re.search(r'\d{14}', message)
        if cnpj_match and intent.get("tool_name") != "find_customer_by_cnpj":
            logging.warning(f"[VALIDATION] Corrigindo intent: deveria ser find_customer_by_cnpj")
            return {
                "tool_name": "find_customer_by_cnpj",
                "parameters": {"cnpj": cnpj_match.group()}
            }
    
    return intent


# ================================================================================
# PROCESSAMENTO PRINCIPAL
# ================================================================================

def _extract_state(session: Dict) -> Dict:
    """Extrai o estado atual da sessão."""
    return {
        "customer_context": session.get("customer_context"),
        "shopping_cart": session.get("shopping_cart", []),
        "last_search_type": session.get("last_search_type"),
        "last_search_params": session.get("last_search_params", {}),
        "current_offset": session.get("current_offset", 0),
        "last_shown_products": session.get("last_shown_products", []),
        "last_bot_action": session.get("last_bot_action"),
        "pending_action": session.get("pending_action"),
        "last_kb_search_term": session.get("last_kb_search_term"),
    }


def _handle_pending_action(session: Dict, state: Dict, incoming_msg: str) -> Tuple[Dict, str]:
    """Trata ações pendentes da sessão anterior."""
    intent = None
    response_text = ""
    pending_action = state.get("pending_action")
    
    if not pending_action:
        return intent, response_text
    
    # Implementar lógica de ações pendentes aqui
    # ...
    
    return intent, response_text


def _process_user_message(session: Dict, state: Dict, incoming_msg: str) -> Tuple[Dict, str]:
    """Processa mensagem do usuário com validações aprimoradas."""
    intent = None
    response_text = ""
    shopping_cart = state.get("shopping_cart", [])
    last_shown = state.get("last_shown_products", [])

    # Extrai quantidade do texto e valida
    quantity = extract_quantity(incoming_msg, last_shown)
    if not is_valid_quantity(quantity):
        quantity = 1

    # Detecção imediata de comandos de limpeza do carrinho
    if detect_cart_clear_commands(incoming_msg):
        intent = {"tool_name": "clear_cart", "parameters": {}}
        logging.info("[PROCESS] Comando de limpeza detectado (detect_cart_clear_commands)")
        return intent, response_text

    # Detecta tipo de intenção
    intent_type = detect_user_intent_type(incoming_msg, session)

    logging.info(f"[INTENT_TYPE] Detectado: {intent_type} para mensagem: '{incoming_msg}'")

    # PRIORIDADE MÁXIMA: Comandos de limpeza
    if intent_type == "CLEAR_CART":
        intent = {"tool_name": "clear_cart", "parameters": {}}
        logging.info("[PROCESS] Comando de limpeza detectado - usando clear_cart")
        return intent, response_text
    
    # VALIDAÇÃO DE CNPJ EM CONTEXTO
    if intent_type == "CNPJ_PROVIDED" or session.get("awaiting_cnpj"):
        cnpj_match = re.search(r'\d{14}', incoming_msg)
        if cnpj_match:
            intent = {
                "tool_name": "find_customer_by_cnpj",
                "parameters": {"cnpj": cnpj_match.group()}
            }
            logging.info(f"[PROCESS] CNPJ detectado: {cnpj_match.group()}")
            return intent, response_text
    
    # Seleção numérica
    if intent_type == "NUMERIC_SELECTION":
        last_shown = state.get("last_shown_products", [])
        if last_shown:
            try:
                selection_text = incoming_msg.strip()
                selection = int(selection_text.split()[0]) - 1
                if 0 <= selection < len(last_shown):
                    product = last_shown[selection]
                    qt = quantity if (not selection_text.isdigit() and is_valid_quantity(quantity)) else 1
                    intent = {
                        "tool_name": "add_item_to_cart",
                        "parameters": {
                            "codprod": product.get("codprod"),
                            "qt": qt
                        }
                    }
                    logging.info(f"[PROCESS] Seleção numérica: produto {selection+1} - qtd {qt}")
                    return intent, response_text
            except ValueError:
                pass
    
    # Comandos diretos
    if intent_type == "VIEW_CART":
        intent = {"tool_name": "view_cart", "parameters": {}}
        return intent, response_text
    
    if intent_type == "CHECKOUT":
        intent = {"tool_name": "checkout", "parameters": {}}
        return intent, response_text
    
    # Remover item do carrinho
    if intent_type == "REMOVE_CART_ITEM":
        params = {"action": "remove"}
        index_match = re.search(r"\b(\d+)\b", incoming_msg)
        if index_match:
            params["index"] = int(index_match.group(1))
        else:
            product_name = re.sub(
                r"\b(remover|tirar|excluir|deletar)\b", "", 
                incoming_msg, 
                flags=re.IGNORECASE
            ).strip()
            if product_name:
                params["product_name"] = product_name
        intent = {"tool_name": "update_cart_item", "parameters": params}
        return intent, response_text
    
    # Comandos de navegação
    if incoming_msg.lower() in ["mais", "proximo", "próximo", "mais produtos"]:
        intent = {"tool_name": "show_more_products", "parameters": {}}
        return intent, response_text

    # Detecção de padrões explícitos de compra
    compra_match = re.search(r"\b(?:quero\s+comprar|comprar)\s+(.+)", incoming_msg, re.IGNORECASE)
    if compra_match:
        product_name = compra_match.group(1).strip()
        search_result = search_products_with_suggestions(product_name, limit=3)
        products = search_result.get("products", [])
        suggestions = search_result.get("suggestions", [])

        if products:
            response_text = format_product_list_for_display(products, 0, 3)
            state["last_shown_products"] = products[:3]
            state["last_search_type"] = "by_name"
            state["last_search_params"] = {"product_name": product_name}
            state["current_offset"] = 0
        elif suggestions:
            suggestion_text = ", ".join(suggestions)
            response_text = (
                f"🤖 Não encontrei produtos para '{product_name}'. \n"
                f"Você quis dizer: {suggestion_text}?"
            )
        else:
            response_text = (
                f"🤖 Não encontrei produtos para '{product_name}'.\n\n"
                "Tente buscar por categoria ou marca."
            )

        add_message_to_history(session, "assistant", response_text, "SEARCH_PRODUCTS")
        state["last_bot_action"] = "PRODUCTS_SEARCHED"
        return intent, response_text

    # Processamento com IA para casos gerais
    if intent_type in ["GENERAL", "SEARCH_PRODUCT"]:
        logging.info("[PROCESS] Consultando IA com contexto completo...")
        
        # Log do estado atual
        stats = get_session_stats(session)
        logging.info(f"[SESSION_STATS] {stats}")
        logging.debug(f"[CTX_CART] {format_cart_context(shopping_cart)}")
        logging.debug(f"[CTX_CUSTOMER] {format_customer_context(state.get('customer_context'))}")
        logging.debug(f"[CTX_PRODUCTS] {format_products_context(state.get('last_shown_products'))}")

        intent = llm_interface.get_intent(
            user_message=incoming_msg,
            session_data=session,  # Passa sessão completa com histórico
            customer_context=state.get("customer_context"),
            cart_items_count=len(shopping_cart)
        )

        if intent.get("tool_name") == "add_item_to_cart":
            params = intent.setdefault("parameters", {})
            if "qt" not in params or not is_valid_quantity(params.get("qt")):
                params["qt"] = quantity

        logging.info(f"[AI_RESPONSE] Tool: {intent.get('tool_name')} | Params: {intent.get('parameters')}")

        # Validação final de segurança
        intent = validate_and_correct_intent(intent, incoming_msg, session)

        return intent, response_text
    
    # Saudações
    if intent_type == "GREETING":
        response_text = "🤖 Olá! Bem-vindo ao Comercial Esperança. Como posso ajudar?"
        add_message_to_history(session, "assistant", response_text, "GREETING")
        return intent, response_text
    
    # Fallback
    response_text = "🤖 Desculpe, não entendi. Pode reformular?"
    add_message_to_history(session, "assistant", response_text, "REQUEST_CLARIFICATION")
    
    return intent, response_text


def _route_tool(session: Dict, state: Dict, intent: Dict, sender_phone: str) -> str:
    """Executa a ferramenta baseada na intenção identificada."""
    response_text = ""
    tool_name = intent.get("tool_name")
    parameters = intent.get("parameters", {})
    
    # Log da ferramenta sendo executada
    logging.info(f"[TOOL] Executando: {tool_name} com parâmetros: {parameters}")
    
    # Extrai dados do estado
    customer_context = state.get("customer_context")
    shopping_cart = state.get("shopping_cart", [])
    last_shown_products = state.get("last_shown_products", [])
    
    # FERRAMENTA: clear_cart
    if tool_name == "clear_cart":
        logging.info("[TOOL] Executando limpeza completa do carrinho...")
        message, empty_cart = clear_cart_completely(shopping_cart)
        shopping_cart.clear()
        
        response_text = message
        add_message_to_history(session, "assistant", response_text, "CLEAR_CART")
        
        # Atualiza estado
        state["shopping_cart"] = []
        state["last_shown_products"] = []
        state["last_bot_action"] = "CART_CLEARED"
        state["pending_action"] = None
        
        logging.info(f"[TOOL] Carrinho limpo. Itens removidos: {len(shopping_cart)}")
    
    # FERRAMENTA: view_cart
    elif tool_name == "view_cart":
        if shopping_cart:
            response_text = format_cart_for_display(shopping_cart)
        else:
            response_text = "🛒 Seu carrinho está vazio.\n\n" + format_quick_actions(has_cart=False)
        
        add_message_to_history(session, "assistant", response_text, "VIEW_CART")
        state["last_bot_action"] = "CART_VIEWED"
    
    # FERRAMENTA: checkout
    elif tool_name == "checkout":
        if not shopping_cart:
            response_text = "🛒 Seu carrinho está vazio!\n\n" + format_quick_actions(has_cart=False)
            add_message_to_history(session, "assistant", response_text, "EMPTY_CART")
        elif not customer_context:
            response_text = "⭐ Para finalizar a compra, preciso do seu CNPJ."
            add_message_to_history(session, "assistant", response_text, "REQUEST_CNPJ")
            session["awaiting_cnpj"] = True
        else:
            response_text = generate_checkout_summary(shopping_cart, customer_context)
            add_message_to_history(session, "assistant", response_text, "CHECKOUT_COMPLETE")
            
            # Limpa carrinho após finalização
            shopping_cart.clear()
            state["shopping_cart"] = []
            state["last_shown_products"] = []
            state["last_bot_action"] = "ORDER_COMPLETED"
    
    # FERRAMENTA: find_customer_by_cnpj
    elif tool_name == "find_customer_by_cnpj":
        cnpj = parameters.get("cnpj")
        if cnpj:
            logging.info(f"[TOOL] Buscando cliente por CNPJ: {cnpj}")
            customer = database.find_customer_by_cnpj(cnpj)
            
            if customer:
                customer_context = customer
                state["customer_context"] = customer_context
                
                if shopping_cart:
                    response_text = generate_checkout_summary(shopping_cart, customer_context)
                    add_message_to_history(session, "assistant", response_text, "CHECKOUT_COMPLETE")
                    
                    shopping_cart.clear()
                    state["shopping_cart"] = []
                else:
                    response_text = (
                        f"🤖 Olá, {customer_context['nome']}! Bem-vindo(a) de volta.\n\n"
                        + format_quick_actions(has_cart=False)
                    )
                    add_message_to_history(session, "assistant", response_text, "CUSTOMER_IDENTIFIED")
            else:
                response_text = f"🤖 Não encontrei um cliente com o CNPJ {cnpj}."
                
                if shopping_cart:
                    response_text += " Mas posso registrar seu pedido mesmo assim!\n\n"
                    response_text += generate_checkout_summary(shopping_cart)
                    add_message_to_history(session, "assistant", response_text, "CHECKOUT_COMPLETE")
                    
                    shopping_cart.clear()
                    state["shopping_cart"] = []
                else:
                    add_message_to_history(session, "assistant", response_text, "CUSTOMER_NOT_FOUND")
            
            session["awaiting_cnpj"] = False
        else:
            response_text = "🤖 Por favor, informe seu CNPJ."
            add_message_to_history(session, "assistant", response_text, "REQUEST_CNPJ")
    
    # FERRAMENTA: get_top_selling_products
    elif tool_name == "get_top_selling_products":
        logging.info("[TOOL] Buscando produtos mais vendidos...")
        products = database.get_top_selling_products(limit=3)
        
        if products:
            response_text = format_product_list_for_display(products, 0, 3)
            state["last_shown_products"] = products[:3]
            state["last_search_type"] = "top_selling"
            state["current_offset"] = 0
        else:
            response_text = "🤖 Não encontrei produtos no momento. Tente novamente mais tarde."
        
        add_message_to_history(session, "assistant", response_text, "SHOW_PRODUCTS")
        state["last_bot_action"] = "PRODUCTS_SHOWN"
    
    # FERRAMENTA: get_top_selling_products_by_name
    elif tool_name == "get_top_selling_products_by_name":
        product_name = parameters.get("product_name", "")
        logging.info(f"[TOOL] Buscando produtos por nome: {product_name}")

        search_result = search_products_with_suggestions(product_name, limit=3)
        products = search_result.get("products", [])
        suggestions = search_result.get("suggestions", [])

        if products:
            response_text = format_product_list_for_display(products, 0, 3)
            state["last_shown_products"] = products[:3]
            state["last_search_type"] = "by_name"
            state["last_search_params"] = {"product_name": product_name}
            state["current_offset"] = 0
        elif suggestions:
            suggestion_text = ", ".join(suggestions)
            response_text = (
                f"🤖 Não encontrei produtos para '{product_name}'. \n"
                f"Você quis dizer: {suggestion_text}?"
            )
        else:
            kb_products, kb_analysis = find_product_in_kb_with_analysis(product_name)
            if kb_products:
                logging.info(f"[KB_ANALYSIS] {kb_analysis}")
                response_text = format_product_list_for_display(kb_products, 0, min(3, len(kb_products)))
                state["last_shown_products"] = kb_products[:3]
                state["last_search_type"] = "kb"
                state["last_search_params"] = {"product_name": product_name}
                state["current_offset"] = 0
            else:
                response_text = (
                    f"🤖 Não encontrei produtos para '{product_name}'.\n\n"
                    "Tente buscar por categoria ou marca."
                )

        add_message_to_history(session, "assistant", response_text, "SEARCH_PRODUCTS")
        state["last_bot_action"] = "PRODUCTS_SEARCHED"
    
    # FERRAMENTA: add_item_to_cart
    elif tool_name == "add_item_to_cart":
        codprod = parameters.get("codprod")
        quantity = parameters.get("qt", 1)
        if not is_valid_quantity(quantity):
            quantity = 1

        product = None

        if codprod:
            logging.info(f"[TOOL] Adicionando produto {codprod} ao carrinho. Quantidade: {quantity}")
            product = database.get_product_by_codprod(codprod)
        elif parameters.get("product_name"):
            name_search = parameters.get("product_name")
            logging.info(f"[TOOL] Buscando produto por nome fuzzy: {name_search}")
            fuzzy_results = get_product_details_fuzzy(name_search)
            if fuzzy_results:
                product = fuzzy_results[0]
                codprod = product.get("codprod")

        if product:
            # Verifica se já existe no carrinho
            existing_item = None
            for item in shopping_cart:
                if item.get("codprod") == codprod:
                    existing_item = item
                    break

            if existing_item:
                existing_item["qt"] += quantity
                response_text = f"✅ Adicionei mais {quantity} {get_product_name(product)} ao carrinho."
            else:
                product["qt"] = quantity
                shopping_cart.append(product)
                response_text = f"✅ Adicionei {quantity} {get_product_name(product)} ao carrinho."

            response_text += "\n\n" + generate_continue_or_checkout_message(shopping_cart)

            add_message_to_history(session, "assistant", response_text, "ADD_TO_CART")
            state["last_bot_action"] = "ITEM_ADDED"
        else:
            response_text = "🤖 Produto não encontrado. Tente buscar novamente."
            add_message_to_history(session, "assistant", response_text, "PRODUCT_NOT_FOUND")
    
    # FERRAMENTA: handle_chitchat
    elif tool_name == "handle_chitchat":
        response_text = parameters.get("response_text", "Como posso ajudar você hoje?")
        response_text += "\n\n" + format_quick_actions(has_cart=bool(shopping_cart))
        add_message_to_history(session, "assistant", response_text, "CHITCHAT")
    
    # FERRAMENTA: start_new_order
    elif tool_name == "start_new_order":
        clear_session(sender_phone)
        shopping_cart.clear()
        state["shopping_cart"] = []
        state["customer_context"] = None
        state["last_shown_products"] = []
        state["last_bot_action"] = "NEW_ORDER_STARTED"

        response_text = "🆕 Novo pedido iniciado! Carrinho limpo.\n\n" + format_quick_actions(has_cart=False)
        add_message_to_history(session, "assistant", response_text, "NEW_ORDER")
    
    # Fallback para ferramentas não implementadas
    else:
        logging.warning(f"[TOOL] Ferramenta desconhecida: {tool_name}")
        response_text = "🤖 Desculpe, não consegui processar sua solicitação. Tente novamente."
        add_message_to_history(session, "assistant", response_text, "ERROR")
    
    return response_text


def _finalize_session(sender_phone: str, session: Dict, state: Dict, response_text: str) -> None:
    """Atualiza e persiste a sessão, além de enviar a resposta ao usuário."""
    # Atualiza contexto da sessão
    update_session_context(session, state)
    
    # Valida e corrige sessão antes de salvar
    session = validate_and_correct_session(session)
    
    # Salva sessão
    save_session(sender_phone, session)
    
    # Envia resposta
    if response_text:
        logging.info(f"[RESPONSE] Enviando para {sender_phone}: {response_text[:100]}...")
        twilio_client.send_whatsapp_message(to=sender_phone, body=response_text)


def process_message_async(sender_phone: str, incoming_msg: str):
    """Processa mensagem em thread separada com contexto completo."""
    with app.app_context():
        try:
            logging.info(f"\n{'='*60}")
            logging.info(f"[NEW_MESSAGE] De: {sender_phone} | Mensagem: '{incoming_msg}'")
            logging.info(f"{'='*60}")
            
            # Carrega sessão
            session = load_session(sender_phone)
            
            # Valida e corrige sessão
            session = validate_and_correct_session(session)
            
            # Registra mensagem do usuário no histórico
            add_message_to_history(session, "user", incoming_msg)
            
            # Log do contexto atual
            context = get_conversation_context(session, max_messages=5)
            logging.info(f"[CONTEXT]\n{context}")
            
            # Extrai estado
            state = _extract_state(session)
            
            # Processa ações pendentes
            intent, response_text = _handle_pending_action(session, state, incoming_msg)
            
            # Se não houve resposta, processa mensagem
            if not intent and not response_text:
                intent, response_text = _process_user_message(session, state, incoming_msg)
            
            # Executa ferramenta se houver intenção
            if intent:
                response_text = _route_tool(session, state, intent, sender_phone)
            
            # Finaliza e envia resposta
            _finalize_session(sender_phone, session, state, response_text)
            
            logging.info(f"[COMPLETED] Processamento finalizado para: '{incoming_msg}'")
            
        except Exception as e:
            logging.error(f"[ERROR] Erro no processamento: {e}", exc_info=True)
            error_msg = "🤖 Desculpe, ocorreu um erro. Por favor, tente novamente."
            try:
                twilio_client.send_whatsapp_message(to=sender_phone, body=error_msg)
            except:
                pass


# ================================================================================
# ENDPOINTS
# ================================================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint principal do webhook do WhatsApp."""
    try:
        incoming_msg = request.form.get('Body', '').strip()
        sender_phone = request.form.get('From', '').replace('whatsapp:', '')
        
        if incoming_msg and sender_phone:
            # Processa em thread separada
            thread = threading.Thread(
                target=process_message_async,
                args=(sender_phone, incoming_msg)
            )
            thread.start()
        
        # Resposta vazia para o Twilio
        resp = MessagingResponse()
        return str(resp)
    
    except Exception as e:
        logging.error(f"[WEBHOOK] Erro: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/health', methods=['GET'])
def health():
    """Endpoint de health check."""
    kb_stats = knowledge.get_kb_statistics()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0",
        "knowledge_base": kb_stats
    })


@app.route('/stats/<phone>', methods=['GET'])
def get_stats(phone):
    """Endpoint para obter estatísticas de uma sessão."""
    try:
        session = load_session(phone)
        stats = get_session_stats(session)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ================================================================================
# INICIALIZAÇÃO
# ================================================================================

if __name__ == '__main__':
    logging.info("🚀 G.A.V. 2.0 - Sistema iniciado com sucesso!")
    logging.info(f"📊 Contexto: COMPLETO | Histórico: ATIVO | Validações: ATIVAS")
    app.run(host='0.0.0.0', port=8080, debug=True)
