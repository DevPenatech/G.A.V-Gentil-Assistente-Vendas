# file: IA/knowledge.py
import json
import logging
from typing import Dict, Union

KNOWLEDGE_BASE_FILE = "IA/knowledge_base.json"
SEMANTIC_MAP_FILE = "IA/semantic_map.json"
_kb = None
_semantic_map = None

def _load_kb() -> Dict:
    global _kb
    if _kb is not None:
        return _kb
    try:
        with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
            _kb = json.load(f)
            logging.info(f"Base de conhecimento '{KNOWLEDGE_BASE_FILE}' carregada.")
            return _kb
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning(f"Arquivo '{KNOWLEDGE_BASE_FILE}' não encontrado. Iniciando com base vazia.")
        _kb = {}
        return _kb

def find_product_in_kb(term: str) -> Union[Dict, None]:
    kb = _load_kb()
    return kb.get(term.lower())

def update_kb(term: str, correct_product: Dict):
    if not term or not correct_product or not correct_product.get("codprod"):
        logging.warning(f"Tentativa de atualizar KB com dados inválidos.")
        return
    term_lower = term.lower()
    kb = _load_kb()
    synonyms = {term_lower, term_lower.replace("-", ""), term_lower.replace("-", " ")}
    new_entry = {
        "codprod": correct_product["codprod"],
        "canonical_name": correct_product["descricao"],
        "related_words": kb.get(term_lower, {}).get("related_words", [])
    }
    for synonym in synonyms:
        if synonym: kb[synonym] = new_entry
    try:
        with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
            logging.info(f"KB atualizado para os termos {list(synonyms)}")
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")

def load_semantic_map() -> Dict:
    """Carrega o mapa de sinônimos de um arquivo JSON externo."""
    global _semantic_map
    if _semantic_map is not None:
        return _semantic_map
    try:
        with open(SEMANTIC_MAP_FILE, 'r', encoding='utf-8') as f:
            _semantic_map = json.load(f)
            logging.info(f"Mapa semântico '{SEMANTIC_MAP_FILE}' carregado.")
            return _semantic_map
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning(f"Arquivo '{SEMANTIC_MAP_FILE}' não encontrado ou inválido.")
        _semantic_map = {}
        return _semantic_map
