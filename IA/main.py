# file: main.py
import database
import llm_interface
import logger_config
import logging
from typing import List, Dict, Union
import json
import os
import knowledge

# --- Funções de Gerenciamento de Sessão ---
SESSION_FILE = "session.json"

def save_session(session_data: Dict):
    """Salva os dados da sessão atual em um arquivo JSON."""
    logging.info(f"Salvando sessão: {session_data}")
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=4, ensure_ascii=False)

def load_session() -> Union[Dict, None]:
    """Carrega os dados da sessão de um arquivo JSON, se existir."""
    if os.path.exists(SESSION_FILE):
        logging.info("Arquivo de sessão encontrado. Carregando.")
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Erro ao decodificar o arquivo de sessão. Ignorando.")
                return None
    logging.info("Nenhum arquivo de sessão encontrado.")
    return None

def clear_session():
    """Remove o arquivo de sessão."""
    if os.path.exists(SESSION_FILE):
        logging.info("Limpando sessão (removendo arquivo).")
        os.remove(SESSION_FILE)

# --- Funções de Formatação de Texto ---
def format_product_list_for_display(products: List[Dict], title: str, has_more: bool, offset: int = 0) -> str:
    if not products:
        return f"🤖 {title}\nNenhum produto encontrado com esse critério."
    
    response = f"🤖 {title}\n"
    for i, p in enumerate(products, 1 + offset):
        price = p.get('pvenda') or 0.0
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        response += f"{i}. {p['descricao']} - {price_str}\n"
    
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
        response += f"- {item['descricao']} (Qtd: {qt}) - Unit: {price_str} - Subtotal: {subtotal_str}\n"
    
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"-----------------------------------\nTOTAL DO PEDIDO: {total_str}"
    return response

