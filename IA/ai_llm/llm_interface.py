# file: IA/ai_llm/llm_interface.py
"""
Interface LLM - Comunicação com Modelo de Linguagem
Versão 2.0 - Com Sistema de Contexto Completo e Validações Aprimoradas
"""

import os
import ollama
import json
import logging
import re
from typing import Union, Dict, List, Tuple
import time
from datetime import datetime

from core.session_manager import get_conversation_context
from utils.quantity_extractor import detect_quantity_modifiers

# --- Configurações Globais ---
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
USE_AI_FALLBACK = os.getenv("USE_AI_FALLBACK", "true").lower() == "true"
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "5"))

AVAILABLE_TOOLS = [
    "find_customer_by_cnpj",
    "get_top_selling_products",
    "get_top_selling_products_by_name",
    "add_item_to_cart",
    "update_cart_item",
    "view_cart",
    "checkout",
    "handle_chitchat",
    "start_new_order",
    "show_more_products",
    "report_incorrect_product",
    "ask_continue_or_checkout",
    "clear_cart",
]

# Cache do prompt
_prompt_cache = None
_prompt_cache_time = 0


def is_valid_cnpj(cnpj: str) -> bool:
    """Valida se uma string é um CNPJ válido."""
    cnpj_digits = re.sub(r'\D', '', cnpj)
    
    if len(cnpj_digits) != 14:
        return False
    
    if cnpj_digits == cnpj_digits[0] * 14:
        return False
    
    try:
        sequence = [int(cnpj_digits[i]) for i in range(12)]
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum1 = sum(sequence[i] * weights1[i] for i in range(12))
        digit1 = ((sum1 % 11) < 2) and 0 or (11 - (sum1 % 11))
        
        if digit1 != int(cnpj_digits[12]):
            return False
        
        sequence.append(digit1)
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum2 = sum(sequence[i] * weights2[i] for i in range(13))
        digit2 = ((sum2 % 11) < 2) and 0 or (11 - (sum2 % 11))
        
        return digit2 == int(cnpj_digits[13])
        
    except (ValueError, IndexError):
        return False


def detect_cart_clearing_intent(message: str) -> bool:
    """Detecta intenção de limpar/esvaziar carrinho com alta precisão."""
    message_lower = message.lower().strip()
    
    # Comandos diretos e explícitos
    clear_commands = [
        'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
        'resetar carrinho', 'apagar carrinho', 'deletar carrinho',
        'esvaziar tudo', 'limpar tudo', 'zerar tudo',
        'apagar tudo', 'deletar tudo', 'remover tudo',
        'começar de novo', 'recomeçar', 'reiniciar',
        'do zero', 'novo pedido', 'nova compra',
        'limpa carrinho', 'esvazia carrinho', 'zera carrinho',
        'clear cart', 'empty cart', 'reset cart'
    ]
    
    if message_lower in clear_commands:
        return True
    
    # Padrões com regex mais flexíveis
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
            
            if action == "REQUEST_CNPJ" or "preciso do seu cnpj" in content:
                context["awaiting_cnpj"] = True
            
            if any(word in content for word in ["finalizar", "checkout", "fechar pedido"]):
                context["checkout_initiated"] = True
    
    context["can_checkout"] = (
        len(session_data.get("shopping_cart", [])) > 0 and
        bool(session_data.get("customer_context"))
    )
    
    return context


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
        items.append(f"{i}. {name} (cod: {codprod})")
    
    return " | ".join(items)


