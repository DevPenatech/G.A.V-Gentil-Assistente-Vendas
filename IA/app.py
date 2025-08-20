# file: IA/app.py - CORREÇÕES APLICADAS
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import logging
import threading
import re
from datetime import datetime
from typing import Dict, List, Tuple, Union
from db import database
from ai_llm import llm_interface
from ai_llm.llm_interface import generate_personalized_response
from knowledge import knowledge
from utils.gav_logger import (
    obter_logger, log_com_contexto, log_performance, log_audit,
    log_info, log_error, log_warning, log_debug, log_critical,
    log_whatsapp_error, ContextoLog
)
from core.gerenciador_sessao import (
    carregar_sessao,
    salvar_sessao,
    formatar_lista_produtos_para_exibicao,
    formatar_lista_produtos_inteligente, # ETAPA 5
    formatar_carrinho_para_exibicao,
    adicionar_mensagem_historico,
    obter_contexto_conversa,
    atualizar_contexto_sessao,
    formatar_acoes_rapidas,
)
from utils.extrator_quantidade import (
    extrair_quantidade, 
    e_quantidade_valida,
    extrair_quantidade_com_ia,
    processar_pedido_complexo_ia
)
from utils.classificador_categoria import (
    classificar_categoria_produto,
    classificar_categoria_com_contexto_ia
)
from utils.detector_intencao_avancado import (
    detectar_intencao_carrinho_ia,
    analisar_contexto_emocional_ia,
    extrair_especificacoes_produto_ia,
    corrigir_e_sugerir_ia
)
from utils.detector_marca_produto import (
    detectar_marca_e_produto_ia,
    filtrar_produtos_por_marca,
    gerar_busca_otimizada
)
from communication import twilio_client, vonage_client


from db.database import pesquisar_produtos_com_sugestoes, obter_detalhes_produto_fuzzy
from knowledge.knowledge import encontrar_produto_na_kb_com_analise

# =============================================================
# AÇÃO: A INICIALIZAÇÃO DO APP FOI MOVIDA PARA CÁ (O LUGAR CERTO)
# =============================================================
aplicativo = Flask(__name__)
app_logger = obter_logger("app")
log_info("Sistema G.A.V. iniciando...")
# ============================================================="



def obter_nome_produto(produto: Dict) -> str:
    """Extrai o nome do produto de um dicionário.

    Args:
        produto: Um dicionário representando o produto.

    Returns:
        O nome do produto.
    """
    return produto.get("descricao") or produto.get("canonical_name", "Produto sem nome")


def encontrar_produtos_carrinho_por_nome(
    carrinho: List[Dict], nome_produto: str
) -> List[Tuple[int, Dict]]:
    """Encontra produtos no carrinho por nome usando busca aproximada.

    Args:
        carrinho: A lista de itens no carrinho.
        nome_produto: O nome do produto a ser buscado.

    Returns:
        Uma lista de tuplas contendo o índice e o dicionário do produto.
    """
    if not carrinho or not nome_produto:
        return []

    # Importa aqui para evitar imports circulares
    from utils.busca_aproximada import MotorBuscaAproximada
    motor_busca = MotorBuscaAproximada()

    correspondencias = []
    termo_busca = nome_produto.lower().strip()

    for i, item in enumerate(carrinho):
        nome_item = obter_nome_produto(item).lower()

        # Busca exata
        if termo_busca in nome_item or nome_item in termo_busca:
            correspondencias.append((i, item))
            continue

        # Busca fuzzy
        similaridade = motor_busca.calcular_similaridade(termo_busca, nome_item)
        if similaridade >= 0.6:  # Threshold para considerar uma correspondência
            correspondencias.append((i, item))

    return correspondencias


def formatar_carrinho_com_indices(carrinho: List[Dict]) -> str:
    """Formata o carrinho com índices para facilitar a seleção.

    Args:
        carrinho: A lista de itens no carrinho.

    Returns:
        Uma string formatada com os itens do carrinho.
    """
    if not carrinho:
        return "Seu carrinho tá vazio ainda! Que tal começarmos escolhendo alguns produtos?"

    resposta = "🛒 Seu Carrinho de Compras:\n"
    total = 0.0

    for i, item in enumerate(carrinho, 1):
        # 🎯 PRIORIZA PREÇO PROMOCIONAL se disponível
        preco = item.get("_preco_promo") or item.get("preco_promocional") or item.get("preco_atual") or item.get("pvenda") or item.get("preco_varejo", 0.0)
        qt = item.get("qt", 0)
        subtotal = preco * qt
        total += subtotal

        preco_str = (
            f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        subtotal_str = (
            f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        nome_produto = obter_nome_produto(item)

        resposta += f"{i}. {nome_produto} (Qtd: {qt}) - Unit: {preco_str} - Subtotal: {subtotal_str}\n"

    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    resposta += f"-----------------------------------\nTOTAL DO PEDIDO: {total_str}"
    return resposta


def remover_item_do_carrinho(carrinho: List[Dict], indice: int) -> Tuple[bool, str, List[Dict]]:
    """Remove um item do carrinho pelo seu índice.

    Args:
        carrinho: A lista de itens no carrinho.
        indice: O índice do item a ser removido.

    Returns:
        Uma tupla contendo um booleano de sucesso, uma mensagem e a lista do carrinho atualizada.
    """
    if not carrinho:
        return False, "Opa, seu carrinho tá vazio!", carrinho

    if not (1 <= indice <= len(carrinho)):
        return False, f"Hmm, esse número não tá na lista. Escolha entre 1 e {len(carrinho)}, por favor!", carrinho

    item_removido = carrinho.pop(indice - 1)
    nome_produto = obter_nome_produto(item_removido)

    if carrinho:
        display_carrinho = formatar_carrinho_para_exibicao(carrinho)
        mensagem = f"🗑️ {nome_produto} removido do carrinho.\n\n{display_carrinho}"
    else:
        mensagem = f"🗑️ {nome_produto} removido do carrinho.\n\n🤖 Seu carrinho de compras está vazio."

    acoes_rapidas = formatar_acoes_rapidas(tem_carrinho=bool(carrinho))
    mensagem = f"{mensagem}\n\n{acoes_rapidas}"

    return True, mensagem, carrinho

def adicionar_quantidade_item_carrinho(
    carrinho: List[Dict], indice: int, qt_adicional: Union[int, float]
) -> Tuple[bool, str, List[Dict]]:
    """Adiciona uma quantidade a um item específico do carrinho.

    Args:
        carrinho: A lista de itens no carrinho.
        indice: O índice do item a ser atualizado.
        qt_adicional: A quantidade a ser adicionada.

    Returns:
        Uma tupla contendo um booleano de sucesso, uma mensagem e a lista do carrinho atualizada.
    """
    if not carrinho:
        return False, "Opa, seu carrinho tá vazio!", carrinho

    if not (1 <= indice <= len(carrinho)):
        return False, f"Hmm, esse número não tá na lista. Escolha entre 1 e {len(carrinho)}, por favor!", carrinho

    if not e_quantidade_valida(qt_adicional):
        return False, f"Essa quantidade ({qt_adicional}) não tá valendo! Tenta outra.", carrinho

    carrinho[indice - 1]["qt"] += qt_adicional
    nome_produto = obter_nome_produto(carrinho[indice - 1])
    novo_total = carrinho[indice - 1]["qt"]

    # Formata a quantidade para exibição
    if isinstance(qt_adicional, float):
        display_qt = f"{qt_adicional:.1f}".rstrip("0").rstrip(".")
    else:
        display_qt = str(qt_adicional)

    if isinstance(novo_total, float):
        display_total = f"{novo_total:.1f}".rstrip("0").rstrip(".")
    else:
        display_total = str(novo_total)

    display_carrinho = formatar_carrinho_para_exibicao(carrinho)
    mensagem = f"✅ Adicionei +{display_qt} {nome_produto}. Total agora: {display_total}\n\n{display_carrinho}"

    return True, mensagem, carrinho

def atualizar_quantidade_item_carrinho(
    carrinho: List[Dict], indice: int, nova_qt: Union[int, float]
) -> Tuple[bool, str, List[Dict]]:
    """Atualiza a quantidade de um item do carrinho.

    Args:
        carrinho: A lista de itens no carrinho.
        indice: O índice do item a ser atualizado.
        nova_qt: A nova quantidade do item.

    Returns:
        Uma tupla contendo um booleano de sucesso, uma mensagem e a lista do carrinho atualizada.
    """
    if not carrinho:
        return False, "Opa, seu carrinho tá vazio!", carrinho

    if not (1 <= indice <= len(carrinho)):
        return False, f"Hmm, esse número não tá na lista. Escolha entre 1 e {len(carrinho)}, por favor!", carrinho

    if not e_quantidade_valida(nova_qt):
        return False, f"Opa, quantidade ({nova_qt}) não tá certa! Pode tentar outra?", carrinho

    carrinho[indice - 1]["qt"] = nova_qt
    nome_produto = obter_nome_produto(carrinho[indice - 1])

    # Formata a quantidade para exibição
    if isinstance(nova_qt, float):
        display_qt = f"{nova_qt:.1f}".rstrip("0").rstrip(".")
    else:
        display_qt = str(nova_qt)

    display_carrinho = formatar_carrinho_para_exibicao(carrinho)
    mensagem = f"✅ Quantidade de {nome_produto} atualizada para {display_qt}\n\n{display_carrinho}"

    return True, mensagem, carrinho

def limpar_carrinho_completamente(carrinho: List[Dict]) -> Tuple[str, List[Dict]]:
    """Esvazia completamente o carrinho.

    Args:
        carrinho: A lista de itens no carrinho.

    Returns:
        Uma tupla contendo uma mensagem e uma lista de carrinho vazia.
    """
    if not carrinho:
        mensagem = "Seu carrinho já tá vazio mesmo! Mas posso te ajudar a escolher uns produtos legais."
    else:
        contagem_itens = len(carrinho)
        carrinho.clear()  # Limpa completamente
        
        mensagem = f"🗑️ Carrinho esvaziado! {contagem_itens} {'item' if contagem_itens == 1 else 'itens'} removido{'s' if contagem_itens > 1 else ''}."
        mensagem += f"\n\n{formatar_acoes_rapidas(tem_carrinho=False)}"
    
    return mensagem, []


def gerar_mensagem_continuar_ou_finalizar(carrinho: List[Dict]) -> str:
    """Gera uma mensagem para o usuário continuar comprando ou finalizar o pedido.

    Args:
        carrinho: A lista de itens no carrinho.

    Returns:
        Uma string com a mensagem.
    """
    acoes_rapidas = formatar_acoes_rapidas(tem_carrinho=bool(carrinho))
    return "🛍️ Deseja continuar comprando ou finalizar o pedido?\n\n" f"{acoes_rapidas}"


def gerar_resumo_finalizacao(carrinho: List[Dict], contexto_cliente: Dict = None) -> str:
    """Gera um resumo completo do pedido para finalização.

    Args:
        carrinho: A lista de itens no carrinho.
        contexto_cliente: O dicionário de contexto do cliente.

    Returns:
        Uma string com o resumo do pedido.
    """
    if not carrinho:
        return "Não dá pra finalizar com o carrinho vazio! Que tal escolher alguns produtos primeiro?"
    
    # Cabeçalho
    resumo = "✅ *RESUMO DO PEDIDO*\n"
    resumo += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Informações do cliente
    if contexto_cliente:
        resumo += f"👤 *Cliente:* {contexto_cliente.get('nome', 'Não identificado')}\n"
        if contexto_cliente.get('cnpj'):
            cnpj_formatado = contexto_cliente['cnpj']
            # Formata CNPJ se tiver 14 dígitos
            if len(cnpj_formatado) == 14:
                cnpj_formatado = f"{cnpj_formatado[:2]}.{cnpj_formatado[2:5]}.{cnpj_formatado[5:8]}/{cnpj_formatado[8:12]}-{cnpj_formatado[12:14]}"
            resumo += f"📄 *CNPJ:* {cnpj_formatado}\n\n"
    
    # Itens do pedido
    resumo += "📦 *ITENS DO PEDIDO:*\n"
    total_geral = 0.0
    
    for i, item in enumerate(carrinho, 1):
        # 🎯 PRIORIZA PREÇO PROMOCIONAL se disponível
        preco = item.get("_preco_promo") or item.get("preco_promocional") or item.get("preco_atual") or item.get("pvenda") or item.get("preco_varejo", 0.0)
        qt = item.get("qt", 0)
        subtotal = preco * qt
        total_geral += subtotal
        
        # Formatação da quantidade
        if isinstance(qt, float):
            display_qt = f"{qt:.1f}".rstrip("0").rstrip(".")
        else:
            display_qt = str(qt)
        
        # Formatação dos valores
        preco_str = f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        nome_produto = obter_nome_produto(item)
        resumo += f"*{i}.* {nome_produto}\n"
        resumo += f"    {display_qt}× {preco_str} = *{subtotal_str}*\n\n"
    
    # Total
    resumo += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    total_str = f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    resumo += f"💰 *TOTAL GERAL: {total_str}*\n\n"
    
    # Status
    resumo += "✅ *Pedido registrado com sucesso!*\n"
    resumo += "📞 Em breve entraremos em contato para confirmação.\n\n"
    
    # Opções finais
    resumo += f"{formatar_acoes_rapidas(tem_carrinho=False)}"
    
    return resumo


def sugerir_alternativas(termo_busca_falho: str) -> str:
    """Gera sugestões de busca quando a busca original falha.

    Args:
        termo_busca_falho: O termo de busca que falhou.

    Returns:
        Uma string com as sugestões.
    """

    # Importa aqui para evitar imports circulares
    from utils.busca_aproximada import MotorBuscaAproximada
    motor_busca = MotorBuscaAproximada()

    sugestoes = []

    # Aplica correções automáticas
    corrigido = motor_busca.aplicar_correcoes(termo_busca_falho)
    if corrigido != termo_busca_falho:
        sugestoes.append(f"Tente: '{corrigido}'")

    # Expande com sinônimos
    expansoes = motor_busca.expandir_com_sinonimos(termo_busca_falho)
    for expansao in expansoes[:2]:
        if expansao != termo_busca_falho:
            sugestoes.append(f"Ou tente: '{expansao}'")

    # Sugestões gerais baseadas na palavra
    palavras = termo_busca_falho.lower().split()
    sugestoes_gerais = []

    for palavra in palavras:
        if any(x in palavra for x in ["coca", "refri", "soda"]):
            sugestoes_gerais.append("refrigerantes")
        elif any(x in palavra for x in ["sabao", "deterg", "limp"]):
            sugestoes_gerais.append("produtos de limpeza")
        elif any(x in palavra for x in ["cafe", "acu", "arroz", "feij"]):
            sugestoes_gerais.append("alimentos básicos")

    if sugestoes_gerais:
        sugestoes.extend([f"Categoria: {s}" for s in sugestoes_gerais[:2]])

    if not sugestoes:
        sugestoes = [
            "Tente termos mais simples",
            "Use nomes de categoria: 'refrigerante', 'sabão', 'arroz'",
        ]

    return " • ".join(sugestoes[:3])


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
    print(f">>> CONSOLE: pending_action atual: '{pending_action}'")
    shopping_cart = state.get("shopping_cart", [])
    intent = None
    response_text = ""

    if pending_action == "AWAITING_QUANTITY":
        print(">>> CONSOLE: Tratando ação pendente AWAITING_QUANTITY")

        # 🆕 Extrai quantidade usando IA-FIRST com fallback
        conversation_context = obter_contexto_conversa(session)
        last_shown_products = state.get("last_shown_products", [])
        qt = extrair_quantidade_com_ia(incoming_msg, last_shown_products, conversation_context)
        
        # 🆕 FALLBACK: Se IA não conseguiu, usa extração básica
        if qt is None:
            print(">>> CONSOLE: IA falhou, usando extração básica de quantidade...")
            qt = extrair_quantidade(incoming_msg)
            if qt is not None:
                print(f">>> CONSOLE: Extração básica encontrou quantidade: {qt}")

        if qt is not None and e_quantidade_valida(qt):
            product_to_add = session.get("pending_product_for_cart")
            if product_to_add:
                term_to_learn = session.get("term_to_learn_after_quantity")
                if term_to_learn:
                    print(
                        f">>> CONSOLE: Aprendendo que '{term_to_learn}' se refere a '{obter_nome_produto(product_to_add)}'..."
                    )
                    knowledge.atualizar_kb(term_to_learn, product_to_add)
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
                        and obter_nome_produto(item).lower()
                        == obter_nome_produto(product_to_add).lower()
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
                    product_name = obter_nome_produto(existing_item)

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

                    product_name = obter_nome_produto(product_to_add).replace('CERVEJA ', '').replace('BALA ', '')[:20]
                    from core.gerenciador_sessao import formatar_carrinho_para_exibicao
                    
                    # 🆕 MENSAGEM COMPACTA: Usa IA para gerar resposta natural
                    response_text = generate_personalized_response(
                        "operation_success", 
                        session, 
                        success_details=f"Adicionei {qt_display} {product_name}"
                    )
                    response_text += f"\n\n{formatar_carrinho_para_exibicao(shopping_cart)}"

                    # 📝 REGISTRA A RESPOSTA DO BOT
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "ADD_TO_CART"
                    )

                    atualizar_contexto_sessao(
                        session,
                        {
                            "pending_action": None,
                            "pending_product_for_cart": None,
                            "last_bot_action": "AWAITING_CHECKOUT_CONFIRMATION",
                        },
                    )
                    pending_action = None
                    # Define o estado correto para aguardar confirmação de checkout
                    state["last_bot_action"] = "AWAITING_CHECKOUT_CONFIRMATION"

            else:
                response_text = generate_personalized_response("error", session)
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
                response_text = generate_personalized_response("invalid_quantity", session)
            else:
                response_text = generate_personalized_response("invalid_quantity", session, invalid_quantity=qt)

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
                    success, message, shopping_cart = remover_item_do_carrinho(
                        shopping_cart, selection
                    )
                    response_text = message
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "REMOVE_FROM_CART"
                    )
                elif cart_action == "add":
                    quantity = session.get("pending_cart_quantity", 1)
                    success, message, shopping_cart = adicionar_quantidade_item_carrinho(
                        shopping_cart, selection, quantity
                    )
                    response_text = message
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "ADD_QUANTITY_TO_CART"
                    )
                elif cart_action == "update":
                    quantity = session.get("pending_cart_quantity", 1)
                    success, message, shopping_cart = atualizar_quantidade_item_carrinho(
                        shopping_cart, selection, quantity
                    )
                    response_text = message
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "UPDATE_CART_ITEM"
                    )
                else:
                    response_text = generate_personalized_response("clarification", session)
                    adicionar_mensagem_historico(session, "assistant", response_text, "ERROR")

                # Limpa estado pendente
                pending_action = None
                session.pop("pending_cart_action", None)
                session.pop("pending_cart_matches", None)
                session.pop("pending_cart_quantity", None)
            else:
                response_text = (
                    f"Esse número não tá na lista! Escolhe um desses: {', '.join(map(str, valid_indices))}\n\n"
                    f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart), tem_produtos=True)}"
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REQUEST_CLARIFICATION"
                )
        else:
            response_text = (
                "Digita o número do item que você quer, por favor!\n\n"
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
            success, message, shopping_cart = adicionar_quantidade_item_carrinho(
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
                    "last_bot_action": "AWAITING_CHECKOUT_CONFIRMATION",
                },
            )
            state["last_bot_action"] = "AWAITING_CHECKOUT_CONFIRMATION"
        elif choice == "2":
            success, message, shopping_cart = atualizar_quantidade_item_carrinho(
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
                    "last_bot_action": "AWAITING_CHECKOUT_CONFIRMATION",
                },
            )
            state["last_bot_action"] = "AWAITING_CHECKOUT_CONFIRMATION"
        else:
            if index and 1 <= index <= len(shopping_cart):
                existing_item = shopping_cart[index - 1]
                existing_qty = existing_item.get("qt", 0)
                if isinstance(existing_qty, float):
                    existing_qty_display = f"{existing_qty:.1f}".rstrip("0").rstrip(".")
                else:
                    existing_qty_display = str(existing_qty)
                product_name = obter_nome_produto(existing_item)
                response_text = (
                    f"Você já possui **{product_name}** com **{existing_qty_display}** unidades. "
                    "Deseja *1* somar ou *2* substituir pela nova quantidade?"
                )
            else:
                response_text = generate_personalized_response("clarification", session)
            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_DUPLICATE_DECISION"
            )

        state["pending_action"] = pending_action
        state["shopping_cart"] = shopping_cart

    elif pending_action == "AWAITING_SMART_UPDATE_SELECTION":
        print(">>> CONSOLE: CHEGOU NO ELIF AWAITING_SMART_UPDATE_SELECTION")
        # 🆕 Tratamento para seleção em smart_cart_update
        print(">>> CONSOLE: Tratando ação pendente AWAITING_SMART_UPDATE_SELECTION")
        print(f">>> CONSOLE: Mensagem recebida: '{incoming_msg}'")
        try:
            selection = int(incoming_msg.strip())
            pending_smart_update = session.get("pending_smart_update", {})
            matching_items = pending_smart_update.get("matching_items", [])
            print(f">>> CONSOLE: Seleção: {selection}, Itens disponíveis: {len(matching_items)}")
            
            if 1 <= selection <= len(matching_items):
                cart_idx, item = matching_items[selection - 1]
                action = pending_smart_update.get("action", "add")
                quantity = pending_smart_update.get("quantity", 1)
                old_qty = item.get("qt", 1)
                
                if action == "add":
                    new_qty = old_qty + quantity
                elif action == "set":
                    new_qty = quantity
                elif action == "remove":
                    new_qty = max(0, old_qty - quantity)
                else:
                    new_qty = old_qty
                
                if new_qty <= 0:
                    # Remove do carrinho
                    removed_item = shopping_cart.pop(cart_idx)
                    product_display_name = obter_nome_produto(removed_item)
                    response_text = generate_personalized_response(
                        "operation_success", 
                        session, 
                        success_details=f"{product_display_name} removido do carrinho"
                    )
                else:
                    # Atualiza quantidade
                    shopping_cart[cart_idx]["qt"] = new_qty
                    product_display_name = obter_nome_produto(item)
                    success_msg = f"{product_display_name} atualizado para {new_qty} unidades"
                    print(f">>> CONSOLE: Mensagem de sucesso: '{success_msg}'")
                    response_text = generate_personalized_response(
                        "operation_success", 
                        session, 
                        success_details=success_msg
                    )
                    print(f">>> CONSOLE: Response gerada: '{response_text[:100]}...')")
                    
                    # 🆕 MENSAGEM MAIS CONCISA
                    from core.gerenciador_sessao import formatar_carrinho_para_exibicao
                    cart_display = formatar_carrinho_para_exibicao(shopping_cart)
                    response_text = f"{response_text}\n\n{cart_display}"
                
                adicionar_mensagem_historico(session, "assistant", response_text, "SMART_UPDATE_COMPLETED")
            else:
                response_text = generate_personalized_response("invalid_selection", session, 
                    invalid_number=selection, max_options=len(matching_items))
                adicionar_mensagem_historico(session, "assistant", response_text, "INVALID_SELECTION")
            
            # Limpa estado pendente
            atualizar_contexto_sessao(session, {
                "pending_smart_update": None,
                "pending_action": None
            })
            pending_action = None
            state["pending_action"] = pending_action
            
            # Retorna uma intent fake para indicar que a ação foi processada
            return {"nome_ferramenta": "action_processed", "parametros": {}}, response_text
            
        except ValueError as e:
            # Não é um número, deixa continuar com o processamento normal
            print(f">>> CONSOLE: ValueError no AWAITING_SMART_UPDATE_SELECTION: {e}")
            pass
        except Exception as e:
            print(f">>> CONSOLE: Exception inesperada no AWAITING_SMART_UPDATE_SELECTION: {e}")
            pass

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
                intent = {"tool_name": "get_top_selling_products", "parameters": {}}
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

    return None, response_text

