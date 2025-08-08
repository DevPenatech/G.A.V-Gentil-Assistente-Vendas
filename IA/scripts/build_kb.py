# file: IA/build_kb.py
from IA.database import database
import json
import re
from psycopg2.extras import DictCursor

def load_semantic_map():
    """Carrega o mapa de sinônimos de um arquivo JSON externo."""
    try:
        with open('semantic_map.json', 'r', encoding='utf-8') as f:
            print(">>> Mapa semântico (semantic_map.json) carregado com sucesso.")
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(">>> AVISO: Arquivo 'semantic_map.json' não encontrado ou inválido. A busca semântica será limitada.")
        return {}

def generate_terms_and_relations(description: str, semantic_map: dict) -> (set, list):
    """
    Gera termos de busca e palavras relacionadas a partir da descrição e do mapa semântico.
    """
    normalized = description.lower()
    normalized = re.sub(r'[.\(\)\*]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    keywords = [word for word in normalized.split() if len(word) > 2]
    search_terms = set()
    related_words = []

    # 1. Gera termos de busca a partir das palavras da descrição
    if len(keywords) >= 2:
        for i in range(len(keywords) - 1):
            term = f"{keywords[i]} {keywords[i+1]}"
            search_terms.add(term)
    for word in keywords:
        search_terms.add(word)

    # 2. Procura por correspondências no mapa semântico para preencher 'related_words'
    for key, synonyms in semantic_map.items():
        # Verifica se algum dos sinônimos da categoria está na descrição
        for synonym in synonyms:
            if synonym in normalized:
                # Se encontrou, adiciona a CHAVE principal (ex: "sabao") como palavra relacionada
                if key not in related_words:
                    related_words.append(key)
                # Não precisa continuar procurando sinônimos para esta chave
                break 

    return {s.strip() for s in search_terms if s}, related_words


def build_knowledge_base():
    """
    Lê a tabela 'produtos' do PostgreSQL e gera o arquivo knowledge_base.json.
    """
    print(">>> Iniciando a construção da Base de Conhecimento...")
    
    semantic_map = load_semantic_map()
    sql = "SELECT codprod, descricao FROM produtos WHERE status = 'ativo';"
    
    try:
        with database.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                print(">>> Conectado ao PostgreSQL. Buscando produtos...")
                cursor.execute(sql)
                all_products = cursor.fetchall()
                print(f">>> {len(all_products)} produtos encontrados.")
        
        knowledge_base = {}
        
        print(">>> Gerando sinônimos e palavras relacionadas para cada produto...")
        for product in all_products:
            search_terms, related_words = generate_terms_and_relations(product['descricao'], semantic_map)
            
            # Cria a entrada base do produto
            product_entry = {
                "codprod": product['codprod'],
                "canonical_name": product['descricao'],
                "related_words": related_words
            }
            
            # Associa todos os termos de busca a esta entrada de produto
            for term in search_terms:
                if term not in knowledge_base:
                    knowledge_base[term] = product_entry

        print(f">>> Base de conhecimento gerada com {len(knowledge_base)} termos.")
        
        output_path = 'knowledge_base.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge_base, f, indent=2, ensure_ascii=False)
            
        print(f">>> SUCESSO! O arquivo '{output_path}' foi criado/atualizado.")

    except Exception as e:
        print(f"!!! ERRO durante a construção da Base de Conhecimento: {e}")

if __name__ == "__main__":
    build_knowledge_base()
