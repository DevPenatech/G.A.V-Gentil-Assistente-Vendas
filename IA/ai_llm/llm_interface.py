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

from utils.command_detector import analyze_critical_command, is_valid_cnpj
from utils.limited_cache import LimitedCache

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
_prompt_cache = LimitedCache(max_size=10, ttl_seconds=300)  # 5 minutos TTL

def load_prompt_template() -> str:
    """🔧 CORREÇÃO: Cache melhorado com invalidação automática"""
    # Verifica cache primeiro
    cached_prompt = _prompt_cache.get("prompt_template")
    if cached_prompt:
        return cached_prompt

    prompt_path = os.path.join("ai_llm", "gav_prompt.txt")

    try:
        logging.info(f"[llm_interface.py] Carregando prompt de: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            
            # Armazena no cache melhorado
            _prompt_cache.set("prompt_template", content)
            
            logging.info(f"[llm_interface.py] Prompt carregado e cacheado. Tamanho: {len(content)} caracteres")
            return content
    except FileNotFoundError:
        logging.warning(f"[llm_interface.py] Arquivo '{prompt_path}' não encontrado. Usando prompt de fallback.")
        fallback = get_fallback_prompt()
        _prompt_cache.set("prompt_template", fallback)
        return fallback


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
    """Extrai seleção numérica (1, 2 ou 3) da mensagem do usuário."""
    # Busca números 1, 2 ou 3 isolados na mensagem
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
    """🔧 CORREÇÃO: Versão simplificada usando funções centralizadas"""
    
    # Usa detecção centralizada
    command_type, command_params = analyze_critical_command(user_message, session_data)
    
    context = {
        "has_cart_items": len(session_data.get("shopping_cart", [])) > 0,
        "cart_count": len(session_data.get("shopping_cart", [])),
        "has_pending_products": len(session_data.get("last_shown_products", [])) > 0,
        "last_action": session_data.get("last_bot_action", ""),
        "customer_identified": bool(session_data.get("customer_context")),
        "recent_search": session_data.get("last_kb_search_term"),
        "conversation_history": session_data.get("conversation_history", []),
        
        # 🔧 Usa detecção centralizada
        "detected_command": command_type,
        "command_parameters": command_params,
        "is_critical_command": command_type != 'unknown'
    }

    # Análise simples de contexto conversacional
    context["conversation_context"] = analyze_conversation_context(
        context["conversation_history"], user_message
    )

    # Determina estágio da compra
    if command_type == 'checkout' or context.get("customer_identified"):
        purchase_stage = "checkout"
    elif command_type == 'view_cart' or context["has_cart_items"]:
        purchase_stage = "cart"
    elif command_type in ['get_top_selling_products', 'get_top_selling_products_by_name']:
        purchase_stage = "search"
    else:
        purchase_stage = "greeting"

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
    """🔧 CORREÇÃO: Versão robusta com fallback melhorado"""
    try:
        logging.info(f"[llm_interface.py] Iniciando get_intent para mensagem: '{user_message}'")

        # 🔧 DETECÇÃO CENTRALIZADA PRIMEIRO
        enhanced_context = enhance_context_awareness(user_message, session_data)
        
        # Se comando crítico foi detectado, retorna imediatamente
        if enhanced_context.get("is_critical_command"):
            command_type = enhanced_context["detected_command"]
            command_params = enhanced_context["command_parameters"]
            
            logging.info(f"[llm_interface.py] Comando crítico detectado: {command_type}")
            return {"tool_name": command_type, "parameters": command_params}

        # Para mensagens simples, usa detecção rápida sem IA
        if _is_simple_message(user_message):
            logging.info("[llm_interface.py] Mensagem simples detectada, usando fallback rápido")
            return _create_simple_fallback(user_message, enhanced_context)

        # Se não for habilitado uso de IA, usa fallback
        if not USE_AI_FALLBACK:
            return _create_simple_fallback(user_message, enhanced_context)

        # 🔧 CONSULTA IA com timeout e fallback robusto
        try:
            logging.info("[llm_interface.py] Consultando IA...")
            
            # Prepara contexto para IA
            ai_context = _prepare_ai_context(user_message, session_data, enhanced_context)
            
            # Configura cliente Ollama
            client = ollama.Client(host=OLLAMA_HOST)
            
            # Carrega prompt template
            system_prompt = load_prompt_template()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ai_context},
            ]

            # Faz chamada com timeout
            start_time = time.time()
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
            logging.info(f"[llm_interface.py] Resposta da IA em {elapsed_time:.2f}s")

            # Processa resposta da IA
            content = response.get("message", {}).get("content", "")
            logging.info(f"[llm_interface.py] Resposta da IA: {content[:100]}...")

            # 🔧 PARSE ROBUSTO DO JSON
            intent_data = _parse_ai_response(content)
            
            if intent_data and intent_data.get("tool_name"):
                # Valida ferramenta
                tool_name = intent_data.get("tool_name", "handle_chitchat")
                if tool_name in AVAILABLE_TOOLS:
                    # Valida parâmetros
                    parameters = validate_intent_parameters(
                        tool_name, intent_data.get("parameters", {})
                    )
                    intent_data["parameters"] = parameters
                    
                    logging.info(f"[llm_interface.py] IA retornou intent válido: {intent_data}")
                    return intent_data
                else:
                    logging.warning(f"[llm_interface.py] IA retornou ferramenta inválida: {tool_name}")

        except Exception as e:
            logging.warning(f"[llm_interface.py] Erro na consulta IA: {e}")

        # 🔧 FALLBACK ROBUSTO se IA falhou
        logging.info("[llm_interface.py] Usando fallback por falha da IA")
        return _create_simple_fallback(user_message, enhanced_context)

    except Exception as e:
        logging.error(f"[llm_interface.py] Erro geral: {e}", exc_info=True)
        # Fallback de emergência
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Desculpe, tive um problema. Pode tentar novamente?"}
        }


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

def create_simple_fallback_intent(user_message: str, session_data: Dict) -> Dict:
    """
    🔧 CORREÇÃO: Fallback simplificado quando IA falha
    Substitui create_fallback_intent que era muito complexa
    """
    if not user_message:
        return {"tool_name": "handle_chitchat", "parameters": {"response_text": "Como posso ajudar?"}}
    
    # Usa detecção centralizada de comandos críticos
    command_type, parameters = analyze_critical_command(user_message, session_data)
    
    if command_type != 'unknown':
        return {"tool_name": command_type, "parameters": parameters}
    
    # Fallback final baseado no contexto da sessão
    cart_items = len(session_data.get("shopping_cart", []))
    
    if cart_items > 0:
        response_text = "Não entendi. Digite o nome de um produto, 'carrinho' para ver seus itens ou 'finalizar' para checkout."
    else:
        response_text = "Não entendi. Digite o nome de um produto ou 'produtos' para ver os mais vendidos."
    
    return {
        "tool_name": "handle_chitchat",
        "parameters": {"response_text": response_text}
    }


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
            response_text = "Como posso ajudar? Digite o nome de um produto para buscar, 'carrinho' para ver suas compras, ou 'produtos' para ver os mais vendidos."
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