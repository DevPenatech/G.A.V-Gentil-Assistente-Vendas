# file: IA/ai_llm/llm_interface.py
import os
import ollama
import json
import logging
from typing import Union, Dict

# --- Configurações Globais ---
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
AVAILABLE_TOOLS = [
    "find_customer_by_cnpj",
    "get_top_selling_products",
    "get_top_selling_products_by_name",
    "add_item_to_cart",
    "update_cart_item",
    "view_cart",
    "remove_item_from_cart",
    "clear_cart",
    "start_new_order",
    "checkout",
    "show_more_products",
    "report_incorrect_product",
    "get_product_by_codprod",
    "handle_chitchat"
]

def _strip_code_fences(text: str) -> str:
    if "```" not in text:
        return text
    import re as _re
    blocks = _re.findall(r"```(?:json)?\s*(.*?)```", text, flags=_re.S|_re.I)
    return blocks[0].strip() if blocks else text

def _extract_json_from_text(text: str):
    # 1) tenta direto
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # 2) remove code fences
    stripped = _strip_code_fences(text)
    if stripped != text:
        try:
            obj = json.loads(stripped)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    # 3) varre por bloco {...} balanceado
    start_idxs = [i for i,ch in enumerate(text) if ch == "{"]
    for start in start_idxs:
        depth = 0
        for j in range(start, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:j+1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
    return None

def load_prompt_template() -> str:
    """
    Carrega um template de prompt do disco (se existir), senão usa padrão interno.
    """
    default_template = (
        "Você é um orquestrador de intenções para um assistente de vendas no WhatsApp.\n"
        "Retorne APENAS um JSON válido com o formato:\n"
        '{"tool_name": "<uma das ferramentas>", "parameters": { ... }}\n'
        "Ferramentas disponíveis: " + ", ".join(AVAILABLE_TOOLS) + "\n"
        "Regras:\n"
        "- Nunca retorne texto fora do JSON.\n"
        "- Não use markdown.\n"
        "- Se não entender, devolva handle_chitchat com uma mensagem educada.\n"
        "- Considere o contexto conversacional (histórico, carrinho, buscas).\n"
    )
    try:
        here = os.path.dirname(__file__)
        path = os.path.join(here, "prompt_template.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        logging.warning(f"[llm_interface.py] Falha ao carregar template externo: {e}")
    return default_template

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
    
    # 4. Cria o prompt completo com contexto
    enhanced_prompt = f"""{prompt_template}
Contexto:
- Cliente conhecido? {customer_context_str}
- Itens no carrinho: {cart_items_count}
- Resumo da sessão: {session_summary}

Histórico (mensagens mais recentes primeiro):
{conversation_context}

Instruções finais:
- Responda apenas com JSON. Nada de texto fora do JSON.
- Utilize exclusivamente as ferramentas listadas em 'Ferramentas disponíveis'.
- Evite erros de formatação.
- Se o usuário se referir a algo mencionado anteriormente, use essa informação
- Mantenha continuidade na conversa baseada no histórico
- Se houver produtos no carrinho ou buscas recentes, considere isso nas respostas"""
    # Reforço para saída estritamente em JSON
    enhanced_prompt = enhanced_prompt + "\nResponda APENAS com um JSON válido seguindo exatamente o schema: {\"tool_name\": \"<string>\", \"parameters\": { ... }}. Sem texto adicional, sem markdown, sem comentários."
    
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
                available_models = [model.get('name', '').split(':')[0] for model in models_response.get('models', [])]
            elif hasattr(models_response, 'models'):
                available_models = [model.get('name', '').split(':')[0] for model in models_response.models]

            logging.info(f"[llm_interface.py] Modelos disponíveis: {available_models}")

            model_name = OLLAMA_MODEL_NAME.split(':')[0]
            if model_name not in available_models:
                logging.error(f"[llm_interface.py] Modelo '{model_name}' não encontrado. Tentando baixar...")
                try:
                    for _ in client.pull(model_name):
                        pass  # consome o progresso para finalizar o download
                    logging.info(f"[llm_interface.py] Modelo '{model_name}' baixado com sucesso")
                    models_response = client.list()
                    if hasattr(models_response, 'get'):
                        available_models = [m.get('name','').split(':')[0] for m in models_response.get('models',[])]
                    elif hasattr(models_response, 'models'):
                        available_models = [m.get('name','').split(':')[0] for m in models_response.models]
                except Exception as pull_error:
                    logging.error(f"[llm_interface.py] Erro ao baixar modelo: {pull_error}")
            if model_name not in available_models:
                fallbacks = [m.split(':')[0] for m in ["llama3.1:8b", "llama3.1", "llama3", "qwen2.5:7b", "mistral"]]
                chosen = next((m for m in fallbacks if m in available_models), None)
                if not chosen:
                    logging.error("[llm_interface.py] Nenhum modelo disponível após tentativas.")
                    return {"tool_name":"handle_chitchat","parameters":{"response_text":"🤖 Serviço de IA indisponível no momento. Tente novamente em instantes."}}
                logging.warning(f"[llm_interface.py] Usando fallback de modelo: {chosen}")
                model_name = chosen
        except Exception as list_error:
            logging.warning(f"[llm_interface.py] Não foi possível verificar modelos disponíveis: {list_error}")
        
        # Faz a chamada para o modelo
        logging.info(f"[llm_interface.py] Fazendo chamada para ollama.chat...")
        try:
            response = client.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": enhanced_prompt},
                    {"role": "user", "content": user_message}
                ],
                format="json"
            )
        except TypeError:
            response = client.chat(
                model=model_name,
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
        
        # Parse do JSON (robusto)
        try:
            parsed_response = _extract_json_from_text(content)
            if not isinstance(parsed_response, dict) or "tool_name" not in parsed_response:
                raise json.JSONDecodeError("no-json-found", content, 0)
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
