"""Utilities to load and maintain the knowledge base.

When executed directly this module rebuilds ``knowledge_base.json`` using the
products stored in the database.  For each product we try to generate at least
20 variations of terms that a user might employ to reference that product.  The
generated terms are saved in the ``related_words`` field and each variation is
also used as a key for quick lookups.

The file is only rewritten when the script is executed directly (``__main__``).
"""

import json
import logging
import os
import sys
import re
import unicodedata
import itertools
from typing import Dict, List, Union, Optional
from pathlib import Path

import ollama
from psycopg2.extras import RealDictCursor


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import database


KB_PATH = Path(__file__).resolve().parent / "knowledge_base.json"
_kb: Optional[Dict[str, List[Dict]]] = None  # ← MUDANÇA: agora é List[Dict]
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")


def _load_kb() -> Dict[str, List[Dict]]:  # ← MUDANÇA: retorna List[Dict]
    """Load the knowledge base from disk into memory.

    If the file does not exist or is empty we return an empty dict.
    The JSON file stores only canonical product names as keys, but in
    memory we also index each related word for faster lookup.
    
    IMPORTANTE: Agora cada termo pode mapear para MÚLTIPLOS produtos.
    """
    global _kb
    if _kb is not None:
        return _kb

    raw_kb: Dict[str, Dict] = {}
    try:
        if not KB_PATH.exists() or KB_PATH.stat().st_size == 0:
            logging.info(f"Arquivo '{KB_PATH}' inexistente ou vazio.")
            raw_kb = {}
        else:
            with KB_PATH.open("r", encoding="utf-8") as f:
                raw_kb = json.load(f)
            if not raw_kb:
                raw_kb = {}
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        logging.warning(f"Erro ao carregar '{KB_PATH}': {e}. Usando base vazia.")
        raw_kb = {}

    # ← MUDANÇA: Cria índice expandido onde cada termo pode mapear para múltiplos produtos
    kb: Dict[str, List[Dict]] = {}
    
    for canonical, entry in raw_kb.items():
        # Adiciona pelo nome canônico
        canonical_lower = canonical.lower()
        if canonical_lower not in kb:
            kb[canonical_lower] = []
        kb[canonical_lower].append(entry)
        
        # Adiciona por cada related_word
        for word in entry.get("related_words", []):
            word_lower = word.lower()
            if word_lower not in kb:
                kb[word_lower] = []
            # Só adiciona se não estiver já na lista (evita duplicatas)
            if entry not in kb[word_lower]:
                kb[word_lower].append(entry)

    _kb = kb
    total_products = len(raw_kb)
    total_terms = len(kb)
    logging.info(
        f"Base de conhecimento '{KB_PATH}' carregada com {total_products} produtos e {total_terms} termos."
    )
    return _kb


def find_product_in_kb(term: str) -> List[Dict]:  # ← MUDANÇA: retorna List[Dict]
    """Busca produtos na base de conhecimento usando o termo fornecido.
    
    RETORNA: Lista de produtos que correspondem ao termo (pode ser vazia).
    """
    if not term:
        return []
        
    kb = _load_kb()
    term_lower = term.lower().strip()
    
    # Busca direta no índice
    if term_lower in kb:
        return kb[term_lower]
    
    # Busca fuzzy: procura se o termo está contido em alguma related_word
    matching_products = []
    seen_codprods = set()  # Evita duplicatas
    
    for indexed_term, products in kb.items():
        if term_lower in indexed_term:
            for product in products:
                codprod = product.get("codprod")
                if codprod and codprod not in seen_codprods:
                    matching_products.append(product)
                    seen_codprods.add(codprod)
            
    return matching_products


def update_kb(term: str, correct_product: Dict):
    """Persistently store a new association in the knowledge base."""
    if not term or not correct_product or not correct_product.get("codprod"):
        logging.warning("Tentativa de atualizar KB com dados inválidos.")
        return

    term_normalized = term.lower().strip()

    # Carrega o arquivo bruto (apenas nomes canônicos como chaves)
    try:
        with KB_PATH.open("r", encoding="utf-8") as f:
            raw_kb = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_kb = {}

    canonical_name = correct_product["descricao"]
    
    # Procura se já existe entrada para este produto
    entry = None
    for name, existing_entry in raw_kb.items():
        if existing_entry.get("codprod") == correct_product["codprod"]:
            entry = existing_entry
            break
    
    # Se não encontrou, cria nova entrada
    if entry is None:
        entry = {
            "codprod": correct_product["codprod"],
            "canonical_name": canonical_name,
            "related_words": [],
        }
        raw_kb[canonical_name] = entry

    # Adiciona o novo termo se não existir
    if term_normalized not in [w.lower() for w in entry["related_words"]]:
        entry["related_words"].append(term_normalized)
        logging.info(f"Adicionado termo '{term_normalized}' ao produto {canonical_name}")

    try:
        with KB_PATH.open("w", encoding="utf-8") as f:
            json.dump(raw_kb, f, indent=2, ensure_ascii=False)
        logging.info(f"KB atualizado com novo termo relacionado '{term_normalized}'")
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")

    # Limpa o cache em memória para refletir as mudanças
    global _kb
    _kb = None


