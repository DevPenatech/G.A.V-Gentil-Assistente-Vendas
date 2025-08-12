"""
Interface LLM - Comunicação com Modelo de Linguagem
Otimizado para respostas rápidas e fallback inteligente
"""

import os
import ollama
import json
import logging
import re
from typing import Union, Dict, List
import time

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
    "ask_continue_or_checkout"
]

# Cache do prompt para evitar leitura repetida do arquivo
_prompt_cache = None
_prompt_cache_time = 0

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
            logging.info(f"[llm_interface.py] Prompt carregado e cacheado. Tamanho: {len(content)} caracteres")
            return content
    except FileNotFoundError:
        logging.warning(f"[llm_interface.py] Arquivo '{prompt_path}' não encontrado. Usando prompt de fallback.")
        return get_fallback_prompt()

def get_fallback_prompt() -> str:
    """Prompt de emergência caso o arquivo não seja encontrado."""
    return """Você é G.A.V., o Gentil Assistente de Vendas do Comercial Esperança. Seu tom é PROFISSIONAL, DIRETO e OBJETIVO. 

ESTILO: Respostas curtas com próxima ação explícita. Liste até 3 opções por vez; peça escolha por número ("1, 2 ou 3").

FERRAMENTAS: get_top_selling_products, get_top_selling_products_by_name, add_item_to_cart, view_cart, update_cart_item, checkout, handle_chitchat, ask_continue_or_checkout

SEMPRE RESPONDA EM JSON VÁLIDO COM tool_name E parameters!"""

def format_conversation_history(history: List[Dict]) -> str:
    """Formata o histórico de conversa para contexto com foco nas últimas interações."""
    if not history:
        return "Primeira interação com o cliente."
    
    # Pega apenas as últimas 6 mensagens para manter contexto relevante
    recent_history = history[-6:]
    
    formatted = "CONTEXTO RECENTE:\n"
    for msg in recent_history:
        role = "Cliente" if msg['role'] == 'user' else "G.A.V."
        # Limita mensagens longas
        message_preview = msg['message'][:100]
        if len(msg['message']) > 100:
            message_preview += "..."
        formatted += f"{role}: {message_preview}\n"
    
    return formatted

def extract_numeric_selection(message: str) -> Union[int, None]:
    """Extrai seleção numérica (1, 2 ou 3) da mensagem do usuário."""
    # Busca números 1, 2 ou 3 isolados na mensagem
    numbers = re.findall(r'\b([123])\b', message.strip())
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
        'um': 1, 'uma': 1,
        'dois': 2, 'duas': 2,
        'três': 3, 'tres': 3,
        'quatro': 4,
        'cinco': 5,
        'seis': 6,
        'sete': 7,
        'oito': 8,
        'nove': 9,
        'dez': 10,
        'meia dúzia': 6, 'meia duzia': 6,
        'uma dúzia': 12, 'uma duzia': 12,
        'dúzia': 12, 'duzia': 12
    }
    
    for word, quantity in quantity_map.items():
        if word in message_lower:
            return float(quantity)
    
    # Busca números decimais
    decimal_match = re.search(r'\b(\d+(?:[.,]\d+)?)\b', message)
    if decimal_match:
        number_str = decimal_match.group(1).replace(',', '.')
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
        "inferred_quantity": detect_quantity_keywords(user_message)
    }
    
    # Detecta padrões específicos
    message_lower = user_message.lower().strip()
    
    # Comandos diretos de carrinho
    if any(cmd in message_lower for cmd in ['carrinho', 'ver carrinho']):
        context["direct_cart_command"] = True
    
    # Comandos de finalização
    if any(cmd in message_lower for cmd in ['finalizar', 'fechar', 'checkout']):
        context["direct_checkout_command"] = True
    
    # Comandos de continuar compra
    if any(cmd in message_lower for cmd in ['continuar', 'mais produtos', 'outros']):
        context["continue_shopping"] = True
    
    # Detecta gírias de produtos
    product_slang = {
        'refri': 'refrigerante',
        'zero': 'coca zero',
        'lata': 'lata',
        '2l': '2 litros',
        'pet': 'garrafa pet'
    }
    
    for slang, meaning in product_slang.items():
        if slang in message_lower:
            context["detected_slang"] = {slang: meaning}
            break
    
    return context

