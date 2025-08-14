# file: IA/knowledge/knowledge.py
"""
Base de Conhecimento Inteligente para o G.A.V.

Sistema aprimorado com:
- Busca tolerante a erros
- Enriquecimento automático com dados do banco
- Análise de qualidade das buscas
- Correção automática de termos
- Expansão com sinônimos
"""

import json
import logging
import os
import sys
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import ollama

# Adiciona paths necessários
utils_path = Path(__file__).resolve().parent.parent / "utils"
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))
    
from fuzzy_search import fuzzy_search_kb, fuzzy_engine, analyze_search_quality

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import database

# Configurações
KB_PATH = Path(__file__).resolve().parent / "knowledge_base.json"
_kb: Optional[Dict[str, List[Dict]]] = None
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

def _load_kb() -> Dict[str, List[Dict]]:
    """
    Carrega a base de conhecimento do disco para memória.
    
    IMPORTANTE: Agora cada termo pode mapear para MÚLTIPLOS produtos.
    Estrutura em memória otimizada para busca rápida.
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

    # Converte estrutura para busca otimizada
    # Em memória: {termo_busca: [lista_de_produtos]}
    indexed_kb = {}
    
    for canonical_name, product_data in raw_kb.items():
        codprod = product_data.get("codprod")
        if not codprod:
            continue
        
        # Produto base
        base_product = {
            "codprod": codprod,
            "canonical_name": canonical_name,
            "source": "knowledge_base"
        }
        
        # Indexa pelo nome canônico
        canonical_normalized = fuzzy_engine.normalize_text(canonical_name)
        if canonical_normalized not in indexed_kb:
            indexed_kb[canonical_normalized] = []
        indexed_kb[canonical_normalized].append(base_product)
        
        # Indexa por todas as palavras relacionadas
        related_words = product_data.get("related_words", [])
        for word in related_words:
            word_normalized = fuzzy_engine.normalize_text(word)
            if word_normalized and word_normalized not in indexed_kb:
                indexed_kb[word_normalized] = []
            indexed_kb[word_normalized].append(base_product)

    _kb = indexed_kb
    
    # Log estatísticas
    total_terms = len(indexed_kb)
    total_products = len(set(p["codprod"] for products in indexed_kb.values() for p in products))
    
    logging.info(f"Base de conhecimento '{KB_PATH}' carregada com {total_products} produtos e {total_terms} termos.")
    
    return _kb

def _enrich_kb_products_with_db_data(kb_products: List[Dict]) -> List[Dict]:
    """
    🆕 NOVA FUNÇÃO: Enriquece produtos da KB com dados atualizados do banco.
    """
    if not kb_products:
        return []
    
    enriched_products = []
    
    for kb_product in kb_products:
        codprod = kb_product.get("codprod")
        if not codprod:
            continue
        
        # Busca dados atualizados no banco
        db_product = database.get_product_by_codprod(codprod)
        
        if db_product:
            # Combina dados da KB com dados atualizados do banco
            enriched_product = {
                **db_product,  # Dados do banco (preços, status, etc.)
                "source": "knowledge_base_enriched",
                "canonical_name": kb_product.get("canonical_name")
            }
            enriched_products.append(enriched_product)
        else:
            # Se não encontrou no banco, mantém dados da KB
            logging.warning(f"Produto {codprod} da KB não encontrado no banco")
            enriched_products.append(kb_product)
    
    return enriched_products

def find_product_in_kb(term: str) -> List[Dict]:
    """
    🆕 NOVA VERSÃO com busca tolerante a erros e enriquecimento de dados!
    
    Args:
        term: Termo de busca (pode ter erros de digitação)
        
    Returns:
        Lista de produtos que correspondem ao termo, enriquecidos com dados do banco
    """
    if not term:
        return []
        
    kb = _load_kb()
    term_lower = term.lower().strip()
    
    # 🆕 ETAPA 1: Busca exata (mais rápida) - mantém compatibilidade
    term_normalized = fuzzy_engine.normalize_text(term)
    if term_normalized in kb:
        logging.info(f"[KB] Busca exata encontrou: {term_normalized}")
        kb_products = kb[term_normalized]
        return _enrich_kb_products_with_db_data(kb_products)
    
    # 🆕 ETAPA 2: Busca fuzzy com alta similaridade (0.8+)
    fuzzy_results = fuzzy_search_kb(term, kb, min_similarity=0.8)
    if fuzzy_results:
        logging.info(f"[KB] Busca fuzzy (alta) encontrou {len(fuzzy_results)} produtos para: {term}")
        return _enrich_kb_products_with_db_data(fuzzy_results)
    
    # 🆕 ETAPA 3: Busca fuzzy com similaridade média (0.6+)
    fuzzy_results = fuzzy_search_kb(term, kb, min_similarity=0.6)
    if fuzzy_results:
        logging.info(f"[KB] Busca fuzzy (média) encontrou {len(fuzzy_results)} produtos para: {term}")
        return _enrich_kb_products_with_db_data(fuzzy_results)
    
    # 🆕 ETAPA 4: Busca fuzzy relaxada (0.4+) - última chance
    fuzzy_results = fuzzy_search_kb(term, kb, min_similarity=0.4)
    if fuzzy_results:
        logging.info(f"[KB] Busca fuzzy (baixa) encontrou {len(fuzzy_results)} produtos para: {term}")
        return _enrich_kb_products_with_db_data(fuzzy_results)
    
    # 🆕 ETAPA 5: Busca por contenção simples (fallback original melhorado)
    matching_products = []
    seen_codprods = set()
    
    # Normaliza o termo de busca
    normalized_term = fuzzy_engine.normalize_text(term)
    corrected_term = fuzzy_engine.apply_corrections(normalized_term)
    
    for indexed_term, products in kb.items():
        # Normaliza o termo indexado
        normalized_indexed = fuzzy_engine.normalize_text(indexed_term)
        
        # Verifica se há contenção em qualquer direção
        if (corrected_term in normalized_indexed or 
            normalized_indexed in corrected_term or
            normalized_term in normalized_indexed):
            
            for product in products:
                codprod = product.get("codprod")
                if codprod and codprod not in seen_codprods:
                    matching_products.append(product)
                    seen_codprods.add(codprod)
    
    if matching_products:
        logging.info(f"[KB] Busca por contenção encontrou {len(matching_products)} produtos para: {term}")
        return _enrich_kb_products_with_db_data(matching_products)
    
    logging.info(f"[KB] Nenhum produto encontrado para: {term}")
    return []

def find_product_in_kb_with_analysis(term: str) -> Tuple[List[Dict], Dict]:
    """🆕 NOVA FUNÇÃO: Busca produtos e retorna análise da qualidade da busca."""
    products = find_product_in_kb(term)
    analysis = analyze_search_quality(term, products)
    return products, analysis

def update_kb(term: str, correct_product: Dict):
    """
    Atualiza persistentemente a base de conhecimento com nova associação.
    🆕 MELHORADA: Agora com melhor estrutura e validações.
    """
    if not term or not correct_product or not correct_product.get("codprod"):
        logging.warning("Tentativa de atualizar KB com dados inválidos.")
        return

    term_normalized = fuzzy_engine.normalize_text(term)

    # Carrega o arquivo bruto (apenas nomes canônicos como chaves)
    try:
        with KB_PATH.open("r", encoding="utf-8") as f:
            raw_kb = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_kb = {}

    # 🆕 COMPATIBILIDADE: Usa descricao ou canonical_name
    canonical_name = correct_product.get("descricao") or correct_product.get("canonical_name", f"Produto {correct_product['codprod']}")
    
    # Procura se já existe entrada para este produto
    entry = None
    entry_key = None
    for name, existing_entry in raw_kb.items():
        if existing_entry.get("codprod") == correct_product["codprod"]:
            entry = existing_entry
            entry_key = name
            break
    
    # Se não encontrou, cria nova entrada
    if entry is None:
        entry = {
            "codprod": correct_product["codprod"],
            "canonical_name": canonical_name,
            "related_words": [],
        }
        entry_key = canonical_name
        raw_kb[entry_key] = entry

    # Adiciona o novo termo se não existir
    existing_words = [fuzzy_engine.normalize_text(w) for w in entry["related_words"]]
    if term_normalized not in existing_words:
        entry["related_words"].append(term)
        logging.info(f"Adicionado termo '{term}' ao produto {canonical_name}")

    try:
        with KB_PATH.open("w", encoding="utf-8") as f:
            json.dump(raw_kb, f, indent=2, ensure_ascii=False)
        logging.info(f"KB atualizado com novo termo relacionado '{term}'")
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")

    # Limpa o cache em memória para refletir as mudanças
    global _kb
    _kb = None

def get_kb_statistics() -> Dict:
    """🆕 NOVA FUNÇÃO: Retorna estatísticas da base de conhecimento."""
    kb = _load_kb()
    
    if not kb:
        return {
            "total_terms": 0,
            "total_products": 0,
            "coverage": 0.0,
            "avg_terms_per_product": 0.0
        }
    
    total_terms = len(kb)
    product_codprods = set()
    term_counts = []
    
    for term, products in kb.items():
        for product in products:
            codprod = product.get("codprod")
            if codprod:
                product_codprods.add(codprod)
        term_counts.append(len(products))
    
    total_products = len(product_codprods)
    
    # Calcula cobertura em relação ao banco
    db_product_count = database.get_products_count()
    coverage = (total_products / db_product_count * 100) if db_product_count > 0 else 0.0
    
    # Média de termos por produto
    avg_terms = sum(term_counts) / len(term_counts) if term_counts else 0.0
    
    return {
        "total_terms": total_terms,
        "total_products": total_products,
        "total_products_in_db": db_product_count,
        "coverage_percentage": coverage,
        "avg_terms_per_product": avg_terms,
        "kb_file_size": KB_PATH.stat().st_size if KB_PATH.exists() else 0
    }

def optimize_kb():
    """🆕 NOVA FUNÇÃO: Otimiza a base de conhecimento removendo duplicatas e termos inválidos."""
    try:
        with KB_PATH.open("r", encoding="utf-8") as f:
            raw_kb = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.error("Não foi possível carregar KB para otimização")
        return False
    
    optimized_count = 0
    
    for canonical_name, product_data in raw_kb.items():
        if "related_words" not in product_data:
            continue
        
        original_words = product_data["related_words"]
        
        # Remove duplicatas (considerando normalização)
        unique_words = []
        seen_normalized = set()
        
        for word in original_words:
            if not word or len(word.strip()) < 2:
                continue
            
            normalized = fuzzy_engine.normalize_text(word)
            if normalized and normalized not in seen_normalized:
                unique_words.append(word.strip())
                seen_normalized.add(normalized)
        
        if len(unique_words) != len(original_words):
            product_data["related_words"] = unique_words
            optimized_count += 1
    
    # Salva KB otimizada
    try:
        with KB_PATH.open("w", encoding="utf-8") as f:
            json.dump(raw_kb, f, indent=2, ensure_ascii=False)
        
        logging.info(f"KB otimizada: {optimized_count} produtos processados")
        
        # Limpa cache
        global _kb
        _kb = None
        
        return True
        
    except Exception as e:
        logging.error(f"Erro ao salvar KB otimizada: {e}")
        return False

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
    for char in ["-", ".", "(", ")", "[", "]"]:
        if char in normalized:
            clean_version = normalized.replace(char, " ")
            variations.add(" ".join(clean_version.split()))
    
    # Adiciona tokens individuais significativos
    for token in tokens:
        if len(token) >= 3:
            variations.add(token)
    
    # Combinações de tokens adjacentes
    for i in range(len(tokens) - 1):
        combo = f"{tokens[i]} {tokens[i+1]}"
        variations.add(combo)
    
    # Remove strings muito curtas ou muito longas
    filtered_variations = [v for v in variations if 2 <= len(v) <= 50]
    
    return list(set(filtered_variations))[:15]  # Máximo 15 variações

def _generate_ai_variations(description: str) -> List[str]:
    """Gera variações usando IA (Ollama) com prompt otimizado."""
    if not OLLAMA_HOST:
        logging.warning("OLLAMA_HOST não configurado, usando variações heurísticas")
        return _heuristic_related_words(description)

    # Prompt otimizado para gerar variações
    prompt = f"""Gere variações de busca para o produto: "{description}"

