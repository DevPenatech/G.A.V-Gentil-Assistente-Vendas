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
    "view_cart",
    "checkout",
    "handle_chitchat"
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

def get_intent(user_message: str, customer_context: Union[Dict, None], cart_items_count: int) -> Dict:
    """
    Usa o LLM para interpretar a mensagem do usuário e traduzir em uma ferramenta.
    """
    logging.info(f"[llm_interface.py] Iniciando get_intent para mensagem: '{user_message[:50]}...'")
    
    # 1. Carrega o template do prompt do arquivo .txt
    prompt_template = load_prompt_template()
    
    # 2. Preenche os placeholders ({...}) no template com os dados da conversa atual
    customer_context_str = f"Sim, {customer_context['nome']}" if customer_context else "Não"
    system_prompt = prompt_template.format(
        customer_context_str=customer_context_str,
        cart_items_count=cart_items_count
    )
    
    logging.info(f"[llm_interface.py] System prompt preparado. Tamanho: {len(system_prompt)} caracteres")
    
    # 3. Verifica e configura conexão com Ollama
    try:
        client_args = {}
        if OLLAMA_HOST:
            logging.info(f"[llm_interface.py] Configurando Ollama Host: '{OLLAMA_HOST}'")
            client_args['host'] = OLLAMA_HOST
        else:
            logging.warning(f"[llm_interface.py] OLLAMA_HOST não definido, usando configuração padrão")
            
        client = ollama.Client(**client_args)
        
        # Verifica se o modelo está disponível
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
                    logging.error(f"[llm_interface.py] Falha ao baixar modelo: {pull_error}")
                    return {"tool_name": "error", "parameters": {"detail": f"Failed to download model {OLLAMA_MODEL_NAME}: {str(pull_error)}"}}
        except Exception as check_error:
            logging.warning(f"[llm_interface.py] Não foi possível verificar modelos disponíveis: {check_error}")

        # 4. Envia a requisição para o LLM
        logging.info(f"[llm_interface.py] Enviando requisição para o modelo {OLLAMA_MODEL_NAME}")
        response = client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message}
            ],
            format='json'
        )
        
        response_content = response['message']['content']
        logging.info(f"[llm_interface.py] Resposta recebida do LLM. Tamanho: {len(response_content)} caracteres")
        logging.debug(f"[llm_interface.py] Conteúdo da resposta: {response_content}")
        
        # O LLM deve retornar um conteúdo em formato JSON, que é carregado para um dicionário Python
        try:
            parsed_response = json.loads(response_content)
            logging.info(f"[llm_interface.py] JSON parseado com sucesso: {parsed_response}")
            return parsed_response
        except json.JSONDecodeError as json_error:
            logging.error(f"[llm_interface.py] Erro ao fazer parse do JSON: {json_error}")
            logging.error(f"[llm_interface.py] Conteúdo problemático: {response_content}")
            return {"tool_name": "error", "parameters": {"detail": f"Invalid JSON response from LLM: {str(json_error)}"}}
        
    except Exception as e:
        logging.error(f"[llm_interface.py] Erro ao comunicar com o LLM: {e}")
        return {"tool_name": "error", "parameters": {"detail": f"Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible. {str(e)}"}}