def load_prompt_template() -> str:
    """Carrega o template do prompt do arquivo ou usa fallback."""
    global _prompt_cache, _prompt_cache_time

    if _prompt_cache and (time.time() - _prompt_cache_time) < 300:
        return _prompt_cache

    prompt_path = os.path.join("ai_llm", "gav_prompt.txt")

    try:
        logging.info(f"[llm_interface.py] Carregando prompt de: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            _prompt_cache = content
            _prompt_cache_time = time.time()
            logging.info(f"[llm_interface.py] Prompt carregado. Tamanho: {len(content)} caracteres")
            return content
    except FileNotFoundError:
        logging.warning(f"[llm_interface.py] Arquivo '{prompt_path}' não encontrado. Usando fallback.")
        return get_fallback_prompt()


def get_fallback_prompt() -> str:
    """Prompt de emergência caso o arquivo não seja encontrado."""
    return """Você é G.A.V., o Gentil Assistente de Vendas do Comercial Esperança.

FERRAMENTAS DISPONÍVEIS:
- clear_cart: Limpar carrinho (sem parâmetros)
- find_customer_by_cnpj: Buscar cliente por CNPJ
- get_top_selling_products: Mostrar mais vendidos
- get_top_selling_products_by_name: Buscar produto por nome
- add_item_to_cart: Adicionar ao carrinho
- view_cart: Ver carrinho
- checkout: Finalizar compra
- handle_chitchat: Conversação geral

COMANDOS ESPECIAIS:
- "limpar/esvaziar/zerar carrinho" → use clear_cart
- CNPJ (14 dígitos) em checkout → use find_customer_by_cnpj

Responda SEMPRE em JSON: {"tool_name": "...", "parameters": {...}}"""


def extract_numeric_selection(message: str) -> Union[int, None]:
    """Extrai seleção numérica (1, 2 ou 3) da mensagem."""
    numbers = re.findall(r"\b([123])\b", message.strip())
    if numbers:
        try:
            return int(numbers[0])
        except ValueError:
            pass
    return None


def detect_quantity_keywords(message: str) -> Union[float, None]:
    """Detecta palavras-chave de quantidade na mensagem."""
    message_lower = message.lower().strip()

    quantity_map = {
        "um": 1, "uma": 1, "dois": 2, "duas": 2,
        "três": 3, "tres": 3, "quatro": 4, "cinco": 5,
        "seis": 6, "sete": 7, "oito": 8, "nove": 9,
        "dez": 10, "meia dúzia": 6, "meia duzia": 6,
        "uma dúzia": 12, "uma duzia": 12, "dúzia": 12, "duzia": 12,
    }

    for word, quantity in quantity_map.items():
        if word in message_lower:
            return float(quantity)

    decimal_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", message)
    if decimal_match:
        number_str = decimal_match.group(1).replace(",", ".")
        try:
            return float(number_str)
        except ValueError:
            pass

    return None


def enhance_context_awareness(user_message: str, session_data: Dict) -> Dict:
    """Melhora a consciência contextual analisando estado da sessão."""
    context = {
        "has_cart_items": len(session_data.get("shopping_cart", [])) > 0,
        "cart_count": len(session_data.get("shopping_cart", [])),
        "has_pending_products": len(session_data.get("last_shown_products", [])) > 0,
        "last_action": session_data.get("last_bot_action", ""),
        "customer_identified": bool(session_data.get("customer_context")),
        "recent_search": session_data.get("last_kb_search_term"),
        "numeric_selection": extract_numeric_selection(user_message),
        "inferred_quantity": detect_quantity_keywords(user_message),
        "conversation_history": session_data.get("conversation_history", [])
    }

    context["clear_cart_command"] = detect_cart_clearing_intent(user_message)
    
    checkout_context = detect_checkout_context(session_data)
    context.update(checkout_context)
    
    context["is_valid_cnpj"] = is_valid_cnpj(user_message)
    context["is_cnpj_in_checkout_context"] = (
        context["is_valid_cnpj"] and 
        (context["awaiting_cnpj"] or context["checkout_initiated"])
    )

    message_lower = user_message.lower().strip()

    if any(cmd in message_lower for cmd in ["carrinho", "ver carrinho"]):
        context["direct_cart_command"] = True

    if any(cmd in message_lower for cmd in ["finalizar", "fechar", "checkout"]):
        context["direct_checkout_command"] = True

    if any(cmd in message_lower for cmd in ["continuar", "mais produtos", "outros"]):
        context["continue_shopping"] = True
    
    context["conversation_context"] = analyze_conversation_context(
        context["conversation_history"], user_message
    )

    product_slang = {
        "refri": "refrigerante",
        "zero": "coca zero",
        "lata": "lata",
        "2l": "2 litros",
        "pet": "garrafa pet",
    }

    for slang, meaning in product_slang.items():
        if slang in message_lower:
            context["detected_slang"] = {slang: meaning}
            break

    purchase_stage = session_data.get("purchase_stage", "greeting")

    greeting_keywords = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "e ai"]
    search_keywords = ["buscar", "procurar", "produto", "comprar", "preciso", "quero", "produtos", "mais vendidos"]

    if context.get("direct_checkout_command") or context.get("awaiting_cnpj"):
        purchase_stage = "checkout"
    elif context.get("direct_cart_command"):
        purchase_stage = "cart"
    elif any(word in message_lower for word in greeting_keywords):
        purchase_stage = "greeting"
    elif any(word in message_lower for word in search_keywords) or context.get("has_pending_products"):
        purchase_stage = "search"
    elif context.get("has_cart_items"):
        purchase_stage = "cart"

    context["purchase_stage"] = purchase_stage
    session_data["purchase_stage"] = purchase_stage

    return context


