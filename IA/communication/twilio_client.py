# file: IA/app.py - CORREÇÕES APLICADAS
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
import re
from typing import Dict, List, Tuple, Union
from db import database
from ai_llm import llm_interface
from knowledge import knowledge
from utils import configuracao_logs
from core.gerenciador_sessao import (
    carregar_sessao,
    salvar_sessao,
    limpar_sessao,
    formatar_lista_produtos_para_exibicao,
    formatar_carrinho_para_exibicao,
    adicionar_mensagem_historico,
    obter_contexto_conversa,
    formatar_acoes_rapidas,
    atualizar_contexto_sessao,
    detectar_tipo_intencao_usuario,
)
from utils.extrator_quantidade import extrair_quantidade, e_quantidade_valida
from communication import twilio_client

from db.database import pesquisar_produtos_com_sugestoes, obter_detalhes_produto_fuzzy
from knowledge.knowledge import encontrar_produto_na_kb_com_analise

app = Flask(__name__)
configuracao_logs.configurar_logs()


def get_product_name(product: Dict) -> str:
    """Extrai o nome do produto, compatível com produtos do banco (descricao) e da KB (canonical_name)."""
    return product.get("descricao") or product.get("canonical_name", "Produto sem nome")


def find_products_in_cart_by_name(
    cart: List[Dict], product_name: str
) -> List[Tuple[int, Dict]]:
    """
    Encontra produtos no carrinho pelo nome (busca fuzzy).

    Returns:
        Lista de tuplas (índice, produto) que correspondem ao nome
    """
    if not cart or not product_name:
        return []

    # Importa aqui para evitar imports circulares
    from utils.fuzzy_search import fuzzy_engine

    matches = []
    search_term = product_name.lower().strip()

    for i, item in enumerate(cart):
        item_name = get_product_name(item).lower()

        # Busca exata
        if search_term in item_name or item_name in search_term:
            matches.append((i, item))
            continue

        # Busca fuzzy
        similarity = fuzzy_engine.calculate_similarity(search_term, item_name)
        if similarity >= 0.6:  # Threshold para considerar uma correspondência
            matches.append((i, item))

    return matches


