# file: llm_interface.py
import os
import ollama
import json
from typing import Union, Dict # Importação necessária para compatibilidade

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
    try:
        with open("gav_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print("AVISO: Arquivo 'gav_prompt.txt' não encontrado. Usando um prompt de fallback genérico.")
        # Este é um prompt de emergência caso o arquivo principal não exista.
        return "Você é um assistente de vendas. Responda em JSON usando as ferramentas disponíveis."

def get_intent(user_message: str, customer_context: Union[Dict, None], cart_items_count: int) -> Dict:
    """
    Usa o LLM para interpretar a mensagem do usuário e traduzir em uma ferramenta.
    """
    # 1. Carrega o template do prompt do arquivo .txt
    prompt_template = load_prompt_template()
    
    # 2. Preenche os placeholders ({...}) no template com os dados da conversa atual
    customer_context_str = f"Sim, {customer_context['nome']}" if customer_context else "Não"
    system_prompt = prompt_template.format(
        customer_context_str=customer_context_str,
        cart_items_count=cart_items_count
    )
    
    # 3. Envia o prompt finalizado para o LLM
    try:
        client_args = {}
        if OLLAMA_HOST:
            print(f">>> OLLAMA HOST: '{OLLAMA_HOST}'")
            client_args['host'] = OLLAMA_HOST
        client = ollama.Client(**client_args)

        response = client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message}
            ],
            format='json'
        )
        # O LLM deve retornar um conteúdo em formato JSON, que é carregado para um dicionário Python
        return json.loads(response['message']['content'])
        
    except Exception as e:
        print(f"Erro ao comunicar com o LLM ou ao processar resposta: {e}")
        # Retorna uma ferramenta de erro para que o main.py saiba que algo deu errado
        return {"tool_name": "error", "parameters": {"detail": str(e)}}