def _process_user_message(
    session: Dict, state: Dict, incoming_msg: str
) -> Tuple[Union[Dict, None], str]:
    """
    Processa a mensagem do usuário e determina a intenção usando o novo fluxo de IA.
    """
    response_text = ""
    shopping_cart = state.get("shopping_cart", [])

    if not incoming_msg:
        response_text = (
            "Me conta o que você precisa que eu te ajudo!\n\n"
            f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
        )
        state["last_shown_products"] = []
        state["last_bot_action"] = "AWAITING_MENU_SELECTION"
        adicionar_mensagem_historico(
            session, "assistant", response_text, "REQUEST_CLARIFICATION"
        )
        return None, response_text

    # 🔍 DETECTA CNPJ ANTES DE NÚMEROS DE SELEÇÃO
    def is_cnpj_format(text: str) -> bool:
        """Detecta se o texto parece ser um CNPJ (com ou sem formatação)"""
        # Remove pontuação e espaços
        clean = ''.join(filter(str.isdigit, text))
        # CNPJ tem 14 dígitos, mas aceita também 11+ para ser mais tolerante
        if len(clean) >= 11:
            return True
        # Detecta padrões com formatação típica de CNPJ
        import re
        cnpj_pattern = r'^\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}$'
        return bool(re.match(cnpj_pattern, text.replace(' ', '')))
    
    # 📋 DETECTA CNPJ NO CONTEXTO DE CHECKOUT
    if is_cnpj_format(incoming_msg.strip()):
        print(f">>> CONSOLE: CNPJ detectado: '{incoming_msg.strip()}' - processando checkout")
        # Força o processamento como checkout com CNPJ
        intent = {"nome_ferramenta": "checkout", "parametros": {"cnpj": incoming_msg.strip()}}
        return intent, response_text
    
    # 🚨 PRIORIDADE MÁXIMA: Detecta números de menu principal (mas não CNPJ)
    if incoming_msg.strip().isdigit() and not is_cnpj_format(incoming_msg.strip()):
        numero = int(incoming_msg.strip())
        ultima_acao = state.get("last_bot_action", "")
        
        print(f">>> CONSOLE: Número {numero} detectado, ultima_acao='{ultima_acao}', tem_carrinho={bool(shopping_cart)}, produtos_mostrados={len(state.get('last_shown_products', []))}")
        
        # Se é contexto de menu e não tem produtos para selecionar
        if ultima_acao == "AWAITING_MENU_SELECTION" and not state.get("last_shown_products"):
            print(f">>> CONSOLE: Processando seleção de menu {numero}")
            if numero == 1:
                intent = {"nome_ferramenta": "smart_search_with_promotions", "parametros": {"search_term": "produtos"}}
                return intent, response_text
            elif numero == 2 and shopping_cart:
                intent = {"nome_ferramenta": "view_cart", "parametros": {}}
                return intent, response_text
            elif numero == 3 and shopping_cart:
                intent = {"nome_ferramenta": "checkout", "parametros": {}}
                return intent, response_text
        
        # 🎯 NOVA CONDIÇÃO: Se é contexto de seleção de produto e tem produtos para selecionar
        elif ultima_acao == "AWAITING_PRODUCT_SELECTION" and state.get("last_shown_products"):
            produtos_mostrados = state.get("last_shown_products", [])
            if 1 <= numero <= len(produtos_mostrados):
                print(f">>> CONSOLE: Processando seleção de produto {numero}")
                intent = {"nome_ferramenta": "add_item_to_cart", "parametros": {"index": numero}}
                return intent, response_text
            else:
                print(f">>> CONSOLE: Número {numero} inválido para {len(produtos_mostrados)} produtos")
                # Deixa a IA processar como fallback

    # 1. Análise avançada de intenções de carrinho (se há carrinho ativo)
    if shopping_cart:
        print(">>> CONSOLE: Analisando intenção de carrinho com IA...")
        historico_conversa = obter_contexto_conversa(session)
        intencao_carrinho = detectar_intencao_carrinho_ia(
            incoming_msg, 
            historico_conversa, 
            shopping_cart
        )
        
        if intencao_carrinho.get("confidence", 0) > 0.7:
            print(f">>> CONSOLE: Intenção de carrinho detectada: {intencao_carrinho}")
            # Converte para formato compatível com o sistema
            if intencao_carrinho.get("action") == "view_cart":
                intent = {"nome_ferramenta": "view_cart", "parametros": {}}
                return intent, response_text
            elif intencao_carrinho.get("action") == "clear_cart":
                intent = {"nome_ferramenta": "clear_cart", "parametros": {}}
                return intent, response_text
            elif intencao_carrinho.get("action") == "checkout":
                intent = {"nome_ferramenta": "checkout", "parametros": {}}
                return intent, response_text

    # 2. Chama a IA para obter a intenção usando o novo classificador inteligente
    intent = llm_interface.get_intent_fast(
        user_message=incoming_msg,
        session_data=session
    )

    print(f">>> CONSOLE: Intenção extraída do JSON: {intent}")

    return intent, response_text

