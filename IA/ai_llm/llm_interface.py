# file: IA/ai_llm/llm_interface.py
"""
Interface LLM - Comunicação com Modelo de Linguagem
Otimizado para respostas rápidas e fallback inteligente
VERSÃO CORRIGIDA: Melhora detecção de CNPJ e comandos de carrinho
"""

import os
import ollama
import json
import logging
import re
from typing import Union, Dict, List
import time


from core.session_manager import get_conversation_context
from utils.quantity_extractor import detect_quantity_modifiers

# --- Configurações Globais ---
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
USE_AI_FALLBACK = os.getenv("USE_AI_FALLBACK", "true").lower() == "true"
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "5"))  # Timeout em segundos

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
    "clear_cart",  # 🆕 ADICIONADO
]

# Cache do prompt para evitar leitura repetida do arquivo
_prompt_cache = None
_prompt_cache_time = 0


def is_valid_cnpj(cnpj: str) -> bool:
    """
    🆕 NOVA FUNÇÃO: Valida se uma string é um CNPJ válido.
    """
    # Remove caracteres não numéricos
    cnpj_digits = re.sub(r'\D', '', cnpj)
    
    # Verifica se tem 14 dígitos
    if len(cnpj_digits) != 14:
        return False
    
    # Verifica se não são todos iguais (ex: 11111111111111)
    if cnpj_digits == cnpj_digits[0] * 14:
        return False
    
    # Validação básica (formato correto)
    try:
        # Verifica primeiro dígito verificador
        sequence = [int(cnpj_digits[i]) for i in range(12)]
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum1 = sum(sequence[i] * weights1[i] for i in range(12))
        digit1 = ((sum1 % 11) < 2) and 0 or (11 - (sum1 % 11))
        
        if digit1 != int(cnpj_digits[12]):
            return False
        
        # Verifica segundo dígito verificador
        sequence.append(digit1)
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum2 = sum(sequence[i] * weights2[i] for i in range(13))
        digit2 = ((sum2 % 11) < 2) and 0 or (11 - (sum2 % 11))
        
        return digit2 == int(cnpj_digits[13])
        
    except (ValueError, IndexError):
        return False


def detect_cart_clearing_intent(message: str) -> bool:
    """
    🆕 NOVA FUNÇÃO: Detecta intenção de limpar/esvaziar carrinho.
    """
    message_lower = message.lower().strip()
    
    # Comandos explícitos de limpeza de carrinho
    clear_commands = [
        # Comandos diretos
        'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
        'resetar carrinho', 'apagar carrinho', 'deletar carrinho',
        
        # Variações com "tudo"
        'esvaziar tudo', 'limpar tudo', 'zerar tudo', 
        'apagar tudo', 'deletar tudo', 'remover tudo',
        
        # Comandos de reinício
        'começar de novo', 'recomeçar', 'reiniciar',
        'do zero', 'novo pedido', 'nova compra',
        
        # Comandos informais
        'limpa', 'esvazia', 'zera', 'apaga'
    ]
    
    # Verifica comandos exatos
    for command in clear_commands:
        if command in message_lower:
            return True
    
    # Padrões mais flexíveis
    clear_patterns = [
        r'\b(limpar|esvaziar|zerar|apagar|deletar|remover)\s+(o\s+)?carrinho\b',
        r'\b(carrinho|tudo)\s+(limpo|vazio|zerado)\b',
        r'\bcomeca\w*\s+de\s+novo\b',
        r'\bdo\s+zero\b',
        r'\breinicia\w*\s+(carrinho|tudo|compra)\b'
    ]
    
    for pattern in clear_patterns:
        if re.search(pattern, message_lower):
            return True
    
    return False


def detect_checkout_context(session_data: Dict) -> Dict:
    """
    🆕 NOVA FUNÇÃO: Detecta se estamos em contexto de finalização/checkout.
    """
    context = {
        'awaiting_cnpj': False,
        'last_request_was_cnpj': False,
        'checkout_initiated': False
    }
    
    # Verifica histórico recente
    history = session_data.get('conversation_history', [])
    
    if not history:
        return context
    
    # Analisa últimas 3 mensagens do bot
    recent_bot_messages = []
    for msg in reversed(history):
        if msg.get('role') == 'assistant':
            recent_bot_messages.append(msg.get('message', '').lower())
            if len(recent_bot_messages) >= 3:
                break
    
    # Verifica se a última mensagem do bot pediu CNPJ
    if recent_bot_messages:
        last_bot_msg = recent_bot_messages[0]
        
        cnpj_request_patterns = [
            'cnpj', 'finalizar', 'checkout', 'compra',
            'identificar', 'cadastro', 'cliente'
        ]
        
        if any(pattern in last_bot_msg for pattern in cnpj_request_patterns):
            context['awaiting_cnpj'] = True
            context['last_request_was_cnpj'] = True
    
    # Verifica se checkout foi iniciado recentemente
    for msg in recent_bot_messages:
        if any(word in msg for word in ['finalizar', 'checkout', 'cnpj']):
            context['checkout_initiated'] = True
            break
    
    return context


