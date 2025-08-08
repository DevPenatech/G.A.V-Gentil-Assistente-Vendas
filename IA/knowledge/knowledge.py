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
_kb: Optional[Dict[str, Dict]] = None
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

def _load_kb() -> Dict:
    """Load the knowledge base from disk into memory.

    If the file does not exist or is empty we attempt to rebuild it using the
    database.  The JSON file stores only canonical product names as keys, but in
    memory we also index each related word for faster lookup.
    """

    global _kb
    if _kb is not None:
        return _kb

    raw_kb: Dict[str, Dict] = {}
    try:
        if not KB_PATH.exists() or KB_PATH.stat().st_size == 0:
            raise FileNotFoundError
        with KB_PATH.open("r", encoding="utf-8") as f:
            raw_kb = json.load(f)
        if not raw_kb:
            raise ValueError("empty")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        logging.warning(
            f"Arquivo '{KB_PATH}' inexistente ou vazio. Reconstruindo base de conhecimento..."
        )
        try:
            build_knowledge_base()
            with KB_PATH.open("r", encoding="utf-8") as f:
                raw_kb = json.load(f)
        except Exception as e:
            logging.error(f"Falha ao construir base de conhecimento: {e}")
            raw_kb = {}

    kb: Dict[str, Dict] = {}
    for canonical, entry in raw_kb.items():
        kb[canonical.lower()] = entry
        for word in entry.get("related_words", []):
            kb[word.lower()] = entry

    _kb = kb
    logging.info(
        f"Base de conhecimento '{KB_PATH}' carregada com {len(raw_kb)} produtos e {len(kb)} termos."
    )
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

    term_normalized = term.lower()

    # Carrega o arquivo bruto (apenas nomes canônicos como chaves)
    try:
        with KB_PATH.open("r", encoding="utf-8") as f:
            raw_kb = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_kb = {}

    canonical_name = correct_product["descricao"]
    entry = raw_kb.get(
        canonical_name,
        {
            "codprod": correct_product["codprod"],
            "canonical_name": canonical_name,
            "related_words": [],
        },
    )

    if term_normalized not in entry["related_words"]:
        entry["related_words"].append(term_normalized)
    raw_kb[canonical_name] = entry

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

    try:
        with database.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql)
                products = cursor.fetchall()
    except Exception as e:
        logging.error(f"Falha ao consultar produtos: {e}")
        products = []

    kb: Dict[str, Dict] = {}
    for product in products:
        related = generate_related_words(product["descricao"])
        entry = {
            "codprod": product["codprod"],
            "canonical_name": product["descricao"],
            "related_words": related,
        }
        kb[product["descricao"]] = entry

    try:
        with KB_PATH.open("w", encoding="utf-8") as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
        logging.info(
            f"Base de conhecimento gerada com {len(products)} produtos."
        )
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")

    # Limpa o cache em memória para garantir recarregamento da nova base
    global _kb
    _kb = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_knowledge_base()