def _processar_pedido_complexo(session: Dict, state: Dict, pedidos_complexos: List[Dict]) -> str:
    """
    Processa pedidos complexos com múltiplos itens usando IA-FIRST.
    
    Args:
        session: Dados da sessão.
        state: Estado atual.
        pedidos_complexos: Lista de pedidos extraídos pela IA.
    
    Returns:
        str: Resposta formatada para o usuário.
    """
    shopping_cart = state.get("shopping_cart", [])
    itens_adicionados = []
    itens_nao_encontrados = []
    
    for pedido in pedidos_complexos:
        produto_nome = pedido.get("produto", "")
        quantidade = pedido.get("quantidade", 1)
        
        # Busca o produto no banco
        search_result = pesquisar_produtos_com_sugestoes(produto_nome, limite=1)
        
        if search_result["products"]:
            produto = search_result["products"][0]
            produto["qt"] = quantidade
            shopping_cart.append(produto)
            itens_adicionados.append(f"{quantidade}x {produto.get('descricao', produto_nome)}")
            
            # Adiciona ao histórico
            adicionar_mensagem_historico(
                session, "assistant", 
                f"Adicionado: {quantidade}x {produto.get('descricao', produto_nome)}", 
                "ADD_TO_CART_COMPLEX"
            )
        else:
            itens_nao_encontrados.append(f"{quantidade}x {produto_nome}")
    
    # Atualiza o estado
    state["shopping_cart"] = shopping_cart
    state["last_bot_action"] = "COMPLEX_ORDER_PROCESSED"
    
    # Gera resposta
    if itens_adicionados:
        resposta = f"✅ Adicionei ao carrinho:\n" + "\n".join([f"• {item}" for item in itens_adicionados])
        
        if itens_nao_encontrados:
            resposta += f"\n\n❌ Não encontrei:\n" + "\n".join([f"• {item}" for item in itens_nao_encontrados])
        
        resposta += f"\n\n🛒 Carrinho com {len(shopping_cart)} itens"
        resposta += f"\n\n{formatar_acoes_rapidas(tem_carrinho=True)}"
    else:
        resposta = "😕 Não consegui encontrar nenhum dos produtos mencionados. Pode tentar com nomes mais específicos?"
        resposta += f"\n\n{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
    
    return resposta

