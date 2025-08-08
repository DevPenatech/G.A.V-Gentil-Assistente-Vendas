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
import re
import unicodedata
import itertools
from typing import Dict, List, Union

import ollama
from psycopg2.extras import RealDictCursor

from db import database


KNOWLEDGE_BASE_FILE = "knowledge/knowledge_base.json"
_kb: Dict[str, Dict] | None = None
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

def _load_kb() -> Dict:
    """Load the knowledge base from disk into memory."""

    global _kb
    if _kb is not None:
        return _kb
    try:
        with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
            _kb = json.load(f)
            logging.info(
                f"Base de conhecimento '{KNOWLEDGE_BASE_FILE}' carregada com {len(_kb)} termos."
            )
            return _kb
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning(
            f"Arquivo '{KNOWLEDGE_BASE_FILE}' não encontrado. Iniciando com base vazia."
        )
        _kb = {}
        return _kb

def find_product_in_kb(term: str) -> Union[Dict, None]:
    """Busca um produto na base de conhecimento."""

    kb = _load_kb()
    term_lower = term.lower()
    if term_lower in kb:
        return kb[term_lower]
    # Fallback: procura dentro de related_words
    for entry in kb.values():
        related = entry.get("related_words", [])
        if any(term_lower == w.lower() for w in related):
            return entry
    return None

def update_kb(term: str, correct_product: Dict):
    """Persistently store a new association in the knowledge base."""

    if not term or not correct_product or not correct_product.get("codprod"):
        logging.warning("Tentativa de atualizar KB com dados inválidos.")
        return

    term_lower = term.lower()
    kb = _load_kb()

    entry = {
        "codprod": correct_product["codprod"],
        "canonical_name": correct_product["descricao"],
        "related_words": kb.get(term_lower, {}).get("related_words", []),
    }

    synonyms = {term_lower, term_lower.replace("-", ""), term_lower.replace("-", " ")}
    for synonym in synonyms:
        if synonym:
            kb[synonym] = entry

    try:
        with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
            logging.info(f"KB atualizado para os termos {list(synonyms)}")
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")


def _normalize(text: str) -> str:
    """Remove acentos e normaliza o texto para minúsculas."""

    nfkd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _heuristic_related_words(description: str) -> List[str]:
    """Fallback simples para gerar variações quando a IA não estiver disponível."""

    normalized = _normalize(description)
    tokens = [t for t in re.split(r"\W+", normalized) if t]
    variations = set()

    variations.add(normalized)
    variations.add(" ".join(tokens))
    variations.add("".join(tokens))
    variations.add(normalized.replace("-", " "))
    variations.add(normalized.replace("-", ""))
    variations.add(normalized.replace(".", " "))
    variations.add(normalized.replace(".", ""))
    variations.add(normalized.replace("/", " "))
    variations.add(normalized.replace("/", ""))

    for r in range(1, min(3, len(tokens)) + 1):
        for combo in itertools.combinations(tokens, r):
            variations.add(" ".join(combo))
            variations.add("".join(combo))

    variations_list = list(variations)
    if len(variations_list) < 20:
        for i in range(20 - len(variations_list)):
            variations_list.append(f"{normalized} {i+1}")
    return variations_list[:20]


def generate_related_words(description: str) -> List[str]:
    """Gera pelo menos 20 variações usando o modelo configurado do Ollama."""

    prompt = (
        "Liste pelo menos 20 variações de palavras ou frases que um cliente "
        f"poderia usar para se referir ao produto: '{description}'. Separe cada termo por vírgula."
    )

    try:
        client_args = {}
        if OLLAMA_HOST:
            client_args["host"] = OLLAMA_HOST
        client = ollama.Client(**client_args)
        response = client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response["message"]["content"]
        words = [w.strip().lower() for w in text.split(",") if w.strip()]
        if len(words) < 20:
            raise ValueError("menor que 20")
        return words[:20]
    except Exception as e:
        logging.warning(f"Falha ao gerar variações via IA: {e}")
        return _heuristic_related_words(description)


def build_knowledge_base() -> None:
    """Consulta todos os produtos e reescreve o arquivo de base de conhecimento."""

    logging.info("Gerando base de conhecimento a partir do banco de dados...")

    sql = "SELECT codprod, descricao FROM produtos WHERE status = 'ativo';"
    products: List[Dict] = []

    with database.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql)
            products = cursor.fetchall()

    kb: Dict[str, Dict] = {}
    for product in products:
        related = generate_related_words(product["descricao"])
        entry = {
            "codprod": product["codprod"],
            "canonical_name": product["descricao"],
            "related_words": related,
        }

        kb[product["descricao"].lower()] = entry
        for word in related:
            kb[word.lower()] = entry

    with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2, ensure_ascii=False)
    logging.info(
        f"Base de conhecimento gerada com {len(products)} produtos e {len(kb)} termos."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_knowledge_base()