def load_prompt_template() -> str:
    """Carrega o prompt do arquivo de texto 'gav_prompt.txt' com cache."""
    global _prompt_cache, _prompt_cache_time

    # Usa cache se foi carregado há menos de 5 minutos
    if _prompt_cache and (time.time() - _prompt_cache_time) < 300:
        return _prompt_cache

    prompt_path = os.path.join("ai_llm", "gav_prompt.txt")

    try:
        logging.info(f"[llm_interface.py] Carregando prompt de: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            _prompt_cache = content
            _prompt_cache_time = time.time()
            logging.info(
                f"[llm_interface.py] Prompt carregado e cacheado. Tamanho: {len(content)} caracteres"
            )
            return content
    except FileNotFoundError:
        logging.warning(
            f"[llm_interface.py] Arquivo '{prompt_path}' não encontrado. Usando prompt de fallback."
        )
        return get_fallback_prompt()


def get_fallback_prompt() -> str:
    """Prompt de emergência caso o arquivo não seja encontrado."""
    return """Você é G.A.V., o Gentil Assistente de Vendas do Comercial Esperança. Seu tom é PROFISSIONAL, DIRETO e OBJETIVO. 

ESTILO: Respostas curtas com próxima ação explícita. Liste até 3 opções por vez; peça escolha por número ("1, 2 ou 3").

FERRAMENTAS: get_top_selling_products, get_top_selling_products_by_name, add_item_to_cart, view_cart, update_cart_item, checkout, handle_chitchat, ask_continue_or_checkout, clear_cart

COMANDOS ESPECIAIS:
- "esvaziar carrinho", "limpar carrinho" → use clear_cart
- CNPJ (14 dígitos) quando solicitado → use find_customer_by_cnpj

SEMPRE RESPONDA EM JSON VÁLIDO COM tool_name E parameters!"""


def extract_numeric_selection(message: str) -> Union[int, None]:
    """Extrai seleção numérica (1 a 10) da mensagem do usuário."""
    # Busca números de 1 a 10 isolados na mensagem
    numbers = re.findall(r"\b([1-9]|10)\b", message.strip())
    if numbers:
        try:
            num = int(numbers[0])
            if 1 <= num <= 10:  # Validação adicional
                return num
        except ValueError:
            pass
    return None


def detect_quantity_keywords(message: str) -> Union[float, None]:
    """Detecta palavras-chave de quantidade na mensagem."""
    message_lower = message.lower().strip()

    # Mapeamento de palavras para quantidades
    quantity_map = {
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "três": 3,
        "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
        "meia dúzia": 6,
        "meia duzia": 6,
        "uma dúzia": 12,
        "uma duzia": 12,
        "dúzia": 12,
        "duzia": 12,
    }

    for word, quantity in quantity_map.items():
        if word in message_lower:
            return float(quantity)

    # Busca números decimais
    decimal_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", message)
    if decimal_match:
        number_str = decimal_match.group(1).replace(",", ".")
        try:
            return float(number_str)
        except ValueError:
            pass

    return None


def enhance_context_awareness(user_message: str, session_data: Dict) -> Dict:
    """
    🆕 VERSÃO MELHORADA: Melhora a consciência contextual analisando estado da sessão.
    """
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

    # 🆕 DETECTA COMANDOS DE LIMPEZA DE CARRINHO
    context["clear_cart_command"] = detect_cart_clearing_intent(user_message)
    
    # 🆕 DETECTA CONTEXTO DE CHECKOUT/FINALIZAÇÃO
    checkout_context = detect_checkout_context(session_data)
    context.update(checkout_context)
    
    # 🆕 DETECTA SE É UM CNPJ VÁLIDO
    context["is_valid_cnpj"] = is_valid_cnpj(user_message)
    context["is_cnpj_in_checkout_context"] = (
        context["is_valid_cnpj"] and 
        (context["awaiting_cnpj"] or context["checkout_initiated"])
    )

    # Detecta padrões específicos
    message_lower = user_message.lower().strip()

    # Comandos diretos de carrinho
    if any(cmd in message_lower for cmd in ["carrinho", "ver carrinho"]):
        context["direct_cart_command"] = True

    # Comandos de finalização
    if any(cmd in message_lower for cmd in ["finalizar", "fechar", "checkout"]):
        context["direct_checkout_command"] = True

    # Comandos de continuar compra
    if any(cmd in message_lower for cmd in ["continuar", "mais produtos", "outros"]):
        context["continue_shopping"] = True
        
    context["conversation_context"] = analyze_conversation_context(
        context["conversation_history"], user_message
    )

    # Detecta gírias de produtos
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

    # Determina estágio da compra
    purchase_stage = session_data.get("purchase_stage", "greeting")

    greeting_keywords = [
        "oi",
        "olá",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "e aí",
        "e ai",
    ]
    search_keywords = [
        "buscar",
        "procurar",
        "produto",
        "comprar",
        "preciso",
        "quero",
        "produtos",
        "mais vendidos",
    ]

    if context.get("direct_checkout_command") or context.get("awaiting_cnpj"):
        purchase_stage = "checkout"
    elif context.get("direct_cart_command"):
        purchase_stage = "cart"
    elif any(word in message_lower for word in greeting_keywords):
        purchase_stage = "greeting"
    elif (
        any(word in message_lower for word in search_keywords)
        or context.get("has_pending_products")
        or context.get("recent_search")
    ):
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
    
    # Analisa últimas mensagens do bot
    recent_bot_messages = []
    for msg in reversed(history[-10:]):  # Últimas 10 mensagens
        if msg.get("role") == "assistant":
            recent_bot_messages.append(msg.get("message", "").lower())
            if len(recent_bot_messages) >= 3:  # Analisa até 3 mensagens do bot
                break
    
    if recent_bot_messages:
        last_bot_msg = recent_bot_messages[0]
        
        # Bot mostrou produtos e está esperando seleção
        if any(phrase in last_bot_msg for phrase in [
            "responda 1, 2 ou 3", "escolha", "qual você quer",
            "digite o número", "selecione"
        ]):
            context_analysis["waiting_for_selection"] = True
            context_analysis["recent_products_shown"] = True
        
        # Bot perguntou se quer continuar ou finalizar
        if "continuar" in last_bot_msg and "finalizar" in last_bot_msg:
            context_analysis["continue_or_checkout_flow"] = True
        
        # Bot adicionou item ao carrinho recentemente
        if any(phrase in last_bot_msg for phrase in [
            "adicionado", "adicionei", "no carrinho"
        ]):
            context_analysis["last_bot_action_type"] = "added_to_cart"
    
    return context_analysis


def get_intent(
    user_message: str,
    session_data: Dict,
    customer_context: Union[Dict, None] = None,
    cart_items_count: int = 0,
) -> Dict:
    """
    🆕 VERSÃO CORRIGIDA: Usa o LLM para interpretar a mensagem do usuário e traduzir em uma ferramenta.
    Com fallback rápido para mensagens simples e timeout para evitar demoras.
    """
    try:
        logging.info(
            f"[llm_interface.py] Iniciando get_intent para mensagem: '{user_message}'"
        )

        # 🆕 MELHORA CONSCIÊNCIA CONTEXTUAL
        enhanced_context = enhance_context_awareness(user_message, session_data)
        
        # 🆕 PRIORIDADE MÁXIMA: CNPJ em contexto de checkout
        if enhanced_context.get("is_cnpj_in_checkout_context"):
            logging.info("[llm_interface.py] CNPJ detectado em contexto de checkout")
            return {
                "tool_name": "find_customer_by_cnpj",
                "parameters": {"cnpj": user_message.strip()}
            }
        
        # 🆕 PRIORIDADE ALTA: Comandos de limpeza de carrinho
        if enhanced_context.get("clear_cart_command"):
            logging.info("[llm_interface.py] Comando de limpeza de carrinho detectado")
            return {"tool_name": "clear_cart", "parameters": {}}

        # Para mensagens simples, usa detecção rápida sem IA
        message_lower = user_message.lower().strip()
        simple_patterns = [
            r"^\s*[123]\s*$",  # Números 1, 2 ou 3
            r"^(oi|olá|ola|e aí|e ai|boa|bom dia|boa tarde|boa noite)$",  # Saudações
            r"^(carrinho|ver carrinho)$",  # Carrinho
            r"^(finalizar|fechar)$",  # Checkout
            r"^(ajuda|help)$",  # Ajuda
            r"^(produtos|mais vendidos)$",  # Produtos populares
            r"^(mais)$",  # Mais produtos
            r"^(novo|nova)$",  # Novo pedido
        ]

        for pattern in simple_patterns:
            if re.match(pattern, message_lower):
                logging.info(
                    "[llm_interface.py] Mensagem simples detectada, usando fallback rápido"
                )
                return create_fallback_intent(user_message, enhanced_context)

        # Se não for habilitado uso de IA ou for mensagem muito curta, usa fallback
        if not USE_AI_FALLBACK or len(user_message.strip()) < 3:
            return create_fallback_intent(user_message, enhanced_context)

        # Carrega template do prompt
        system_prompt = load_prompt_template()
        logging.info(
            f"[llm_interface.py] System prompt preparado. Tamanho: {len(system_prompt)} caracteres"
        )

        # Obtém contexto EXPANDIDO da conversa (14 mensagens para melhor contexto)
        conversation_context = get_conversation_context(session_data, max_messages=14)
        print(f">>> CONSOLE: Contexto da conversa com {len(session_data.get('conversation_history', []))} mensagens totais")

        # Informações do carrinho
        cart_info = ""
        if cart_items_count > 0:
            cart_info = f"CARRINHO ATUAL: {cart_items_count} itens"
            cart_items = session_data.get("shopping_cart", [])
            if cart_items:
                cart_info += " ("
                item_names = []
                for item in cart_items[:3]:  # Mostra apenas primeiros 3
                    name = item.get("descricao") or item.get(
                        "canonical_name", "Produto"
                    )
                    qt = item.get("qt", 0)
                    item_names.append(f"{name} x{qt}")
                cart_info += ", ".join(item_names)
                if len(cart_items) > 3:
                    cart_info += f" e mais {len(cart_items) - 3}"
                cart_info += ")"

        # Produtos disponíveis para seleção
        products_info = ""
        last_shown = session_data.get("last_shown_products", [])
        if last_shown and enhanced_context.get("numeric_selection"):
            products_info = f"PRODUTOS MOSTRADOS RECENTEMENTE: {len(last_shown)} opções disponíveis para seleção numérica"

        # Informações do cliente
        customer_info = ""
        if customer_context:
            customer_info = f"CLIENTE: {customer_context.get('nome', 'Identificado')}"

        # 🆕 CONSTRÓI CONTEXTO ESPECÍFICO PARA PROBLEMAS IDENTIFICADOS
        special_context = ""
        if enhanced_context.get("clear_cart_command"):
            special_context += "⚠️ COMANDO DE LIMPEZA DE CARRINHO DETECTADO - Use clear_cart\n"
        if enhanced_context.get("is_cnpj_in_checkout_context"):
            special_context += "⚠️ CNPJ VÁLIDO EM CONTEXTO DE CHECKOUT - Use find_customer_by_cnpj\n"
        if enhanced_context.get("awaiting_cnpj"):
            special_context += "⚠️ BOT ESTÁ ESPERANDO CNPJ PARA FINALIZAR PEDIDO\n"

        # Constrói contexto completo
        full_context = f"""
MENSAGEM DO USUÁRIO: "{user_message}"

{special_context}

CONTEXTO DA CONVERSA (ESSENCIAL PARA ENTENDER A SITUAÇÃO ATUAL):
{conversation_context}

⚠️ IMPORTANTE: Analise TODO o histórico acima para entender:
- O que o cliente já pediu ou buscou
- Onde a conversa parou
- Se há ações pendentes
- O contexto da mensagem atual

ESTADO ATUAL DA SESSÃO:
- Carrinho: {enhanced_context.get('cart_count', 0)} itens
- Produtos mostrados: {'Sim' if enhanced_context.get('has_pending_products') else 'Não'}
- Última ação do bot: {enhanced_context.get('last_action', 'Nenhuma')}
- Cliente identificado: {'Sim' if enhanced_context.get('customer_identified') else 'Não'}
- Esperando CNPJ: {'Sim' if enhanced_context.get('awaiting_cnpj') else 'Não'}

ANÁLISE CONTEXTUAL:
- Seleção numérica detectada: {enhanced_context.get('numeric_selection', 'Nenhuma')}
- Quantidade inferida: {enhanced_context.get('inferred_quantity', 'Não especificada')}
- É CNPJ válido: {'Sim' if enhanced_context.get('is_valid_cnpj') else 'Não'}
- CNPJ em contexto checkout: {'Sim' if enhanced_context.get('is_cnpj_in_checkout_context') else 'Não'}
- Comando limpar carrinho: {'Sim' if enhanced_context.get('clear_cart_command') else 'Não'}

COMANDOS DETECTADOS:
- Ver carrinho: {'Sim' if enhanced_context.get('direct_cart_command') else 'Não'}
- Finalizar: {'Sim' if enhanced_context.get('direct_checkout_command') else 'Não'}
- Continuar: {'Sim' if enhanced_context.get('continue_shopping') else 'Não'}

INSTRUÇÕES ESPECIAIS DE ALTA PRIORIDADE:
1. ⚠️ Se "Comando limpar carrinho: Sim", SEMPRE use clear_cart
2. ⚠️ Se "CNPJ em contexto checkout: Sim", SEMPRE use find_customer_by_cnpj
3. ⚠️ Se "Esperando CNPJ: Sim" e mensagem parece CNPJ, use find_customer_by_cnpj
4. Se há produtos mostrados e usuário digitou número, use add_item_to_cart
5. Considere TODO o histórico da conversa para interpretar a intenção
"""

        # Prepara mensagens para o modelo
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_context},
        ]

        # Configura cliente Ollama
        client = ollama.Client(host=OLLAMA_HOST)

        logging.info(f"[llm_interface.py] Configurando Ollama Host: '{OLLAMA_HOST}'")

        # Tenta chamar o modelo com timeout
        start_time = time.time()
        try:
            # Faz chamada ao modelo
            response = client.chat(
                model=OLLAMA_MODEL_NAME,
                messages=messages,
                options={
                    "temperature": 0.1,  # 🆕 MAIS DETERMINÍSTICO para melhor detecção
                    "top_p": 0.9,
                    "num_predict": 150,  # Limita tamanho da resposta
                    "stop": ["\n\n", "```"],  # Para em quebras duplas ou markdown
                },
                stream=False,
            )

            elapsed_time = time.time() - start_time
            logging.info(
                f"[llm_interface.py] Resposta recebida do LLM em {elapsed_time:.2f}s"
            )

            # Se demorou muito, considera usar fallback na próxima
            if elapsed_time > AI_TIMEOUT:
                logging.warning(
                    f"[llm_interface.py] LLM demorou {elapsed_time:.2f}s (timeout: {AI_TIMEOUT}s)"
                )

            # Extrai e processa resposta
            content = response.get("message", {}).get("content", "")
            logging.info(f"[llm_interface.py] Resposta do LLM: {content[:100]}...")

            cleaned_content = clean_json_response(content)
            logging.debug(f"[llm_interface.py] Conteúdo limpo: {cleaned_content}")

            # Parse do JSON
            intent_data = json.loads(cleaned_content)
            tool_name = intent_data.get("tool_name", "handle_chitchat")

            # Valida se a ferramenta existe
            if tool_name not in AVAILABLE_TOOLS:
                logging.warning(f"[llm_interface.py] Ferramenta inválida: {tool_name}")
                intent_data = {
                    "tool_name": "handle_chitchat",
                    "parameters": {
                        "response_text": "Tive um problema na consulta agora. Tentar novamente?"
                    },
                }

            # Enriquece parâmetros com contexto adicional
            parameters = intent_data.get("parameters", {})

            # Se é seleção numérica e temos produtos, adiciona quantidade se detectada
            if (
                tool_name == "add_item_to_cart"
                and enhanced_context.get("numeric_selection")
                and enhanced_context.get("inferred_quantity")
            ):

                if "qt" not in parameters:
                    parameters["qt"] = enhanced_context["inferred_quantity"]

            intent_data["parameters"] = validate_intent_parameters(
                tool_name, parameters
            )

            logging.info(f"[llm_interface.py] JSON parseado com sucesso: {intent_data}")
            return intent_data

        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"[llm_interface.py] Erro ao parsear JSON: {e}")
            # Fallback baseado em padrões simples
            return create_fallback_intent(user_message, enhanced_context)

        except TimeoutError:
            logging.warning(
                f"[llm_interface.py] Timeout ao chamar LLM após {AI_TIMEOUT}s"
            )
            return create_fallback_intent(user_message, enhanced_context)

    except Exception as e:
        logging.error(f"[llm_interface.py] Erro geral: {e}", exc_info=True)
        # Usa fallback em caso de erro
        return create_fallback_intent(
            user_message, enhance_context_awareness(user_message, session_data)
        )