def _route_tool(session: Dict, state: Dict, intent: Dict, sender_phone: str, incoming_msg: str = "") -> str:
    """Executa a ferramenta baseada na intenção identificada com IA-FIRST."""
    customer_context = state.get("customer_context")
    shopping_cart = state.get("shopping_cart", [])
    last_search_type = state.get("last_search_type")
    last_search_params = state.get("last_search_params", {})
    current_offset = state.get("current_offset", 0)
    last_shown_products = state.get("last_shown_products", [])
    last_bot_action = state.get("last_bot_action")
    pending_action = state.get("pending_action")
    last_kb_search_term = state.get("last_kb_search_term")
    
    # 🆕 IA-FIRST: Detecta pedidos complexos (múltiplos produtos)
    user_message = intent.get("user_message", "")
    if user_message and any(sep in user_message.lower() for sep in [" e ", ",", " mais ", " também "]):
        conversation_context = obter_contexto_conversa(session)
        pedidos_complexos = processar_pedido_complexo_ia(user_message, conversation_context)
        
        if len(pedidos_complexos) > 1:
            print(f">>> CONSOLE: [IA-FIRST] Detectado pedido complexo com {len(pedidos_complexos)} itens")
            return _processar_pedido_complexo(session, state, pedidos_complexos)
    
    # 🆕 IA-FIRST: Análise contextual emocional
    conversation_context = obter_contexto_conversa(session)
    analise_emocional = analisar_contexto_emocional_ia(user_message, conversation_context)
    
    if analise_emocional.get("urgencia") == "urgente":
        print(f">>> CONSOLE: [IA-FIRST] Cliente com urgência detectada")
        # Pode priorizar respostas mais rápidas ou sugerir produtos populares
    
    if analise_emocional.get("sentimento") in ["frustrado", "negativo"]:
        print(f">>> CONSOLE: [IA-FIRST] Cliente frustrado - priorizando melhor experiência")
        # Pode ativar modo de assistência especial

    response_text = ""
    tool_name = intent.get("nome_ferramenta", intent.get("tool_name"))  # Suporta ambos os formatos
    parameters = intent.get("parametros", intent.get("parameters", {}))  # Suporta ambos os formatos
    
    # Mapeamento de nomes em português para inglês (para compatibilidade)
    nome_para_ingles = {
        "busca_inteligente_com_promocoes": "smart_search_with_promotions",
        "obter_produtos_mais_vendidos_por_nome": "get_top_selling_products_by_name",
        "atualizacao_inteligente_carrinho": "smart_cart_update",
        "visualizar_carrinho": "view_cart",
        "limpar_carrinho": "clear_cart",
        "adicionar_item_ao_carrinho": "add_item_to_cart",
        "selecionar_item_para_atualizacao": "selecionar_item_para_atualizacao",
        "checkout": "checkout",
        "lidar_conversa": "handle_chitchat"
    }
    
    # Converte nome em português para inglês se necessário
    if tool_name in nome_para_ingles:
        tool_name = nome_para_ingles[tool_name]
    
    # Mapeamento de parâmetros em português para inglês
    if "termo_busca" in parameters:
        parameters["search_term"] = parameters["termo_busca"]
    if "nome_produto" in parameters:
        parameters["product_name"] = parameters["nome_produto"]
    if "indice" in parameters:
        parameters["index"] = parameters["indice"]
    if "acao" in parameters:
        parameters["action"] = parameters["acao"]
    if "quantidade" in parameters:
        parameters["quantity"] = parameters["quantidade"]
    if "texto_resposta" in parameters:
        parameters["response_text"] = parameters["texto_resposta"]

    db_intensive_tools = [
        "get_top_selling_products",
        "get_top_selling_products_by_name",
        "show_more_products",
        "report_incorrect_product",
        "get_product_by_codprod",
    ]
    if tool_name in db_intensive_tools:
        print(f">>> CONSOLE: Acessando o Banco de Dados (ferramenta: {tool_name})...")

    # 🆕 NOVA FERRAMENTA: clear_cart
    if tool_name == "clear_cart":
        print(">>> CONSOLE: Executando limpeza completa do carrinho...")
        message, empty_cart = limpar_carrinho_completamente(shopping_cart)
        shopping_cart.clear()  # Garante que o carrinho está vazio
        
        response_text = message
        adicionar_mensagem_historico(session, "assistant", response_text, "CLEAR_CART")
        
        # Atualiza estado
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"
        pending_action = None
        
        print(f">>> CONSOLE: Carrinho limpo. Resposta: {response_text}")

    # ETAPA 4: Implementação da nova ferramenta de busca inteligente
    elif tool_name == "smart_search_with_promotions":
        # Aceita tanto search_term quanto category como parâmetro
        search_term = parameters.get("search_term", "") or parameters.get("category", "") or parameters.get("termo_busca", "")
        
        # 🆕 OTIMIZA TERMO DE BUSCA COM IA
        print(f">>> CONSOLE: Otimizando termo de busca '{search_term}' com IA...")
        historico_conversa = obter_contexto_conversa(session)
        analise_marca = detectar_marca_e_produto_ia(search_term, historico_conversa)
        
        print(f">>> DEBUG: [ANALISE_MARCA] Resultado completo: {analise_marca}")
        
        if analise_marca and analise_marca.get("tipo_busca"):
            termo_otimizado = gerar_busca_otimizada(analise_marca)
            if termo_otimizado and termo_otimizado != search_term:
                print(f">>> CONSOLE: Termo otimizado: '{search_term}' → '{termo_otimizado}'")
                search_term = termo_otimizado
        
        print(f">>> CONSOLE: Executando busca inteligente para '{search_term}'...")

        # 🆕 DETECTAR SE É BUSCA GERAL POR PROMOÇÕES
        promo_keywords = ['promoção', 'promoções', 'oferta', 'ofertas', 'desconto', 'descontos', 'barato']
        is_general_promo_search = any(keyword in search_term.lower() for keyword in promo_keywords)
        
        if is_general_promo_search:
            print(">>> CONSOLE: Detectada busca geral por promoções - buscando promoções mais baratas")
            
            # Busca os 10 produtos mais baratos em promoção
            cheapest_promos = database.obter_promocoes_mais_baratas(limite=10)
            
            if not cheapest_promos:
                response_text = "😕 No momento não temos promoções ativas. Mas temos muitos produtos com ótimos preços!"
                adicionar_mensagem_historico(session, "assistant", response_text, "NO_PROMOTIONS_FOUND")
            else:
                last_shown_products = cheapest_promos
                title = "💰 Promoções Mais Baratas:"
                
                # Formata apenas as promoções (sem produtos normais)
                response_text = formatar_lista_produtos_inteligente([], cheapest_promos, title)
                last_bot_action = "AWAITING_PRODUCT_SELECTION"
                
                # 🆕 SALVA PRODUTOS NO ESTADO PARA PERMITIR SELEÇÃO NUMÉRICA
                state["last_shown_products"] = last_shown_products
                state["last_bot_action"] = last_bot_action
                
                # 🔧 ATUALIZA TAMBÉM AS VARIÁVEIS LOCAIS PARA SEREM SALVAS NO FINAL
                last_shown_products = state["last_shown_products"]  # Atualiza variável local
                last_bot_action = state["last_bot_action"]  # Atualiza variável local
                
                adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_CHEAPEST_PROMOTIONS")
        
        else:
            # 🆕 DETECTAR SE É BUSCA POR CATEGORIA + PROMOÇÃO (ex: "cerveja em promoção")
            is_category_promo_search = any(keyword in search_term.lower() for keyword in ['em promoção', 'promocional', 'promocionais'])
            
            # 1. Classificar a categoria COM CONTEXTO IA-FIRST
            conversation_context = obter_contexto_conversa(session)
            category_raw = classificar_categoria_com_contexto_ia(search_term, conversation_context)
            
            # 🆕 2. REUTILIZAR ANÁLISE DE MARCA JÁ FEITA (evita confusão com termo otimizado)
            # analise_marca já foi feita corretamente nas linhas 1053-1059 acima
            print(f">>> CONSOLE: [IA-MARCA] Análise: {analise_marca.get('tipo_busca')} - Marca: {analise_marca.get('marca')}")
            
            # 🆕 MAPEAMENTO IA-FIRST DE CATEGORIAS
            def _mapear_categoria_com_ia(termo_busca: str, categoria_ia: str) -> str:
                """Usa IA para mapear categoria semântica para categoria específica do banco."""
                try:
                    import ollama
                    import os
                    prompt_mapeamento = f"""Mapeie a categoria semântica para a categoria específica do banco de dados:

TERMO DE BUSCA: "{termo_busca}"
CATEGORIA DETECTADA: "{categoria_ia}"

MAPEAMENTO DE CATEGORIAS DO BANCO:
- bebidas com cerveja/marca de cerveja → CERVEJA
- doces/balas/marca de doce → DOCES  
- limpeza/marca de limpeza → DETERGENTE
- higiene/marca de higiene → HIGIENE
- outros casos → manter categoria original

EXEMPLOS:
- "quero heineken" (bebidas) → CERVEJA
- "quero bala fini" (doces) → DOCES
- "quero omo" (limpeza) → DETERGENTE
- "quero shampoo" (higiene) → HIGIENE

RESPONDA APENAS com a categoria do banco (CERVEJA, DOCES, DETERGENTE, HIGIENE, etc):"""

                    HOST_OLLAMA = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
                    NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
                    
                    if HOST_OLLAMA:
                        client = ollama.Client(host=HOST_OLLAMA)
                    else:
                        client = ollama
                        
                    response = client.chat(
                        model=NOME_MODELO_OLLAMA,
                        messages=[{"role": "user", "content": prompt_mapeamento}],
                        options={"temperature": 0.1, "top_p": 0.3, "num_predict": 20}
                    )
                    
                    categoria_mapeada = response['message']['content'].strip().upper()
                    
                    # Valida se é uma categoria válida
                    categorias_validas = ["CERVEJA", "DOCES", "DETERGENTE", "HIGIENE", "BEBIDAS", "ALIMENTOS", "LIMPEZA", "PADARIA"]
                    if categoria_mapeada in categorias_validas:
                        return categoria_mapeada
                    else:
                        return categoria_ia.upper()
                        
                except Exception as e:
                    logging.warning(f"[IA-CATEGORIA] Erro no mapeamento: {e}")
                    return categoria_ia.upper()
            
            category = _mapear_categoria_com_ia(search_term, category_raw)
            print(f">>> CONSOLE: [IA-FIRST] '{search_term}' ({category_raw}) → categoria: '{category}'")

            # 2. Se a categoria for 'outros', usar a busca por nome como fallback
            if category == "outros":
                print(">>> CONSOLE: Categoria 'outros', usando busca por nome como fallback.")
                # Executa busca por nome diretamente
                product_name = search_term
                
                # Primeiro tenta a Knowledge Base
                print(f">>> CONSOLE: Buscando '{product_name}' na Knowledge Base...")
                kb_result, kb_analysis = knowledge.encontrar_produto_na_kb_com_analise(product_name)
                last_search_params = {"product_name": product_name}
                last_search_type = "by_name"
                
                if kb_result and kb_analysis["quality"] in ["excellent", "good"]:
                    # Knowledge Base encontrou produtos de qualidade
                    current_offset, last_shown_products = 0, kb_result
                    print(f">>> CONSOLE: KB encontrou {len(last_shown_products)} produtos (qualidade: {kb_analysis['quality']})")
                    
                    title = f"🎯 Encontrei para '{product_name}':"
                    response_text = formatar_lista_produtos_para_exibicao(
                        last_shown_products, title, False, 0
                    )
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    
                    # 🆕 SALVA PRODUTOS NO ESTADO PARA PERMITIR SELEÇÃO NUMÉRICA
                    state["last_shown_products"] = last_shown_products
                    state["last_bot_action"] = last_bot_action
                    
                    # 🔧 ATUALIZA TAMBÉM AS VARIÁVEIS LOCAIS PARA SEREM SALVAS NO FINAL
                    last_shown_products = state["last_shown_products"]  # Atualiza variável local
                    last_bot_action = state["last_bot_action"]  # Atualiza variável local
                    
                    adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_PRODUCTS_FROM_KB")
                    
                else:
                    # KB não encontrou ou qualidade baixa - busca no banco
                    print(f">>> CONSOLE: KB qualidade baixa, buscando no banco...")
                    current_offset, last_shown_products = 0, []
                    
                    search_result = pesquisar_produtos_com_sugestoes(product_name, limite=10, offset=current_offset)
                    products = search_result["products"]
                    suggestions = search_result["suggestions"]
                    
                    if products:
                        current_offset += len(products)
                        last_shown_products.extend(products)
                        print(f">>> DEBUG: [INICIAL_SEARCH] Incrementou offset com {len(products)} produtos, novo offset: {current_offset}")
                        
                        title = f"🔍 Encontrei produtos relacionados a '{product_name}':"
                        response_text = formatar_lista_produtos_para_exibicao(products, title, len(products) == 10, 0)
                        
                        if suggestions:
                            response_text += f"\n💡 Dica: {suggestions[0]}"
                        
                        last_bot_action = "AWAITING_PRODUCT_SELECTION"
                        
                        # 🆕 SALVA PRODUTOS NO ESTADO PARA PERMITIR SELEÇÃO NUMÉRICA
                        state["last_shown_products"] = last_shown_products
                        state["last_bot_action"] = last_bot_action
                        
                        # 🔧 ATUALIZA TAMBÉM AS VARIÁVEIS LOCAIS PARA SEREM SALVAS NO FINAL
                        last_shown_products = state["last_shown_products"]  # Atualiza variável local
                        last_bot_action = state["last_bot_action"]  # Atualiza variável local
                        
                        adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_PRODUCTS_FROM_DB")
                    else:
                        response_text = generate_personalized_response("no_products", session, search_term=product_name)
                        if suggestions:
                            response_text += f"\n💡 Dica: {suggestions[0]}"
                        response_text += f"\n\n{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                        adicionar_mensagem_historico(session, "assistant", response_text, "NO_PRODUCTS_FOUND")
            
            elif is_category_promo_search:
                # 3. APENAS produtos promocionais da categoria
                print(f">>> CONSOLE: Busca por promoções na categoria '{category}'")
                promo_products = database.obter_produtos_promocionais_por_categoria(category, limite=10)
                
                if not promo_products:
                    response_text = f"😕 Não temos promoções ativas na categoria '{category}' no momento. Que tal ver nossos produtos normais desta categoria?"
                    adicionar_mensagem_historico(session, "assistant", response_text, "NO_CATEGORY_PROMOTIONS")
                else:
                    last_shown_products = promo_products
                    title = f"🔥 Promoções na categoria '{category.title()}':"
                    
                    # Formata apenas as promoções
                    response_text = formatar_lista_produtos_inteligente([], promo_products, title)
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_CATEGORY_PROMOTIONS")
                    
            else:
                # 4. Buscar produtos normais + seção de promocionais da categoria
                print(f">>> CONSOLE: Busca normal na categoria '{category}' com seção promocional")
                
                # 🆕 BUSCA INTELIGENTE: Se busca marca específica, prioriza essa marca na consulta
                marca_priorizada = None
                limite_busca = 10
                
                if analise_marca.get("tipo_busca") == "marca_especifica" and analise_marca.get("marca"):
                    marca_priorizada = analise_marca.get("marca")
                    limite_busca = 25  # Aumenta limite para ter mais variedade
                    print(f">>> CONSOLE: [IA-MARCA] Priorizando marca '{marca_priorizada}' na busca")
                
                print(f">>> CONSOLE: Limite de busca: {limite_busca} (marca priorizada: {marca_priorizada})")
                
                normal_products = database.obter_produtos_por_categoria(category, limite=limite_busca, marca_priorizada=marca_priorizada)
                promo_products = database.obter_produtos_promocionais_por_categoria(category, limite=10)
                
                print(f">>> DEBUG: [BUSCA_DB] Categoria '{category}' retornou {len(normal_products)} produtos normais")
                print(f">>> DEBUG: [BUSCA_DB] Categoria '{category}' retornou {len(promo_products)} produtos promocionais")
                
                # Log completo dos produtos encontrados
                for i, p in enumerate(normal_products):
                    print(f">>> DEBUG: [NORMAL_{i+1}] {p.get('descricao')} | Marca: {p.get('marca')} | Preço: R$ {p.get('pvenda', p.get('preco_varejo'))}")
                
                for i, p in enumerate(promo_products):
                    print(f">>> DEBUG: [PROMO_{i+1}] {p.get('descricao')} | Marca: {p.get('marca')} | Preço: R$ {p.get('preco_promocional', p.get('preco_atual'))}")
                
                
                # 🆕 5. FILTRAR POR MARCA ESPECÍFICA SE DETECTADA
                if analise_marca.get("tipo_busca") == "marca_especifica" and analise_marca.get("marca"):
                    marca_desejada = analise_marca.get("marca")
                    print(f">>> CONSOLE: [IA-MARCA] Filtrando produtos pela marca '{marca_desejada}'")
                    print(f">>> DEBUG: [FILTRO] Antes do filtro - normais: {len(normal_products)}, promocionais: {len(promo_products)}")
                    
                    # Filtra produtos normais e promocionais pela marca
                    normal_products_filtrados = filtrar_produtos_por_marca(normal_products, marca_desejada)
                    promo_products_filtrados = filtrar_produtos_por_marca(promo_products, marca_desejada)
                    
                    print(f">>> DEBUG: [FILTRO] Depois do filtro - normais: {len(normal_products_filtrados)}, promocionais: {len(promo_products_filtrados)}")
                    
                    # Debug detalhado dos produtos FILTRADOS
                    print(f">>> DEBUG: [FILTRADOS_NORMAIS] Produtos normais da marca '{marca_desejada}':")
                    for i, p in enumerate(normal_products_filtrados):
                        print(f">>> DEBUG: [FILTRADO_NORMAL_{i+1}] {p.get('descricao')} | Marca: {p.get('marca')} | Preço: R$ {p.get('pvenda', p.get('preco_varejo'))}")
                    
                    print(f">>> DEBUG: [FILTRADOS_PROMO] Produtos promocionais da marca '{marca_desejada}':")
                    for i, p in enumerate(promo_products_filtrados):
                        print(f">>> DEBUG: [FILTRADO_PROMO_{i+1}] {p.get('descricao')} | Marca: {p.get('marca')} | Preço: R$ {p.get('preco_promocional', p.get('preco_atual'))}")
                    
                    # 🆕 MELHORIA: Se marca não foi encontrada nos normais, busca diretamente por nome
                    if not normal_products_filtrados and not promo_products_filtrados:
                        print(f">>> CONSOLE: [IA-MARCA] Marca '{marca_desejada}' não encontrada na categoria, buscando por nome específico...")
                        # Busca direta por nome da marca
                        search_result = pesquisar_produtos_com_sugestoes(marca_desejada, limite=10)
                        marca_products = search_result["products"]
                        
                        print(f">>> DEBUG: [BUSCA_DIRETA] Busca por '{marca_desejada}' retornou {len(marca_products)} produtos")
                        for i, p in enumerate(marca_products):
                            print(f">>> DEBUG: [BUSCA_DIRETA_{i+1}] {p.get('descricao')} | Marca: {p.get('marca')} | Preço: R$ {p.get('pvenda', p.get('preco_varejo'))}")
                        
                        if marca_products:
                            # Busca produtos da marca em ambas as tabelas
                            marca_em_promo = database.obter_produtos_promocionais_por_termo(marca_desejada, limite=10)
                            marca_normais = [p for p in marca_products if p['codprod'] not in {pr['codprod'] for pr in marca_em_promo}]
                            
                            print(f">>> DEBUG: [SEPARACAO] {len(marca_normais)} produtos normais + {len(marca_em_promo)} promocionais após separação")
                            
                            normal_products = marca_normais
                            promo_products = marca_em_promo
                            print(f">>> CONSOLE: [IA-MARCA] Busca direta encontrou {len(marca_normais)} normais + {len(marca_em_promo)} promoções da marca '{marca_desejada}'")
                    else:
                        # Usa produtos filtrados da categoria
                        normal_products = normal_products_filtrados
                        promo_products = promo_products_filtrados
                        print(f">>> CONSOLE: [IA-MARCA] Filtro categoria encontrou {len(normal_products)} normais + {len(promo_products)} promoções da marca '{marca_desejada}'")

                # 5. Combinar e formatar a lista
                if not normal_products and not promo_products:
                    response_text = f"😕 Nenhum produto encontrado na categoria '{category}'. Que tal tentar outra busca?"
                    adicionar_mensagem_historico(session, "assistant", response_text, "NO_PRODUCTS_FOUND")
                else:
                    # Remove duplicatas (um produto pode ser normal e estar em promoção)
                    promo_codprods = {p['codprod'] for p in promo_products}
                    unique_normal_products = [p for p in normal_products if p['codprod'] not in promo_codprods]

                    # 🆕 ORDENAÇÃO INTELIGENTE: Separar produtos com e sem desconto real
                    produtos_normais_finais = unique_normal_products.copy()
                    produtos_com_desconto_real = []
                    
                    for p in promo_products:
                        preco_antigo = p.get('pvenda') or p.get('preco_varejo', 0.0) or 0.0
                        preco_promo = p.get('preco_promocional') or p.get('preco_atual') or preco_antigo
                        desconto = p.get('desconto_percentual', 0.0) or 0.0
                        
                        # Calcular desconto se não informado
                        if desconto == 0.0 and preco_antigo > 0 and preco_promo > 0 and preco_promo < preco_antigo:
                            desconto = ((preco_antigo - preco_promo) / preco_antigo) * 100
                        
                        # Se tem desconto real (>1%), é promoção; senão é produto normal
                        if desconto > 1.0:
                            produtos_com_desconto_real.append(p)
                        else:
                            produtos_normais_finais.append(p)
                    
                    # Lista final ordenada: produtos normais primeiro, depois produtos com desconto
                    combined_products = produtos_normais_finais + produtos_com_desconto_real
                    last_shown_products = combined_products
                    
                    # 🆕 6. TÍTULO INTELIGENTE BASEADO NA ANÁLISE DE MARCA
                    if analise_marca.get("tipo_busca") == "marca_especifica" and analise_marca.get("marca"):
                        marca_title = analise_marca.get("marca").title()
                        title = f"🎯 Produtos {marca_title} encontrados:"
                    else:
                        title = f"🎯 Produtos na categoria '{category.title()}':"
                    
                    # ETAPA 5: Utiliza o novo formatador inteligente (produtos normais + promoções)
                    response_text = formatar_lista_produtos_inteligente(
                        produtos_normais_finais, produtos_com_desconto_real, title
                    )
                    
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    
                    # 🆕 7. ADICIONAR OUTRAS PROMOÇÕES DA CATEGORIA COMO PRODUTOS SELECIONÁVEIS
                    # (SEMPRE quando for busca de marca específica, independente de como foram encontrados os produtos)
                    if analise_marca.get("tipo_busca") == "marca_especifica" and analise_marca.get("marca"):
                        # Busca outras promoções da mesma categoria (excluindo a marca específica)
                        outras_promocoes = database.obter_produtos_promocionais_por_categoria(category, limite=5)
                        marca_desejada = analise_marca.get("marca").lower()
                        
                        # Filtra promoções que NÃO são da marca específica
                        outras_promocoes_filtradas = [
                            p for p in outras_promocoes 
                            if p.get('marca', '').lower() != marca_desejada 
                            and marca_desejada not in p.get('descricao', '').lower()
                            and p['codprod'] not in promo_codprods  # Evita duplicatas
                        ]
                        
                        if outras_promocoes_filtradas:
                            print(f">>> CONSOLE: [IA-MARCA] Adicionando {len(outras_promocoes_filtradas)} outras promoções da categoria '{category}'")
                            # Adiciona as outras promoções à lista de produtos selecionáveis
                            outras_promocoes_processadas = []
                            for promo in outras_promocoes_filtradas[:3]:
                                preco_atual = promo.get('preco_atual') or promo.get('preco_promocional') or promo.get('preco_varejo')
                                preco_original = promo.get('preco_varejo', preco_atual)
                                desconto = 0.0
                                if preco_atual < preco_original:
                                    desconto = ((preco_original - preco_atual) / preco_original) * 100
                                
                                # Adiciona metadados de desconto para formatação correta
                                promo['_preco_antigo'] = preco_original
                                promo['_preco_promo'] = preco_atual
                                promo['_desconto'] = desconto
                                outras_promocoes_processadas.append(promo)
                            
                            # Adiciona as outras promoções ao combined_products e atualiza a lista
                            combined_products.extend(outras_promocoes_processadas)
                            last_shown_products = combined_products
                            
                            # Reformata a resposta com todos os produtos (incluindo outras promoções numeradas)
                            response_text = formatar_lista_produtos_inteligente(
                                produtos_normais_finais, 
                                produtos_com_desconto_real + outras_promocoes_processadas, 
                                title
                            )
                    
                    # 🆕 SALVA PRODUTOS NO ESTADO PARA PERMITIR SELEÇÃO NUMÉRICA E "MAIS"
                    state["last_shown_products"] = last_shown_products
                    state["last_bot_action"] = last_bot_action
                    
                    # 🆕 SALVA PARÂMETROS PARA FUNCIONAR COM "MAIS"
                    last_search_type = "smart_search"
                    last_search_params = {
                        "search_term": search_term,
                        "category": category,
                        "marca_priorizada": analise_marca.get("marca") if analise_marca.get("tipo_busca") == "marca_especifica" else None
                    }
                    
                    print(f">>> DEBUG: [SALVAR_BUSCA] Salvando busca inteligente - tipo: {last_search_type}, params: {last_search_params}")
                    
                    # 🔧 ATUALIZA TAMBÉM AS VARIÁVEIS LOCAIS PARA SEREM SALVAS NO FINAL
                    last_shown_products = state["last_shown_products"]  # Atualiza variável local
                    last_bot_action = state["last_bot_action"]  # Atualiza variável local
                    
                    adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_SMART_SEARCH_RESULTS")
                    
                    # 📝 LOG DA RESPOSTA DO BOT PARA ANÁLISE
                    print(f">>> BOT_RESPONSE: {response_text[:200]}..." if len(response_text) > 200 else f">>> BOT_RESPONSE: {response_text}")

    elif tool_name in ["get_top_selling_products", "get_top_selling_products_by_name"]:
        last_kb_search_term, last_shown_products = None, []

        if tool_name == "get_top_selling_products_by_name":
            product_name = parameters.get("product_name", "")

            # 🆕 EXTRAI ESPECIFICAÇÕES DO PRODUTO COM IA
            print(f">>> CONSOLE: Extraindo especificações de '{product_name}' com IA...")
            especificacoes = extrair_especificacoes_produto_ia(product_name)
            
            if especificacoes.get("enhanced_search_term"):
                product_name_enhanced = especificacoes["enhanced_search_term"]
                print(f">>> CONSOLE: Termo otimizado: '{product_name}' → '{product_name_enhanced}'")
                product_name = product_name_enhanced

            # 🆕 BUSCA FUZZY INTELIGENTE
            print(f">>> CONSOLE: Buscando '{product_name}' com sistema fuzzy...")

            # Etapa 1: Tenta Knowledge Base com análise
            kb_products, kb_analysis = encontrar_produto_na_kb_com_analise(product_name)

            if kb_products and kb_analysis.get("quality") in ["excellent", "good"]:
                # Knowledge Base encontrou bons resultados
                last_kb_search_term = product_name
                last_shown_products = kb_products[:10]  # Limita a 10

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
                    product_name, limite=10, offset=current_offset
                )

                products = search_result["products"]
                suggestions = search_result["suggestions"]

                if products:
                    current_offset += len(products)
                    last_shown_products.extend(products)
                    print(f">>> DEBUG: [BY_NAME_SEARCH] Incrementou offset com {len(products)} produtos, novo offset: {current_offset}")

                    # Determina emoji baseado na qualidade
                    if len(products) >= 3:
                        title_emoji = "🎯"
                    elif suggestions:
                        title_emoji = "🔍"
                    else:
                        title_emoji = "📦"

                    title = f"{title_emoji} Encontrei estes produtos relacionados a '{product_name}':"
                    response_text = formatar_lista_produtos_para_exibicao(
                        products, title, len(products) == 10, 0
                    )

                    # 🆕 ADICIONA SUGESTÕES SE HOUVER
                    if suggestions:
                        response_text += f"\n💡 Dica: {suggestions[0]}"

                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "SHOW_PRODUCTS_FROM_DB"
                    )

                else:
                    # Nenhum produto encontrado - usa IA para correção e sugestões
                    print(
                        f">>> CONSOLE: Nenhum produto encontrado para '{product_name}'"
                    )

                    # 🆕 USA IA PARA CORRIGIR E SUGERIR
                    print(">>> CONSOLE: Usando IA para corrigir e sugerir alternativas...")
                    historico_conversa = obter_contexto_conversa(session)
                    correcoes_ia = corrigir_e_sugerir_ia(
                        product_name, 
                        historico_conversa, 
                        shopping_cart
                    )

                    response_text = f"Não achei nada com '{product_name}', mas vou te ajudar a encontrar!"

                    # Adiciona correções da IA se disponíveis
                    if correcoes_ia.get("correction"):
                        response_text += f"\n\n🔧 Você quis dizer: *{correcoes_ia['correction']}*?"
                    
                    if correcoes_ia.get("suggestions"):
                        response_text += f"\n\n💡 Sugestões: {', '.join(correcoes_ia['suggestions'][:3])}"
                    
                    # Fallback para sugestões do banco
                    if suggestions and not correcoes_ia.get("suggestions"):
                        response_text += f"\n\n💡 {suggestions[0]}"
                        response_text += "\n\nOu tente buscar por categoria: 'refrigerantes', 'detergentes', 'alimentos'."
                    elif not correcoes_ia.get("suggestions"):
                        response_text += "\n\nTente usar termos mais gerais como 'refrigerante', 'sabão' ou 'arroz'."

                    last_bot_action = None
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "NO_PRODUCTS_FOUND"
                    )

                print(
                    f">>> CONSOLE: Banco encontrou {len(products)} produtos, {len(suggestions)} sugestões"
                )

        else:  # get_top_selling_products
            current_offset, last_shown_products = 0, []
            last_search_type, last_search_params = "top_selling", parameters
            products = database.obter_produtos_mais_vendidos(limite=10, offset=current_offset)
            title = "⭐ Estes são nossos produtos mais populares:"
            current_offset += len(products)
            last_shown_products.extend(products)
            print(f">>> DEBUG: [TOP_SELLING_SEARCH] Incrementou offset com {len(products)} produtos, novo offset: {current_offset}")
            response_text = formatar_lista_produtos_para_exibicao(
                products, title, len(products) == 10, 0
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
                else:
                    # Índice inválido - fora do range
                    response_text = generate_personalized_response(
                        "invalid_selection", 
                        session, 
                        invalid_number=parameters['index'],
                        max_options=len(last_shown_products)
                    )
                    if last_shown_products:
                        # Mostra os produtos novamente de forma resumida
                        response_text += "\n\n📦 *Produtos disponíveis:*\n"
                        for i, prod in enumerate(last_shown_products, 1):
                            response_text += f"*{i}.* {obter_nome_produto(prod)}\n"
                        response_text += f"\nDigite o número de *1* a *{len(last_shown_products)}*."
                    adicionar_mensagem_historico(session, "assistant", response_text, "INVALID_SELECTION")
                    return response_text
            except (ValueError, IndexError):
                pass

        if not product_to_add and "product_name" in parameters:
            # 🆕 USA BUSCA FUZZY PARA NOME DO PRODUTO
            product_name = parameters["product_name"]
            print(f">>> CONSOLE: Buscando produto direto por nome: '{product_name}'")

            product_to_add = obter_detalhes_produto_fuzzy(product_name)

            if not product_to_add:
                # Tenta busca mais ampla
                search_result = pesquisar_produtos_com_sugestoes(product_name, limite=1)
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

            response_text = f"Quantas unidades de {obter_nome_produto(product_to_add)} você deseja adicionar?"
            adicionar_mensagem_historico(
                session, "assistant", response_text, "REQUEST_QUANTITY"
            )

        else:
            response_text = generate_personalized_response("error", session)
            response_text += f"\n\n{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
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
                response_text = f"{formatar_carrinho_com_indices(shopping_cart)}\n\nDigite o número do item que deseja remover."
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REQUEST_CART_ITEM_SELECTION"
                )
            else:
                pending_action = None
                response_text = generate_personalized_response("empty_cart", session)
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
            matches = encontrar_produtos_carrinho_por_nome(shopping_cart, product_name)
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
                        f"{idx+1}. {obter_nome_produto(item)} (Qtd: {item.get('qt', 0)})"
                        for idx, item in matches
                    ]
                )
                response_text = f"🤖 Encontrei vários itens com esse nome no carrinho:\n{options}\nDigite o número do item desejado."
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REQUEST_CART_ITEM_SELECTION"
                )

        if matched_index is not None:
            if action == "remove":
                success, response_text, shopping_cart = remover_item_do_carrinho(
                    shopping_cart, matched_index
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "REMOVE_FROM_CART"
                )
            elif action == "add_quantity":
                success, response_text, shopping_cart = adicionar_quantidade_item_carrinho(
                    shopping_cart, matched_index, quantity
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "ADD_QUANTITY_TO_CART"
                )
            elif action == "update_quantity":
                success, response_text, shopping_cart = atualizar_quantidade_item_carrinho(
                    shopping_cart, matched_index, quantity
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "UPDATE_CART_ITEM"
                )
            else:
                response_text = generate_personalized_response("error", session)
                adicionar_mensagem_historico(session, "assistant", response_text, "ERROR")
            last_bot_action = "AWAITING_MENU_SELECTION"
            pending_action = None
        elif pending_action != "AWAITING_CART_ITEM_SELECTION":
            from core.gerenciador_sessao import formatar_carrinho_para_exibicao
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
                "Pra eu mostrar mais produtos, você precisa fazer uma busca antes! O que você tá procurando?"
            )
            adicionar_mensagem_historico(
                session, "assistant", response_text, "NO_PREVIOUS_SEARCH"
            )
        else:
            offset_before_call = current_offset
            products = []
            title = ""
            print(f">>> DEBUG: [MAIS_PRODUTOS] last_search_type: {last_search_type}")
            print(f">>> DEBUG: [MAIS_PRODUTOS] last_search_params: {last_search_params}")
            print(f">>> DEBUG: [MAIS_PRODUTOS] current_offset: {current_offset}")
            
            if last_search_type == "top_selling":
                products = database.obter_produtos_mais_vendidos(limite=10, offset=current_offset)
                title = "Mostrando mais produtos populares:"
            elif last_search_type == "by_name":
                product_name = last_search_params.get("product_name", "")
                products = database.obter_produtos_mais_vendidos_por_nome(
                    product_name, limite=10, offset=current_offset
                )
                title = f"Mostrando mais produtos relacionados a '{product_name}':"
            elif last_search_type == "smart_search":
                # 🆕 SUPORTE PARA BUSCA INTELIGENTE COM "MAIS"
                search_term = last_search_params.get("search_term", "")
                category = last_search_params.get("category", "")
                marca_priorizada = last_search_params.get("marca_priorizada")
                
                print(f">>> DEBUG: [MAIS_SMART] Continuando busca inteligente - termo: '{search_term}', categoria: '{category}', marca: '{marca_priorizada}'")
                
                if marca_priorizada:
                    # Se tem marca específica, busca mais produtos dessa marca
                    print(f">>> DEBUG: [MAIS_SMART] Buscando mais produtos da marca '{marca_priorizada}'")
                    search_result = pesquisar_produtos_com_sugestoes(marca_priorizada, limite=10, offset=current_offset)
                    products = search_result["products"]
                    title = f"Mais produtos {marca_priorizada.title()}:"
                elif category and category != "outros":
                    # Se tem categoria, busca mais produtos da categoria
                    print(f">>> DEBUG: [MAIS_SMART] Buscando mais produtos da categoria '{category}'")
                    products = database.obter_produtos_por_categoria(category, limite=10, offset=current_offset)
                    title = f"Mais produtos da categoria {category.title()}:"
                else:
                    # Fallback: busca geral por termo
                    print(f">>> DEBUG: [MAIS_SMART] Busca geral por '{search_term}'")
                    search_result = pesquisar_produtos_com_sugestoes(search_term, limite=10, offset=current_offset)
                    products = search_result["products"]
                    title = f"Mais produtos relacionados a '{search_term}':"
                
                print(f">>> DEBUG: [MAIS_SMART] Encontrados {len(products)} produtos")

            if not products:
                response_text = (
                    "Opa, já mostrei tudo que temos relacionado a essa busca! Quer procurar outra coisa?\n\n"
                    f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "NO_MORE_PRODUCTS"
                )
            else:
                # 🎯 CORRIGE: Incrementa offset com número real de produtos
                current_offset += len(products)
                last_shown_products.extend(products)
                print(f">>> DEBUG: [MAIS_SMART] Incrementou offset com {len(products)} produtos, novo offset: {current_offset}")
                response_text = formatar_lista_produtos_para_exibicao(
                    products, title, len(products) == 10, offset=offset_before_call
                )
                last_bot_action = "AWAITING_PRODUCT_SELECTION"
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "SHOW_MORE_PRODUCTS"
                )

    elif tool_name == "view_cart":
        from core.gerenciador_sessao import formatar_carrinho_para_exibicao
        response_text = formatar_carrinho_para_exibicao(shopping_cart)
        adicionar_mensagem_historico(session, "assistant", response_text, "SHOW_CART")
        last_shown_products = []
        last_bot_action = "AWAITING_CHECKOUT_CONFIRMATION"

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
        # 🔍 VERIFICA SE CNPJ FOI FORNECIDO
        cnpj_fornecido = parameters.get("cnpj")
        
        if not shopping_cart:
            response_text = (
                "Seu carrinho tá vazio ainda! Bora escolher uns produtos legais?\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=False)}"
            )
            adicionar_mensagem_historico(session, "assistant", response_text, "EMPTY_CART")
            last_shown_products = []
            last_bot_action = "AWAITING_MENU_SELECTION"
        elif cnpj_fornecido:
            # 📋 PROCESSA CNPJ FORNECIDO
            print(f">>> CONSOLE: Processando checkout com CNPJ: {cnpj_fornecido}")
            
            # Aqui você pode adicionar validação de CNPJ se necessário
            # Por enquanto, aceita qualquer CNPJ válido em formato
            customer_context = {
                "cnpj": cnpj_fornecido,
                "nome": "Cliente",  # Pode buscar no banco depois
                "validated": True
            }
            
            # Gera resumo de finalização
            response_text = gerar_resumo_finalizacao(shopping_cart, customer_context)
            adicionar_mensagem_historico(session, "assistant", response_text, "CHECKOUT_COMPLETE")
            
            # Limpa carrinho após finalização
            shopping_cart.clear()
            last_shown_products = []
            last_bot_action = "AWAITING_MENU_SELECTION"
        elif not customer_context:
            # 🔧 MENSAGEM FIXA PARA EVITAR CONFUSÃO DA IA
            response_text = "Para finalizar seu pedido, preciso do seu CNPJ. Por favor, me informe o CNPJ da sua empresa."
            adicionar_mensagem_historico(session, "assistant", response_text, "REQUEST_CNPJ")
            last_shown_products = []
            last_bot_action = None
        else:
            # 🆕 GERA RESUMO COMPLETO DO PEDIDO
            response_text = gerar_resumo_finalizacao(shopping_cart, customer_context)
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
            customer = database.find_customer_by_cnpj(cnpj)
            if customer:
                customer_context = customer
                
                # 🆕 FINALIZA AUTOMATICAMENTE SE TEMOS CARRINHO E CLIENTE
                if shopping_cart:
                    response_text = gerar_resumo_finalizacao(shopping_cart, customer_context)
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "CHECKOUT_COMPLETE"
                    )
                    
                    # Limpa carrinho após finalização
                    shopping_cart.clear()
                    last_shown_products = []
                    last_bot_action = "AWAITING_MENU_SELECTION"
                else:
                    response_text = (
                        f"Oi, {customer_context['nome']}! Que bom te ver por aqui de novo! 😊\n\n"
                        f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                    )
                    adicionar_mensagem_historico(
                        session, "assistant", response_text, "CUSTOMER_IDENTIFIED"
                    )
                    last_shown_products = []
                    last_bot_action = "AWAITING_MENU_SELECTION"
            else:
                response_text = f"Não achei esse CNPJ {cnpj} no nosso sistema, mas tudo bem! Posso registrar seu pedido assim mesmo."
                
                # 🆕 PERMITE FINALIZAR MESMO SEM CADASTRO
                if shopping_cart:
                    response_text += f"\n\n{gerar_resumo_finalizacao(shopping_cart)}"
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
            # 🔧 MENSAGEM FIXA PARA EVITAR CONFUSÃO DA IA
            response_text = "Para finalizar seu pedido, preciso do seu CNPJ. Por favor, me informe o CNPJ da sua empresa."
            adicionar_mensagem_historico(session, "assistant", response_text, "REQUEST_CNPJ")

    elif tool_name == "ask_continue_or_checkout":
        if shopping_cart:
            response_text = gerar_mensagem_continuar_ou_finalizar(shopping_cart)
            adicionar_mensagem_historico(
                session, "assistant", response_text, "ASK_CONTINUE_OR_CHECKOUT"
            )
        else:
            response_text = (
                "Seu carrinho tá vazio ainda! Bora escolher uns produtos maneiros?\n\n"
                f"{formatar_acoes_rapidas(tem_carrinho=False)}"
            )
            adicionar_mensagem_historico(session, "assistant", response_text, "EMPTY_CART")
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"

    elif tool_name == "handle_chitchat":
        # 🆕 DETECTA SE DEVE GERAR SAUDAÇÃO DINÂMICA
        response_param = parameters.get('response_text', 'Entendi!')
        
        if response_param == "GENERATE_GREETING":
            # 🆕 RESETA ESTADO ao detectar nova saudação
            last_shown_products = []
            last_bot_action = None
            last_search_type = None
            last_search_params = {}
            current_offset = 0
            last_kb_search_term = None
            
            log_info("RESETANDO ESTADO para nova conversa", user_id=sender_phone, categoria="STATE_RESET")
            
            # Gera saudação personalizada usando IA
            response_text = generate_personalized_response("greeting", session)
            if not response_text or response_text.strip() == "":
                # Fallback para saudação padrão se IA falhar
                response_text = "Olá! Sou o G.A.V., Gentil Assistente de Vendas do Comercial Esperança. É um prazer atender você! Como posso ajudar?"
                
            # Sempre adiciona quick actions nas saudações
            response_text += f"\n\n{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
        elif last_bot_action in ["AWAITING_PRODUCT_SELECTION", "AWAITING_CORRECTION_SELECTION"]:
            # Preserva o estado se estiver aguardando seleção de produtos
            response_text = f"{response_param}"
            if last_shown_products:
                response_text += f"\n\n📦 *Escolha um produto da lista:*\n"
                for i, prod in enumerate(last_shown_products, 1):
                    response_text += f"*{i}.* {obter_nome_produto(prod)}\n"
                response_text += f"\nDigite o número de *1* a *{len(last_shown_products)}*."
            # Mantém o estado atual - não reseta
        else:
            # 🚀 IA-FIRST: DETECÇÃO INTELIGENTE DE "MAIS PRODUTOS"
            # Obtém a última mensagem do usuário do histórico
            history = session.get('conversation_history', [])
            last_user_message = ""
            for msg in reversed(history):
                if msg.get('role') == 'user':
                    last_user_message = msg.get('message', '')
                    break
            
            incoming_msg_lower = last_user_message.lower().strip()
            should_show_more_products = (
                last_search_type and  # Há busca anterior
                any(word in incoming_msg_lower for word in ["mais", "mais produtos", "continuar", "próximo", "more", "next"]) and
                len(incoming_msg_lower.split()) <= 3  # Mensagem curta (até 3 palavras)
            )
            
            if should_show_more_products:
                print(f">>> CONSOLE: 🚀 [IA-FIRST] Chitchat detectou 'mais produtos' - executando automaticamente")
                
                # 🎯 EXECUTA AUTOMATICAMENTE A LÓGICA DE "MAIS PRODUTOS"
                offset_before_call = current_offset
                products = []
                title = ""
                
                if last_search_type == "smart_search":
                    # 🆕 SUPORTE PARA BUSCA INTELIGENTE COM "MAIS"
                    search_term = last_search_params.get("search_term", "")
                    category = last_search_params.get("category", "")
                    marca_priorizada = last_search_params.get("marca_priorizada")
                    
                    print(f">>> DEBUG: [IA-FIRST-SMART] Continuando busca - termo: '{search_term}', categoria: '{category}', marca: '{marca_priorizada}'")
                    
                    if marca_priorizada:
                        # Se tem marca específica, busca mais produtos dessa marca
                        search_result = pesquisar_produtos_com_sugestoes(marca_priorizada, limite=10, offset=current_offset)
                        products = search_result["products"]
                        title = f"Mais produtos {marca_priorizada.title()}:"
                    elif category and category != "outros":
                        # Se tem categoria, busca mais produtos da categoria
                        products = database.obter_produtos_por_categoria(category, limite=10, offset=current_offset)
                        title = f"Mais produtos da categoria {category.title()}:"
                    else:
                        # Fallback: busca geral por termo
                        search_result = pesquisar_produtos_com_sugestoes(search_term, limite=10, offset=current_offset)
                        products = search_result["products"]
                        title = f"Mais produtos relacionados a '{search_term}':"
                
                elif last_search_type == "by_name":
                    product_name = last_search_params.get("product_name", "")
                    products = database.obter_produtos_mais_vendidos_por_nome(product_name, limite=10, offset=current_offset)
                    title = f"Mais produtos relacionados a '{product_name}':"
                
                elif last_search_type == "top_selling":
                    products = database.obter_produtos_mais_vendidos(limite=10, offset=current_offset)
                    title = "Mais produtos populares:"
                
                if products:
                    # 🎯 SUCESSO: Encontrou mais produtos
                    current_offset += len(products)
                    last_shown_products.extend(products)
                    print(f">>> DEBUG: [IA_FIRST_SMART] Incrementou offset com {len(products)} produtos, novo offset: {current_offset}")
                    
                    # 🤖 IA GERA RESPOSTA PERSONALIZADA + PRODUTOS
                    ai_intro = generate_personalized_response("show_more_products", session)
                    if not ai_intro or ai_intro.strip() == "":
                        ai_intro = "Perfeito! Aqui estão mais opções para você:"
                    
                    products_list = formatar_lista_produtos_para_exibicao(products, title, len(products) == 10, offset=offset_before_call)
                    response_text = f"{ai_intro}\n\n{products_list}"
                    
                    last_bot_action = "AWAITING_PRODUCT_SELECTION"
                    adicionar_mensagem_historico(session, "assistant", response_text, "IA_FIRST_MORE_PRODUCTS")
                    
                    print(f">>> CONSOLE: 🚀 [IA-FIRST] Sucesso! Mostrou {len(products)} produtos adicionais")
                    
                else:
                    # 🚫 NÃO HÁ MAIS PRODUTOS
                    ai_response = generate_personalized_response("no_more_products", session)
                    if not ai_response or ai_response.strip() == "":
                        ai_response = "Opa, já mostrei todos os produtos relacionados! Quer procurar outra coisa?"
                    
                    response_text = f"{ai_response}\n\n{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                    last_shown_products = []
                    last_bot_action = "AWAITING_MENU_SELECTION"
                    adicionar_mensagem_historico(session, "assistant", response_text, "IA_FIRST_NO_MORE_PRODUCTS")
            else:
                # 🗣️ CHITCHAT NORMAL
                response_text = (
                    f"{response_param}\n\n"
                    f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
                )
                last_shown_products = []
                last_bot_action = "AWAITING_MENU_SELECTION"
        
        adicionar_mensagem_historico(session, "assistant", response_text, "CHITCHAT")

    elif not tool_name and "response_text" in intent:
        response_text = (
            f"{intent['response_text']}\n\n"
            f"{formatar_acoes_rapidas(tem_carrinho=bool(shopping_cart))}"
        )
        adicionar_mensagem_historico(session, "assistant", response_text, "GENERIC_RESPONSE")
        last_shown_products = []
        last_bot_action = "AWAITING_MENU_SELECTION"

    elif tool_name == "selecionar_item_para_atualizacao":
        # 🆕 NOVA FERRAMENTA: Seleção de item para atualização durante ação pendente AWAITING_SMART_UPDATE_SELECTION
        try:
            selection = int(parameters.get("indice", parameters.get("index", 0)))
            pending_smart_update = session.get("pending_smart_update", {})
            matching_items = pending_smart_update.get("matching_items", [])
            
            if 1 <= selection <= len(matching_items):
                cart_idx, item = matching_items[selection - 1]
                action = pending_smart_update.get("action", "add")
                quantity = pending_smart_update.get("quantity", 1)
                product_name = pending_smart_update.get("product_name", "")
                
                # Executa a ação no carrinho
                response_text = _executar_acao_carrinho(shopping_cart, cart_idx, item, action, quantity, product_name)
                
                # Limpa ação pendente
                atualizar_contexto_sessao(session, {
                    "pending_smart_update": None,
                    "pending_action": None
                })
                pending_action = None
                
                adicionar_mensagem_historico(session, "assistant", response_text, "SMART_CART_UPDATE_SELECTION")
                
            else:
                response_text = f"❌ Opção inválida! Digite um número de 1 a {len(matching_items)}."
                adicionar_mensagem_historico(session, "assistant", response_text, "INVALID_SELECTION")
        
        except (ValueError, KeyError) as e:
            response_text = "❌ Erro ao processar seleção. Tente novamente."
            logging.error(f"Erro na seleção de item para atualização: {e}")
            # Limpa ação pendente em caso de erro
            atualizar_contexto_sessao(session, {
                "pending_smart_update": None,
                "pending_action": None
            })
            pending_action = None

    elif tool_name == "smart_cart_update":
        # 🆕 NOVA FERRAMENTA: Atualização inteligente do carrinho
        product_name = parameters.get("product_name", "").strip()
        action = parameters.get("action", "add")  # "add", "set", "remove"
        quantity = parameters.get("quantity", 1)
        
        try:
            quantity = float(quantity)
        except (ValueError, TypeError):
            quantity = 1
            
        if not product_name:
            response_text = generate_personalized_response("error", session)
            adicionar_mensagem_historico(session, "assistant", response_text, "ERROR")
        else:
            # Busca produtos no carrinho que correspondem ao nome
            matching_items = []
            for i, item in enumerate(shopping_cart):
                item_name = obter_nome_produto(item).lower()
                if product_name.lower() in item_name or any(word in item_name for word in product_name.lower().split()):
                    matching_items.append((i, item))
            
            if not matching_items:
                # Não há produtos no carrinho, tentar adicionar novo produto
                if action in ["add", "set"]:
                    # Busca o produto no banco para adicionar
                    search_result = pesquisar_produtos_com_sugestoes(product_name, limite=5)
                    if search_result["products"]:
                        best_match = search_result["products"][0]  # Pega o melhor resultado
                        # Adiciona ao carrinho
                        best_match["qt"] = quantity
                        shopping_cart.append(best_match)
                        product_display_name = obter_nome_produto(best_match)
                        
                        # Resposta clara + carrinho atualizado
                        from core.gerenciador_sessao import formatar_carrinho_para_exibicao
                        cart_display = formatar_carrinho_para_exibicao(shopping_cart)
                        response_text = f"✅ Adicionei *{quantity}* {product_display_name} ao seu carrinho!\n\n{cart_display}"
                    else:
                        response_text = f"Não encontrei '{product_name}' nos nossos produtos. Quer ver produtos similares?"
                else:
                    response_text = f"Não encontrei '{product_name}' no seu carrinho para {action}."
            
            elif len(matching_items) == 1:
                # Um produto correspondente - atualiza diretamente
                idx, item = matching_items[0]
                old_qty = item.get("qt", 1)
                
                if action == "add":
                    new_qty = old_qty + quantity
                elif action == "set":
                    new_qty = quantity
                elif action == "remove":
                    new_qty = max(0, old_qty - quantity)
                else:
                    new_qty = old_qty
                
                if new_qty <= 0:
                    # Remove do carrinho
                    removed_item = shopping_cart.pop(idx)
                    product_display_name = obter_nome_produto(removed_item)
                    
                    # Resposta clara + carrinho atualizado
                    if shopping_cart:
                        # Se ainda há itens, mostra carrinho atualizado
                        from core.gerenciador_sessao import formatar_carrinho_para_exibicao
                        cart_display = formatar_carrinho_para_exibicao(shopping_cart)
                        response_text = f"✅ *{product_display_name}* removido do carrinho!\n\n{cart_display}"
                    else:
                        # Carrinho vazio
                        response_text = f"✅ *{product_display_name}* removido!\n\n🛒 Seu carrinho está vazio agora."
                else:
                    # Atualiza quantidade
                    shopping_cart[idx]["qt"] = new_qty
                    product_display_name = obter_nome_produto(item)
                    
                    # Resposta clara + carrinho atualizado
                    if action == "add":
                        action_msg = f"✅ Adicionei *{quantity}* {product_display_name}! Agora você tem *{new_qty}* no total."
                    elif action == "set":
                        action_msg = f"✅ Quantidade alterada! Agora você tem *{new_qty}* {product_display_name}."
                    else:
                        action_msg = f"✅ Quantidade atualizada para *{new_qty}* {product_display_name}!"
                    
                    from core.gerenciador_sessao import formatar_carrinho_para_exibicao
                    cart_display = formatar_carrinho_para_exibicao(shopping_cart)
                    response_text = f"{action_msg}\n\n{cart_display}"
            
            else:
                # Múltiplos produtos correspondentes - solicita escolha
                response_text = f"Encontrei {len(matching_items)} produtos com '{product_name}' no seu carrinho:\n\n"
                for i, (cart_idx, item) in enumerate(matching_items, 1):
                    product_display_name = obter_nome_produto(item)
                    current_qty = item.get("qt", 1)
                    response_text += f"*{i}.* {product_display_name} (quantidade atual: {current_qty})\n"
                
                response_text += f"\nDigite o número do produto que você quer {action}."
                
                # Salva contexto para próxima interação
                atualizar_contexto_sessao(session, {
                    "pending_smart_update": {
                        "action": action,
                        "quantity": quantity,
                        "matching_items": matching_items,
                        "product_name": product_name
                    },
                    "pending_action": "AWAITING_SMART_UPDATE_SELECTION"
                })
                pending_action = "AWAITING_SMART_UPDATE_SELECTION"
            
            adicionar_mensagem_historico(session, "assistant", response_text, "SMART_CART_UPDATE")

    elif tool_name == "action_processed":
        # Esta é uma intent fake usada quando uma ação pendente foi processada
        # Não precisa fazer nada, apenas retorna resposta vazia para indicar que foi processada
        response_text = ""
    
    else:
        logging.warning(f"Fallback Final: Ferramenta desconhecida '{tool_name}'")
        response_text = generate_personalized_response("clarification", session)
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
    sender_phone: str, session_id: str, session: Dict, state: Dict, response_text: str
) -> None:
    """Atualiza e persiste a sessão, além de enviar a resposta ao usuário.
    ATUALIZADO: Sempre salva resposta no histórico e exibe no console. SUPORTA CNPJ.
    Args:
        sender_phone: Número de telefone original (para envio de mensagens)
        session_id: ID da sessão (pode incluir CNPJ)
        session: Dados da sessão
        state: Estado atual
        response_text: Texto da resposta
    """
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
    
    if response_text:
        # 📝 SEMPRE salva a resposta no histórico antes de tentar enviar 
        # 🆕 EVITA DUPLICAÇÃO: Só salva se não for idêntica à última mensagem
        history = session.get("conversation_history", [])
        last_msg = history[-1] if history else {}
        if not (last_msg.get("role") == "assistant" and last_msg.get("message") == response_text):
            adicionar_mensagem_historico(session, "assistant", response_text, "BOT_RESPONSE")
    
    salvar_sessao(session_id, session)

    if response_text:
        # 📺 CONSOLE: Exibe a resposta completa
        print(f"\n=== RESPOSTA DO BOT ===\n{response_text}\n=====================")
        
        # 📝 LOG DETALHADO: Resposta completa sendo enviada
        log_info(
            "RESPOSTA ENVIADA AO USUARIO",
            user_id=sender_phone,
            session_id=session_id,
            resposta_completa=response_text,
            tamanho_resposta=len(response_text),
            categoria="RESPONSE_OUT"
        )
        
        # Tenta enviar por WhatsApp
        try:
            print(f">>> CONSOLE: Tentando enviar resposta para {sender_phone}...")
            log_debug(f"Tentando enviar via WhatsApp", user_id=sender_phone, categoria="WHATSAPP_SEND")
            
            twilio_client.send_whatsapp_message(to=sender_phone, body=response_text)
            #vonage_client.enviar_whatsapp(response_text)
            
            print(f">>> CONSOLE: ✅ Mensagem enviada com sucesso!")
            log_info("WhatsApp enviado com sucesso", user_id=sender_phone, categoria="WHATSAPP_SUCCESS")
        except Exception as e:
            print(f">>> CONSOLE: ❌ ERRO ao enviar mensagem: {e}")
            log_error(f"Erro ao enviar mensagem WhatsApp: {str(e)}", user_id=sender_phone, exception=e, categoria="WHATSAPP_ERROR")