def get_intent(user_message: str, session_data: Dict, customer_context: Union[Dict, None] = None, cart_items_count: int = 0) -> Dict:
    """
    Usa o LLM para interpretar a mensagem do usuário e traduzir em uma ferramenta.
    Com fallback rápido para mensagens simples e timeout para evitar demoras.
    """
    try:
        logging.info(f"[llm_interface.py] Iniciando get_intent para mensagem: '{user_message}'")
        
        # Melhora consciência contextual
        enhanced_context = enhance_context_awareness(user_message, session_data)
        
        # Para mensagens simples, usa detecção rápida sem IA
        message_lower = user_message.lower().strip()
        simple_patterns = [
            r'^\s*[123]\s*$',  # Números 1, 2 ou 3
            r'^(oi|olá|ola|e aí|e ai|boa|bom dia|boa tarde|boa noite)$',  # Saudações
            r'^(carrinho|ver carrinho)$',  # Carrinho
            r'^(finalizar|fechar)$',  # Checkout
            r'^(ajuda|help)$',  # Ajuda
            r'^(produtos|mais vendidos)$',  # Produtos populares
            r'^(mais)$',  # Mais produtos
            r'^(novo|nova)$'  # Novo pedido
        ]
        
        for pattern in simple_patterns:
            if re.match(pattern, message_lower):
                logging.info("[llm_interface.py] Mensagem simples detectada, usando fallback rápido")
                return create_fallback_intent(user_message, enhanced_context)
        
        # Se não for habilitado uso de IA ou for mensagem muito curta, usa fallback
        if not USE_AI_FALLBACK or len(user_message.strip()) < 3:
            return create_fallback_intent(user_message, enhanced_context)
        
        # Carrega template do prompt
        system_prompt = load_prompt_template()
        logging.info(f"[llm_interface.py] System prompt preparado. Tamanho: {len(system_prompt)} caracteres")
        
        # Formata histórico de conversa
        conversation_history = format_conversation_history(
            session_data.get("conversation_history", [])
        )
        
        # Informações do carrinho
        cart_info = ""
        if cart_items_count > 0:
            cart_info = f"CARRINHO ATUAL: {cart_items_count} itens"
            cart_items = session_data.get("shopping_cart", [])
            if cart_items:
                cart_info += " ("
                item_names = []
                for item in cart_items[:3]:  # Mostra apenas primeiros 3
                    name = item.get('descricao') or item.get('canonical_name', 'Produto')
                    qt = item.get('qt', 0)
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
        
        # Constrói contexto completo
        full_context = f"""
MENSAGEM DO USUÁRIO: "{user_message}"

{conversation_history}

{cart_info}
{products_info}
{customer_info}

CONTEXTO ADICIONAL:
- Última ação do bot: {session_data.get('last_bot_action', 'NONE')}
- Seleção numérica detectada: {enhanced_context.get('numeric_selection', 'Nenhuma')}
- Quantidade inferida: {enhanced_context.get('inferred_quantity', 'Não especificada')}
- Gíria detectada: {enhanced_context.get('detected_slang', 'Nenhuma')}

IMPORTANTE: Baseie sua resposta no contexto acima. Se há produtos mostrados e o usuário digitou um número (Ex: 1, 2 ou 3), use add_item_to_cart. Se há itens no carrinho e usuário quer finalizar, use checkout.
"""
        
        # Prepara mensagens para o modelo
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_context}
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
                    "temperature": 0.3,  # Mais determinístico
                    "top_p": 0.9,
                    "num_predict": 150,  # Limita tamanho da resposta
                    "stop": ["\n\n", "```"]  # Para em quebras duplas ou markdown
                },
                stream=False
            )
            
            elapsed_time = time.time() - start_time
            logging.info(f"[llm_interface.py] Resposta recebida do LLM em {elapsed_time:.2f}s")
            
            # Se demorou muito, considera usar fallback na próxima
            if elapsed_time > AI_TIMEOUT:
                logging.warning(f"[llm_interface.py] LLM demorou {elapsed_time:.2f}s (timeout: {AI_TIMEOUT}s)")
            
            # Extrai e processa resposta
            content = response.get('message', {}).get('content', '')
            logging.info(f"[llm_interface.py] Resposta do LLM: {content[:200]}...")
            
            cleaned_content = clean_json_response(content)
            logging.debug(f"[llm_interface.py] Conteúdo limpo: {cleaned_content}")
            
            # Parse do JSON
            intent_data = json.loads(cleaned_content)
            tool_name = intent_data.get("tool_name", "handle_chitchat")
            
            # Valida se a ferramenta existe
            if tool_name not in AVAILABLE_TOOLS:
                logging.warning(f"[llm_interface.py] Ferramenta inválida: {tool_name}")
                intent_data = {"tool_name": "handle_chitchat", "parameters": {"response_text": "Tive um problema na consulta agora. Tentar novamente?"}}
            
            # Enriquece parâmetros com contexto adicional
            parameters = intent_data.get("parameters", {})
            
            # Se é seleção numérica e temos produtos, adiciona quantidade se detectada
            if (tool_name == "add_item_to_cart" and 
                enhanced_context.get("numeric_selection") and 
                enhanced_context.get("inferred_quantity")):
                
                if "qt" not in parameters:
                    parameters["qt"] = enhanced_context["inferred_quantity"]
            
            intent_data["parameters"] = validate_intent_parameters(tool_name, parameters)
            
            logging.info(f"[llm_interface.py] JSON parseado com sucesso: {intent_data}")
            return intent_data
            
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"[llm_interface.py] Erro ao parsear JSON: {e}")
            # Fallback baseado em padrões simples
            return create_fallback_intent(user_message, enhanced_context)
        
        except TimeoutError:
            logging.warning(f"[llm_interface.py] Timeout ao chamar LLM após {AI_TIMEOUT}s")
            return create_fallback_intent(user_message, enhanced_context)
        
    except Exception as e:
        logging.error(f"[llm_interface.py] Erro geral: {e}", exc_info=True)
        # Usa fallback em caso de erro
        return create_fallback_intent(user_message, enhance_context_awareness(user_message, session_data))