def clean_json_response(content: str) -> str:
    """Limpa a resposta do LLM para extrair JSON válido."""
    # Remove markdown se presente
    content = re.sub(r"```json\s*", "", content)
    content = re.sub(r"```\s*", "", content)

    # Remove texto antes e depois do JSON
    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    if json_match:
        return json_match.group(0).strip()

    return content.strip()


def create_fallback_intent(user_message: str, context: Dict) -> Dict:
    """
    🆕 VERSÃO CORRIGIDA: Cria intenção de fallback baseada em padrões simples quando LLM falha ou demora.
    """
    message_lower = user_message.lower().strip()
    stage = context.get("purchase_stage", "greeting")

    # 🆕 PRIORIDADE MÁXIMA: CNPJ em contexto de checkout
    if context.get("is_cnpj_in_checkout_context"):
        return {
            "tool_name": "find_customer_by_cnpj",
            "parameters": {"cnpj": user_message.strip()}
        }

    # 🆕 PRIORIDADE ALTA: Comandos de limpeza de carrinho
    if context.get("clear_cart_command"):
        return {"tool_name": "clear_cart", "parameters": {}}

    modifiers = detect_quantity_modifiers(message_lower)
    if modifiers.get("action") == "remove":
        if context.get("has_cart_items"):
            return {"tool_name": "update_cart_item", "parameters": {"action": "remove"}}
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Seu carrinho está vazio."},
        }

    modifiers = detect_quantity_modifiers(message_lower)
    if modifiers.get("action") == "clear":
        return {"tool_name": "clear_cart", "parameters": {}}

    # Seleção numérica direta
    if context.get("numeric_selection") and context.get("has_pending_products"):
        # Assume que o usuário quer adicionar o produto selecionado
        return {
            "tool_name": "add_item_to_cart",
            "parameters": {
                "index": context.get("numeric_selection"),  # 🆕 CORRIGIDO
                "qt": context.get("inferred_quantity", 1),
            },
        }

    # Comandos de carrinho
    if context.get("direct_cart_command"):
        return {"tool_name": "view_cart", "parameters": {}}

    # Comandos de checkout
    if context.get("direct_checkout_command"):
        return {"tool_name": "checkout", "parameters": {}}

    # Continuar comprando
    if context.get("continue_shopping"):
        return {"tool_name": "get_top_selling_products", "parameters": {}}

    # Busca de produtos (detecta palavras-chave)
    product_keywords = ["quero", "buscar", "procurar", "produto", "comprar", "preciso"]
    if any(keyword in message_lower for keyword in product_keywords):
        # Extrai nome do produto (remove palavras de comando)
        product_name = message_lower
        for keyword in product_keywords:
            product_name = product_name.replace(keyword, "").strip()

        if product_name and not context.get("is_valid_cnpj"):  # 🆕 EVITA BUSCAR CNPJ COMO PRODUTO
            return {
                "tool_name": "get_top_selling_products_by_name",
                "parameters": {"product_name": product_name},
            }

    # Comandos de produtos populares
    if any(
        word in message_lower
        for word in ["produtos", "mais vendidos", "populares", "top"]
    ):
        return {"tool_name": "get_top_selling_products", "parameters": {}}

    # Saudações
    greetings = [
        "oi",
        "olá",
        "ola",
        "boa",
        "bom dia",
        "boa tarde",
        "boa noite",
        "e aí",
        "e ai",
    ]
    if any(greeting in message_lower for greeting in greetings):
        if stage == "cart":
            response_text = "Olá! Você tem itens no carrinho. Digite 'checkout' para finalizar ou informe outro produto."
        elif stage == "checkout":
            response_text = "Olá! Para concluir a compra digite 'finalizar' ou 'carrinho' para revisar seus itens."
        else:
            response_text = "Olá! Sou o G.A.V. do Comercial Esperança. Posso mostrar nossos produtos mais vendidos ou você já sabe o que procura?"
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": response_text},
        }

    # Ajuda
    if any(word in message_lower for word in ["ajuda", "help", "como", "funciona"]):
        if stage == "cart":
            response_text = "Você pode digitar 'checkout' para finalizar ou informar outro produto para continuar comprando."
        elif stage == "checkout":
            response_text = "Para concluir digite 'finalizar'. Se quiser revisar os itens, digite 'carrinho'."
        else:
            response_text = "Como posso te ajudar? Digite o nome de um produto que você quer buscar, 'carrinho' para ver suas compras, ou 'produtos' para ver os mais vendidos."
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": response_text},
        }

    # Novo pedido
    if "novo" in message_lower or "nova" in message_lower:
        return {"tool_name": "start_new_order", "parameters": {}}

    # Comando "mais" para ver mais produtos
    if (
        "mais" in message_lower
        and context.get("last_action") == "AWAITING_PRODUCT_SELECTION"
    ):
        return {"tool_name": "show_more_products", "parameters": {}}

    # Fallback padrão - tenta buscar o termo completo (EXCETO se for CNPJ)
    if len(message_lower) > 2 and not context.get("is_valid_cnpj"):
        return {
            "tool_name": "get_top_selling_products_by_name",
            "parameters": {"product_name": message_lower},
        }

    # 🆕 SE FOR CNPJ MAS NÃO ESTAMOS EM CONTEXTO DE CHECKOUT
    if context.get("is_valid_cnpj") and not context.get("checkout_initiated"):
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Identifico que você digitou um CNPJ. Para usá-lo, primeiro adicione itens ao carrinho e depois digite 'finalizar pedido'."},
        }

    # Mensagens padrão baseadas no estágio
    if stage == "cart":
        default_text = "Não entendi. Você pode digitar o nome de um produto para adicionar mais itens ou 'checkout' para finalizar."
    elif stage == "checkout":
        default_text = "Não entendi. Digite 'finalizar' para concluir a compra ou 'carrinho' para revisar."
    elif stage == "search":
        default_text = "Não entendi. Digite o nome de um produto para buscar ou 'carrinho' para ver seus itens."
    else:
        default_text = "Não entendi. Posso mostrar os produtos mais vendidos ou buscar algo específico."
    return {
        "tool_name": "handle_chitchat",
        "parameters": {"response_text": default_text},
    }