def _validate_cnpj_first(sender_phone: str, incoming_msg: str) -> Tuple[bool, str, str]:
    """
    Valida se o CNPJ foi fornecido no início da conversa.
    
    Returns:
        Tuple[bool, str, str]: (cnpj_validated, session_id, response_text)
            - cnpj_validated: True se CNPJ já foi validado ou fornecido agora
            - session_id: ID da sessão (com CNPJ se validado)  
            - response_text: Mensagem para enviar (se ainda precisar do CNPJ)
    """
    from ai_llm.llm_interface import is_valid_cnpj
    import glob
    import os
    
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] Função _validate_cnpj_first chamada")
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] sender_phone: {sender_phone}")
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] incoming_msg: {incoming_msg}")
    
    # 🔍 Primeiro, procura por qualquer sessão existente com CNPJ para este telefone
    safe_phone_id = sender_phone.replace(":", "_").replace("/", "_")
    pattern = f"data/sessao_{safe_phone_id}_*.json"
    existing_sessions = glob.glob(pattern)
    
    print(f">>> CONSOLE: 🔍 Procurando sessões com padrão: {pattern}")
    print(f">>> CONSOLE: 🔍 Sessões encontradas: {existing_sessions}")
    
    if existing_sessions:
        # Encontrou sessão com CNPJ, usa a mais recente (ordenar por data de modificação)
        session_file = max(existing_sessions, key=os.path.getmtime)
        # Normaliza o nome do arquivo para obter o session_id
        session_filename = os.path.basename(session_file)
        session_id = session_filename.replace("sessao_", "").replace(".json", "")
        print(f">>> CONSOLE: ✅ Sessão com CNPJ encontrada: {session_id} (arquivo: {session_filename})")
        return True, session_id, ""
    
    # Se não encontrou sessão com CNPJ, verifica sessão temporária
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] Não encontrou sessão com CNPJ, verificando sessão temporária...")
    temp_session = carregar_sessao(sender_phone)
    existing_cnpj = temp_session.get("validated_cnpj")
    
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] CNPJ na sessão temporária: {existing_cnpj}")
    
    if existing_cnpj:
        # Já tem CNPJ validado na sessão atual, usa session_id com CNPJ
        session_id = f"{sender_phone}_{existing_cnpj}"
        print(f">>> CONSOLE: ✅ [VALIDATE_CNPJ] CNPJ encontrado na sessão atual: {existing_cnpj}")
        print(f">>> CONSOLE: ✅ [VALIDATE_CNPJ] Retornando session_id: {session_id}")
        return True, session_id, ""
    
    # Verifica se a mensagem atual é um CNPJ
    print(f">>> CONSOLE: 🔍 Verificando se '{incoming_msg.strip()}' é um CNPJ válido...")
    cnpj_validation_result = is_valid_cnpj(incoming_msg.strip())
    print(f">>> CONSOLE: 🔍 Resultado da validação: {cnpj_validation_result}")
    
    if cnpj_validation_result:
        # É um CNPJ válido!
        cnpj_clean = incoming_msg.strip().replace(".", "").replace("/", "").replace("-", "")
        print(f">>> CONSOLE: ✅ CNPJ válido detectado: {cnpj_clean}")
        
        # Migra dados da sessão temporária para a sessão com CNPJ
        session_id_with_cnpj = f"{sender_phone}_{cnpj_clean}"
        
        # Carrega sessão temporária e adiciona CNPJ validado
        temp_session["validated_cnpj"] = cnpj_clean
        temp_session["customer_context"] = temp_session.get("customer_context", {})
        temp_session["customer_context"]["cnpj"] = cnpj_clean
        
        # Salva na nova sessão com CNPJ
        salvar_sessao(session_id_with_cnpj, temp_session)
        
        # Limpa sessão temporária se for diferente
        if session_id_with_cnpj != sender_phone:
            from core.gerenciador_sessao import limpar_sessao
            limpar_sessao(sender_phone)
        
        print(f">>> CONSOLE: ✅ CNPJ {cnpj_clean} validado e sessão migrada!")
        
        # Verifica se já é primeira mensagem após validação
        if len(temp_session.get("historico_conversa", [])) <= 2:
            # Primeira vez validando CNPJ, adiciona mensagem de boas-vindas
            welcome_message = (
                f"✅ *CNPJ validado com sucesso!*\n\n"
                f"🎉 Bem-vindo à *Comercial Esperança*!\n"
                f"Agora posso te ajudar com seus pedidos de forma personalizada.\n\n"
                f"🔍 Digite o nome do produto que deseja\n"
                f"📦 Digite *produtos* para ver os mais vendidos\n"
                f"❓ Digite *ajuda* para mais opções"
            )
            adicionar_mensagem_historico(temp_session, "assistant", welcome_message, "CNPJ_VALIDATED")
            salvar_sessao(session_id_with_cnpj, temp_session)
            
            # CORREÇÃO: Retorna a mensagem de boas-vindas para ser exibida no webchat
            return True, session_id_with_cnpj, welcome_message
        
        # Se não é primeira vez, retorna mensagem simples
        simple_welcome = (
            f"✅ *CNPJ validado!*\n\n"
            f"Como posso te ajudar hoje?\n\n"
            f"🔍 Digite o nome do produto que deseja\n"
            f"📦 Digite *produtos* para ver os mais vendidos"
        )
        return True, session_id_with_cnpj, simple_welcome
    
    # Ainda não tem CNPJ, verifica se já pediu antes
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] CNPJ não é válido, verificando histórico de conversa...")
    conversation_history = temp_session.get("historico_conversa", [])
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] Histórico tem {len(conversation_history)} mensagens")
    
    already_asked_cnpj = any("cnpj" in msg.get("message", "").lower() 
                            and msg.get("role") == "assistant" 
                            for msg in conversation_history[-3:])  # Últimas 3 mensagens
    
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] Já perguntou CNPJ antes: {already_asked_cnpj}")
    
    # Verifica se o usuário tentou enviar algo que parece ser um CNPJ mas é inválido
    user_attempted_cnpj = (
        already_asked_cnpj and 
        len(incoming_msg.strip()) >= 11 and  # Pelo menos 11 caracteres (pode ser CNPJ)
        any(char.isdigit() for char in incoming_msg.strip()) and  # Contém números
        not is_valid_cnpj(incoming_msg.strip())  # Mas não é válido
    )
    
    print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] Usuário tentou CNPJ inválido: {user_attempted_cnpj}")
    
    if user_attempted_cnpj:
        # Usuário tentou enviar CNPJ mas é inválido
        response_text = (
            "❌ CNPJ inválido. Por favor, digite um CNPJ válido no formato:\n"
            "XX.XXX.XXX/XXXX-XX ou apenas os 14 dígitos.\n\n"
            "Exemplo: 12.345.678/0001-95"
        )
        print(f">>> CONSOLE: ❌ [VALIDATE_CNPJ] Retornando erro de CNPJ inválido")
    else:
        # Primeira vez pedindo CNPJ ou usuário não tentou enviar CNPJ ainda
        response_text = (
            "🎉 *Olá! Seja bem-vindo à Comercial Esperança!*\n\n"
            "Eu sou o *G.A.V.* (Gentil Assistente de Vendas) e estou aqui para "
            "te ajudar com seus pedidos de forma rápida e personalizada! 😊\n\n"
            "Para começarmos, preciso apenas do CNPJ da sua empresa:\n"
            "📄 Digite seu CNPJ (pode ser com ou sem pontuação)"
        )
        print(f">>> CONSOLE: 🔍 [VALIDATE_CNPJ] Retornando solicitação inicial de CNPJ")
    
    # Adiciona a mensagem ao histórico da sessão temporária
    adicionar_mensagem_historico(temp_session, "user", incoming_msg)
    adicionar_mensagem_historico(temp_session, "assistant", response_text, "REQUEST_CNPJ")
    salvar_sessao(sender_phone, temp_session)
    
    print(f">>> CONSOLE: ❌ [VALIDATE_CNPJ] Retornando: False, {sender_phone}, response_text")
    return False, sender_phone, response_text