def clean_json_response(content: str) -> str:
    """Limpa a resposta do LLM para extrair JSON válido."""
    # Remove markdown se presente
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    
    # Remove texto antes e depois do JSON
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        return json_match.group(0).strip()
    
    return content.strip()

def create_fallback_intent(user_message: str, context: Dict) -> Dict:
    """Cria intenção de fallback baseada em padrões simples quando LLM falha ou demora."""
    message_lower = user_message.lower().strip()
    
    # Seleção numérica direta
    if context.get("numeric_selection") and context.get("has_pending_products"):
        # Assume que o usuário quer adicionar o produto selecionado
        return {
            "tool_name": "add_item_to_cart", 
            "parameters": {
                "codprod": 0,  # Será resolvido no app.py
                "qt": context.get("inferred_quantity", 1)
            }
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
    product_keywords = ['quero', 'buscar', 'procurar', 'produto', 'comprar', 'preciso']
    if any(keyword in message_lower for keyword in product_keywords):
        # Extrai nome do produto (remove palavras de comando)
        product_name = message_lower
        for keyword in product_keywords:
            product_name = product_name.replace(keyword, '').strip()
        
        if product_name:
            return {
                "tool_name": "get_top_selling_products_by_name", 
                "parameters": {"product_name": product_name}
            }
    
    # Comandos de produtos populares
    if any(word in message_lower for word in ['produtos', 'mais vendidos', 'populares', 'top']):
        return {"tool_name": "get_top_selling_products", "parameters": {}}
    
    # Saudações
    greetings = ['oi', 'olá', 'ola', 'boa', 'bom dia', 'boa tarde', 'boa noite', 'e aí', 'e ai']
    if any(greeting in message_lower for greeting in greetings):
        return {
            "tool_name": "handle_chitchat", 
            "parameters": {"response_text": "Olá! Sou o G.A.V. do Comercial Esperança. Posso mostrar nossos produtos mais vendidos ou você já sabe o que procura?"}
        }
    
    # Ajuda
    if any(word in message_lower for word in ['ajuda', 'help', 'como', 'funciona']):
        return {
            "tool_name": "handle_chitchat",
            "parameters": {"response_text": "Como posso ajudar? Digite o nome de um produto para buscar, 'carrinho' para ver suas compras, ou 'produtos' para ver os mais vendidos."}
        }
    
    # Novo pedido
    if 'novo' in message_lower or 'nova' in message_lower:
        return {"tool_name": "start_new_order", "parameters": {}}
    
    # Comando "mais" para ver mais produtos
    if 'mais' in message_lower and context.get("last_action") == "AWAITING_PRODUCT_SELECTION":
        return {"tool_name": "show_more_products", "parameters": {}}
    
    # Fallback padrão - tenta buscar o termo completo
    if len(message_lower) > 2:
        return {
            "tool_name": "get_top_selling_products_by_name",
            "parameters": {"product_name": message_lower}
        }
    
    return {
        "tool_name": "handle_chitchat", 
        "parameters": {"response_text": "Não entendi. Digite o nome do produto que procura ou 'ajuda' para ver as opções."}
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
    
    return parameters

def get_enhanced_intent(user_message: str, session_data: Dict, customer_context: Union[Dict, None] = None) -> Dict:
    """Versão melhorada da função get_intent com validação adicional."""
    
    # Obtém intenção básica
    intent = get_intent(user_message, session_data, customer_context, len(session_data.get("shopping_cart", [])))
    
    if not intent:
        return create_fallback_intent(user_message, enhance_context_awareness(user_message, session_data))
    
    # Valida e corrige parâmetros
    tool_name = intent.get("tool_name", "handle_chitchat")
    parameters = intent.get("parameters", {})
    
    validated_parameters = validate_intent_parameters(tool_name, parameters)
    
    return {
        "tool_name": tool_name,
        "parameters": validated_parameters
    }
    
def get_intent_fast(user_message: str, session_data: Dict) -> Dict:
    """Versão rápida de detecção de intenção sem usar IA."""
    # Melhora consciência contextual
    context = enhance_context_awareness(user_message, session_data)
    
    # Retorna intenção baseada em padrões
    return create_fallback_intent(user_message, context)
    