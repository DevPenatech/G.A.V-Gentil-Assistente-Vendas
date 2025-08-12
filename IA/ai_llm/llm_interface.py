# file: IA/ai_llm/llm_interface.py
import os
import ollama
import json
import logging
from typing import Union, Dict, List

# --- Configurações Globais ---
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")

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

def load_prompt_template() -> str:
    """Carrega o prompt do arquivo de texto 'gav_prompt.txt'."""
    prompt_path = os.path.join("ai_llm", "gav_prompt.txt")
    
    try:
        logging.info(f"[llm_interface.py] Tentando carregar prompt de: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            logging.info(f"[llm_interface.py] Prompt carregado com sucesso. Tamanho: {len(content)} caracteres")
            return content
    except FileNotFoundError:
        logging.warning(f"[llm_interface.py] Arquivo '{prompt_path}' não encontrado. Usando prompt de fallback.")
        return get_fallback_prompt()

def get_fallback_prompt() -> str:
    """Prompt de emergência caso o arquivo não seja encontrado."""
    return """Você é G.A.V., o Gentil Assistente de Vendas do Comercial Esperança. 
Sempre responda com JSON válido para executar ferramentas.
Ferramentas disponíveis: get_top_selling_products, get_top_selling_products_by_name, 
add_item_to_cart, view_cart, update_cart_item, checkout, handle_chitchat, ask_continue_or_checkout"""

def format_conversation_history(history: List[Dict]) -> str:
    """Formata o histórico de conversa para contexto."""
    if not history:
        return "Primeira interação com o cliente."
    
    formatted = "HISTÓRICO DA CONVERSA:\n"
    for msg in history[-10:]:  # Últimas 10 mensagens
        role = "Cliente" if msg['role'] == 'user' else "G.A.V."
        formatted += f"{role}: {msg['message']}\n"
    
    return formatted

def get_intent(user_message: str, session_data: Dict, customer_context: Union[Dict, None] = None, cart_items_count: int = 0) -> Dict:
    """
    Usa o LLM para interpretar a mensagem do usuário e traduzir em uma ferramenta.
    
    Args:
        user_message: Mensagem do usuário
        session_data: Dados completos da sessão incluindo histórico
        customer_context: Contexto do cliente (se identificado)
        cart_items_count: Número de itens no carrinho
        
    Returns:
        Dict com a ferramenta e parâmetros a executar
    """
    logging.info(f"[llm_interface.py] Iniciando get_intent para mensagem: '{user_message}...'")
    
    # Carrega o prompt base
    base_prompt = load_prompt_template()
    
    # Adiciona contexto da conversa
    conversation_context = format_conversation_history(
        session_data.get('conversation_history', [])
    )
    
    # Informações do carrinho
    cart_info = f"CARRINHO: {cart_items_count} itens" if cart_items_count > 0 else "CARRINHO: vazio"
    
    # Informações do cliente
    customer_info = f"CLIENTE: {customer_context['nome']}" if customer_context else "CLIENTE: não identificado"
    
    # Monta o prompt completo
    system_prompt = f"""{base_prompt}

{conversation_context}

ESTADO ATUAL:
{cart_info}
{customer_info}

ÚLTIMA MENSAGEM DO USUÁRIO: {user_message}

Responda APENAS com JSON válido para executar a ferramenta apropriada."""

    logging.info(f"[llm_interface.py] System prompt preparado. Tamanho: {len(system_prompt)} caracteres")
    logging.info(f"[llm_interface.py] Configurando Ollama Host: '{OLLAMA_HOST}'")
    
    # Configura o cliente Ollama
    ollama_client = ollama.Client(host=OLLAMA_HOST)
    
    # Verifica disponibilidade do modelo
    try:
        logging.info(f"[llm_interface.py] Verificando disponibilidade do modelo: {OLLAMA_MODEL_NAME}")
        models = ollama_client.list()
        model_names = [m.get('name', '').split(':')[0] for m in models.get('models', [])]
        
        if OLLAMA_MODEL_NAME not in model_names:
            logging.warning(f"[llm_interface.py] Modelo {OLLAMA_MODEL_NAME} não encontrado. Modelos disponíveis: {model_names}")
    except Exception as e:
        logging.warning(f"[llm_interface.py] Não foi possível verificar modelos disponíveis: {e}")
    
    # Envia requisição para o modelo
    try:
        logging.info(f"[llm_interface.py] Enviando requisição para o modelo {OLLAMA_MODEL_NAME}")
        
        response = ollama_client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            options={
                "temperature": 0.3,
                "top_p": 0.9,
                "seed": 42
            }
        )
        
        content = response['message']['content']
        logging.info(f"[llm_interface.py] Resposta recebida do LLM. Tamanho: {len(content)} caracteres")
        logging.debug(f"[llm_interface.py] Conteúdo da resposta: {content}")
        
        # Tenta parsear o JSON
        try:
            # Remove possíveis caracteres extras
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            result = json.loads(content)
            logging.info(f"[llm_interface.py] JSON parseado com sucesso: {result}")
            
            # Valida estrutura básica
            if 'tool_name' not in result:
                logging.warning("[llm_interface.py] JSON sem 'tool_name'. Adicionando fallback.")
                result = {
                    "tool_name": "handle_chitchat",
                    "parameters": {"response_text": "Desculpe, não entendi. Posso mostrar nossos produtos?"}
                }
            
            return result
            
        except json.JSONDecodeError as e:
            logging.error(f"[llm_interface.py] Erro ao parsear JSON: {e}")
            logging.error(f"[llm_interface.py] Conteúdo que falhou: {content}")
            
            # Fallback para chitchat
            return {
                "tool_name": "handle_chitchat",
                "parameters": {"response_text": "Olá! Como posso ajudar você hoje?"}
            }
            
    except Exception as e:
        logging.error(f"[llm_interface.py] Erro ao chamar Ollama: {e}")
        
        # Fallback baseado em palavras-chave
        msg_lower = user_message.lower()
        
        if any(word in msg_lower for word in ['oi', 'olá', 'ola', 'bom dia', 'boa tarde', 'boa noite']):
            return {
                "tool_name": "handle_chitchat",
                "parameters": {
                    "response_text": "Olá! Sou o G.A.V., assistente do Comercial Esperança. Como posso ajudar?"
                }
            }
        elif 'carrinho' in msg_lower or 'pedido' in msg_lower:
            return {"tool_name": "view_cart", "parameters": {}}
        elif 'finalizar' in msg_lower or 'fechar' in msg_lower:
            return {"tool_name": "checkout", "parameters": {}}
        else:
            return {"tool_name": "get_top_selling_products", "parameters": {}}