@log_performance
def process_message_async(sender_phone: str, incoming_msg: str):
    """
    Esta função faz todo o trabalho pesado em segundo plano (thread) para não causar timeout.
    ATUALIZADA COM MEMÓRIA CONVERSACIONAL COMPLETA E VALIDAÇÃO OBRIGATÓRIA DE CNPJ
    """
    with aplicativo.app_context():
        try:
            with ContextoLog(user_id=sender_phone, session_id=f"whatsapp_{sender_phone}"):
                log_info(
                    "MENSAGEM RECEBIDA DO USUARIO", 
                    user_id=sender_phone,
                    mensagem_completa_recebida=incoming_msg,
                    tamanho_mensagem=len(incoming_msg),
                    categoria="MESSAGE_IN"
                )
            
            # 🆕 VALIDAÇÃO OBRIGATÓRIA DE CNPJ NO INÍCIO DA CONVERSA
            cnpj_validated, session_id, response_text = _validate_cnpj_first(sender_phone, incoming_msg)
            
            # Se ainda não temos CNPJ válido, envia mensagem solicitando CNPJ e para por aqui
            if not cnpj_validated:
                if response_text:
                    try:
                        twilio_client.send_whatsapp_message(to=sender_phone, body=response_text)
                        print(f">>> CONSOLE: ✅ Mensagem solicitando CNPJ enviada!")
                    except Exception as send_error:
                        print(f">>> CONSOLE: ❌ ERRO ao enviar mensagem: {send_error}")
                return
            
            # Usa o session_id que inclui o CNPJ
            session = carregar_sessao(session_id)

            # 📝 REGISTRA A MENSAGEM DO USUÁRIO NO HISTÓRICO
            adicionar_mensagem_historico(session, "user", incoming_msg)

            # Carrega estado atual da sessão
            state = _extract_state(session)

            # 1. Trata ações pendentes
            intent, response_text = _handle_pending_action(session, state, incoming_msg)

            # 2. Se não houve resposta ou intenção, determina a intenção
            if not intent and not response_text:
                log_debug("Processando mensagem para detectar intencao", user_id=sender_phone, categoria="INTENT_DETECTION")
                intent, response_text = _process_user_message(
                    session, state, incoming_msg
                )
                
                # Log da intenção detectada
                if intent:
                    log_info(
                        "INTENCAO DETECTADA",
                        user_id=sender_phone,
                        intencao_completa=str(intent),
                        tool_name=intent.get("tool_name"),
                        parametros=str(intent.get("parameters", {})),
                        categoria="INTENT_DETECTED"
                    )
                
            # 2.1. PRIORIDADE ESPECIAL: Se detectou checkout, limpa ações pendentes conflitantes
            if intent and intent.get("nome_ferramenta") == "checkout":
                if intent.get("parametros", {}).get("force_checkout"):
                    state["pending_action"] = None  # Limpa qualquer ação pendente
                    print(">>> CONSOLE: Checkout forçado - limpando ações pendentes")

            # 3. Executa a intenção identificada
            if intent and not response_text:
                log_debug("Executando ferramenta detectada", user_id=sender_phone, tool_name=intent.get("tool_name"), categoria="TOOL_EXECUTION")
                response_text = _route_tool(session, state, intent, sender_phone, incoming_msg)
                
                # Log do resultado da ferramenta
                if response_text:
                    log_info(
                        "FERRAMENTA EXECUTADA",
                        user_id=sender_phone,
                        tool_name=intent.get("tool_name"),
                        resposta_gerada=response_text,
                        tamanho_resposta=len(response_text),
                        categoria="TOOL_RESULT"
                    )

            # 4. Mensagem padrão caso nenhuma resposta seja definida
            if not response_text and not state.get("pending_action"):
                # Não adiciona quick_actions se estiver aguardando confirmação de checkout
                if state.get("last_bot_action") == "AWAITING_CHECKOUT_CONFIRMATION":
                    response_text = "Operação concluída."
                else:
                    response_text = (
                        "Operação concluída. O que mais posso fazer por você?\n\n"
                        f"{formatar_acoes_rapidas(tem_carrinho=bool(state.get('shopping_cart', [])))}"
                    )
                adicionar_mensagem_historico(
                    session, "assistant", response_text, "OPERATION_COMPLETE"
                )

            # 5. Atualiza e persiste a sessão, enviando a resposta
            _finalize_session(sender_phone, session_id, session, state, response_text)

            logging.info(f"THREAD: Processamento finalizado para '{incoming_msg}'")
            print(f"--- FIM DO PROCESSAMENTO DA THREAD PARA: '{incoming_msg}' ---\n")
        except Exception as e:
            logging.error(f"ERRO CRÍTICO NA THREAD: {e}", exc_info=True)
            print(f"!!! ERRO CRÍTICO NA THREAD: {e}")

            error_response = "Opa, algo deu errado aqui! Pode tentar de novo, por favor?"
            
            # 📝 SEMPRE salva o erro no histórico primeiro
            try:
                session = carregar_sessao(sender_phone)
                adicionar_mensagem_historico(session, "assistant", error_response, "ERROR")
                salvar_sessao(sender_phone, session)
                print(f"\n=== RESPOSTA DE ERRO ===\n{error_response}\n=====================")
            except:
                pass  # Se falhar aqui, apenas ignora para não causar loop de erro
            
            # Tenta enviar por WhatsApp
            try:
                print(f">>> CONSOLE: Tentando enviar resposta de erro para {sender_phone}...")
                twilio_client.send_whatsapp_message(to=sender_phone, body=error_response)
                #vonage_client.enviar_whatsapp(error_response)
                print(f">>> CONSOLE: ✅ Mensagem de erro enviada com sucesso!")
            except Exception as send_error:
                print(f">>> CONSOLE: ❌ ERRO ao enviar mensagem de erro: {send_error}")

