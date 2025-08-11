# file: IA/ai_llm/llm_interface.py
import os
import ollama
import json
import logging
from typing import Union, Dict

# --- Configurações Globais ---
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
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
    "report_incorrect_product"
]

def load_prompt_template() -> str:
    """
    Carrega o prompt do arquivo de texto 'gav_prompt.txt'.
    Isso separa a "personalidade" da IA do código Python.
    """
    # Caminho corrigido para o arquivo de prompt
    prompt_path = os.path.join("ai_llm", "gav_prompt.txt")
    
    try:
        logging.info(f"[llm_interface.py] Tentando carregar prompt de: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            logging.info(f"[llm_interface.py] Prompt carregado com sucesso. Tamanho: {len(content)} caracteres")
            return content
    except FileNotFoundError:
        logging.warning(f"[llm_interface.py] Arquivo '{prompt_path}' não encontrado. Usando prompt de fallback.")
        # Prompt de emergência mais robusto
        return """Você é G.A.V., o Gentil Assistente de Vendas do Comercial Esperança. Seu tom é sempre prestativo, amigável e proativo.

**REGRAS DE OURO DA PERSONALIDADE:**
1. **SAUDAÇÃO INICIAL:** Ao receber a primeira mensagem do usuário (como "oi", "olá", "bom dia"), sua primeira resposta DEVE ser amigável e informativa. USE a ferramenta "handle_chitchat".
2. **SEJA UM VENDEDOR:** Sempre guie a conversa para uma venda. Se o usuário falar de assuntos aleatórios, responda brevemente e puxe de volta para o negócio.

**FERRAMENTAS DISPONÍVEIS:**
- `get_top_selling_products`
- `get_top_selling_products_by_name`
- `add_item_to_cart`
- `view_cart`
- `checkout`
- `find_customer_by_cnpj`
- `handle_chitchat`

**ESTRUTURA DE SAÍDA OBRIGATÓRIA:**
Responda APENAS com um objeto JSON válido e nada mais, seguindo a estrutura de ferramenta.

**EXEMPLOS OBRIGATÓRIOS:**
- Para uma saudação como "oi": {"tool_name": "handle_chitchat", "parameters": {"response_text": "Olá! Tudo bem? Sou o G.A.V., seu assistente de vendas virtual do Comercial Esperança. Estou aqui para ajudar você a encontrar produtos e montar seu pedido. O que você gostaria de ver hoje?"}}
- Para "quero comprar": {"tool_name": "get_top_selling_products", "parameters": {}}
- Para buscas por produto (ex: "quero omo"): {"tool_name": "get_top_selling_products_by_name", "parameters": {"product_name": "omo"}}"""

def get_intent(user_message: str, session_data: Dict, customer_context: Union[Dict, None] = None, cart_items_count: int = 0) -> Dict:
    """
    Usa o LLM para interpretar a mensagem do usuário e traduzir em uma ferramenta.
    Agora inclui contexto conversacional completo.
    
    Args:
        user_message: Mensagem atual do usuário
        session_data: Dados completos da sessão (incluindo histórico)
        customer_context: Informações do cliente (mantido para compatibilidade)
        cart_items_count: Quantidade de itens no carrinho (mantido para compatibilidade)
    """
    from core.session_manager import get_conversation_context, get_session_context_summary
    
    logging.info(f"[llm_interface.py] Iniciando get_intent para mensagem: '{user_message[:50]}...'")
    
    # 1. Carrega o template do prompt do arquivo .txt
    prompt_template = load_prompt_template()
    
    # 2. Prepara o contexto conversacional
    conversation_context = get_conversation_context(session_data, max_messages=12)
    session_summary = get_session_context_summary(session_data)
    
    # 3. Prepara variáveis para o template
    customer_context_str = f"Sim, {customer_context['nome']}" if customer_context else "Não"
    
    # 4. Cria o prompt completo com contexto conversacional
    enhanced_prompt = f"""{prompt_template}

{conversation_context}

**ESTADO ATUAL DA SESSÃO:**
{session_summary}

**CONTEXTO DINÂMICO:**
- Cliente identificado: {customer_context_str}
- Itens no carrinho: {cart_items_count}

**MENSAGEM ATUAL DO USUÁRIO:** "{user_message}"

**INSTRUÇÕES IMPORTANTES:**
- Use o HISTÓRICO DA CONVERSA para entender o contexto e dar respostas coerentes
- Se o usuário se referir a algo mencionado anteriormente, use essa informação
- Mantenha continuidade na conversa baseada no histórico
- Se houver produtos no carrinho ou buscas recentes, considere isso nas respostas"""
    
    logging.info(f"[llm_interface.py] Prompt com contexto preparado. Tamanho: {len(enhanced_prompt)} caracteres")
    
    # 5. Chama o modelo de linguagem
    try:
        client_args = {}
        if OLLAMA_HOST:
            logging.info(f"[llm_interface.py] Configurando Ollama Host: '{OLLAMA_HOST}'")
            client_args['host'] = OLLAMA_HOST
        else:
            logging.warning(f"[llm_interface.py] OLLAMA_HOST não definido, usando configuração padrão")
            
        client = ollama.Client(**client_args)
        
        # Verifica disponibilidade do modelo
        try:
            logging.info(f"[llm_interface.py] Verificando disponibilidade do modelo: {OLLAMA_MODEL_NAME}")
            models_response = client.list()
            available_models = []
            if hasattr(models_response, 'get'):
                available_models = [model.get('name', '') for model in models_response.get('models', [])]
            elif hasattr(models_response, 'models'):
                available_models = [model.get('name', '') for model in models_response.models]
            
            logging.info(f"[llm_interface.py] Modelos disponíveis: {available_models}")
            
            if OLLAMA_MODEL_NAME not in available_models:
                logging.error(f"[llm_interface.py] Modelo '{OLLAMA_MODEL_NAME}' não encontrado. Tentando baixar...")
                try:
                    client.pull(OLLAMA_MODEL_NAME)
                    logging.info(f"[llm_interface.py] Modelo '{OLLAMA_MODEL_NAME}' baixado com sucesso")
                except Exception as pull_error:
                    logging.error(f"[llm_interface.py] Erro ao baixar modelo: {pull_error}")
                    return {"tool_name": "handle_chitchat", "parameters": {"response_text": "🤖 Desculpe, estou com problemas técnicos. Tente novamente em alguns instantes."}}
                    
        except Exception as list_error:
            logging.warning(f"[llm_interface.py] Não foi possível verificar modelos disponíveis: {list_error}")
        
        # Faz a chamada para o modelo
        logging.info(f"[llm_interface.py] Fazendo chamada para ollama.chat...")
        response = client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        
        logging.info(f"[llm_interface.py] Resposta recebida do LLM")
        content = response.get('message', {}).get('content', '')
        
        if not content:
            logging.error(f"[llm_interface.py] Resposta vazia do LLM")
            return {"tool_name": "handle_chitchat", "parameters": {"response_text": "🤖 Desculpe, não consegui processar sua mensagem. Pode repetir?"}}
        
        logging.debug(f"[llm_interface.py] Conteúdo da resposta: {content}")
        
        # Parse do JSON
        try:
            parsed_response = json.loads(content)
            logging.info(f"[llm_interface.py] JSON parseado com sucesso: {parsed_response}")
            return parsed_response
            
        except json.JSONDecodeError as json_error:
            logging.error(f"[llm_interface.py] Erro ao fazer parse do JSON: {json_error}")
            logging.error(f"[llm_interface.py] Conteúdo que causou erro: {content}")
            
            # Fallback para resposta de erro
            return {
                "tool_name": "handle_chitchat", 
                "parameters": {
                    "response_text": "🤖 Desculpe, tive dificuldade para entender. Pode reformular sua pergunta?"
                }
            }
            
    except Exception as e:
        logging.error(f"[llm_interface.py] Erro na comunicação com Ollama: {e}")
        return {
            "tool_name": "handle_chitchat", 
            "parameters": {
                "response_text": "🤖 Estou com problemas de conexão. Tente novamente em alguns segundos."
            }
        }