def _normalize(text: str) -> str:
    """Remove acentos e normaliza o texto para minúsculas."""
    nfkd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _heuristic_related_words(description: str) -> List[str]:
    """Fallback simples para gerar variações quando a IA não estiver disponível."""
    normalized = _normalize(description)
    tokens = [t for t in re.split(r"\W+", normalized) if t and len(t) > 1]
    variations = set()

    # Variações básicas
    variations.add(normalized)
    variations.add(" ".join(tokens))
    variations.add("".join(tokens))
    
    # Remove pontuação
    for char in ["-", ".", "/", "_"]:
        variations.add(normalized.replace(char, " "))
        variations.add(normalized.replace(char, ""))

    # Combinações de tokens
    for r in range(1, min(4, len(tokens)) + 1):
        for combo in itertools.combinations(tokens, r):
            variations.add(" ".join(combo))
            variations.add("".join(combo))

    # Remove variações muito curtas ou vazias
    variations = {v for v in variations if v and len(v.strip()) > 1}
    
    variations_list = list(variations)
    
    # Garante pelo menos 20 variações
    if len(variations_list) < 20:
        for i in range(20 - len(variations_list)):
            variations_list.append(f"{tokens[0] if tokens else 'produto'} variacao {i+1}")
    
    return variations_list[:20]


def generate_related_words(description: str) -> List[str]:
    """Gera pelo menos 20 variações usando o modelo configurado do Ollama."""
    prompt = f"""
Gere exatamente 20 variações de palavras ou frases que um cliente brasileiro poderia usar para se referir ao produto: '{description}'.

Inclua:
- Variações com e sem acentos
- Abreviações comuns
- Sinônimos
- Variações de grafia
- Termos populares/informais
- Marcas relacionadas (se aplicável)

Responda APENAS com as 20 variações separadas por vírgula, sem numeração ou explicações.
"""

    try:
        client_args = {}
        if OLLAMA_HOST:
            client_args["host"] = OLLAMA_HOST
        
        client = ollama.Client(**client_args)
        response = client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        
        text = response["message"]["content"].strip()
        
        # Parse da resposta
        words = []
        for w in text.split(","):
            word = w.strip().lower()
            if word and len(word) > 1:
                words.append(word)
        
        # Remove duplicatas mantendo ordem
        seen = set()
        unique_words = []
        for w in words:
            if w not in seen:
                seen.add(w)
                unique_words.append(w)
        
        if len(unique_words) >= 15:  # Aceita se tiver pelo menos 15 boas variações
            return unique_words[:20]
        else:
            raise ValueError(f"IA retornou apenas {len(unique_words)} variações válidas")
            
    except Exception as e:
        logging.warning(f"Falha ao gerar variações via IA para '{description}': {e}")
        return _heuristic_related_words(description)


def build_knowledge_base() -> None:
    """Consulta todos os produtos e reescreve o arquivo de base de conhecimento."""
    logging.info("=== INICIANDO GERAÇÃO DA BASE DE CONHECIMENTO ===")
    logging.info("Consultando produtos ativos no banco de dados...")

    sql = "SELECT codprod, descricao FROM produtos WHERE status = 'ativo' ORDER BY codprod;"
    products: List[Dict] = []

    try:
        with database.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                products = cursor.fetchall()
                logging.info(f"Encontrados {len(products)} produtos ativos no banco")
    except Exception as e:
        logging.error(f"Falha ao consultar produtos: {e}")
        return

    if not products:
        logging.warning("Nenhum produto encontrado. Base de conhecimento não será gerada.")
        return

    kb: Dict[str, Dict] = {}
    
    for i, product in enumerate(products, 1):
        logging.info(f"Processando produto {i}/{len(products)}: {product['descricao']}")
        
        try:
            related = generate_related_words(product["descricao"])
            entry = {
                "codprod": product["codprod"],
                "canonical_name": product["descricao"],
                "related_words": related,
            }
            kb[product["descricao"]] = entry
            logging.info(f"  -> Geradas {len(related)} variações")
            
        except Exception as e:
            logging.error(f"Erro ao processar produto {product['descricao']}: {e}")
            # Adiciona entrada básica mesmo com erro
            kb[product["descricao"]] = {
                "codprod": product["codprod"],
                "canonical_name": product["descricao"],
                "related_words": _heuristic_related_words(product["descricao"]),
            }

    try:
        # Cria backup do arquivo anterior se existir
        if KB_PATH.exists():
            backup_path = KB_PATH.with_suffix(".json.backup")
            KB_PATH.rename(backup_path)
            logging.info(f"Backup criado: {backup_path}")
        
        # Salva nova base de conhecimento
        with KB_PATH.open("w", encoding="utf-8") as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
        
        logging.info(f"=== BASE DE CONHECIMENTO GERADA COM SUCESSO ===")
        logging.info(f"Arquivo: {KB_PATH}")
        logging.info(f"Produtos processados: {len(products)}")
        logging.info(f"Total de entradas: {len(kb)}")
        
        # Calcula total de termos indexados
        total_terms = sum(len(entry.get("related_words", [])) for entry in kb.values())
        logging.info(f"Total de termos relacionados: {total_terms}")
        
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")
        return

    # Limpa o cache em memória para garantir recarregamento da nova base
    global _kb
    _kb = None
    logging.info("Cache em memória limpo. Próxima consulta carregará a nova base.")


if __name__ == "__main__":
    # Configura logging para execução direta
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("knowledge_generation.log", mode='a', encoding='utf-8')
        ]
    )
    
    print("=== GERADOR DE BASE DE CONHECIMENTO ===")
    print("Este script irá:")
    print("1. Consultar todos os produtos ativos no banco")
    print("2. Gerar 20+ variações para cada produto usando IA")
    print("3. Reescrever o arquivo knowledge_base.json")
    print()
    
    build_knowledge_base()
    print("\nProcesso concluído! Verifique o arquivo knowledge_base.json e os logs.")