def analyze_conversation_context(history: List[Dict], current_message: str) -> Dict:
    """Analisa o contexto da conversa para melhor interpretação."""
    context_analysis = {
        "last_bot_action_type": None,
        "waiting_for_selection": False,
        "continue_or_checkout_flow": False,
        "recent_products_shown": False
    }
    
    if not history:
        return context_analysis
    
    recent_bot_messages = []
    for msg in reversed(history[-10:]):
        if msg.get("role") == "assistant":
            recent_bot_messages.append(msg.get("message", "").lower())
            if len(recent_bot_messages) >= 3:
                break
    
    if recent_bot_messages:
        last_bot_msg = recent_bot_messages[0]
        
        if any(phrase in last_bot_msg for phrase in [
            "responda 1, 2 ou 3", "escolha", "qual você quer",
            "digite o número", "selecione"
        ]):
            context_analysis["waiting_for_selection"] = True
            context_analysis["recent_products_shown"] = True
        
        if "continuar" in last_bot_msg and "finalizar" in last_bot_msg:
            context_analysis["continue_or_checkout_flow"] = True
        
        if any(phrase in last_bot_msg for phrase in ["adicionado", "adicionei", "no carrinho"]):
            context_analysis["last_bot_action_type"] = "added_to_cart"
    
    return context_analysis


