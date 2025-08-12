# file: IA/app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
from typing import Dict, List, Tuple, Union
from datetime import datetime
import re
from db import database
from ai_llm import llm_interface
from knowledge import knowledge
from utils import logger_config
from core.session_manager import (
    load_session, save_session, clear_session,
    format_product_list_for_display, format_cart_for_display,
    add_message_to_history, get_conversation_context
)
from utils.quantity_extractor import extract_quantity, is_valid_quantity
from communication import twilio_client

from db.database import search_products_with_suggestions, get_product_details_fuzzy
from knowledge.knowledge import find_product_in_kb_with_analysis

app = Flask(__name__)
logger_config.setup_logger()

def get_product_name(product: Dict) -> str:
    """Extrai o nome do produto, compatível com produtos do banco (descricao) e da KB (canonical_name)."""
    return product.get('descricao') or product.get('canonical_name', 'Produto sem nome')

def format_options_menu(options: List[str]) -> str:
    """Formata um menu de opções numeradas (máximo 3)."""
    if not options:
        return ""
    
    # Limita a 3 opções conforme especificação
    limited_options = options[:3]
    menu = ""
    for i, option in enumerate(limited_options, 1):
        menu += f"[{i} {option}] "
    return menu.strip()

def format_product_selection(products: List[Dict], title: str = "Opções encontradas") -> str:
    """Formata lista de produtos para seleção (máximo 3) com estilo direto."""
    if not products:
        return "Não achei esse item. Posso sugerir similares?"
    
    # Limita a 3 produtos conforme especificação
    limited_products = products[:3]
    
    response = f"{title}:\n"
    for i, product in enumerate(limited_products, 1):
        price = product.get('pvenda') or product.get('preco_varejo', 0.0)
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        product_name = get_product_name(product)
        response += f"{i}. {product_name} — {price_str}\n"
    
    response += "Qual você quer? Responda 1, 2 ou 3."
    return response

def format_checkout_summary(cart: List[Dict], customer_context: Dict = None) -> str:
    """Formata resumo final do pedido com estilo objetivo."""
    if not cart:
        return "Carrinho vazio — nenhum pedido para finalizar."
    
    summary = "Resumo:\n"
    total = 0.0
    
    for item in cart:
        price = item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        subtotal = price * qt
        total += subtotal
        
        product_name = get_product_name(item)
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # Formata quantidade para exibição
        if isinstance(qt, float):
            qty_display = f"{qt:.1f}".rstrip('0').rstrip('.')
        else:
            qty_display = str(qt)
        
        summary += f"• {product_name} — {qty_display}× {price_str} = {subtotal_str}\n"
    
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    summary += f"Total: {total_str}\n"
    summary += "Pedido fechado (MODO TESTE — sem pagamento/entrega). Deseja fazer outra busca?"
    
    return summary

def handle_numeric_selection(user_message: str, last_shown_products: List[Dict], session_id: str) -> Tuple[bool, str]:
    """Processa seleção numérica (1, 2 ou 3) baseada nos últimos produtos mostrados."""
    if not last_shown_products:
        return False, ""
    
    # Extrai números da mensagem
    numbers = re.findall(r'\b([123])\b', user_message.strip())
    if not numbers:
        return False, ""
    
    try:
        selection = int(numbers[0])
        if 1 <= selection <= len(last_shown_products):
            selected_product = last_shown_products[selection - 1]
            
            # Extrai quantidade da mensagem se especificada
            quantity = extract_quantity(user_message)
            if not quantity or quantity <= 0:
                quantity = 1
            
            # Adiciona ao carrinho
            success, cart_message, updated_cart = add_item_to_cart_quantity(
                load_session(session_id).get("shopping_cart", []),
                selected_product.get('codprod'),
                quantity
            )
            
            if success:
                # Atualiza sessão
                session_data = load_session(session_id)
                session_data["shopping_cart"] = updated_cart
                session_data["last_bot_action"] = "ITEM_ADDED"
                save_session(session_id, session_data)
                
                product_name = get_product_name(selected_product)
                qty_display = f"{quantity:.1f}".rstrip('0').rstrip('.') if isinstance(quantity, float) else str(quantity)
                
                response = f"Adicionado: {product_name} ({qty_display} un). O que prefere? [1 Ver carrinho] [2 Continuar] [3 Fechar pedido]"
                return True, response
            
        return False, ""
    except (ValueError, IndexError):
        return False, ""

