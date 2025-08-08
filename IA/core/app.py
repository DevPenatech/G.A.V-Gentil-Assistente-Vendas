# file: IA/app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
from IA.database import database
from IA.ai_llm import llm_interface
from IA.knowledge import knowledge
from IA.utils import logger_config
from IA.core.session_manager import (
    load_session, save_session, clear_session,
    format_product_list_for_display, format_cart_for_display
)
from IA.communication import twilio_client
import os

app = Flask(__name__)
logger_config.setup_logger()

def process_message_async(sender_phone, incoming_msg):
    """
    Esta função faz todo o trabalho pesado em segundo plano (thread) para não causar timeout.
    """
    with app.app_context():
        try:
            print(f"\n--- INÍCIO DO PROCESSAMENTO DA THREAD PARA: '{incoming_msg}' ---")
            session = load_session()
            
            # Extrai dados da sessão para variáveis locais
            customer_context = session.get("customer_context")
            shopping_cart = session.get("shopping_cart", [])
            last_search_type = session.get("last_search_type")
            last_search_params = session.get("last_search_params", {})
            current_offset = session.get("current_offset", 0)
            last_shown_products = session.get("last_shown_products", [])
            last_bot_action = session.get("last_bot_action")
            pending_action = session.get("pending_action")
            last_kb_search_term = session.get("last_kb_search_term")
            intent = None
            response_text = ""

            # 1. Trata ações pendentes que requerem uma resposta direta
            if pending_action == 'AWAITING_QUANTITY':
                print(">>> CONSOLE: Tratando ação pendente AWAITING_QUANTITY")
                try:
                    qt = int(incoming_msg)
                    if qt > 0:
                        product_to_add = session.get('pending_product_for_cart')
                        if product_to_add:
                            term_to_learn = session.get("term_to_learn_after_quantity")
                            if term_to_learn:
                                print(f">>> CONSOLE: Aprendendo que '{term_to_learn}' se refere a '{product_to_add['descricao']}'...")
                                knowledge.update_kb(term_to_learn, product_to_add)
                                session["term_to_learn_after_quantity"] = None
                            shopping_cart.append({**product_to_add, "qt": qt})
                            response_text = f"✅ Adicionado!\n\n{format_cart_for_display(shopping_cart)}"
                        else:
                            response_text = "🤖 Ocorreu um erro. Não sei qual produto adicionar."
                    else:
                        response_text = "🤖 Por favor, insira uma quantidade positiva."
                except ValueError:
                    response_text = "🤖 Quantidade inválida. Por favor, digite apenas números."
                pending_action = None
                session['pending_product_for_cart'] = None
            
            elif pending_action:
                print(f">>> CONSOLE: Tratando ação pendente {pending_action}")
                affirmative_responses = ["sim", "pode ser", "s", "claro", "quero", "ok", "beleza"]
                negative_responses = ["não", "n", "agora não", "deixa"]
                if incoming_msg.lower() in affirmative_responses:
                    if pending_action == "show_top_selling":
                        intent = {"tool_name": "get_top_selling_products", "parameters": {}}
                    pending_action = None
                elif incoming_msg.lower() in negative_responses:
                    response_text = "🤖 Tudo bem! O que você gostaria de fazer então?"
                    pending_action = None
                else:
                    pending_action = None

            # 2. Se nenhuma intenção foi definida, processa o input do usuário
            if not intent and not response_text:
                if not incoming_msg:
                    if last_bot_action == "AWAITING_PRODUCT_SELECTION":
                        response_text = "🤖 Não entendi. Quer selecionar um dos produtos da lista? Se sim, me diga o número. Se quiser buscar outra coisa, é só digitar o nome do produto."
                    else:
                        response_text = "🤖 Por favor, me diga o que você precisa."
                elif incoming_msg.isdigit() and last_bot_action in ["AWAITING_PRODUCT_SELECTION", "AWAITING_CORRECTION_SELECTION"]:
                    intent = {"tool_name": "add_item_to_cart", "parameters": {"index": int(incoming_msg)}}
                elif incoming_msg.lower() in ["mais", "proximo", "próximo", "mais produtos"]:
                    intent = {"tool_name": "show_more_products", "parameters": {}}
                else:
                    print(">>> CONSOLE: Consultando a IA (Ollama)...")
                    intent = llm_interface.get_intent(incoming_msg, customer_context, len(shopping_cart))
                    print(f">>> CONSOLE: IA retornou a intenção: {intent}")

            # 3. Roteamento de Ferramentas
            if intent and not response_text:
                logging.info(f"INTENÇÃO PROCESSADA: {intent}")
                tool_name = intent.get("tool_name")
                parameters = intent.get("parameters", {})
                
                db_intensive_tools = ["get_top_selling_products", "get_top_selling_products_by_name", "show_more_products", "report_incorrect_product", "get_product_by_codprod", "search_by_category"]
                if tool_name in db_intensive_tools:
                    print(f">>> CONSOLE: Acessando o Banco de Dados (ferramenta: {tool_name})...")

                if tool_name in ["get_top_selling_products", "get_top_selling_products_by_name"]:
                    last_kb_search_term, last_shown_products = None, []
                    if tool_name == "get_top_selling_products_by_name":
                        product_name = parameters.get("product_name", "")
                        kb_entry = knowledge.find_product_in_kb(product_name)
                        if kb_entry and kb_entry.get("codprod"):
                            last_kb_search_term = product_name
                            product = database.get_product_by_codprod(kb_entry["codprod"])
                            products, title = [product] if product else [], f"Encontrei isto para '{product_name}' (busca rápida):"
                            last_shown_products = products
                            response_text = format_product_list_for_display(products, title, False, 0)
                            last_bot_action = "AWAITING_PRODUCT_SELECTION"
                        else:
                            current_offset, last_shown_products = 0, []
                            last_search_type, last_search_params = "by_name", {'product_name': product_name}
                            products = database.get_top_selling_products_by_name(product_name, offset=current_offset)
                            title = f"Encontrei estes produtos relacionados a '{product_name}':"
                            current_offset += 5
                            last_shown_products.extend(products)
                            response_text = format_product_list_for_display(products, title, len(products) == 5, 0)
                            last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    else: # get_top_selling_products
                        current_offset, last_shown_products = 0, []
                        last_search_type, last_search_params = "top_selling", parameters
                        products = database.get_top_selling_products(offset=current_offset)
                        title = "Estes são nossos produtos mais populares:"
                        current_offset += 5
                        last_shown_products.extend(products)
                        response_text = format_product_list_for_display(products, title, len(products) == 5, 0)
                        last_bot_action = "AWAITING_PRODUCT_SELECTION"
                
                elif tool_name == "search_by_category":
                    category = parameters.get("category", "")
                    print(f">>> CONSOLE: Buscando pela categoria '{category}'...")
                    semantic_map = knowledge.load_semantic_map()
                    category_lower = category.lower()
                    search_terms = semantic_map.get(category_lower) or semantic_map.get(category_lower.rstrip('s'))

                    if search_terms:
                        print(f">>> CONSOLE: Termos semânticos encontrados: {search_terms}")
                        current_offset, last_shown_products = 0, []
                        last_search_type = "by_category"
                        last_search_params = {'category_terms': search_terms, 'category_name': category}
                        products = database.search_products_by_category_terms(search_terms, offset=current_offset)
                        title = f"Encontrei estes produtos na categoria '{category}':"
                        current_offset += 5
                        last_shown_products.extend(products)
                        response_text = format_product_list_for_display(products, title, len(products) == 5, 0)
                        last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    else:
                        print(f">>> CONSOLE: Categoria '{category}' não encontrada no mapa semântico.")
                        response_text = f"🤖 Desculpe, não conheço a categoria '{category}'. Tente buscar por um produto específico."

                elif tool_name == "add_item_to_cart":
                    product_to_add = None
                    if "index" in parameters:
                        try:
                            idx = int(parameters["index"]) - 1
                            if 0 <= idx < len(last_shown_products): product_to_add = last_shown_products[idx]
                        except (ValueError, IndexError): pass
                    if not product_to_add and "product_name" in parameters:
                        product_to_add = database.get_product_details(parameters["product_name"])
                    if product_to_add:
                        term_to_learn = None
                        is_correction = last_bot_action == "AWAITING_CORRECTION_SELECTION"
                        is_new_learning = last_bot_action == "AWAITING_PRODUCT_SELECTION" and last_search_type == "by_name"
                        if is_correction: term_to_learn = last_kb_search_term
                        elif is_new_learning: term_to_learn = last_search_params.get("product_name")
                        if term_to_learn:
                            session["term_to_learn_after_quantity"] = term_to_learn
                        pending_action = 'AWAITING_QUANTITY'
                        session['pending_product_for_cart'] = product_to_add
                        response_text = f"🤖 Qual a quantidade de '{product_to_add['descricao']}' você deseja?"
                    else:
                        response_text = "🤖 Desculpe, não consegui identificar o produto."

                elif tool_name == "report_incorrect_product":
                    if last_kb_search_term:
                        response_text = f"🤖 Entendido! Desculpe pelo erro. Buscando no banco por '{last_kb_search_term}'...\n\n"
                        current_offset, last_shown_products = 0, []
                        products = database.get_top_selling_products_by_name(last_kb_search_term, offset=current_offset)
                        last_search_type, last_search_params = "by_name", {"product_name": last_kb_search_term}
                        current_offset += 5
                        last_shown_products.extend(products)
                        title = f"Resultados da busca ampla para '{last_kb_search_term}':"
                        response_text += format_product_list_for_display(products, title, len(products) == 5, 0)
                        last_bot_action = "AWAITING_CORRECTION_SELECTION"
                    else:
                        response_text = "🤖 Entendido. Por favor, me diga o que você estava procurando."

                elif tool_name == "show_more_products":
                    if not last_search_type:
                        response_text = "🤖 Para eu mostrar mais, primeiro você precisa fazer uma busca."
                    else:
                        offset_before_call = current_offset
                        products = []
                        title = ""
                        if last_search_type == "top_selling":
                            products = database.get_top_selling_products(offset=current_offset)
                            title = "Mostrando mais produtos populares:"
                        elif last_search_type == "by_name":
                            product_name = last_search_params.get("product_name", "")
                            products = database.get_top_selling_products_by_name(product_name, offset=current_offset)
                            title = f"Mostrando mais produtos relacionados a '{product_name}':"
                        elif last_search_type == "by_category":
                            search_terms = last_search_params.get('category_terms', [])
                            category_name = last_search_params.get('category_name', 'resultados')
                            products = database.search_products_by_category_terms(search_terms, offset=current_offset)
                            title = f"Mostrando mais produtos da categoria '{category_name}':"
                        
                        if not products:
                            response_text = "🤖 Não encontrei mais produtos para essa busca."
                        else:
                            current_offset += 5
                            last_shown_products.extend(products)
                            response_text = format_product_list_for_display(products, title, len(products) == 5, offset=offset_before_call)
                            last_bot_action = "AWAITING_PRODUCT_SELECTION"
                
                elif tool_name == 'view_cart': response_text = format_cart_for_display(shopping_cart)
                
                elif tool_name == 'start_new_order':
                    customer_context, shopping_cart, last_shown_products, last_search_type, last_search_params, current_offset, last_kb_search_term = None, [], [], None, {}, 0, None
                    clear_session()
                    response_text = "🧹 Certo! Carrinho e dados limpos. Vamos começar de novo!"

                elif tool_name == 'checkout':
                    if not shopping_cart: response_text = "🤖 Seu carrinho está vazio!"
                    elif not customer_context: response_text = "⭐ Para finalizar a compra, preciso do seu CNPJ."
                    else:
                        response_text = f"✅ Pedido para {customer_context['nome']} pronto para ser finalizado!\n\n{format_cart_for_display(shopping_cart)}\n(Funcionalidade de inserção do pedido no sistema será implementada futuramente)"
                
                elif tool_name == 'find_customer_by_cnpj':
                    cnpj = parameters.get("cnpj")
                    if cnpj:
                        customer = database.find_customer_by_cnpj(cnpj)
                        if customer:
                            customer_context = customer
                            response_text = f"🤖 Olá, {customer_context['nome']}! Bem-vindo(a) de volta."
                        else:
                            response_text = f"🤖 Não encontrei um cliente com o CNPJ {cnpj}."
                
                elif tool_name == 'handle_chitchat': response_text = parameters.get('response_text', 'Entendi!')
                
                elif not tool_name and "response_text" in intent: response_text = intent['response_text']
                
                else:
                    logging.warning(f"Fallback Final: Ferramenta desconhecida '{tool_name}'")
                    response_text = "🤖 Hum, não entendi muito bem. Que tal começarmos pelos produtos mais vendidos? Posso te mostrar?"
                    pending_action = "show_top_selling"
            
            if not response_text and not pending_action:
                response_text = "Operação concluída. O que mais posso fazer por você?"

            session.update({
                "customer_context": customer_context, "shopping_cart": shopping_cart,
                "last_search_type": last_search_type, "last_search_params": last_search_params,
                "current_offset": current_offset, "last_shown_products": last_shown_products,
                "last_bot_action": last_bot_action, "pending_action": pending_action,
                "last_kb_search_term": last_kb_search_term
            })
            save_session(session)
            
            if response_text:
                print(f">>> CONSOLE: Enviando resposta para o usuário: '{response_text[:80]}...'")
                twilio_client.send_whatsapp_message(to=sender_phone, body=response_text)
            
            logging.info(f"THREAD: Processamento finalizado para '{incoming_msg}'")
            print(f"--- FIM DO PROCESSAMENTO DA THREAD PARA: '{incoming_msg}' ---\n")
        except Exception as e:
            logging.error(f"ERRO CRÍTICO NA THREAD: {e}", exc_info=True)
            print(f"!!! ERRO CRÍTICO NA THREAD: {e}")

@app.route("/webhook", methods=['POST'])
def webhook():
    incoming_msg = request.values.get('Body', '').strip()
    sender_phone = request.values.get('From', '')
    thread = threading.Thread(target=process_message_async, args=(sender_phone, incoming_msg))
    thread.start()
    return "", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)