Inclua:
- Abreviações comuns (ex: refri para refrigerante)
- Gírias e apelidos
- Variações de escrita
- Termos relacionados à marca/categoria
- Diferentes formas de escrever quantidades/medidas

Responda APENAS com uma lista JSON de strings, máximo 20 variações.
Exemplo: ["variacao1", "variacao2", "variacao3"]

Produto: {description}
Variações:"""

    try:
        client = ollama.Client(host=OLLAMA_HOST)
        response = client.chat(
            model=OLLAMA_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "max_tokens": 300}
        )
        
        content = response["message"]["content"].strip()
        
        # Extrai JSON da resposta
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            try:
                variations = json.loads(json_match.group(0))
                if isinstance(variations, list):
                    # Filtra e normaliza variações
                    valid_variations = []
                    for var in variations:
                        if isinstance(var, str) and 2 <= len(var.strip()) <= 50:
                            valid_variations.append(var.strip().lower())
                    
                    return valid_variations[:20]  # Máximo 20
            except json.JSONDecodeError:
                pass
    
    except Exception as e:
        logging.warning(f"Erro ao gerar variações com IA: {e}")
    
    # Fallback para heurística
    return _heuristic_related_words(description)

def rebuild_knowledge_base():
    """
    Reconstrói a base de conhecimento gravando incrementalmente no disco
    e permitindo interrupção segura com CTRL+C.
    """
    logging.info("=== INICIANDO GERAÇÃO DA BASE DE CONHECIMENTO (stream) ===")

    if KB_PATH.exists():
        backup_path = KB_PATH.with_suffix(".json.backup")
        try:
            import shutil
            shutil.copy2(KB_PATH, backup_path)
            logging.info(f"Backup criado: {backup_path}")
        except Exception as e:
            logging.warning(f"Falha ao criar backup: {e}")

    products = database.get_all_active_products()
    if not products:
        logging.error("Nenhum produto encontrado no banco de dados")
        return False

    temp_path = KB_PATH.with_suffix(".ndjson.tmp")
    processed_count = 0
    total_terms = 0

    try:
        with temp_path.open("w", encoding="utf-8") as f:
            try:
                for i, product in enumerate(products, 1):
                    codprod = product.get("codprod")
                    description = product.get("descricao", "")

                    if not codprod or not description:
                        continue

                    logging.info(f"Processando produto {i}/{len(products)}: {description}")

                    variations = _generate_ai_variations(description)
                    heuristic_vars = _heuristic_related_words(description)
                    all_variations = list(set(variations + heuristic_vars))[:25]

                    kb_entry = {
                        "codprod": codprod,
                        "canonical_name": description,
                        "related_words": all_variations
                    }

                    # Grava como NDJSON (1 produto por linha)
                    f.write(json.dumps({description: kb_entry}, ensure_ascii=False) + "\n")
                    f.flush()

                    processed_count += 1
                    total_terms += len(all_variations)

            except KeyboardInterrupt:
                logging.warning("⚠ Interrupção detectada (CTRL+C). Finalizando com dados parciais...")
                # Continua para gerar o arquivo final com o que já foi processado

        # Converte NDJSON para JSON final
        from collections import ChainMap
        with temp_path.open("r", encoding="utf-8") as f:
            final_data = dict(ChainMap(*[json.loads(line) for line in f]))

        with KB_PATH.open("w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)

        logging.info("=== BASE DE CONHECIMENTO GERADA COM SUCESSO ===")
        logging.info(f"Produtos processados: {processed_count}")
        logging.info(f"Total de termos relacionados: {total_terms}")

        global _kb
        _kb = None
        return True

    except Exception as e:
        logging.error(f"Erro ao gerar KB: {e}")
        return False
    finally:
        if temp_path.exists():
            temp_path.unlink()



def validate_kb_integrity() -> Dict:
    """🆕 NOVA FUNÇÃO: Valida integridade da base de conhecimento."""
    try:
        with KB_PATH.open("r", encoding="utf-8") as f:
            raw_kb = json.load(f)
    except Exception as e:
        return {"valid": False, "error": f"Erro ao carregar KB: {e}"}
    
    issues = []
    valid_entries = 0
    total_entries = len(raw_kb)
    
    for canonical_name, product_data in raw_kb.items():
        entry_issues = []
        
        # Verifica estrutura básica
        if not isinstance(product_data, dict):
            entry_issues.append("Entrada não é um dicionário")
            continue
        
        # Verifica campos obrigatórios
        if "codprod" not in product_data:
            entry_issues.append("Campo 'codprod' ausente")
        elif not isinstance(product_data["codprod"], int):
            entry_issues.append("Campo 'codprod' não é inteiro")
        
        if "related_words" not in product_data:
            entry_issues.append("Campo 'related_words' ausente")
        elif not isinstance(product_data["related_words"], list):
            entry_issues.append("Campo 'related_words' não é lista")
        
        # Verifica se produto existe no banco
        if "codprod" in product_data:
            db_product = database.get_product_by_codprod(product_data["codprod"])
            if not db_product:
                entry_issues.append(f"Produto {product_data['codprod']} não encontrado no banco")
        
        if entry_issues:
            issues.append({
                "canonical_name": canonical_name,
                "issues": entry_issues
            })
        else:
            valid_entries += 1
    
    return {
        "valid": len(issues) == 0,
        "total_entries": total_entries,
        "valid_entries": valid_entries,
        "invalid_entries": len(issues),
        "issues": issues[:10],  # Limita a 10 para não poluir log
        "integrity_score": (valid_entries / total_entries * 100) if total_entries > 0 else 0
    }

def search_kb_with_suggestions(term: str) -> Dict:
    """🆕 NOVA FUNÇÃO: Busca na KB com sugestões automáticas."""
    products = find_product_in_kb(term)
    
    result = {
        "products": products,
        "suggestions": [],
        "search_quality": "unknown"
    }
    
    if products:
        # Analisa qualidade da busca
        analysis = analyze_search_quality(term, products)
        result["search_quality"] = analysis.get("quality", "unknown")
        
        # Se qualidade baixa, adiciona sugestões
        if analysis.get("quality") in ["fair", "poor"]:
            result["suggestions"] = analysis.get("suggestions", [])
    else:
        # Nenhum produto encontrado - gera sugestões
        corrected = fuzzy_engine.apply_corrections(term)
        if corrected != fuzzy_engine.normalize_text(term):
            result["suggestions"].append(corrected)
        
        synonyms = fuzzy_engine.expand_with_synonyms(term)
        result["suggestions"].extend(synonyms[:2])
        
        result["search_quality"] = "no_results"
    
    return result

# Script principal para geração
if __name__ == "__main__":
    import sys
    
    # Configura logging para script
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler('knowledge_generation.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Executa geração da base de conhecimento
    success = rebuild_knowledge_base()
    
    if success:
        # Valida integridade
        validation = validate_kb_integrity()
        if validation["valid"]:
            logging.info("✅ Base de conhecimento gerada e validada com sucesso!")
        else:
            logging.warning(f"⚠️ Base gerada com {validation['invalid_entries']} problemas")
            
        # Mostra estatísticas
        stats = get_kb_statistics()
        logging.info(f"📊 Estatísticas: {stats['total_products']} produtos, {stats['total_terms']} termos, {stats['coverage_percentage']:.1f}% cobertura")
    else:
        logging.error("❌ Falha na geração da base de conhecimento")
        sys.exit(1)