def format_cart_with_indices(cart: List[Dict]) -> str:
    """Formata o carrinho com índices para facilitar seleção."""
    if not cart:
        return "🤖 Seu carrinho de compras está vazio."

    response = "🛒 Seu Carrinho de Compras:\n"
    total = 0.0

    for i, item in enumerate(cart, 1):
        # 🎯 PRIORIZA PREÇO PROMOCIONAL se disponível
        price = item.get("_preco_promo") or item.get("preco_promocional") or item.get("preco_atual") or item.get("pvenda") or item.get("preco_varejo", 0.0)
        qt = item.get("qt", 0)
        subtotal = price * qt
        total += subtotal

        price_str = (
            f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        subtotal_str = (
            f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        product_name = get_product_name(item)

        response += f"{i}. {product_name} (Qtd: {qt}) - Unit: {price_str} - Subtotal: {subtotal_str}\n"

    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"-----------------------------------\nTOTAL DO PEDIDO: {total_str}"
    return response


def remove_item_from_cart(cart: List[Dict], index: int) -> Tuple[bool, str, List[Dict]]:
    """
    Remove item do carrinho pelo índice.

    Returns:
        Tupla (sucesso, mensagem, novo_carrinho)
    """
    if not cart:
        return False, "🤖 Seu carrinho está vazio.", cart

    if not (1 <= index <= len(cart)):
        return False, f"🤖 Número inválido. Escolha entre 1 e {len(cart)}.", cart

    removed_item = cart.pop(index - 1)
    product_name = get_product_name(removed_item)

    if cart:
        cart_display = formatar_carrinho_para_exibicao(cart)
        message = f"🗑️ {product_name} removido do carrinho.\n\n{cart_display}"
    else:
        message = f"🗑️ {product_name} removido do carrinho.\n\n🤖 Seu carrinho de compras está vazio."

    quick_actions = formatar_acoes_rapidas(tem_carrinho=bool(cart))
    message = f"{message}\n\n{quick_actions}"

    return True, message, cart


def add_quantity_to_cart_item(
    cart: List[Dict], index: int, additional_qty: Union[int, float]
) -> Tuple[bool, str, List[Dict]]:
    """
    Adiciona quantidade a um item específico do carrinho.

    Returns:
        Tupla (sucesso, mensagem, novo_carrinho)
    """
    if not cart:
        return False, "🤖 Seu carrinho está vazio.", cart

    if not (1 <= index <= len(cart)):
        return False, f"🤖 Número inválido. Escolha entre 1 e {len(cart)}.", cart

    if not e_quantidade_valida(additional_qty):
        return False, f"🤖 Quantidade inválida: {additional_qty}", cart

    cart[index - 1]["qt"] += additional_qty
    product_name = get_product_name(cart[index - 1])
    new_total = cart[index - 1]["qt"]

    # Formata a quantidade para exibição
    if isinstance(additional_qty, float):
        qty_display = f"{additional_qty:.1f}".rstrip("0").rstrip(".")
    else:
        qty_display = str(additional_qty)

    if isinstance(new_total, float):
        total_display = f"{new_total:.1f}".rstrip("0").rstrip(".")
    else:
        total_display = str(new_total)

    cart_display = formatar_carrinho_para_exibicao(cart)
    message = f"✅ Adicionei +{qty_display} {product_name}. Total agora: {total_display}\n\n{cart_display}"

    quick_actions = formatar_acoes_rapidas(tem_carrinho=bool(cart))
    message = f"{message}\n\n{quick_actions}"

    return True, message, cart


def update_cart_item_quantity(
    cart: List[Dict], index: int, new_qty: Union[int, float]
) -> Tuple[bool, str, List[Dict]]:
    """
    Atualiza a quantidade de um item do carrinho.

    Returns:
        Tupla (sucesso, mensagem, novo_carrinho)
    """
    if not cart:
        return False, "🤖 Seu carrinho está vazio.", cart

    if not (1 <= index <= len(cart)):
        return False, f"🤖 Número inválido. Escolha entre 1 e {len(cart)}.", cart

    if not e_quantidade_valida(new_qty):
        return False, f"🤖 Quantidade inválida: {new_qty}", cart

    cart[index - 1]["qt"] = new_qty
    product_name = get_product_name(cart[index - 1])

    # Formata a quantidade para exibição
    if isinstance(new_qty, float):
        qty_display = f"{new_qty:.1f}".rstrip("0").rstrip(".")
    else:
        qty_display = str(new_qty)

    cart_display = formatar_carrinho_para_exibicao(cart)
    message = f"✅ Quantidade de {product_name} atualizada para {qty_display}\n\n{cart_display}"

    quick_actions = formatar_acoes_rapidas(tem_carrinho=bool(cart))
    message = f"{message}\n\n{quick_actions}"

    return True, message, cart


def clear_cart_completely(cart: List[Dict]) -> Tuple[str, List[Dict]]:
    """
    🆕 NOVA FUNÇÃO: Esvazia completamente o carrinho.
    
    Returns:
        Tupla (mensagem, carrinho_vazio)
    """
    if not cart:
        message = "🤖 Seu carrinho já está vazio."
    else:
        item_count = len(cart)
        cart.clear()  # Limpa completamente
        
        message = f"🗑️ Carrinho esvaziado! {item_count} {'item' if item_count == 1 else 'itens'} removido{'s' if item_count > 1 else ''}."
        message += f"\n\n{formatar_acoes_rapidas(tem_carrinho=False)}"
    
    return message, []


def generate_continue_or_checkout_message(cart: List[Dict]) -> str:
    """Gera uma mensagem amigável perguntando se o cliente deseja continuar ou finalizar."""
    quick_actions = formatar_acoes_rapidas(tem_carrinho=bool(cart))
    return "🛍️ Deseja continuar comprando ou finalizar o pedido?\n\n" f"{quick_actions}"


def generate_checkout_summary(cart: List[Dict], customer_context: Dict = None) -> str:
    """
    🆕 NOVA FUNÇÃO: Gera resumo completo para finalização do pedido.
    """
    if not cart:
        return "🤖 Não é possível finalizar: carrinho vazio."
    
    # Cabeçalho
    summary = "✅ *RESUMO DO PEDIDO*\n"
    summary += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Informações do cliente
    if customer_context:
        summary += f"👤 *Cliente:* {customer_context.get('nome', 'Não identificado')}\n"
        if customer_context.get('cnpj'):
            cnpj_formatted = customer_context['cnpj']
            # Formata CNPJ se tiver 14 dígitos
            if len(cnpj_formatted) == 14:
                cnpj_formatted = f"{cnpj_formatted[:2]}.{cnpj_formatted[2:5]}.{cnpj_formatted[5:8]}/{cnpj_formatted[8:12]}-{cnpj_formatted[12:14]}"
            summary += f"📄 *CNPJ:* {cnpj_formatted}\n\n"
    
    # Itens do pedido
    summary += "📦 *ITENS DO PEDIDO:*\n"
    total_geral = 0.0
    
    for i, item in enumerate(cart, 1):
        # 🎯 PRIORIZA PREÇO PROMOCIONAL se disponível
        price = item.get("_preco_promo") or item.get("preco_promocional") or item.get("preco_atual") or item.get("pvenda") or item.get("preco_varejo", 0.0)
        qt = item.get("qt", 0)
        subtotal = price * qt
        total_geral += subtotal
        
        # Formatação da quantidade
        if isinstance(qt, float):
            qty_display = f"{qt:.1f}".rstrip("0").rstrip(".")
        else:
            qty_display = str(qt)
        
        # Formatação dos valores
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        product_name = get_product_name(item)
        summary += f"*{i}.* {product_name}\n"
        summary += f"    {qty_display}× {price_str} = *{subtotal_str}*\n\n"
    
    # Total
    summary += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    total_str = f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    summary += f"💰 *TOTAL GERAL: {total_str}*\n\n"
    
    # Status
    summary += "✅ *Pedido registrado com sucesso!*\n"
    summary += "📞 Em breve entraremos em contato para confirmação.\n\n"
    
    # Opções finais
    summary += f"{formatar_acoes_rapidas(tem_carrinho=False)}"
    
    return summary


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
        if any(x in word for x in ["coca", "refri", "soda"]):
            general_suggestions.append("refrigerantes")
        elif any(x in word for x in ["sabao", "deterg", "limp"]):
            general_suggestions.append("produtos de limpeza")
        elif any(x in word for x in ["cafe", "acu", "arroz", "feij"]):
            general_suggestions.append("alimentos básicos")

    if general_suggestions:
        suggestions.extend([f"Categoria: {s}" for s in general_suggestions[:2]])

    if not suggestions:
        suggestions = [
            "Tente termos mais simples",
            "Use nomes de categoria: 'refrigerante', 'sabão', 'arroz'",
        ]

    return " • ".join(suggestions[:3])


def _extract_state(session: Dict) -> Dict:
    """Extrai os dados relevantes da sessão em um dicionário mutável."""
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


def _handle_pending_action(
    session: Dict, state: Dict, incoming_msg: str
) -> Tuple[Union[Dict, None], str]:
    """Processa ações pendentes existentes na sessão."""
    pending_action = state.get("pending_action")
    shopping_cart = state.get("shopping_cart", [])
    intent = None
    response_text = ""

    if pending_action == "AWAITING_QUANTITY":
        print(">>> CONSOLE: Tratando ação pendente AWAITING_QUANTITY")

        # 🆕 Extrai quantidade usando linguagem natural
        qt = extrair_quantidade(incoming_msg)

        if qt is not None and e_quantidade_valida(qt):
            product_to_add = session.get("pending_product_for_cart")
            if product_to_add:
                term_to_learn = session.get("term_to_learn_after_quantity")
                if term_to_learn:
                    print(
                        f">>> CONSOLE: Aprendendo que '{term_to_learn}' se refere a '{get_product_name(product_to_add)}'..."
                    )
                    knowledge.update_kb(term_to_learn, product_to_add)
                    atualizar_contexto_sessao(
                        session, {"term_to_learn_after_quantity": None}
                    )

                # Converte para int se for número inteiro
                if isinstance(qt, float) and qt.is_integer():
                    qt = int(qt)

                # Verifica se o item já existe no carrinho (por codprod ou nome)
                duplicate_index = None
                for i, item in enumerate(shopping_cart):
                    if (
                        product_to_add.get("codprod")
                        and item.get("codprod") == product_to_add.get("codprod")
                    ) or (
                        not product_to_add.get("codprod")
                        and get_product_name(item).lower()
                        == get_product_name(product_to_add).lower()
                    ):
                        duplicate_index = i
                        break

                if duplicate_index is not None:
                    existing_item = shopping_cart[duplicate_index]
                    existing_qty = existing_item.get("qt", 0)
                    if isinstance(existing_qty, float):
                        existing_qty_display = f"{existing_qty:.1f}".rstrip("0").rstrip(
                            "."
                        )
                    else:
                        existing_qty_display = str(existing_qty)
                    product_name = get_product_name(existing_item)

                    response_text = (
                        f"Você já possui **{product_name}** com **{existing_qty_display}** unidades. "
                        "Deseja *1* somar ou *2* substituir pela nova quantidade?"
                    )

                    atualizar_contexto_sessao(
                        session,
                        {
                            "pending_product_for_cart": None,
                            "duplicate_item_index": duplicate_index + 1,
                            "duplicate_item_qty": qt,
                            "pending_action": "AWAITING_DUPLICATE_DECISION",
                        },
                    )

                    adicionar_mensagem_historico(
                        session,
                        "assistant",
                        response_text,
                        "REQUEST_DUPLICATE_DECISION",
                    )

                    pending_action = "AWAITING_DUPLICATE_DECISION"
                else:
                    shopping_cart.append({**product_to_add, "qt": qt})

                    # 🆕 Resposta mais natural baseada na entrada
                    if isinstance(qt, float):
                        qt_display = f"{qt:.1f}".rstrip("0").rstrip(".")
                    else:
                        qt_display = str(qt)

                    product_name = get_product_name(product_to_add)
                    response_text = (
                        f"✅ Perfeito! Adicionei {qt_display} {product_name} ao seu carrinho.\n\n"
                        f"{formatar_carrinho_para_exibicao(shopping_cart)}\n\n"
                        f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                    )

                    # 📝 REGISTRA A RESPOSTA DO BOT
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "ADD_TO_CART"
                    )

                    atualizar_contexto_sessao(
                        session,
                        {
                            "pending_action": None,
                            "pending_product_for_cart": None,
                        },
                    )
                    pending_action = None

            else:
                response_text = "🤖 Ocorreu um erro. Não sei qual produto adicionar."
                adicionar_mensagem_historico(session, "assistant", response_text, "ERROR")
                atualizar_contexto_sessao(
                    session,
                    {
                        "pending_action": None,
                        "pending_product_for_cart": None,
                    },
                )
                pending_action = None

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

            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_QUANTITY"
            )
            pending_action = None

        state["pending_action"] = pending_action
        state["shopping_cart"] = shopping_cart

    elif pending_action == "AWAITING_CART_ITEM_SELECTION":
        # Usuário está selecionando item do carrinho após ambiguidade
        cart_action = session.get("pending_cart_action")
        cart_matches = session.get("pending_cart_matches", [])

        if incoming_msg.isdigit():
            selection = int(incoming_msg)

            # Verifica se a seleção é válida
            valid_indices = [
                match[0] + 1 for match in cart_matches
            ]  # +1 para índice baseado em 1

            if selection in valid_indices:
                if cart_action == "remove":
                    success, message, shopping_cart = remove_item_from_cart(
                        shopping_cart, selection
                    )
                    response_text = message
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "REMOVE_FROM_CART"
                    )
                elif cart_action == "add":
                    quantity = session.get("pending_cart_quantity", 1)
                    success, message, shopping_cart = add_quantity_to_cart_item(
                        shopping_cart, selection, quantity
                    )
                    response_text = message
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "ADD_QUANTITY_TO_CART"
                    )
                elif cart_action == "update":
                    quantity = session.get("pending_cart_quantity", 1)
                    success, message, shopping_cart = update_cart_item_quantity(
                        shopping_cart, selection, quantity
                    )
                    response_text = message
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "UPDATE_CART_ITEM"
                    )
                else:
                    response_text = "🤖 Ação inválida."
                    adicionar_mensagem_historico(session, "assistant", response_text, "ERROR")

                # Limpa estado pendente
                pending_action = None
                session.pop("pending_cart_action", None)
                session.pop("pending_cart_matches", None)
                session.pop("pending_cart_quantity", None)
            else:
                response_text = (
                    f"🤖 Número inválido. Escolha um dos números listados: {', '.join(map(str, valid_indices))}\n\n"
                    f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart), tem_produtos=True)}"
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REQUEST_CLARIFICATION"
                )
        else:
            response_text = (
                "🤖 Por favor, digite o número do item que você quer selecionar.\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart), tem_produtos=True)}"
            )
            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_CLARIFICATION"
            )

        state["pending_action"] = pending_action
        state["shopping_cart"] = shopping_cart

    elif pending_action == "AWAITING_DUPLICATE_DECISION":
        print(">>> CONSOLE: Tratando ação pendente AWAITING_DUPLICATE_DECISION")
        choice = incoming_msg.strip()
        index = session.get("duplicate_item_index")
        qty = session.get("duplicate_item_qty")

        if choice == "1":
            success, message, shopping_cart = add_quantity_to_cart_item(
                shopping_cart, index, qty
            )
            response_text = message
            adicionar_mensagem_historico(
                session, "assistant", response_text, "ADD_QUANTITY_TO_CART"
            )
            pending_action = None
            atualizar_contexto_sessao(
                session,
                {
                    "duplicate_item_index": None,
                    "duplicate_item_qty": None,
                    "pending_action": None,
                },
            )
        elif choice == "2":
            success, message, shopping_cart = update_cart_item_quantity(
                shopping_cart, index, qty
            )
            response_text = message
            adicionar_mensagem_historico(
                session, "assistant", response_text, "UPDATE_CART_ITEM_QUANTITY"
            )
            pending_action = None
            atualizar_contexto_sessao(
                session,
                {
                    "duplicate_item_index": None,
                    "duplicate_item_qty": None,
                    "pending_action": None,
                },
            )
        else:
            if index and 1 <= index <= len(shopping_cart):
                existing_item = shopping_cart[index - 1]
                existing_qty = existing_item.get("qt", 0)
                if isinstance(existing_qty, float):
                    existing_qty_display = f"{existing_qty:.1f}".rstrip("0").rstrip(".")
                else:
                    existing_qty_display = str(existing_qty)
                product_name = get_product_name(existing_item)
                response_text = (
                    f"Você já possui **{product_name}** com **{existing_qty_display}** unidades. "
                    "Deseja *1* somar ou *2* substituir pela nova quantidade?"
                )
            else:
                response_text = "Por favor, responda com *1* para somar ou *2* substituir pela nova quantidade."
            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_DUPLICATE_DECISION"
            )

        state["pending_action"] = pending_action
        state["shopping_cart"] = shopping_cart

    elif pending_action:
        print(f">>> CONSOLE: Tratando ação pendente {pending_action}")
        affirmative_responses = [
            "sim",
            "pode ser",
            "s",
            "claro",
            "quero",
            "ok",
            "beleza",
        ]
        negative_responses = ["não", "n", "agora não", "deixa"]
        if incoming_msg.lower() in affirmative_responses:
            if pending_action == "show_top_selling":
                intent = {"tool_name": "obter_produtos_mais_vendidos", "parameters": {}}
            pending_action = None
        elif incoming_msg.lower() in negative_responses:
            response_text = (
                "🤖 Tudo bem! O que você gostaria de fazer então?\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
            )
            adicionar_mensagem_historico(session, "assistant", response_text, "CHITCHAT")
            pending_action = None
            state["last_shown_products"] = []
            state["last_bot_action"] = "AWAITING_MENU_SELECTION"
        else:
            pending_action = None

        state["pending_action"] = pending_action

    return intent, response_text