def add_item_to_cart_quantity(cart: List[Dict], codprod: int, quantity: Union[int, float]) -> Tuple[bool, str, List[Dict]]:
    """Adiciona item ao carrinho com quantidade especificada."""
    if not codprod or not is_valid_quantity(quantity):
        return False, "Dados inválidos para adicionar ao carrinho.", cart
    
    # Busca detalhes do produto
    product_details = database.get_product_by_codprod(codprod)
    if not product_details:
        return False, f"Produto {codprod} não encontrado.", cart
    
    # Verifica se já existe no carrinho
    for item in cart:
        if item.get('codprod') == codprod:
            item['qt'] += quantity
            product_name = get_product_name(item)
            cart_display = format_cart_for_display(cart)
            return True, f"Quantidade de {product_name} atualizada.\n\n{cart_display}", cart
    
    # Adiciona novo item
    new_item = product_details.copy()
    new_item['qt'] = quantity
    cart.append(new_item)
    
    product_name = get_product_name(new_item)
    cart_display = format_cart_for_display(cart)
    
    return True, f"{product_name} adicionado ao carrinho.\n\n{cart_display}", cart

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
    
    # Formata a quantidade para exibição
    if isinstance(new_qty, float):
        qty_display = f"{new_qty:.1f}".rstrip('0').rstrip('.')
    else:
        qty_display = str(new_qty)
    
    cart_display = format_cart_for_display(cart)
    message = f"Quantidade de {product_name} atualizada para {qty_display}\n\n{cart_display}"
    
    return True, message, cart

def handle_update_cart_item(cart: List[Dict], parameters: Dict) -> Tuple[bool, str]:
    """Gerencia atualizações no carrinho (remover, atualizar quantidade, adicionar quantidade)."""
    action = parameters.get('action', '').lower()
    
    if not cart:
        return False, "Seu carrinho está vazio."
    
    if action == 'remove':
        # Remove item por índice ou nome
        index = parameters.get('index')
        product_name = parameters.get('product_name')
        
        if index is not None:
            if 0 <= index < len(cart):
                removed = cart.pop(index)
                return True, f"{get_product_name(removed)} removido do carrinho."
            else:
                return False, f"Número inválido. Use um número entre 1 e {len(cart)}."
        
        elif product_name:
            # Busca por nome
            product_name_lower = product_name.lower()
            for i, item in enumerate(cart):
                if product_name_lower in get_product_name(item).lower():
                    removed = cart.pop(i)
                    return True, f"{get_product_name(removed)} removido do carrinho."
            return False, f"Produto '{product_name}' não encontrado no carrinho."
        
        return False, "Especifique o índice ou nome do produto para remover."
    
    elif action == 'update_quantity':
        # Atualiza quantidade total
        index = parameters.get('index')
        qt = parameters.get('qt', 0)
        
        if not is_valid_quantity(qt):
            return False, f"Quantidade inválida: {qt}"
        
        if index is not None and 0 <= index < len(cart):
            cart[index]['qt'] = qt
            return True, f"Quantidade de {get_product_name(cart[index])} atualizada para {qt}."
        
        return False, "Índice inválido."
    
    elif action == 'add_quantity':
        # Adiciona quantidade ao item existente
        index = parameters.get('index')
        qt = parameters.get('qt', 0)
        
        if not is_valid_quantity(qt):
            return False, f"Quantidade inválida: {qt}"
        
        if index is not None and 0 <= index < len(cart):
            cart[index]['qt'] += qt
            return True, f"Adicionado {qt} unidades de {get_product_name(cart[index])}."
        
        return False, "Índice inválido."
    
    return False, "Ação não reconhecida."

def clear_cart(cart: List[Dict]) -> Tuple[bool, str, List[Dict]]:
    """Esvazia o carrinho completamente."""
    if not cart:
        return False, "Carrinho já está vazio.", cart
    
    cart.clear()
    return True, "Carrinho esvaziado com sucesso.", cart