def get_intent(
    user_message: str,
    session_data: Dict,
    customer_context: Union[Dict, None] = None,
    cart_items_count: int = 0,
) -> Dict:
    """Usa o LLM para interpretar a mensagem com contexto completo."""
    try:
        logging.info(f"[llm_interface.py] Processando mensagem: '{user_message}'")
        
        # Obtém contexto completo
        conversation_context = get_conversation_context(session_data, max_messages=10)
        enhanced_context = enhance_context_awareness(user_message, session_data)
        
        # Log do contexto
        logging.info(f"[CONTEXT] História: {len(session_data.get('conversation_history', []))} mensagens")
        logging.info(f"[CONTEXT] Carrinho: {enhanced_context['cart_count']} itens")
        logging.info(f"[CONTEXT] Cliente identificado: {enhanced_context['customer_identified']}")
        
        # PRIORIDADE MÁXIMA: CNPJ em contexto de checkout
        if enhanced_context.get("is_cnpj_in_checkout_context"):
            logging.info("[llm_interface.py] CNPJ detectado em contexto de checkout")
            return {
                "tool_name": "find_customer_by_cnpj",
                "parameters": {"cnpj": user_message.strip()}
            }
        
        # PRIORIDADE ALTA: Comandos de limpeza de carrinho
        if enhanced_context.get("clear_cart_command"):
            logging.info("[llm_interface.py] Comando de limpeza de carrinho detectado")
            return {"tool_name": "clear_cart", "parameters": {}}

        # Para mensagens simples, usa detecção rápida
        message_lower = user_message.lower().strip()
        simple_patterns = [
            r"^\s*[123]\s*$",
            r"^(oi|olá|ola|e aí|e ai|boa|bom dia|boa tarde|boa noite)$",
            r"^(carrinho|ver carrinho)$",
            r"^(finalizar|fechar)$",
            r"^(ajuda|help)$",
            r"^(produtos|mais vendidos)$",
            r"^(mais)$",
            r"^(novo|nova)$",
        ]

        for pattern in simple_patterns:
            if re.match(pattern, message_lower):
                logging.info("[llm_interface.py] Mensagem simples detectada, usando fallback")
                return create_fallback_intent(user_message, enhanced_context)

        if not USE_AI_FALLBACK or len(user_message.strip()) < 3:
            return create_fallback_intent(user_message, enhanced_context)

        # Prepara contexto para o LLM
        system_prompt = load_prompt_template()
        
        cart_details = format_cart_context(session_data.get("shopping_cart", []))
        customer_info = format_customer_context(customer_context)
        products_shown = format_products_context(session_data.get("last_shown_products", []))
        
        special_context = ""
        if enhanced_context.get("clear_cart_command"):
            special_context += "⚠️ COMANDO DE LIMPEZA DE CARRINHO DETECTADO - Use clear_cart\n"
        if enhanced_context.get("is_cnpj_in_checkout_context"):
            special_context += "⚠️ CNPJ VÁLIDO EM CONTEXTO DE CHECKOUT - Use find_customer_by_cnpj\n"
        if enhanced_context.get("awaiting_cnpj"):
            special_context += "⚠️ BOT ESTÁ ESPERANDO CNPJ PARA FINALIZAR PEDIDO\n"

        full_context = f"""
MENSAGEM ATUAL: "{user_message}"

{special_context}

===== HISTÓRICO DA CONVERSA (IMPORTANTE) =====
{conversation_context}

===== ESTADO ATUAL =====
Cliente: {customer_info}
Carrinho: {cart_details}
Produtos Mostrados Recentemente: {products_shown}
Aguardando CNPJ: {'Sim' if enhanced_context.get('awaiting_cnpj') else 'Não'}
Aguardando Seleção: {'Sim' if enhanced_context.get('conversation_context', {}).get('waiting_for_selection') else 'Não'}
Estágio da Compra: {enhanced_context.get('purchase_stage', 'unknown')}

===== ANÁLISE CONTEXTUAL =====
- Comando limpar carrinho: {'Sim' if enhanced_context.get('clear_cart_command') else 'Não'}
- CNPJ válido: {'Sim' if enhanced_context.get('is_valid_cnpj') else 'Não'}
- Seleção numérica: {enhanced_context.get('numeric_selection', 'Não')}
- Quantidade inferida: {enhanced_context.get('inferred_quantity', 'Não')}

INSTRUÇÕES CRÍTICAS:
1. ⚠️ Se "Comando limpar carrinho: Sim", SEMPRE use clear_cart
2. ⚠️ Se "CNPJ válido: Sim" E "Aguardando CNPJ: Sim", use find_customer_by_cnpj
3. ⚠️ Se "Aguardando Seleção: Sim" e mensagem é número, use add_item_to_cart com o produto correspondente
4. Considere TODO o histórico para manter coerência
5. Se produtos foram mostrados e usuário digitou número, adicione o produto correspondente

Responda APENAS com JSON válido: {"tool_name": "...", "parameters": {...}}
"""

        # Chama o modelo
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_context},
        ]

        client = ollama.Client(host=OLLAMA_HOST)
        
        logging.info(f"[llm_interface.py] Chamando Ollama em: '{OLLAMA_HOST}'")

        start_time = time.time()
        try:
            response = client.chat(
                model=OLLAMA_MODEL_NAME,
                messages=messages,
                options={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_predict": 150,
                    "stop": ["\n\n", "```"],
                },
                stream=False,
            )

            elapsed_time = time.time() - start_time
            logging.info(f"[llm_interface.py] Resposta recebida em {elapsed_time:.2f}s")

            content = response.get("message", {}).get("content", "")
            logging.info(f"[llm_interface.py] Resposta do LLM: {content[:200]}...")

            cleaned_content = clean_json_response(content)
            intent_data = json.loads(cleaned_content)
            
            tool_name = intent_data.get("tool_name", "handle_chitchat")
            
            if tool_name not in AVAILABLE_TOOLS:
                logging.warning(f"[llm_interface.py] Ferramenta inválida: {tool_name}")
                intent_data = {
                    "tool_name": "handle_chitchat",
                    "parameters": {"response_text": "Não entendi. Pode reformular?"}
                }

            parameters = intent_data.get("parameters", {})

            if tool_name == "add_item_to_cart" and enhanced_context.get("numeric_selection"):
                if enhanced_context.get("inferred_quantity"):
                    if "qt" not in parameters:
                        parameters["qt"] = enhanced_context["inferred_quantity"]

            intent_data["parameters"] = validate_intent_parameters(tool_name, parameters)
            
            logging.info(f"[INTENT] Detectado: {tool_name} | Params: {intent_data['parameters']}")
            
            return intent_data

        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"[llm_interface.py] Erro ao parsear JSON: {e}")
            return create_fallback_intent(user_message, enhanced_context)

        except TimeoutError:
            logging.warning(f"[llm_interface.py] Timeout após {AI_TIMEOUT}s")
            return create_fallback_intent(user_message, enhanced_context)

    except Exception as e:
        logging.error(f"[llm_interface.py] Erro geral: {e}", exc_info=True)
        return create_fallback_intent(user_message, enhanced_context)