def _process_user_message(
    session: Dict, state: Dict, incoming_msg: str
) -> Tuple[Union[Dict, None], str]:
    """
    🆕 VERSÃO CORRIGIDA: Processa a mensagem do usuário e determina a intenção.
    """
    intent = None
    response_text = ""
    last_bot_action = state.get("last_bot_action")
    shopping_cart = state.get("shopping_cart", [])

    if not incoming_msg:
        if last_bot_action == "AWAITING_PRODUCT_SELECTION":
            response_text = (
                "🤖 Não entendi. Quer selecionar um dos produtos da lista? Se sim, me diga o número.\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart), tem_produtos=True)}"
            )
            state["last_bot_action"] = "AWAITING_PRODUCT_SELECTION"
        else:
            response_text = (
                "🤖 Por favor, me diga o que você precisa.\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
            )
            state["last_shown_products"] = []
            state["last_bot_action"] = "AWAITING_MENU_SELECTION"
        adicionar_mensagem_historico(
            session, "assistant", response_text, "REQUEST_CLARIFICATION"
        )
        return intent, response_text

    # 🆕 DETECÇÃO DIRETA DE COMANDOS CRÍTICOS - PRIORIDADE MÁXIMA
    intent_type = detectar_tipo_intencao_usuario(incoming_msg, session)
    
    # 🆕 COMANDO DE LIMPEZA DE CARRINHO - PRIORIDADE ABSOLUTA
    if intent_type == "CLEAR_CART":
        print(f">>> CONSOLE: Comando de limpeza detectado diretamente: '{incoming_msg}'")
        intent = {"tool_name": "clear_cart", "parameters": {}}
        return intent, response_text

    # 🆕 DETECÇÃO DIRETA DE CNPJ (14 dígitos) EM CONTEXTO DE FINALIZAÇÃO
    if re.match(r'^\d{14}$', incoming_msg.strip()):
        # Verifica se o contexto indica que estamos esperando CNPJ
        history = session.get('conversation_history', [])
        recent_bot_messages = []
        for msg in reversed(history):
            if msg.get('role') == 'assistant':
                recent_bot_messages.append(msg.get('message', '').lower())
                if len(recent_bot_messages) >= 2:
                    break
        
        # Se a última mensagem do bot mencionou CNPJ, finalização ou checkout
        if recent_bot_messages:
            last_bot_msg = recent_bot_messages[0]
            if any(keyword in last_bot_msg for keyword in ['cnpj', 'finalizar', 'checkout', 'compra']):
                print(f">>> CONSOLE: CNPJ detectado em contexto de checkout: '{incoming_msg}'")
                intent = {"tool_name": "find_customer_by_cnpj", "parameters": {"cnpj": incoming_msg.strip()}}
                return intent, response_text

    # Continua com detecção normal
    if intent_type == "VIEW_CART":
        intent = {"tool_name": "view_cart", "parameters": {}}
    elif intent_type == "CHECKOUT":
        intent = {"tool_name": "checkout", "parameters": {}}
    elif intent_type == "NUMERIC_SELECTION" and last_bot_action in [
        "AWAITING_PRODUCT_SELECTION",
        "AWAITING_CORRECTION_SELECTION",
    ]:
        intent = {
            "tool_name": "add_item_to_cart",
            "parameters": {"index": int(incoming_msg)},
        }
    elif (
        intent_type == "NUMERIC_SELECTION"
        and last_bot_action == "AWAITING_MENU_SELECTION"
    ):
        if incoming_msg == "1":
            intent = {"tool_name": "obter_produtos_mais_vendidos", "parameters": {}}
        elif incoming_msg == "2":
            intent = {"tool_name": "view_cart", "parameters": {}}
        elif incoming_msg == "3":
            intent = {"tool_name": "checkout", "parameters": {}}
        else:
            response_text = (
                "🤖 Opção inválida. Escolha 1, 2 ou 3.\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
            )
            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_CLARIFICATION"
            )
            state["last_shown_products"] = []
            state["last_bot_action"] = "AWAITING_MENU_SELECTION"
            return intent, response_text

    elif intent_type == "REMOVE_CART_ITEM":
        params = {"action": "remove"}
        index_match = re.search(r"\b(\d+)\b", incoming_msg)
        if index_match:
            params["index"] = int(index_match.group(1))
        else:
            product_name = re.sub(r"\b(remover|tirar|excluir|deletar)\b", "", incoming_msg, flags=re.IGNORECASE).strip()
            if product_name:
                params["product_name"] = product_name
        intent = {"tool_name": "update_cart_item", "parameters": params}
    elif incoming_msg.lower() in ["mais", "proximo", "próximo", "mais produtos"]:
        intent = {"tool_name": "show_more_products", "parameters": {}}
    elif intent_type in ["GENERAL", "SEARCH_PRODUCT"]:
        print(">>> CONSOLE: Consultando a IA (Ollama) com memória conversacional...")
        intent = llm_interface.get_intent(
            user_message=incoming_msg,
            session_data=session,
            customer_context=state.get("customer_context"),
            cart_items_count=len(shopping_cart),
        )
        print(f">>> CONSOLE: IA retornou a intenção: {intent}")
        
        # 🆕 VALIDAÇÃO FINAL: Se a IA não detectou limpeza mas deveria ter detectado
        if intent.get("tool_name") != "clear_cart":
            message_lower = incoming_msg.lower().strip()
            clear_phrases = [
                'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
                'esvaziar tudo', 'limpar tudo', 'zerar tudo',
                'apagar carrinho', 'deletar carrinho'
            ]
            if any(phrase in message_lower for phrase in clear_phrases):
                print(f">>> CONSOLE: CORREÇÃO - IA não detectou comando de limpeza, forçando clear_cart")
                intent = {"tool_name": "clear_cart", "parameters": {}}

    elif intent_type == "GREETING":
        response_text = "🤖 Oi! Sou o G.A.V. e estou aqui pra te ajudar! Como posso te atender hoje?"
        adicionar_mensagem_historico(session, "assistant", response_text, "GREETING")
    else:
        response_text = "🤖 Desculpe, não entendi o que você quis dizer. Pode me explicar de outro jeito?"
        adicionar_mensagem_historico(
            session, "assistant", response_text, "REQUEST_CLARIFICATION"
        )

    return intent, response_text