def validate_intent_parameters(tool_name: str, parameters: Dict) -> Dict:
    """Valida e corrige parâmetros da intenção conforme a ferramenta."""

    if tool_name == "add_item_to_cart":
        # Garante que codprod seja inteiro e qt seja número válido
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
        # Garante que product_name seja string não vazia
        if "product_name" not in parameters or not parameters["product_name"]:
            parameters["product_name"] = "produto"

        # Limita tamanho do nome do produto
        parameters["product_name"] = str(parameters["product_name"])[:100]

    elif tool_name == "update_cart_item":
        # Valida ação e parâmetros relacionados
        valid_actions = ["remove", "update_quantity", "add_quantity"]
        if "action" not in parameters or parameters["action"] not in valid_actions:
            parameters["action"] = "remove"
    
    elif tool_name == "find_customer_by_cnpj":
        # 🆕 VALIDA CNPJ
        cnpj = parameters.get("cnpj", "")
        # Remove caracteres especiais do CNPJ
        clean_cnpj = re.sub(r'\D', '', cnpj)
        parameters["cnpj"] = clean_cnpj

    return parameters


def get_enhanced_intent(
    user_message: str, session_data: Dict, customer_context: Union[Dict, None] = None
) -> Dict:
    """Versão melhorada da função get_intent com validação adicional."""

    # Obtém intenção básica
    intent = get_intent(
        user_message,
        session_data,
        customer_context,
        len(session_data.get("shopping_cart", [])),
    )

    if not intent:
        return create_fallback_intent(
            user_message, enhance_context_awareness(user_message, session_data)
        )

    # Valida e corrige parâmetros
    tool_name = intent.get("tool_name", "handle_chitchat")
    parameters = intent.get("parameters", {})

    validated_parameters = validate_intent_parameters(tool_name, parameters)

    return {"tool_name": tool_name, "parameters": validated_parameters}