def process_message_async(session_id: str, user_message: str):
    """Processa mensagem de forma assíncrona com melhorias de UX."""
    try:
        # Carrega estado da sessão
        state = load_session(session_id)
        customer_context = state.get("customer_context")
        shopping_cart = state.get("shopping_cart", [])
        last_search_type = state.get("last_search_type")
        last_search_params = state.get("last_search_params", {})
        current_offset = state.get("current_offset", 0)
        last_shown_products = state.get("last_shown_products", [])
        last_bot_action = state.get("last_bot_action")
        pending_action = state.get("pending_action")
        last_kb_search_term = state.get("last_kb_search_term")

        response_text = ""

        # 🆕 PRIORIDADE 1: Verifica seleção numérica (1, 2, 3)
        if last_shown_products and re.match(r'^\s*[123]\s*$', user_message.strip()):
            handled, response = handle_numeric_selection(user_message, last_shown_products, session_id)
            if handled:
                add_message_to_history(load_session(session_id), 'user', user_message, 'NUMERIC_SELECTION')
                add_message_to_history(load_session(session_id), 'assistant', response, 'ITEM_ADDED_WITH_OPTIONS')
                
                twilio_client.send_message(session_id, response)
                logging.info(f"THREAD: Processamento finalizado para '{user_message}'")
                return

        # 🆕 PRIORIDADE 2: Verifica comandos de carrinho diretos
        user_lower = user_message.lower().strip()
        
        # Comandos de esvaziar carrinho
        if any(cmd in user_lower for cmd in ['esvaziar carrinho', 'limpar carrinho', 'zerar carrinho']):
            success, message, new_cart = clear_cart(shopping_cart)
            if success:
                state["shopping_cart"] = new_cart
                save_session(session_id, state)
                response_text = message + " Posso ajudar com mais alguma coisa?"
                add_message_to_history(state, 'user', user_message, 'CLEAR_CART')
                add_message_to_history(state, 'assistant', response_text, 'CART_CLEARED')
                
                twilio_client.send_message(session_id, response_text)
                logging.info(f"THREAD: Processamento finalizado para '{user_message}'")
                return

        # 🆕 PRIORIDADE 3: Processa através do LLM
        intent = llm_interface.get_intent(
            user_message, 
            state, 
            customer_context, 
            len(shopping_cart)
        )
        
        if not intent:
            response_text = "Não entendi. Diga o nome do produto (ex.: 'Arroz 5kg')."
            add_message_to_history(state, 'user', user_message, 'NO_INTENT')
            add_message_to_history(state, 'assistant', response_text, 'FALLBACK')
            
            twilio_client.send_message(session_id, response_text)
            logging.info(f"THREAD: Processamento finalizado para '{user_message}'")
            return

        logging.info(f"INTENÇÃO PROCESSADA: {intent}")
        
        tool_name = intent.get("tool_name")
        parameters = intent.get("parameters", {})

        # Log para ferramentas que acessam banco
        db_intensive_tools = [
            "get_top_selling_products",
            "get_top_selling_products_by_name",
            "show_more_products",
            "report_incorrect_product",
            "get_product_by_codprod",
        ]
        if tool_name in db_intensive_tools:
            print(f">>> CONSOLE: Acessando o Banco de Dados (ferramenta: {tool_name})...")

        # 🆕 PROCESSAMENTO DE FERRAMENTAS COM ESTILO ATUALIZADO
        if tool_name in ["get_top_selling_products", "get_top_selling_products_by_name"]:
            last_kb_search_term, last_shown_products = None, []

            if tool_name == "get_top_selling_products_by_name":
                product_name = parameters.get("product_name", "")

                # Busca inteligente com Knowledge Base primeiro
                kb_products, kb_analysis = find_product_in_kb_with_analysis(product_name)

                if kb_products and kb_analysis.get("quality") in ["excellent", "good"]:
                    # Knowledge Base encontrou bons resultados
                    last_kb_search_term = product_name
                    last_shown_products = kb_products[:3]  # Limita a 3 conforme especificação

                    response_text = format_product_selection(last_shown_products, "Encontrei")
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    add_message_to_history(state, 'assistant', response_text, 'SHOW_PRODUCTS_FROM_KB')

                else:
                    # Busca no banco de dados
                    current_offset, last_shown_products = 0, []
                    last_search_type, last_search_params = "by_name", {'product_name': product_name}

                    search_result = search_products_with_suggestions(
                        product_name,
                        limit=3,  # Limita a 3 conforme especificação
                        offset=current_offset
                    )
                    
                    found_products = search_result.get("products", [])
                    suggestions = search_result.get("suggestions", [])

                    if found_products:
                        last_shown_products = found_products
                        response_text = format_product_selection(last_shown_products, "Encontrei")
                        last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    else:
                        response_text = "Não achei esse item. Posso sugerir similares?"
                        if suggestions:
                            response_text += f" Tente: {', '.join(suggestions[:2])}"
                        last_bot_action = "NO_PRODUCTS_FOUND"

                    add_message_to_history(state, 'assistant', response_text, 'SHOW_PRODUCTS_FROM_DB')

            else:  # get_top_selling_products
                products = database.get_top_selling_products(limit=3, offset=current_offset)
                if products:
                    last_shown_products = products
                    response_text = format_product_selection(last_shown_products, "Produtos mais vendidos")
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                else:
                    response_text = "Nenhum produto disponível no momento."
                    last_bot_action = "NO_PRODUCTS_FOUND"

                last_search_type, last_search_params = "top_selling", {}
                add_message_to_history(state, 'assistant', response_text, 'SHOW_TOP_PRODUCTS')

        elif tool_name == "add_item_to_cart":
            codprod = parameters.get("codprod")
            qt = parameters.get("qt", 1)

            success, cart_message, updated_cart = add_item_to_cart_quantity(shopping_cart, codprod, qt)
            
            if success:
                shopping_cart = updated_cart
                product_name = get_product_name(updated_cart[-1]) if updated_cart else "Produto"
                qty_display = f"{qt:.1f}".rstrip('0').rstrip('.') if isinstance(qt, float) else str(qt)
                
                response_text = f"Adicionado: {product_name} ({qty_display} un). O que prefere? [1 Ver carrinho] [2 Continuar] [3 Fechar pedido]"
                last_bot_action = "ITEM_ADDED"
            else:
                response_text = cart_message
                last_bot_action = "ADD_ITEM_FAILED"

            add_message_to_history(state, 'assistant', response_text, 'ADD_TO_CART')

        elif tool_name == "view_cart":
            if shopping_cart:
                response_text = format_cart_for_display(shopping_cart)
                response_text += "\nO que prefere? [1 Continuar] [2 Fechar pedido]"
            else:
                response_text = "Seu carrinho está vazio. Posso mostrar nossos produtos?"
            
            last_bot_action = "SHOW_CART"
            add_message_to_history(state, 'assistant', response_text, 'VIEW_CART')

        elif tool_name == "update_cart_item":
            success, update_message = handle_update_cart_item(shopping_cart, parameters)
            response_text = update_message
            
            if success:
                last_bot_action = "CART_UPDATED"
            else:
                last_bot_action = "CART_UPDATE_FAILED"

            add_message_to_history(state, 'assistant', response_text, 'UPDATE_CART')

        elif tool_name == "checkout":
            if shopping_cart:
                response_text = format_checkout_summary(shopping_cart, customer_context)
                
                # Limpa carrinho após finalizar
                shopping_cart.clear()
                last_bot_action = "ORDER_COMPLETED"
                
                # Registra estatísticas se aplicável
                if last_kb_search_term:
                    database.add_search_statistic(last_kb_search_term, "knowledge_base", None, "success")
            else:
                response_text = "Carrinho vazio — nenhum pedido para finalizar. Posso mostrar nossos produtos?"
                last_bot_action = "EMPTY_CART_CHECKOUT"

            add_message_to_history(state, 'assistant', response_text, 'CHECKOUT')

        elif tool_name == "handle_chitchat":
            response_text = parameters.get("response_text", "Olá! Sou o G.A.V. do Comercial Esperança. Posso mostrar nossos produtos mais vendidos ou você já sabe o que procura?")
            last_bot_action = "CHITCHAT"
            add_message_to_history(state, 'assistant', response_text, 'CHITCHAT')

        elif tool_name == "ask_continue_or_checkout":
            response_text = "O que prefere? [1 Ver carrinho] [2 Continuar] [3 Fechar pedido]"
            last_bot_action = "ASKING_NEXT_ACTION"
            add_message_to_history(state, 'assistant', response_text, 'ASK_CONTINUE_OR_CHECKOUT')

        elif tool_name == "show_more_products":
            if last_search_type and last_search_params:
                current_offset += 3  # Incrementa para próximos 3 produtos
                
                if last_search_type == "by_name":
                    product_name = last_search_params.get("product_name", "")
                    search_result = search_products_with_suggestions(
                        product_name,
                        limit=3,
                        offset=current_offset
                    )
                    products = search_result.get("products", [])
                else:
                    products = database.get_top_selling_products(limit=3, offset=current_offset)

                if products:
                    last_shown_products = products
                    response_text = format_product_selection(products, "Mais opções")
                    last_bot_action = "SHOWING_MORE_PRODUCTS"
                else:
                    response_text = "Não há mais produtos para mostrar."
                    last_bot_action = "NO_MORE_PRODUCTS"
            else:
                response_text = "Nenhuma busca anterior para continuar."
                last_bot_action = "NO_PREVIOUS_SEARCH"

            add_message_to_history(state, 'assistant', response_text, 'SHOW_MORE_PRODUCTS')

        elif tool_name == "find_customer_by_cnpj":
            cnpj = parameters.get("cnpj", "")
            customer = database.find_customer_by_cnpj(cnpj)
            
            if customer:
                customer_context = customer
                response_text = f"Olá, {customer['nome']}! Como posso ajudar hoje?"
                last_bot_action = "CUSTOMER_IDENTIFIED"
            else:
                response_text = "CNPJ não encontrado. Posso ajudar mesmo assim?"
                last_bot_action = "CUSTOMER_NOT_FOUND"

            add_message_to_history(state, 'assistant', response_text, 'FIND_CUSTOMER')

        elif tool_name == "start_new_order":
            shopping_cart.clear()
            last_shown_products.clear()
            current_offset = 0
            last_search_type = None
            last_search_params = {}
            last_kb_search_term = None
            
            response_text = "Novo pedido iniciado! O que você gostaria de comprar?"
            last_bot_action = "NEW_ORDER_STARTED"
            add_message_to_history(state, 'assistant', response_text, 'START_NEW_ORDER')

        else:
            response_text = "Tive um problema na consulta agora. Tentar novamente?"
            last_bot_action = "UNKNOWN_TOOL"
            add_message_to_history(state, 'assistant', response_text, 'UNKNOWN_TOOL')

        # Atualiza e salva estado
        state.update({
            "customer_context": customer_context,
            "shopping_cart": shopping_cart,
            "last_search_type": last_search_type,
            "last_search_params": last_search_params,
            "current_offset": current_offset,
            "last_shown_products": last_shown_products,
            "last_bot_action": last_bot_action,
            "pending_action": pending_action,
            "last_kb_search_term": last_kb_search_term
        })

        save_session(session_id, state)
        add_message_to_history(state, 'user', user_message, tool_name.upper())
        
        # Envia resposta
        twilio_client.send_message(session_id, response_text)
        logging.info(f"THREAD: Processamento finalizado para '{user_message}'")

    except Exception as e:
        logging.error(f"ERRO CRÍTICO NA THREAD: {e}", exc_info=True)
        error_message = "Tive um problema na consulta agora. Tentar novamente?"
        twilio_client.send_message(session_id, error_message)

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint para receber mensagens do WhatsApp via Twilio."""
    try:
        incoming_msg = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")
        
        if not incoming_msg or not from_number:
            return str(MessagingResponse())

        # Inicia processamento assíncrono
        session_id = from_number
        thread = threading.Thread(
            target=process_message_async,
            args=(session_id, incoming_msg)
        )
        thread.daemon = True
        thread.start()

        return str(MessagingResponse())

    except Exception as e:
        logging.error(f"Erro no webhook: {e}", exc_info=True)
        return str(MessagingResponse())

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check."""
    return {"status": "ok", "service": "G.A.V. WhatsBot"}, 200

if __name__ == "__main__":
    logging.info("🤖 G.A.V. (Gentil Assistente de Vendas) iniciando...")
    
    # Teste de conexões
    try:
        if database.test_connection():
            logging.info("✅ Conexão com banco de dados OK")
        else:
            logging.warning("⚠️ Falha na conexão com banco de dados")
    except Exception as e:
        logging.error(f"❌ Erro ao testar conexão: {e}")

    # Inicia aplicação
    app.run(host="0.0.0.0", port=8080, debug=True)