def clean_json_response(content: str) -> str:
    """Limpa a resposta do LLM para extrair JSON válido."""
    content = re.sub(r"```json\s*", "", content)
    content = re.sub(r"```\s*", "", content)

    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    if json_match:
        return json_match.group(0).strip()

    return content.strip()


def create_fallback_intent(user_message: str, context: Dict) -> Dict:
    """Cria intenção de fallback baseada em padrões simples."""
    message_lower = user_message.lower().strip()
    stage = context.get("purchase_stage", "greeting")

    # PRIORIDADE MÁXIMA: CNPJ em contexto de checkout
    if context.get("is_cnpj_in_checkout_context"):
        return {
            "tool_name": "find_customer_by_cnpj",
            "parameters": {"cnpj": user_message.strip()}
        }

    # PRIORIDADE ALTA: Comandos de limpeza
    if context.get("clear_cart_command"):
        return {"tool_name": "clear_cart", "parameters": {}}

    modifiers = detect_quantity_modifiers(message_lower)
    if modifiers.get("action") == "remove":
        if context.get("has_cart_items"):
            return {"tool_name": "update_cart_item", "parameters": {"action": "remove"}}
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Seu carrinho está vazio. Que tal ver nossos produtos?"}
        }

    # Seleção numérica com produtos pendentes
    if context.get("numeric_selection") and context.get("has_pending_products"):
        last_shown = context.get("conversation_history", [])
        if last_shown:
            selected_index = context["numeric_selection"] - 1
            products = []
            for msg in reversed(last_shown[-10:]):
                if msg.get("role") == "assistant" and "codprod" in str(msg.get("message", "")):
                    products = re.findall(r'codprod[:\s]+(\d+)', str(msg["message"]))
                    break
            
            if products and 0 <= selected_index < len(products):
                return {
                    "tool_name": "add_item_to_cart",
                    "parameters": {
                        "codprod": int(products[selected_index]),
                        "qt": context.get("inferred_quantity", 1)
                    }
                }

    # Comandos diretos
    if context.get("direct_cart_command"):
        return {"tool_name": "view_cart", "parameters": {}}

    if context.get("direct_checkout_command"):
        if context.get("has_cart_items"):
            return {"tool_name": "checkout", "parameters": {}}
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Seu carrinho está vazio. Adicione produtos primeiro!"}
        }

    # Saudações
    if any(word in message_lower for word in ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"]):
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Olá! Bem-vindo ao Comercial Esperança. Como posso ajudar?"}
        }

    # Busca de produtos
    if any(word in message_lower for word in ["quero", "buscar", "procurar", "preciso"]):
        product_name = re.sub(r"\b(quero|buscar|procurar|preciso)\b", "", message_lower).strip()
        if product_name:
            return {
                "tool_name": "get_top_selling_products_by_name",
                "parameters": {"product_name": product_name}
            }

    # Produtos populares
    if any(word in message_lower for word in ["produtos", "mais vendidos", "populares"]):
        return {"tool_name": "get_top_selling_products", "parameters": {}}

    # Mais produtos
    if message_lower in ["mais", "próximo", "proximo", "outros"]:
        return {"tool_name": "show_more_products", "parameters": {}}

    # Novo pedido
    if any(word in message_lower for word in ["novo", "nova", "recomeçar"]):
        return {"tool_name": "start_new_order", "parameters": {}}

    # Fallback baseado no estágio
    default_text = "Como posso ajudar você hoje?"
    
    if stage == "cart":
        default_text = "Você pode finalizar o pedido ou continuar comprando."
    elif stage == "checkout":
        default_text = "Digite 'finalizar' para concluir ou informe seu CNPJ."
    elif stage == "search":
        default_text = "Digite o nome de um produto ou 'produtos' para ver os mais vendidos."
    
    return {
        "tool_name": "handle_chitchat",
        "parameters": {"response_text": default_text},
    }