def _route_tool(session: Dict, state: Dict, intent: Dict, sender_phone: str) -> str:
    """Executa a ferramenta baseada na intenção identificada."""
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
    tool_name = intent.get("tool_name")
    parameters = intent.get("parameters", {})

    db_intensive_tools = [
        "obter_produtos_mais_vendidos",
        "obter_produtos_mais_vendidos_por_nome",
        "show_more_products",
        "report_incorrect_product",
        "get_product_by_codprod",
    ]
    if tool_name in db_intensive_tools:
        print(f">>> CONSOLE: Acessando o Banco de Dados (ferramenta: {tool_name})...")

    # 🆕 NOVA FERRAMENTA: clear_cart
    if tool_name == "clear_cart":
        print(">>> CONSOLE: Executando limpeza completa do carrinho...")
        message, empty_cart = clear_cart_completely(shopping_cart)
        shopping_cart.clear()  # Garante que o carrinho está vazio
        
        response_text = message
        adicionar_mensagem_historico(session, "assistant", response_text, "CLEAR_CART")
        
        # Atualiza estado
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"
        pending_action = None
        
        print(f">>> CONSOLE: Carrinho limpo. Resposta: {response_text}")

    elif tool_name in ["obter_produtos_mais_vendidos", "obter_produtos_mais_vendidos_por_nome"]:
        last_kb_search_term, last_shown_products = None, []

        if tool_name == "obter_produtos_mais_vendidos_por_nome":
            product_name = parameters.get("product_name", "")

            # 🆕 BUSCA FUZZY INTELIGENTE
            print(f">>> CONSOLE: Buscando '{product_name}' com sistema fuzzy...")

            # Etapa 1: Tenta Knowledge Base com análise
            kb_products, kb_analysis = encontrar_produto_na_kb_com_analise(product_name)

            if kb_products and kb_analysis.get("quality") in ["excellent", "good"]:
                # Knowledge Base encontrou bons resultados
                last_kb_search_term = product_name
                last_shown_products = kb_products[:5]  # Limita a 5

                quality_emoji = "⚡" if kb_analysis["quality"] == "excellent" else "🎯"
                title = f"{quality_emoji} Encontrei isto para '{product_name}' (busca rápida):"

                response_text = formatar_lista_produtos_para_exibicao(
                    last_shown_products, title, False, 0
                )
                last_bot_action = "AWAITING_PRODUCT_SELECTION"
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "SHOW_PRODUCTS_FROM_KB"
                )

                print(
                    f">>> CONSOLE: KB encontrou {len(last_shown_products)} produtos (qualidade: {kb_analysis['quality']})"
                )

            else:
                # Knowledge Base não encontrou ou qualidade baixa - busca no banco com fuzzy
                print(
                    f">>> CONSOLE: KB qualidade baixa ({kb_analysis.get('quality', 'none')}), buscando no banco..."
                )

                current_offset, last_shown_products = 0, []
                last_search_type, last_search_params = "by_name", {
                    "product_name": product_name
                }

                # 🆕 USA BUSCA FUZZY COM SUGESTÕES
                search_result = pesquisar_produtos_com_sugestoes(
                    product_name, limit=5, offset=current_offset
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
                    response_text = formatar_lista_produtos_para_exibicao(
                        products, title, len(products) == 5, 0
                    )

                    # 🆕 ADICIONA SUGESTÕES SE HOUVER
                    if suggestions:
                        response_text += f"\n💡 Dica: {suggestions[0]}"

                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "SHOW_PRODUCTS_FROM_DB"
                    )

                else:
                    # Nenhum produto encontrado - resposta inteligente
                    print(
                        f">>> CONSOLE: Nenhum produto encontrado para '{product_name}'"
                    )

                    response_text = f"🤖 Não encontrei produtos para '{product_name}'."

                    # Adiciona sugestões de correção
                    if suggestions:
                        response_text += f"\n\n💡 {suggestions[0]}"
                        response_text += "\n\nOu tente buscar por categoria: 'refrigerantes', 'detergentes', 'alimentos'."
                    else:
                        response_text += "\n\nTente usar termos mais gerais como 'refrigerante', 'sabão' ou 'arroz'."

                    last_bot_action = None
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "NO_PRODUCTS_FOUND"
                    )

                print(
                    f">>> CONSOLE: Banco encontrou {len(products)} produtos, {len(suggestions)} sugestões"
                )

        else:  # obter_produtos_mais_vendidos
            current_offset, last_shown_products = 0, []
            last_search_type, last_search_params = "top_selling", parameters
            products = database.obter_produtos_mais_vendidos(offset=current_offset)
            title = "⭐ Estes são nossos produtos mais populares:"
            current_offset += 5
            last_shown_products.extend(products)
            response_text = formatar_lista_produtos_para_exibicao(
                products, title, len(products) == 5, 0
            )
            last_bot_action = "AWAITING_PRODUCT_SELECTION"
            adicionar_mensagem_historico(
                session, "assistant", response_text, "SHOW_TOP_PRODUCTS"
            )

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

            product_to_add = obter_detalhes_produto_fuzzy(product_name)

            if not product_to_add:
                # Tenta busca mais ampla
                search_result = pesquisar_produtos_com_sugestoes(product_name, limit=1)
                if search_result["products"]:
                    product_to_add = search_result["products"][0]

        if product_to_add:
            term_to_learn = None
            is_correction = last_bot_action == "AWAITING_CORRECTION_SELECTION"
            is_new_learning = (
                last_bot_action == "AWAITING_PRODUCT_SELECTION"
                and last_search_type == "by_name"
            )

            if is_correction:
                term_to_learn = last_kb_search_term
            elif is_new_learning:
                term_to_learn = last_search_params.get("product_name")

            atualizar_contexto_sessao(
                session,
                {
                    "pending_product_for_cart": product_to_add,
                    "term_to_learn_after_quantity": term_to_learn,
                    "pending_action": "AWAITING_QUANTITY",
                },
            )
            pending_action = "AWAITING_QUANTITY"

            response_text = f"Quantas unidades de {get_product_name(product_to_add)} você deseja adicionar?"
            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_QUANTITY"
            )

        else:
            response_text = (
                "🤖 Produto não encontrado. Você pode tentar buscar novamente?\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
            )
            adicionar_mensagem_historico(
                session, "assistant", response_text, "PRODUCT_NOT_FOUND"
            )

    elif tool_name == "update_cart_item":
        action = parameters.get("action")
        quantity = parameters.get("qt", 1)
        try:
            quantity = float(quantity)
        except (ValueError, TypeError):
            quantity = 1

        index = parameters.get("index")
        product_name = parameters.get("product_name")
        matched_index = None

        if action == "remove" and not index and not product_name:
            if shopping_cart:
                matches = list(enumerate(shopping_cart))
                pending_action = "AWAITING_CART_ITEM_SELECTION"
                atualizar_contexto_sessao(
                    session,
                    {
                        "pending_cart_matches": matches,
                        "pending_cart_action": "remove",
                        "pending_cart_quantity": quantity,
                        "pending_action": pending_action,
                    },
                )
                response_text = f"{format_cart_with_indices(shopping_cart)}\n\nDigite o número do item que deseja remover."
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REQUEST_CART_ITEM_SELECTION"
                )
            else:
                pending_action = None
                response_text = "🤖 Seu carrinho está vazio."
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "CART_EMPTY"
                )
                state.update(
                    {
                        "customer_context": customer_context,
                        "shopping_cart": shopping_cart,
                        "last_search_type": last_search_type,
                        "last_search_params": last_search_params,
                        "current_offset": current_offset,
                        "last_shown_products": last_shown_products,
                        "last_bot_action": "AWAITING_MENU_SELECTION",
                        "pending_action": pending_action,
                        "last_kb_search_term": last_kb_search_term,
                    }
                )
                return response_text

            last_bot_action = "AWAITING_MENU_SELECTION"

        if index:
            try:
                idx = int(index)
                if 1 <= idx <= len(shopping_cart):
                    matched_index = idx
            except (ValueError, TypeError):
                pass
        elif product_name:
            matches = find_products_in_cart_by_name(shopping_cart, product_name)
            if len(matches) == 1:
                matched_index = matches[0][0] + 1
            elif len(matches) > 1:
                pending_action = "AWAITING_CART_ITEM_SELECTION"
                pending_cart_action = (
                    "remove"
                    if action == "remove"
                    else ("add" if action == "add_quantity" else "update")
                )
                atualizar_contexto_sessao(
                    session,
                    {
                        "pending_cart_matches": matches,
                        "pending_cart_action": pending_cart_action,
                        "pending_cart_quantity": quantity,
                        "pending_action": pending_action,
                    },
                )
                options = "\n".join(
                    [
                        f"{idx+1}. {get_product_name(item)} (Qtd: {item.get('qt', 0)})"
                        for idx, item in matches
                    ]
                )
                response_text = f"🤖 Encontrei vários itens com esse nome no carrinho:\n{options}\nDigite o número do item desejado."
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REQUEST_CART_ITEM_SELECTION"
                )

        if matched_index is not None:
            if action == "remove":
                success, response_text, shopping_cart = remove_item_from_cart(
                    shopping_cart, matched_index
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REMOVE_FROM_CART"
                )
            elif action == "add_quantity":
                success, response_text, shopping_cart = add_quantity_to_cart_item(
                    shopping_cart, matched_index, quantity
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "ADD_QUANTITY_TO_CART"
                )
            elif action == "update_quantity":
                success, response_text, shopping_cart = update_cart_item_quantity(
                    shopping_cart, matched_index, quantity
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "UPDATE_CART_ITEM"
                )
            else:
                response_text = "🤖 Ação inválida."
                adicionar_mensagem_historico(session, "assistant", response_text, "ERROR")
            last_bot_action = "AWAITING_MENU_SELECTION"
            pending_action = None
        elif pending_action != "AWAITING_CART_ITEM_SELECTION":
            response_text = (
                f"🤖 Não encontrei esse item no carrinho.\n\n{formatar_carrinho_para_exibicao(shopping_cart)}\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
            )
            adicionar_mensagem_historico(
                session, "assistant", response_text, "CART_ITEM_NOT_FOUND"
            )
            last_bot_action = "AWAITING_MENU_SELECTION"
            pending_action = None

    elif tool_name == "show_more_products":
        if not last_search_type:
            response_text = (
                "🤖 Para eu mostrar mais, primeiro você precisa fazer uma busca."
            )
            adicionar_mensagem_historico(
                session, "assistant", response_text, "NO_PREVIOUS_SEARCH"
            )
        else:
            offset_before_call = current_offset
            products = []
            title = ""
            if last_search_type == "top_selling":
                products = database.obter_produtos_mais_vendidos(offset=current_offset)
                title = "Mostrando mais produtos populares:"
            elif last_search_type == "by_name":
                product_name = last_search_params.get("product_name", "")
                products = database.obter_produtos_mais_vendidos_by_name(
                    product_name, offset=current_offset
                )
                title = f"Mostrando mais produtos relacionados a '{product_name}':"

            if not products:
                response_text = (
                    "🤖 Não encontrei mais produtos para essa busca.\n\n"
                    f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "NO_MORE_PRODUCTS"
                )
            else:
                current_offset += 5
                last_shown_products.extend(products)
                response_text = formatar_lista_produtos_para_exibicao(
                    products, title, len(products) == 5, offset=offset_before_call
                )
                last_bot_action = "AWAITING_PRODUCT_SELECTION"
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "SHOW_MORE_PRODUCTS"
                )

    elif tool_name == "view_cart":
        response_text = (
            f"{formatar_carrinho_para_exibicao(shopping_cart)}\n\n"
            f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
        )
        adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_CART")
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"

    elif tool_name == "start_new_order":
        (
            customer_context,
            shopping_cart,
            last_shown_products,
            last_search_type,
            last_search_params,
            current_offset,
            last_kb_search_term,
        ) = (None, [], [], None, {}, 0, None)
        pending_action = None
        last_bot_action = None
        limpar_sessao(sender_phone)
        session.clear()

        atualizar_contexto_sessao(
            session,
            {
                "shopping_cart": shopping_cart,
                "pending_action": pending_action,
                "last_bot_action": last_bot_action,
            },
        )
        response_text = (
            "🧹 Certo! Carrinho e dados limpos. Vamos começar de novo!\n\n"
            f"{formatar_acoes_rapidas(tem_carrinho=False)}"
        )

        adicionar_mensagem_historico(session, "assistant", response_text, "NEW_ORDER")

    elif tool_name == "checkout":
        if not shopping_cart:
            response_text = (
                "🤖 Seu carrinho está vazio!\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=False)}"
            )
            adicionar_mensagem_historico(session, "assistant", response_text, "EMPTY_CART")
            last_shown_products = []
            last_bot_action = "AWAITING_MENU_SELECTION"
        elif not customer_context:
            response_text = "⭐ Para finalizar a compra, preciso do seu CNPJ."
            adicionar_mensagem_historico(session, "assistant", response_text, "REQUEST_CNPJ")
            last_shown_products = []
            last_bot_action = None
        else:
            # 🆕 GERA RESUMO COMPLETO DO PEDIDO
            response_text = generate_checkout_summary(shopping_cart, customer_context)
            adicionar_mensagem_historico(
                session, "assistant", response_text, "CHECKOUT_COMPLETE"
            )
            
            # 🆕 LIMPA CARRINHO APÓS FINALIZAÇÃO
            shopping_cart.clear()
            last_shown_products = []
            last_bot_action = "AWAITING_MENU_SELECTION"

    elif tool_name == "find_customer_by_cnpj":
        cnpj = parameters.get("cnpj")
        if cnpj:
            print(f">>> CONSOLE: Buscando cliente por CNPJ: {cnpj}")
            customer = database.encontrar_cliente_por_cnpj(cnpj)
            if customer:
                customer_context = customer
                
                # 🆕 FINALIZA AUTOMATICAMENTE SE TEMOS CARRINHO E CLIENTE
                if shopping_cart:
                    response_text = generate_checkout_summary(shopping_cart, customer_context)
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "CHECKOUT_COMPLETE"
                    )
                    
                    # Limpa carrinho após finalização
                    shopping_cart.clear()
                    last_shown_products = []
                    last_bot_action = "AWAITING_MENU_SELECTION"
                else:
                    response_text = (
                        f"🤖 Olá, {customer_context['nome']}! Bem-vindo(a) de volta.\n\n"
                        f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                    )
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "CUSTOMER_IDENTIFIED"
                    )
                    last_shown_products = []
                    last_bot_action = "AWAITING_MENU_SELECTION"
            else:
                response_text = f"🤖 Não encontrei um cliente com o CNPJ {cnpj}. Mas posso registrar seu pedido mesmo assim!"
                
                # 🆕 PERMITE FINALIZAR MESMO SEM CADASTRO
                if shopping_cart:
                    response_text += f"\n\n{generate_checkout_summary(shopping_cart)}"
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "CHECKOUT_COMPLETE"
                    )
                    
                    # Limpa carrinho após finalização
                    shopping_cart.clear()
                    last_shown_products = []
                    last_bot_action = "AWAITING_MENU_SELECTION"
                else:
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "CUSTOMER_NOT_FOUND"
                    )
        else:
            response_text = "🤖 Por favor, informe seu CNPJ."
            adicionar_mensagem_historico(session, "assistant", response_text, "REQUEST_CNPJ")

    elif tool_name == "ask_continue_or_checkout":
        if shopping_cart:
            response_text = generate_continue_or_checkout_message(shopping_cart)
            adicionar_mensagem_historico(
                session, "assistant", response_text, "ASK_CONTINUE_OR_CHECKOUT"
            )
        else:
            response_text = (
                "🤖 Seu carrinho está vazio. Que tal começar adicionando um produto?\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=False)}"
            )
            adicionar_mensagem_historico(session, "assistant", response_text, "EMPTY_CART")
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"

    elif tool_name == "handle_chitchat":
        response_text = (
            f"{parameters.get('response_text', 'Entendi!')}\n\n"
            f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
        )
        adicionar_mensagem_historico(session, "assistant", response_text, "CHITCHAT")
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"

    elif not tool_name and "response_text" in intent:
        response_text = (
            f"{intent['response_text']}\n\n"
            f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
        )
        adicionar_mensagem_historico(session, "assistant", response_text, "GENERIC_RESPONSE")
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"

    else:
        logging.warning(f"Fallback Final: Ferramenta desconhecida '{tool_name}'")
        response_text = "🤖 Hum, não entendi muito bem. Que tal começarmos pelos produtos mais vendidos? Posso te mostrar?"
        pending_action = "show_top_selling"
        adicionar_mensagem_historico(session, "assistant", response_text, "FALLBACK")

    state.update(
        {
            "customer_context": customer_context,
            "shopping_cart": shopping_cart,
            "last_search_type": last_search_type,
            "last_search_params": last_search_params,
            "current_offset": current_offset,
            "last_shown_products": last_shown_products,
            "last_bot_action": last_bot_action,
            "pending_action": pending_action,
            "last_kb_search_term": last_kb_search_term,
        }
    )

    return response_text