@log_performance
def process_message_for_web(sender_id: str, incoming_msg: str) -> str:
    """
    Processa uma mensagem e retorna o texto da resposta para o webchat.
    Não envia a mensagem por APIs externas. INCLUI VALIDAÇÃO OBRIGATÓRIA DE CNPJ.
    """
    # O 'with app.app_context()' é crucial para que a thread acesse a aplicação Flask
    with aplicativo.app_context():
        try:
            with ContextoLog(user_id=sender_id, session_id=f"webchat_{sender_id}"):
                log_info(
                    "[WEBCHAT] MENSAGEM RECEBIDA DO USUARIO",
                    user_id=sender_id,
                    mensagem_completa_recebida=incoming_msg,
                    tamanho_mensagem=len(incoming_msg),
                    categoria="WEBCHAT_MESSAGE_IN"
                )
            
            cnpj_validated, session_id, response_text = _validate_cnpj_first(sender_id, incoming_msg)
            
            print(f">>> CONSOLE: 🔍 [WEBCHAT] Resultado validação CNPJ:")
            print(f">>> CONSOLE: 🔍 [WEBCHAT] - cnpj_validated: {cnpj_validated}")
            print(f">>> CONSOLE: 🔍 [WEBCHAT] - session_id: {session_id}")
            print(f">>> CONSOLE: 🔍 [WEBCHAT] - response_text: {response_text}")
            
            # Se ainda não temos CNPJ válido, retorna mensagem solicitando CNPJ
            if not cnpj_validated:
                print(f">>> CONSOLE: ❌ [WEBCHAT] CNPJ não validado, retornando: {response_text}")
                return response_text if response_text else "Por favor, informe seu CNPJ para continuar."
            
            # Se CNPJ foi validado agora e temos uma resposta, retorna ela imediatamente
            if response_text and response_text.strip():
                print(f">>> CONSOLE: ✅ [WEBCHAT] CNPJ validado COM resposta, retornando mensagem completa")
                return response_text
            
            print(f">>> CONSOLE: ✅ [WEBCHAT] CNPJ validado SEM resposta, continuando fluxo normal")
            
            # Usa o session_id que inclui o CNPJ
            session = carregar_sessao(session_id)
            adicionar_mensagem_historico(session, "user", incoming_msg)
            state = _extract_state(session)

            intent, response_text = _handle_pending_action(session, state, incoming_msg)

            if not intent and not response_text:
                intent, response_text = _process_user_message(session, state, incoming_msg)
            
            if intent and not response_text:
                # Para web, extraímos o sender_id original da session_id se necessário
                original_sender_id = sender_id.split('_')[0] if '_' in session_id else sender_id
                response_text = _route_tool(session, state, intent, original_sender_id, incoming_msg)
            
            if not response_text and not state.get("pending_action"):
                response_text = "Operação concluída. O que mais posso fazer por você?"
                adicionar_mensagem_historico(session, "assistant", response_text, "OPERATION_COMPLETE")

            # A grande diferença: não chamamos _finalize_session, apenas salvamos o estado e retornamos o texto.
            _finalize_session_for_web(session_id, session, state, response_text)
            
            # 📝 LOG DETALHADO: Resposta sendo retornada para webchat
            log_info(
                "[WEBCHAT] RESPOSTA ENVIADA AO USUARIO",
                user_id=sender_id,
                resposta_completa=response_text,
                tamanho_resposta=len(response_text),
                categoria="WEBCHAT_RESPONSE_OUT"
            )
            
            return response_text

        except Exception as e:
            log_critical(f"WEBCHAT - ERRO CRÍTICO: {str(e)}", user_id=sender_id, exception=e, categoria="WEBCHAT_ERROR")
            return "Opa, algo deu errado aqui! Tente novamente."