def get_intent_fast(user_message: str, session_data: Dict) -> Dict:
    """Versão rápida de detecção de intenção sem usar IA."""
    # Melhora consciência contextual
    context = enhance_context_awareness(user_message, session_data)

    # Retorna intenção baseada em padrões
    return create_fallback_intent(user_message, context)


def generate_personalized_response(context_type: str, session_data: Dict, **kwargs) -> str:
    """
    Gera respostas personalizadas e dinâmicas usando a IA para situações específicas.
    
    Args:
        context_type: Tipo de contexto (error, greeting, clarification, etc.)
        session_data: Dados da sessão para contexto
        **kwargs: Parâmetros específicos do contexto
    """
    try:
        # Constrói o contexto baseado no tipo
        conversation_history = session_data.get("conversation_history", [])
        cart_items = len(session_data.get("shopping_cart", []))
        
        # Prompt específico para geração de resposta - sempre direcionado a UMA pessoa
        contexts = {
            "error": "Algo deu errado com o que o usuário tentou fazer. Responda diretamente a ELE de forma amigável, explicando que houve um problema e pedindo para tentar novamente. Use 'você' e seja pessoal.",
            "greeting": "Cumprimente o usuário de forma calorosa, se apresentando como G.A.V. e perguntando diretamente como pode ajudar ELE especificamente. Seja acolhedor e pessoal.",
            "clarification": "O usuário disse algo que você não entendeu. Peça esclarecimento diretamente a ELE de forma amigável, usando 'você' e tratamento pessoal.",
            "invalid_quantity": "O usuário informou uma quantidade inválida. Explique diretamente a ELE como informar a quantidade corretamente, de forma didática mas amigável.",
            "invalid_selection": f"O usuário escolheu um número inválido ({kwargs.get('invalid_number', 'X')}). Explique diretamente a ELE que deve escolher entre 1 e {kwargs.get('max_options', 'N')}, sendo amigável e pessoal.",
            "empty_cart": "O carrinho do usuário está vazio. Sugira diretamente a ELE ver produtos, sendo animado e natural. Use 'seu carrinho' e fale diretamente com ele.",
            "cnpj_request": "Peça diretamente ao usuário o CNPJ dele para finalizar a compra. Seja profissional mas amigável, explicando que precisa dessa informação.",
            "operation_success": f"A operação que o usuário fez deu certo! Comemore diretamente com ELE de forma natural: {kwargs.get('success_details', '')}. Seja caloroso e pessoal.",
        }
        
        context_prompt = contexts.get(context_type, "Responda de forma natural e amigável.")
        
        prompt = f"""Você é G.A.V., assistente de vendas carismático e natural falando com UMA pessoa via WhatsApp.

CONTEXTO: {context_prompt}

HISTÓRICO DA CONVERSA: {conversation_history[-3:] if conversation_history else 'Primeira interação'}

CARRINHO: {cart_items} itens

INSTRUÇÕES CRÍTICAS:
- Seja NATURAL, HUMANO e BRASILEIRO 
- SEMPRE fale com UMA pessoa: use "você", "seu", "sua" (NUNCA "vocês", "pessoal")
- WhatsApp é conversa 1-para-1, trate como amigo atendente
- Use expressões como "Opa!", "Tranquilo!", "Perfeito!", "Que tal?"
- VARIE as respostas - nunca seja repetitivo
- Mantenha tom caloroso e prestativo
- Resposta CURTA (máximo 2 frases)
- Exemplos: "Como posso te ajudar?" (✅) vs "Como posso ajudar vocês?" (❌)

Responda APENAS o texto da mensagem, sem explicações extras:"""

        # Faz a chamada para a IA
        response = ollama.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.8, "num_predict": 100}  # Mais criatividade, resposta curta
        )
        
        generated_text = response["message"]["content"].strip()
        
        # Remove aspas ou formatação extra se houver
        generated_text = generated_text.strip('"\'')
        
        logging.info(f"[llm_interface.py] Resposta dinâmica gerada para {context_type}: {generated_text[:50]}...")
        return generated_text
        
    except Exception as e:
        logging.error(f"[llm_interface.py] Erro ao gerar resposta personalizada: {e}")
        
        # Fallbacks individuais por contexto
        fallbacks = {
            "error": "Opa, algo deu errado aqui! Que tal você tentar de novo?",
            "greeting": "Oi! Sou o G.A.V. e estou aqui pra te ajudar! 😊 Como posso te atender?",
            "clarification": "Não consegui entender direito o que você quis dizer. Pode me explicar de novo?",
            "invalid_quantity": "Não entendi a quantidade que você quer. Pode me falar o número?",
            "invalid_selection": f"Esse número não tá na lista que te mostrei. Escolhe entre 1 e {kwargs.get('max_options', 'os números mostrados')}!",
            "empty_cart": "Seu carrinho tá vazio ainda! Que tal você dar uma olhada nos nossos produtos?",
            "cnpj_request": "Pra finalizar sua compra, vou precisar do seu CNPJ. Pode me passar?",
            "operation_success": "Pronto! Deu tudo certo pra você!",
        }
        return fallbacks.get(context_type, "Ops, tive um probleminha. Pode tentar de novo?")