def _finalize_session(
    sender_phone: str, session: Dict, state: Dict, response_text: str
) -> None:
    """Atualiza e persiste a sessão, além de enviar a resposta ao usuário."""
    atualizar_contexto_sessao(
        session,
        {
            "customer_context": state.get("customer_context"),
            "shopping_cart": state.get("shopping_cart", []),
            "last_search_type": state.get("last_search_type"),
            "last_search_params": state.get("last_search_params", {}),
            "current_offset": state.get("current_offset", 0),
            "last_shown_products": state.get("last_shown_products", []),
            "last_bot_action": state.get("last_bot_action"),
            "pending_action": state.get("pending_action"),
            "last_kb_search_term": state.get("last_kb_search_term"),
        },
    )
    salvar_sessao(sender_phone, session)

    if response_text:
        print(
            f">>> CONSOLE: Enviando resposta para o usuário: '{response_text[:100]}...'"
        )
        twilio_client.send_whatsapp_message(to=sender_phone, body=response_text)


def process_message_async(sender_phone: str, incoming_msg: str):
    """
    Esta função faz todo o trabalho pesado em segundo plano (thread) para não causar timeout.
    ATUALIZADA COM MEMÓRIA CONVERSACIONAL COMPLETA
    """
    with app.app_context():
        try:
            print(f"\n--- INÍCIO DO PROCESSAMENTO DA THREAD PARA: '{incoming_msg}' ---")
            session = carregar_sessao(sender_phone)

            # 📝 REGISTRA A MENSAGEM DO USUÁRIO NO HISTÓRICO
            adicionar_mensagem_historico(session, "user", incoming_msg)

            # Carrega estado atual da sessão
            state = _extract_state(session)

            # 1. Trata ações pendentes
            intent, response_text = _handle_pending_action(session, state, incoming_msg)

            # 2. Se não houve resposta ou intenção, determina a intenção
            if not intent and not response_text:
                intent, response_text = _process_user_message(
                    session, state, incoming_msg
                )

            # 3. Executa a intenção identificada
            if intent and not response_text:
                response_text = _route_tool(session, state, intent, sender_phone)

            # 4. Mensagem padrão caso nenhuma resposta seja definida
            if not response_text and not state.get("pending_action"):
                response_text = (
                    "Operação concluída. O que mais posso fazer por você?\n\n"
                    f"{formatar_acoes_rapidas(tem_carrinho=bool(state.get('shopping_cart', [])))}"
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "OPERATION_COMPLETE"
                )

            # 5. Atualiza e persiste a sessão, enviando a resposta
            _finalize_session(sender_phone, session, state, response_text)

            logging.info(f"THREAD: Processamento finalizado para '{incoming_msg}'")
            print(f"--- FIM DO PROCESSAMENTO DA THREAD PARA: '{incoming_msg}' ---\n")
        except Exception as e:
            logging.error(f"ERRO CRÍTICO NA THREAD: {e}", exc_info=True)
            print(f"!!! ERRO CRÍTICO NA THREAD: {e}")

            error_response = "🤖 Desculpe, ocorreu um erro interno. Tente novamente!"
            twilio_client.send_whatsapp_message(to=sender_phone, body=error_response)

            # Registra o erro no histórico também
            try:
                session = carregar_sessao(sender_phone)
                adicionar_mensagem_historico(session, "assistant", error_response, "ERROR")
                salvar_sessao(sender_phone, session)
            except:
                pass  # Se falhar aqui, apenas ignora para não causar loop de erro


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    sender_phone = request.values.get("From", "")
    thread = threading.Thread(
        target=process_message_async, args=(sender_phone, incoming_msg)
    )
    thread.start()
    return "", 200

