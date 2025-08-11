# file: IA/app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
from typing import Dict
from db import database
from ai_llm import llm_interface
from knowledge import knowledge
from utils import logger_config
from core.session_manager import (
    load_session, save_session, clear_session,
    format_product_list_for_display, format_cart_for_display
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

def suggest_alternatives(failed_search_term: str) -> str:
    """Gera sugestões quando uma busca falha completamente."""
    
    # Importa aqui para evitar imports circulares
    from utils.fuzzy_search import fuzzy_engine
    
    suggestions = []
    
    # Aplica correções automáticas
    corrected = fuzzy_engine.apply_corrections(failed_search_term)
    if corrected != failed_search_term:
        suggestions.append(f"Tente: '{corrected}'")
    
    # Expande com sinônimos
    expansions = fuzzy_engine.expand_with_synonyms(failed_search_term)
    for expansion in expansions[:2]:
        if expansion != failed_search_term:
            suggestions.append(f"Ou tente: '{expansion}'")
    
    # Sugestões gerais baseadas na palavra
    words = failed_search_term.lower().split()
    general_suggestions = []
    
    for word in words:
        if any(x in word for x in ['coca', 'refri', 'soda']):
            general_suggestions.append("refrigerantes")
        elif any(x in word for x in ['sabao', 'deterg', 'limp']):
            general_suggestions.append("produtos de limpeza")
        elif any(x in word for x in ['cafe', 'acu', 'arroz', 'feij']):
            general_suggestions.append("alimentos básicos")
    
    if general_suggestions:
        suggestions.extend([f"Categoria: {s}" for s in general_suggestions[:2]])
    
    if not suggestions:
        suggestions = [
            "Tente termos mais simples",
            "Use nomes de categoria: 'refrigerante', 'sabão', 'arroz'"
        ]
    
    return " • ".join(suggestions[:3])
                
def process_message_async(sender_phone, incoming_msg):
    """
    Esta função faz todo o trabalho pesado em segundo plano (thread) para não causar timeout.
    """
    with app.app_context():
        try:
            print(f"\n--- INÍCIO DO PROCESSAMENTO DA THREAD PARA: '{incoming_msg}' ---")
            session = load_session(sender_phone)
            
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
                
                # 🆕 Extrai quantidade usando linguagem natural
                qt = extract_quantity(incoming_msg)
                
                if qt is not None and is_valid_quantity(qt):
                    product_to_add = session.get('pending_product_for_cart')
                    if product_to_add:
                        term_to_learn = session.get("term_to_learn_after_quantity")
                        if term_to_learn:
                            print(f">>> CONSOLE: Aprendendo que '{term_to_learn}' se refere a '{get_product_name(product_to_add)}'...")
                            knowledge.update_kb(term_to_learn, product_to_add)
                            session["term_to_learn_after_quantity"] = None
                        
                        # Converte para int se for número inteiro
                        if isinstance(qt, float) and qt.is_integer():
                            qt = int(qt)
                            
                        shopping_cart.append({**product_to_add, "qt": qt})
                        
                        # 🆕 Resposta mais natural baseada na entrada
                        if isinstance(qt, float):
                            qt_display = f"{qt:.1f}".rstrip('0').rstrip('.')
                        else:
                            qt_display = str(qt)
                            
                        product_name = get_product_name(product_to_add)
                        response_text = f"✅ Perfeito! Adicionei {qt_display} {product_name} ao seu carrinho.\n\n{format_cart_for_display(shopping_cart)}"
                    else:
                        response_text = "🤖 Ocorreu um erro. Não sei qual produto adicionar."
                else:
                    # 🆕 Mensagem de erro mais útil
                    if qt is None:
                        response_text = """🤖 Não consegui entender a quantidade. Você pode usar:
            • Números: 5, 10, 2.5
            • Por extenso: cinco, duas, dez
            • Expressões: meia duzia, uma duzia
            • Com unidade: 2 pacotes, 3 unidades

            Qual quantidade você quer?"""
                    else:
                        response_text = f"🤖 A quantidade {qt} parece muito alta. Por favor, digite uma quantidade entre 1 e 1000."
                
                pending_action = None
                session['pending_product_for_cart'] = None
                session['pending_action'] = pending_action
                session['shopping_cart'] = shopping_cart
                save_session(sender_phone, session)
            
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
                
                db_intensive_tools = ["get_top_selling_products", "get_top_selling_products_by_name", "show_more_products", "report_incorrect_product", "get_product_by_codprod"]
                if tool_name in db_intensive_tools:
                    print(f">>> CONSOLE: Acessando o Banco de Dados (ferramenta: {tool_name})...")

                if tool_name in ["get_top_selling_products", "get_top_selling_products_by_name"]:
                    last_kb_search_term, last_shown_products = None, []
                    
                    if tool_name == "get_top_selling_products_by_name":
                        product_name = parameters.get("product_name", "")
                        
                        # 🆕 BUSCA FUZZY INTELIGENTE
                        print(f">>> CONSOLE: Buscando '{product_name}' com sistema fuzzy...")
                        
                        # Etapa 1: Tenta Knowledge Base com análise
                        kb_products, kb_analysis = find_product_in_kb_with_analysis(product_name)
                        
                        if kb_products and kb_analysis.get("quality") in ["excellent", "good"]:
                            # Knowledge Base encontrou bons resultados
                            last_kb_search_term = product_name
                            last_shown_products = kb_products[:5]  # Limita a 5
                            
                            quality_emoji = "⚡" if kb_analysis["quality"] == "excellent" else "🎯"
                            title = f"{quality_emoji} Encontrei isto para '{product_name}' (busca rápida):"
                            
                            response_text = format_product_list_for_display(last_shown_products, title, False, 0)
                            last_bot_action = "AWAITING_PRODUCT_SELECTION"
                            
                            print(f">>> CONSOLE: KB encontrou {len(last_shown_products)} produtos (qualidade: {kb_analysis['quality']})")
                            
                        else:
                            # Knowledge Base não encontrou ou qualidade baixa - busca no banco com fuzzy
                            print(f">>> CONSOLE: KB qualidade baixa ({kb_analysis.get('quality', 'none')}), buscando no banco...")
                            
                            current_offset, last_shown_products = 0, []
                            last_search_type, last_search_params = "by_name", {'product_name': product_name}
                            
                            # 🆕 USA BUSCA FUZZY COM SUGESTÕES
                            search_result = search_products_with_suggestions(
                                product_name, 
                                limit=5, 
                                offset=current_offset
                            )
                            
                            products = search_result["products"]
                            suggestions = search_result["suggestions"]
                            
                            if products:
                                current_offset += 5
                                last_shown_products.extend(products)
                                
                                # Determina emoji baseado na qualidade
                                if len(products) >= 3:
                                    title_emoji = "🎯"
                                elif suggestions:
                                    title_emoji = "🔍"
                                else:
                                    title_emoji = "📦"
                                
                                title = f"{title_emoji} Encontrei estes produtos relacionados a '{product_name}':"
                                response_text = format_product_list_for_display(products, title, len(products) == 5, 0)
                                
                                # 🆕 ADICIONA SUGESTÕES SE HOUVER
                                if suggestions:
                                    response_text += f"\n💡 Dica: {suggestions[0]}"
                                
                                last_bot_action = "AWAITING_PRODUCT_SELECTION"
                                
                            else:
                                # Nenhum produto encontrado - resposta inteligente
                                print(f">>> CONSOLE: Nenhum produto encontrado para '{product_name}'")
                                
                                response_text = f"🤖 Não encontrei produtos para '{product_name}'."
                                
                                # Adiciona sugestões de correção
                                if suggestions:
                                    response_text += f"\n\n💡 {suggestions[0]}"
                                    response_text += "\n\nOu tente buscar por categoria: 'refrigerantes', 'detergentes', 'alimentos'."
                                else:
                                    response_text += "\n\nTente usar termos mais gerais como 'refrigerante', 'sabão' ou 'arroz'."
                                
                                last_bot_action = None
                            
                            print(f">>> CONSOLE: Banco encontrou {len(products)} produtos, {len(suggestions)} sugestões")
                    
                    else:  # get_top_selling_products
                        current_offset, last_shown_products = 0, []
                        last_search_type, last_search_params = "top_selling", parameters
                        products = database.get_top_selling_products(offset=current_offset)
                        title = "⭐ Estes são nossos produtos mais populares:"
                        current_offset += 5
                        last_shown_products.extend(products)
                        response_text = format_product_list_for_display(products, title, len(products) == 5, 0)
                        last_bot_action = "AWAITING_PRODUCT_SELECTION"
                
                elif tool_name == "add_item_to_cart":
                    product_to_add = None
                    
                    if "index" in parameters:
                        try:
                            idx = int(parameters["index"]) - 1
                            if 0 <= idx < len(last_shown_products): 
                                product_to_add = last_shown_products[idx]
                        except (ValueError, IndexError): 
                            pass
                    
                    if not product_to_add and "product_name" in parameters:
                        # 🆕 USA BUSCA FUZZY PARA NOME DO PRODUTO
                        product_name = parameters["product_name"]
                        print(f">>> CONSOLE: Buscando produto direto por nome: '{product_name}'")
                        
                        product_to_add = get_product_details_fuzzy(product_name)
                        
                        if not product_to_add:
                            # Tenta busca mais ampla
                            search_result = search_products_with_suggestions(product_name, limit=1)
                            if search_result["products"]:
                                product_to_add = search_result["products"][0]
                    
                    if product_to_add:
                        term_to_learn = None
                        is_correction = last_bot_action == "AWAITING_CORRECTION_SELECTION"
                        is_new_learning = last_bot_action == "AWAITING_PRODUCT_SELECTION" and last_search_type == "by_name"
                        
                        if is_correction: 
                            term_to_learn = last_kb_search_term
                        elif is_new_learning: 
                            term_to_learn = last_search_params.get("product_name")
                        
                        if term_to_learn:
                            session["term_to_learn_after_quantity"] = term_to_learn
                        
                        pending_action = 'AWAITING_QUANTITY'
                        session['pending_product_for_cart'] = product_to_add
                        
                        session['pending_action'] = pending_action
                        session['shopping_cart'] = shopping_cart
                        save_session(sender_phone, session)
                        
                        # 🆕 RESPOSTA MAIS NATURAL - Compatibilidade com produtos do banco e KB
                        product_name = get_product_name(product_to_add)
                        response_text = f"🛒 Qual a quantidade de '{product_name}' você deseja?\n\n💡 Você pode dizer: 'duas', 'meia duzia', '5 unidades', etc."
                    else:
                        response_text = "🤖 Desculpe, não consegui identificar o produto. Pode tentar novamente com um nome diferente?"


                elif tool_name == "report_incorrect_product":
                    if last_kb_search_term:
                        response_text = f"🤖 Entendido! Vou buscar melhor no banco de dados por '{last_kb_search_term}'...\n\n"
                        current_offset, last_shown_products = 0, []
                        
                        # 🆕 USA BUSCA FUZZY COM SUGESTÕES
                        search_result = search_products_with_suggestions(
                            last_kb_search_term, 
                            limit=5, 
                            offset=current_offset
                        )
                        
                        products = search_result["products"]
                        suggestions = search_result["suggestions"]
                        
                        last_search_type, last_search_params = "by_name", {"product_name": last_kb_search_term}
                        current_offset += 5
                        last_shown_products.extend(products)
                        
                        if products:
                            title = f"🔍 Resultados da busca ampla para '{last_kb_search_term}':"
                            response_text += format_product_list_for_display(products, title, len(products) == 5, 0)
                            
                            if suggestions:
                                response_text += f"\n💡 {suggestions[0]}"
                        else:
                            response_text += f"Infelizmente não encontrei produtos para '{last_kb_search_term}'."
                            if suggestions:
                                response_text += f"\n\n💡 {suggestions[0]}"
                        
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
                        
                        if not products:
                            response_text = "🤖 Não encontrei mais produtos para essa busca."
                        else:
                            current_offset += 5
                            last_shown_products.extend(products)
                            response_text = format_product_list_for_display(products, title, len(products) == 5, offset=offset_before_call)
                            last_bot_action = "AWAITING_PRODUCT_SELECTION"
                
                elif tool_name == 'view_cart': 
                    response_text = format_cart_for_display(shopping_cart)
                
                elif tool_name == 'start_new_order':
                    customer_context, shopping_cart, last_shown_products, last_search_type, last_search_params, current_offset, last_kb_search_term = None, [], [], None, {}, 0, None
                    pending_action = None
                    last_bot_action = None
                    clear_session(sender_phone)
                    session = {}
                    session['shopping_cart'] = shopping_cart
                    session['pending_action'] = pending_action
                    session['last_bot_action'] = last_bot_action
                    save_session(sender_phone, session)
                    response_text = "🧹 Certo! Carrinho e dados limpos. Vamos começar de novo!"

                elif tool_name == 'checkout':
                    if not shopping_cart: 
                        response_text = "🤖 Seu carrinho está vazio!"
                    elif not customer_context: 
                        response_text = "⭐ Para finalizar a compra, preciso do seu CNPJ."
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
                
                elif tool_name == 'handle_chitchat': 
                    response_text = parameters.get('response_text', 'Entendi!')
                
                elif not tool_name and "response_text" in intent: 
                    response_text = intent['response_text']
                
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
            save_session(sender_phone, session)
            
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