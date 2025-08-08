# file: IA/scripts/discover_keywords.py
from db import database
import json
import ollama
import time
from psycopg2.extras import DictCursor
import os

def get_suggestions_from_llm(description: str) -> list:
    """
    Envia a descrição de um produto para o LLM e pede sugestões de termos de busca.
    """
    prompt = f"""
    Aja como um especialista em catalogação de produtos de varejo.
    Dada a seguinte descrição de produto, extraia os termos de busca mais comuns,
    apelidos, categorias e abreviações que um cliente brasileiro usaria para encontrá-lo.

    Descrição do Produto: "{description}"

    Retorne sua resposta como um objeto JSON com uma única chave chamada "termos",
    que contém uma lista de strings. Inclua apenas os 3 ou 4 termos mais relevantes.
    Exemplo de resposta para "REFRIG.COCA-COLA PET 2L":
    {{"termos": ["coca cola 2l", "coca-cola garrafa", "refrigerante coca"]}}
    """
    
    try:
        print(f"  - Consultando LLM para: '{description}'")
        # Garante que a variável de ambiente OLLAMA_HOST está sendo lida
        ollama_host = os.getenv("OLLAMA_HOST")
        client_args = {}
        if ollama_host:
            client_args['host'] = ollama_host

        client = ollama.Client(**client_args)
        response = client.chat(
            model='llama3',
            messages=[{'role': 'user', 'content': prompt}],
            format='json'
        )
        data = json.loads(response['message']['content'])
        return data.get('termos', [])
    except Exception as e:
        print(f"    !!! Erro ao consultar o LLM: {e}")
        return []

def discover_keywords():
    """
    Analisa os produtos no banco de dados, usa o LLM para gerar sinônimos
    e cria um arquivo 'suggested_semantic_map.json' para revisão.
    """
    print(">>> Iniciando descoberta de palavras-chave com IA...")
    sql = "SELECT codprod, descricao FROM produtos WHERE status = 'ativo';"
    
    try:
        with database.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                print(">>> Conectado ao PostgreSQL. Buscando produtos...")
                cursor.execute(sql)
                all_products = cursor.fetchall()
                print(f">>> {len(all_products)} produtos encontrados.")

        if not all_products:
            print(">>> Nenhum produto encontrado para analisar.")
            return

        suggested_map = {}
        
        print("\n>>> Gerando sugestões com LLM (isso pode levar alguns minutos)...")
        for i, product in enumerate(all_products):
            if i > 0:
                time.sleep(0.5) # Pausa para não sobrecarregar o LLM

            suggestions = get_suggestions_from_llm(product['descricao'])
            
            for term in suggestions:
                term_lower = term.lower()
                if term_lower not in suggested_map:
                    suggested_map[term_lower] = [product['descricao']]
                else:
                    if product['descricao'] not in suggested_map[term_lower]:
                        suggested_map[term_lower].append(product['descricao'])

        if not suggested_map:
            print("\n>>> O LLM não retornou nenhuma sugestão válida.")
            return

        output_path = 'suggested_semantic_map.json'
        print(f"\n>>> Gerando arquivo de sugestões em '{output_path}'...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(suggested_map, f, indent=2, ensure_ascii=False)
            
        print("\n--- Processo Concluído ---")
        print(f"Analise o arquivo '{output_path}'.")
        print("Copie as associações corretas para o seu arquivo 'semantic_map.json' principal.")
        print("--------------------------")

    except Exception as e:
        print(f"!!! ERRO durante a descoberta de palavras-chave: {e}")

if __name__ == "__main__":
    discover_keywords()