# Usado pela vonage
from fastapi import Request
@app.route("/webhooks/inbound-message", methods=["POST"])
async def inbound_message(request: Request):
    data = await request.json()
    print(data)

    # incoming_msg = request.values.get("Body", "").strip()
    # sender_phone = request.values.get("From", "")
    # thread = threading.Thread(
    #     target=process_message_async, args=(sender_phone, incoming_msg)
    # )
    # thread.start()
    return "", 200

@app.route("/clear_cart", methods=["POST"])
def clear_cart_endpoint():
    """🆕 ENDPOINT PARA LIMPEZA DE CARRINHO VIA API."""
    data = request.get_json() or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id é obrigatório"}), 400
    
    session = carregar_sessao(user_id)
    shopping_cart = session.get("shopping_cart", [])
    
    message, empty_cart = clear_cart_completely(shopping_cart)
    session["shopping_cart"] = empty_cart
    
    # Atualiza estado da sessão
    session["last_bot_action"] = "AWAITING_MENU_SELECTION"
    session["pending_action"] = None
    session["last_shown_products"] = []
    
    adicionar_mensagem_historico(session, "assistant", message, "CLEAR_CART_API")
    salvar_sessao(user_id, session)
    
    return jsonify({
        "success": True,
        "response_text": message,
        "session_data": session
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)