def validate_intent_parameters(tool_name: str, parameters: Dict) -> Dict:
    """Valida e corrige parâmetros da intenção."""
    if tool_name == "add_item_to_cart":
        if "codprod" in parameters:
            try:
                parameters["codprod"] = int(parameters["codprod"])
            except (ValueError, TypeError):
                parameters["codprod"] = 0

        if "qt" in parameters:
            try:
                qt = float(parameters["qt"])
                if qt <= 0:
                    qt = 1
                parameters["qt"] = qt
            except (ValueError, TypeError):
                parameters["qt"] = 1

    elif tool_name == "get_top_selling_products_by_name":
        if "product_name" not in parameters or not parameters["product_name"]:
            parameters["product_name"] = "produto"
        parameters["product_name"] = str(parameters["product_name"])[:100]

    elif tool_name == "update_cart_item":
        valid_actions = ["remove", "update_quantity", "add_quantity"]
        if "action" not in parameters or parameters["action"] not in valid_actions:
            parameters["action"] = "remove"
    
    elif tool_name == "find_customer_by_cnpj":
        cnpj = parameters.get("cnpj", "")
        clean_cnpj = re.sub(r'\D', '', cnpj)
        parameters["cnpj"] = clean_cnpj

    return parameters


def get_enhanced_intent(
    user_message: str, session_data: Dict, customer_context: Union[Dict, None] = None
) -> Dict:
    """Versão melhorada da função get_intent com validação adicional."""
    intent = get_intent(
        user_message,
        session_data,
        customer_context,
        len(session_data.get("shopping_cart", []))
    )

    if not intent:
        return create_fallback_intent(
            user_message, enhance_context_awareness(user_message, session_data)
        )

    tool_name = intent.get("tool_name", "handle_chitchat")
    parameters = intent.get("parameters", {})

    validated_parameters = validate_intent_parameters(tool_name, parameters)

    return {"tool_name": tool_name, "parameters": validated_parameters}


def get_intent_fast(user_message: str, session_data: Dict) -> Dict:
    """Versão rápida de detecção de intenção sem usar IA."""
    context = enhance_context_awareness(user_message, session_data)
    return create_fallback_intent(user_message, context)