# --- Lógica Principal do Chat ---
def start_ai_chat():
    logger_config.setup_logger()
    logging.info("================ G.A.V. INICIADO ================")
    
    session = load_session() or {}
    customer_context = session.get("customer_context")
    shopping_cart = session.get("shopping_cart", [])
    last_search_type = session.get("last_search_type")
    last_search_params = session.get("last_search_params", {})
    current_offset = session.get("current_offset", 0)
    last_shown_products = session.get("last_shown_products", [])
    last_bot_action = None
    pending_action = None
    last_kb_search_term = session.get("last_kb_search_term")

    print("🤖 G.A.V. (Gentil Assistente de Vendas) | Converse comigo ou digite 'sair'.")
    if shopping_cart:
        print("💡 Olá! Vi que você tem um pedido em andamento. Deseja continuar?")
        print(format_cart_for_display(shopping_cart))

    while True:
        user_input = input("👤 > ").strip()
        logging.info(f"INPUT DO USUÁRIO: '{user_input}'")
        intent = None

        if user_input.lower() == 'sair':
            logging.info("================ G.A.V. FINALIZADO ================")
            print("👋 Até logo! Volte sempre!")
            break

        if pending_action:
            affirmative_responses = ["sim", "pode ser", "s", "claro", "quero", "ok", "beleza"]
            negative_responses = ["não", "n", "agora não", "deixa"]
            
            if user_input.lower() in affirmative_responses:
                if pending_action == "show_top_selling":
                    intent = {"tool_name": "get_top_selling_products", "parameters": {}}
                pending_action = None
            elif user_input.lower() in negative_responses:
                print("🤖 Tudo bem! O que você gostaria de fazer então?")
                pending_action = None
                continue
            else:
                pending_action = None
        
        if not intent:
            if not user_input:
                if last_bot_action == "AWAITING_PRODUCT_SELECTION":
                    print("🤖 Não entendi. Quer selecionar um dos produtos da lista? Se sim, me diga o número. Se quiser buscar outra coisa, é só digitar o nome do produto.")
                else:
                    print("🤖 Por favor, me diga o que você precisa.")
                continue
            
            if user_input.isdigit() and last_bot_action in ["AWAITING_PRODUCT_SELECTION", "AWAITING_CORRECTION_SELECTION"]:
                intent = {"tool_name": "add_item_to_cart", "parameters": {"index": int(user_input)}}
            elif user_input.lower() in ["mais", "proximo", "próximo", "mais produtos"]:
                intent = {"tool_name": "show_more_products", "parameters": {}}
            else:
                intent = llm_interface.get_intent(user_input, customer_context, len(shopping_cart))
        
        logging.info(f"INTENÇÃO PROCESSADA: {intent}")
        tool_name = intent.get("tool_name")
        parameters = intent.get("parameters", {})

        if tool_name in ["get_top_selling_products", "get_top_selling_products_by_name"]:
            last_kb_search_term = None
            last_shown_products = []
            if tool_name == "get_top_selling_products_by_name":
                product_name = parameters.get("product_name", "")
                logging.info(f"Buscando termo '{product_name}' na Base de Conhecimento.")
                kb_entry = knowledge.find_product_in_kb(product_name)
                
                if kb_entry and kb_entry.get("codprod"):
                    logging.info(f"Termo encontrado no KB! CODPROD: {kb_entry['codprod']}")
                    last_kb_search_term = product_name
                    product = database.get_product_by_codprod(kb_entry["codprod"])
                    products = [product] if product else []
                    title = f"Encontrei isto para '{product_name}' (busca rápida):"
                    last_shown_products = products
                    print(format_product_list_for_display(products, title, has_more=False, offset=0))
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                else:
                    logging.info("Termo não encontrado no KB. Usando busca por LIKE no banco.")
                    current_offset = 0
                    last_search_params = parameters
                    last_search_type = "by_name"
                    last_search_params['product_name'] = product_name
                    products = database.get_top_selling_products_by_name(product_name, offset=current_offset)
                    title = f"Encontrei estes produtos relacionados a '{product_name}':"
                    current_offset += 5
                    last_shown_products.extend(products)
                    print(format_product_list_for_display(products, title, has_more=len(products) == 5, offset=0))
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
            else: # get_top_selling_products
                current_offset, last_shown_products = 0, []
                last_search_params = parameters
                last_search_type = "top_selling"
                products = database.get_top_selling_products(offset=current_offset)
                title = "Estes são nossos produtos mais populares:"
                current_offset += 5
                last_shown_products.extend(products)
                print(format_product_list_for_display(products, title, has_more=len(products) == 5, offset=0))
                last_bot_action = "AWAITING_PRODUCT_SELECTION"

        elif tool_name == "show_more_products":
            if not last_search_type:
                print("🤖 Para eu mostrar mais, primeiro você precisa fazer uma busca.")
                continue
            logging.info(f"AÇÃO: Mostrar mais. Tipo: {last_search_type}, Offset: {current_offset}")
            offset_before_call = current_offset
            products = []
            if last_search_type == "top_selling":
                products = database.get_top_selling_products(offset=current_offset)
                title = "Mostrando mais produtos populares:"
            elif last_search_type == "by_name":
                product_name = last_search_params.get("product_name", "")
                products = database.get_top_selling_products_by_name(product_name, offset=current_offset)
                title = f"Mostrando mais produtos relacionados a '{product_name}':"
            if not products:
                print("🤖 Não encontrei mais produtos para essa busca.")
                last_bot_action = None
            else:
                current_offset += 5
                last_shown_products.extend(products)
                print(format_product_list_for_display(products, title, has_more=len(products) == 5, offset=offset_before_call))
                last_bot_action = "AWAITING_PRODUCT_SELECTION"
        
        elif tool_name == "report_incorrect_product":
            if last_kb_search_term:
                logging.warning(f"Feedback negativo para '{last_kb_search_term}'. Iniciando busca fallback.")
                print(f"🤖 Entendido! Desculpe pelo erro. Vou fazer uma busca mais ampla no banco de dados por '{last_kb_search_term}'...")
                current_offset, last_shown_products = 0, []
                products = database.get_top_selling_products_by_name(last_kb_search_term, offset=current_offset)
                last_search_type = "by_name"
                last_search_params = {"product_name": last_kb_search_term}
                current_offset += 5
                last_shown_products.extend(products)
                title = f"Resultados da busca ampla para '{last_kb_search_term}':"
                print(format_product_list_for_display(products, title, has_more=len(products) == 5, offset=0))
                last_bot_action = "AWAITING_CORRECTION_SELECTION"
            else:
                print("🤖 Entendido. Por favor, me diga o que você estava procurando para eu poder ajudar melhor.")

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
                is_correction = last_bot_action == "AWAITING_CORRECTION_SELECTION"
                is_new_learning = last_bot_action == "AWAITING_PRODUCT_SELECTION" and last_search_type == "by_name"
                term_to_learn = last_kb_search_term if is_correction else last_search_params.get("product_name")

                if (is_correction or is_new_learning) and term_to_learn:
                    existing_entry = knowledge.find_product_in_kb(term_to_learn)
                    if not existing_entry or existing_entry.get("codprod") != product_to_add["codprod"]:
                        print(f"🤖 Entendido! Aprendendo que '{term_to_learn}' se refere a '{product_to_add['descricao']}'.")
                        knowledge.update_kb(term_to_learn, product_to_add)
                    last_kb_search_term = None
                    last_search_type = None
                
                while True:
                    try:
                        qt_str = input(f"🤖 Qual a quantidade de '{product_to_add['descricao']}' você deseja? > ")
                        qt = int(qt_str)
                        if qt > 0:
                            shopping_cart.append({"codprod": product_to_add["codprod"], "descricao": product_to_add["descricao"], "pvenda": product_to_add.get("pvenda", 0.0), "qt": qt})
                            print(f"✅ Adicionado!")
                            print(format_cart_for_display(shopping_cart))
                            break
                        else: print("🤖 Por favor, insira uma quantidade positiva.")
                    except ValueError: print("🤖 Quantidade inválida.")
            else:
                print("🤖 Desculpe, não consegui identificar qual produto você quer adicionar.")
            last_bot_action = None

        elif tool_name == "view_cart":
            print(format_cart_for_display(shopping_cart))
            last_bot_action = None
        
        elif tool_name == "start_new_order":
            customer_context, shopping_cart, last_shown_products = None, [], []
            last_search_type, last_search_params, current_offset, last_kb_search_term = None, {}, 0, None
            clear_session()
            print("🧹 Certo! Carrinho e dados limpos. Vamos começar de novo! O que você procura?")
            last_bot_action = None

        elif tool_name == "checkout":
            if not shopping_cart: print("🤖 Seu carrinho está vazio!")
            elif not customer_context: print("⭐ Para finalizar a compra, preciso que você se identifique. Por favor, qual o seu CNPJ?")
            else:
                print(f"✅ Pedido para {customer_context['nome']} pronto para ser finalizado!")
                print(format_cart_for_display(shopping_cart))
                print("(Funcionalidade de inserção do pedido no sistema será implementada futuramente)")
            last_bot_action = None
        
        elif tool_name == "find_customer_by_cnpj":
            cnpj = parameters.get("cnpj")
            if cnpj:
                customer = database.find_customer_by_cnpj(cnpj)
                if customer:
                    customer_context = customer
                    print(f"🤖 Olá, {customer_context['nome']}! Bem-vindo(a) de volta.")
                else:
                    print(f"🤖 Não encontrei um cliente com o CNPJ {cnpj}.")
            last_bot_action = None

        elif tool_name == "handle_chitchat":
            print(f"🤖 {parameters.get('response_text', 'Entendi!')}")
            last_bot_action = None
        
        elif tool_name == "error":
             logging.error(f"Erro no LLM: {parameters.get('detail')}")
             print("🤖 Ocorreu um erro interno.")
             last_bot_action = None
        
        elif not tool_name and "response_text" in intent:
            logging.warning("Fallback Inteligente: LLM forneceu 'response_text' sem 'tool_name'.")
            print(f"🤖 {intent['response_text']}")
            last_bot_action = None
        
        else:
            logging.warning(f"Fallback Final: Ferramenta desconhecida '{tool_name}'")
            print("🤖 Hum, não entendi muito bem. Que tal começarmos pelos produtos mais vendidos? Posso te mostrar?")
            pending_action = "show_top_selling"

        save_session({
            "customer_context": customer_context, "shopping_cart": shopping_cart,
            "last_shown_products": last_shown_products, "last_search_type": last_search_type,
            "last_search_params": last_search_params, "current_offset": current_offset,
            "last_kb_search_term": last_kb_search_term
        })

if __name__ == "__main__":
    start_ai_chat()