def _finalize_session_for_web(sender_id: str, session: Dict, state: Dict, response_text: str):
    """Uma versão do _finalize_session que apenas salva o estado, sem enviar mensagem."""
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
    if response_text:
        # 🆕 EVITA DUPLICAÇÃO: Só salva se não for idêntica à última mensagem
        history = session.get("conversation_history", [])
        last_msg = history[-1] if history else {}
        if not (last_msg.get("role") == "assistant" and last_msg.get("message") == response_text):
            adicionar_mensagem_historico(session, "assistant", response_text, "BOT_RESPONSE")
    
    salvar_sessao(sender_id, session)
    
# twillio
@aplicativo.route("/webhook", methods=["POST"])
def webhook():
    """
    Endpoint para o webhook da Twilio.
    A Twilio envia os dados como 'form data' (request.values).
    """
    # Extrai a mensagem e o telefone do remetente dos valores do formulário
    incoming_msg = request.values.get("Body", "").strip()
    sender_phone = request.values.get("From", "")
    
    log_info(
        "TWILIO WEBHOOK | Mensagem recebida",
        user_id=sender_phone,
        mensagem_completa_recebida=incoming_msg,
        tamanho_mensagem=len(incoming_msg) if incoming_msg else 0,
        categoria="TWILIO_WEBHOOK"
    )
    
    # Valida se os dados essenciais foram recebidos
    if not incoming_msg or not sender_phone:
        logging.warning("TWILIO | 'Body' ou 'From' ausentes na requisição.")
        return "", 200 # Responde OK para não gerar erro na plataforma

    # Inicia a thread para processar a mensagem sem bloquear a resposta do webhook
    thread = threading.Thread(
        target=process_message_async, args=(sender_phone, incoming_msg)
    )
    thread.start()
    
    # Responde imediatamente à Twilio com um status 200 (OK)
    return "", 200


# Vonage
@aplicativo.route("/webhooks/inbound-message", methods=["POST"])
def inbound_message():
    """
    Endpoint para o webhook da Vonage.
    A Vonage envia os dados como um corpo JSON (request.get_json()).
    """
    # Obtém o corpo da requisição como um dicionário Python (JSON)
    data = request.get_json()
    if not data:
        logging.warning("VONAGE | Webhook recebido sem corpo JSON.")
        return jsonify({"error": "Missing JSON body"}), 400

    # Extrai a mensagem e o telefone do remetente do JSON
    incoming_msg = (data.get("text", "") or "").strip()
    sender_phone = str(data.get("from", "") or "").strip() # Garante que seja uma string

    logging.info(f"VONAGE | Mensagem recebida de {sender_phone}: {incoming_msg}")

    # Valida se a mensagem e o remetente foram recebidos
    if not incoming_msg or not sender_phone:
        logging.info("VONAGE | 'text' ou 'from' ausentes no JSON do webhook.")
        return "", 200

    # Reutiliza EXATAMENTE a mesma função de processamento da Twilio
    thread = threading.Thread(
        target=process_message_async, args=(sender_phone, incoming_msg)
    )
    thread.start()

    # Responde imediatamente à Vonage com um status 200 (OK)
    return "", 200

@aplicativo.route("/webchat", methods=["POST"])
def webchat():
    """
    Endpoint para receber mensagens da interface de teste em React.
    Comunicação via JSON.
    """
    data = request.get_json()
    if not data or "message" not in data or "sender_id" not in data:
        return jsonify({"error": "Requisição inválida. 'message' e 'sender_id' são obrigatórios."}), 400

    incoming_msg = data["message"]
    # Usamos um 'sender_id' para manter o histórico da conversa, pode ser qualquer string.
    sender_id = f"webchat:{data['sender_id']}" 
    
    logging.info(f"WEBCHAT | Mensagem recebida de {sender_id}: {incoming_msg}")
    print(f">>> 📥 [ENTRADA] ==========================================")
    print(f">>> 📥 [ENTRADA] Nova mensagem recebida do webchat")  
    print(f">>> 📥 [ENTRADA] Sender ID: {sender_id}")
    print(f">>> 📥 [ENTRADA] Mensagem: '{incoming_msg}'")
    print(f">>> 📥 [ENTRADA] Timestamp: {datetime.now().strftime('%H:%M:%S')}")
    print(f">>> 📥 [ENTRADA] ==========================================")

    # Este é o ponto crucial: precisamos refatorar um pouco o process_message_async
    # para que ele RETORNE a resposta em vez de enviá-la.
    # Por enquanto, vamos chamar uma versão adaptada.
    
    # A lógica de processamento é a mesma, mas a resposta volta para o React.
    response_text = process_message_for_web(sender_id, incoming_msg)

    return jsonify({"reply": response_text})

@aplicativo.route("/clear_cart", methods=["POST"])
def clear_cart_endpoint():
    """ENDPOINT PARA LIMPEZA DE CARRINHO VIA API."""
    data = request.get_json() or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id é obrigatório"}), 400
    
    session = carregar_sessao(user_id)
    shopping_cart = session.get("shopping_cart", [])
    
    message, empty_cart = limpar_carrinho_completamente(shopping_cart)
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
    aplicativo.run(host="0.0.0.0", port=8080, debug=True)