# file: IA/utils/fuzzy_search.py
"""
Sistema de busca fuzzy tolerante a erros para o G.A.V.
Implementa correção automática, busca por similaridade e expansão com sinônimos.
"""

import re
import unicodedata
import logging
from typing import List, Dict, Tuple
from difflib import SequenceMatcher

# Dicionário de correções comuns
COMMON_CORRECTIONS = {
    # Erros de digitação comuns
    'coca-cola': ['coca cola', 'cocacola', 'cokacola', 'coca kola'],
    'refrigerante': ['refri', 'regrigerante', 'refriferante'],
    'detergente': ['detergente', 'ditergente'],
    'sabão': ['sabao', 'xampu'],
    'açúcar': ['acucar', 'azucar'],
    'óleo': ['oleo'],
    'água': ['agua'],
    'pão': ['pao'],
    
    # Marcas e produtos específicos
    'omo': ['omô', 'homo'],
    'coca': ['koca', 'coka'],
    'pepsi': ['pepssi', 'pepci'],
    'guaraná': ['guarana', 'guaranah'],
    
    # Unidades e medidas
    '2l': ['2 litros', '2lt', '2 l'],
    '350ml': ['350 ml', '350ml', 'lata'],
    'pet': ['garrafa', 'garrafa pet'],
    'lata': ['latinha', 'lt'],
    
    # Gírias e abreviações
    'refri': ['refrigerante', 'refriferante'],
    'zero': ['diet', 'sem açúcar', 'sem acucar'],
    'light': ['diet', 'zero'],
}

# Sinônimos expandidos
SYNONYMS = {
    'refrigerante': ['refri', 'bebida', 'soda'],
    'coca cola': ['coca', 'coke'],
    'detergente': ['sabão', 'limpeza'],
    'óleo': ['azeite'],
    'açúcar': ['adoçante', 'cristal'],
    'água': ['agua mineral'],
    'limpeza': ['detergente', 'sabão', 'produtos de limpeza'],
    'bebida': ['refrigerante', 'suco', 'água'],
    'alimento': ['comida', 'produto alimentício'],
    'higiene': ['produtos de higiene', 'limpeza pessoal']
}

class FuzzySearchEngine:
    """Motor de busca fuzzy com correções automáticas e sinônimos."""
    
    def __init__(self):
        self.correction_cache = {}
        self.similarity_cache = {}
        
    def normalize_text(self, text: str) -> str:
        """Normaliza texto removendo acentos, pontuação e padronizando."""
        if not text:
            return ""
        
        # Remove acentos
        nfkd = unicodedata.normalize('NFD', text.lower())
        ascii_text = ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')
        
        # Remove pontuação e caracteres especiais, mantém espaços
        cleaned = re.sub(r'[^\w\s]', ' ', ascii_text)
        
        # Normaliza espaços
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcula similaridade entre dois textos (0-1)."""
        if not text1 or not text2:
            return 0.0
        
        # Usa cache para evitar recálculos
        cache_key = f"{text1}|||{text2}"
        if cache_key in self.similarity_cache:
            return self.similarity_cache[cache_key]
        
        # Normaliza textos
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)
        
        if norm1 == norm2:
            similarity = 1.0
        else:
            # Combina diferentes métricas de similaridade
            
            # 1. Similaridade de sequência
            seq_sim = SequenceMatcher(None, norm1, norm2).ratio()
            
            # 2. Similaridade de palavras (Jaccard)
            words1 = set(norm1.split())
            words2 = set(norm2.split())
            if words1 or words2:
                jaccard_sim = len(words1 & words2) / len(words1 | words2)
            else:
                jaccard_sim = 0.0
            
            # 3. Similaridade de contenção
            if norm1 in norm2 or norm2 in norm1:
                contain_sim = 0.8
            else:
                contain_sim = 0.0
            
            # 4. Similaridade de prefixo/sufixo
            prefix_sim = 0.0
            if len(norm1) >= 3 and len(norm2) >= 3:
                if norm1[:3] == norm2[:3]:
                    prefix_sim = 0.3
                if norm1[-3:] == norm2[-3:]:
                    prefix_sim += 0.2
            
            # Combina métricas com pesos
            similarity = (
                seq_sim * 0.4 +
                jaccard_sim * 0.3 +
                contain_sim * 0.2 +
                prefix_sim * 0.1
            )
        
        # Armazena no cache
        self.similarity_cache[cache_key] = similarity
        return similarity
    
    def apply_corrections(self, text: str) -> str:
        """Aplica correções automáticas para erros comuns."""
        if not text:
            return text
        
        # Usa cache
        if text in self.correction_cache:
            return self.correction_cache[text]
        
        normalized = self.normalize_text(text)
        corrected = normalized
        
        # Aplica correções diretas
        for correct_term, variations in COMMON_CORRECTIONS.items():
            for variation in variations:
                if self.normalize_text(variation) == normalized:
                    corrected = correct_term
                    break
            if corrected != normalized:
                break
        
        # Correções baseadas em padrões
        if corrected == normalized:
            # Correção de unidades comuns
            corrected = re.sub(r'\b(\d+)\s*l\b', r'\1 litros', corrected)
            corrected = re.sub(r'\b(\d+)\s*ml\b', r'\1ml', corrected)
            corrected = re.sub(r'\b(\d+)\s*kg\b', r'\1kg', corrected)
            
            # Correção de duplicações
            corrected = re.sub(r'\b(\w+)\s+\1\b', r'\1', corrected)
            
            # Correção de espaços em marcas
            corrected = re.sub(r'\bcoca\s+cola\b', 'coca cola', corrected)
            corrected = re.sub(r'\bomô\b', 'omo', corrected)
        
        # Armazena no cache
        self.correction_cache[text] = corrected
        return corrected
    
    def expand_with_synonyms(self, text: str) -> List[str]:
        """Expande termo com sinônimos relacionados."""
        if not text:
            return []
        
        normalized = self.normalize_text(text)
        expansions = [normalized]
        
        # Busca sinônimos diretos
        for base_term, synonym_list in SYNONYMS.items():
            if self.normalize_text(base_term) == normalized:
                expansions.extend(synonym_list)
                break
            
            # Verifica se o termo está na lista de sinônimos
            for synonym in synonym_list:
                if self.normalize_text(synonym) == normalized:
                    expansions.append(base_term)
                    expansions.extend([s for s in synonym_list if s != synonym])
                    break
        
        # Expansão baseada em palavras-chave
        words = normalized.split()
        for word in words:
            if len(word) >= 4:  # Só palavras significativas
                for base_term, synonym_list in SYNONYMS.items():
                    if word in self.normalize_text(base_term):
                        expansions.extend(synonym_list)
        
        # Remove duplicatas e o termo original
        unique_expansions = []
        seen = set()
        for exp in expansions:
            norm_exp = self.normalize_text(exp)
            if norm_exp and norm_exp not in seen:
                unique_expansions.append(exp)
                seen.add(norm_exp)
        
        return unique_expansions[:5]  # Limita para evitar muitas opções
    
    def generate_search_variations(self, text: str) -> List[str]:
        """Gera variações de busca para um termo."""
        if not text:
            return []
        
        variations = []
        normalized = self.normalize_text(text)
        
        # Termo original normalizado
        variations.append(normalized)
        
        # Termo corrigido
        corrected = self.apply_corrections(text)
        if corrected != normalized:
            variations.append(corrected)
        
        # Sinônimos
        synonyms = self.expand_with_synonyms(text)
        variations.extend(synonyms)
        
        # Variações de palavras individuais
        words = normalized.split()
        if len(words) > 1:
            # Cada palavra individualmente
            variations.extend(words)
            
            # Combinações de 2 palavras
            for i in range(len(words) - 1):
                variations.append(f"{words[i]} {words[i+1]}")
        
        # Remove duplicatas
        unique_variations = []
        seen = set()
        for var in variations:
            norm_var = self.normalize_text(var)
            if norm_var and norm_var not in seen and len(norm_var) >= 2:
                unique_variations.append(var)
                seen.add(norm_var)
        
        return unique_variations
    
    def find_best_matches(self, search_term: str, candidate_list: List[str], 
                         min_similarity: float = 0.6, max_results: int = 5) -> List[Tuple[str, float]]:
        """Encontra as melhores correspondências em uma lista de candidatos."""
        if not search_term or not candidate_list:
            return []
        
        matches = []
        for candidate in candidate_list:
            similarity = self.calculate_similarity(search_term, candidate)
            if similarity >= min_similarity:
                matches.append((candidate, similarity))
        
        # Ordena por similaridade (maior primeiro)
        matches.sort(key=lambda x: x[1], reverse=True)
        
        return matches[:max_results]

# Instância global do motor de busca
fuzzy_engine = FuzzySearchEngine()

def fuzzy_search_kb(search_term: str, knowledge_base: Dict, min_similarity: float = 0.6) -> List[Dict]:
    """
    Busca fuzzy na base de conhecimento.
    
    Args:
        search_term: Termo de busca
        knowledge_base: Base de conhecimento carregada
        min_similarity: Similaridade mínima (0-1)
        
    Returns:
        Lista de produtos que correspondem ao termo
    """
    if not search_term or not knowledge_base:
        return []
    
    logging.info(f"[FUZZY] Iniciando busca fuzzy para: '{search_term}'")
    
    # Gera variações do termo de busca
    search_variations = fuzzy_engine.generate_search_variations(search_term)
    
    matching_products = []
    seen_codprods = set()
    
    # Para cada variação, busca na KB
    for variation in search_variations:
        normalized_variation = fuzzy_engine.normalize_text(variation)
        
        # Busca exata primeiro
        if normalized_variation in knowledge_base:
            products = knowledge_base[normalized_variation]
            for product in products:
                codprod = product.get("codprod")
                if codprod and codprod not in seen_codprods:
                    matching_products.append(product)
                    seen_codprods.add(codprod)
        
        # Busca por similaridade
        for kb_term, products in knowledge_base.items():
            similarity = fuzzy_engine.calculate_similarity(normalized_variation, kb_term)
            
            if similarity >= min_similarity:
                for product in products:
                    codprod = product.get("codprod")
                    if codprod and codprod not in seen_codprods:
                        # Adiciona score de similaridade ao produto
                        product_with_score = product.copy()
                        product_with_score["fuzzy_score"] = similarity
                        product_with_score["matched_term"] = kb_term
                        matching_products.append(product_with_score)
                        seen_codprods.add(codprod)
    
    # Ordena por score de similaridade se disponível
    matching_products.sort(key=lambda p: p.get("fuzzy_score", 0), reverse=True)
    
    logging.info(f"[FUZZY] Encontrados {len(matching_products)} produtos com similaridade >= {min_similarity}")
    
    return matching_products

def fuzzy_search_products(search_term: str, limit: int = 10) -> List[Dict]:
    """
    Busca fuzzy diretamente no banco de dados.
    
    Args:
        search_term: Termo de busca
        limit: Número máximo de resultados
        
    Returns:
        Lista de produtos encontrados
    """
    # Import local para evitar dependência circular
    from db.database import get_all_active_products
    
    if not search_term or len(search_term.strip()) < 2:
        return []
    
    logging.info(f"[FUZZY] Busca fuzzy no banco para: '{search_term}'")
    
    # Busca todos os produtos ativos
    all_products = get_all_active_products()
    if not all_products:
        return []
    
    # Gera variações do termo de busca
    search_variations = fuzzy_engine.generate_search_variations(search_term)
    
    scored_products = []
    seen_codprods = set()
    
    for product in all_products:
        product_name = product.get('descricao', '')
        if not product_name:
            continue
        
        codprod = product.get('codprod')
        if codprod in seen_codprods:
            continue
        
        max_similarity = 0.0
        best_match_variation = ""
        
        # Testa todas as variações de busca contra o nome do produto
        for variation in search_variations:
            similarity = fuzzy_engine.calculate_similarity(variation, product_name)
            if similarity > max_similarity:
                max_similarity = similarity
                best_match_variation = variation
        
        # Se passou do limiar mínimo, adiciona à lista
        if max_similarity >= 0.4:  # Limiar mais baixo para busca no banco
            product_with_score = product.copy()
            product_with_score["fuzzy_score"] = max_similarity
            product_with_score["matched_variation"] = best_match_variation
            scored_products.append(product_with_score)
            seen_codprods.add(codprod)
    
    # Ordena por score e limita resultados
    scored_products.sort(key=lambda p: p["fuzzy_score"], reverse=True)
    
    result = scored_products[:limit]
    
    logging.info(f"[FUZZY] Retornando {len(result)} produtos do banco")
    
    return result

def suggest_corrections(search_term: str, max_suggestions: int = 3) -> List[str]:
    """
    Sugere correções para um termo de busca.
    
    Args:
        search_term: Termo original
        max_suggestions: Número máximo de sugestões
        
    Returns:
        Lista de sugestões de correção
    """
    if not search_term:
        return []
    
    suggestions = []
    
    # Correção automática
    corrected = fuzzy_engine.apply_corrections(search_term)
    if corrected != fuzzy_engine.normalize_text(search_term):
        suggestions.append(corrected)
    
    # Sinônimos
    synonyms = fuzzy_engine.expand_with_synonyms(search_term)
    suggestions.extend(synonyms[:2])  # Máximo 2 sinônimos
    
    # Remove duplicatas
    unique_suggestions = []
    seen = set()
    for suggestion in suggestions:
        norm_sugg = fuzzy_engine.normalize_text(suggestion)
        if norm_sugg and norm_sugg not in seen:
            unique_suggestions.append(suggestion)
            seen.add(norm_sugg)
    
    return unique_suggestions[:max_suggestions]

def analyze_search_quality(search_term: str, found_products: List[Dict]) -> Dict:
    """
    Analisa a qualidade dos resultados de uma busca.
    
    Args:
        search_term: Termo buscado
        found_products: Produtos encontrados
        
    Returns:
        Análise da qualidade da busca
    """
    if not search_term:
        return {"quality": "invalid", "details": "Termo de busca vazio"}
    
    if not found_products:
        return {
            "quality": "no_results",
            "details": "Nenhum produto encontrado",
            "suggestions": suggest_corrections(search_term)
        }
    
    # Calcula scores de similaridade
    similarities = []
    for product in found_products:
        if "fuzzy_score" in product:
            similarities.append(product["fuzzy_score"])
        else:
            # Calcula similaridade com o nome do produto
            product_name = product.get('descricao') or product.get('canonical_name', '')
            if product_name:
                similarity = fuzzy_engine.calculate_similarity(search_term, product_name)
                similarities.append(similarity)
    
    if not similarities:
        return {"quality": "unknown", "details": "Não foi possível calcular similaridade"}
    
    avg_similarity = sum(similarities) / len(similarities)
    max_similarity = max(similarities)
    
    # Classifica qualidade baseada na similaridade
    if max_similarity >= 0.9:
        quality = "excellent"
    elif max_similarity >= 0.7:
        quality = "good"
    elif max_similarity >= 0.5:
        quality = "fair"
    else:
        quality = "poor"
    
    analysis = {
        "quality": quality,
        "max_similarity": max_similarity,
        "avg_similarity": avg_similarity,
        "total_results": len(found_products),
        "details": f"Melhor correspondência: {max_similarity:.2f}"
    }
    
    # Adiciona sugestões para qualidades baixas
    if quality in ["fair", "poor"]:
        analysis["suggestions"] = suggest_corrections(search_term)
    
    return analysis

def optimize_search_term(search_term: str) -> str:
    """
    Otimiza um termo de busca aplicando as melhores práticas.
    
    Args:
        search_term: Termo original
        
    Returns:
        Termo otimizado
    """
    if not search_term:
        return ""
    
    # Normaliza
    optimized = fuzzy_engine.normalize_text(search_term)
    
    # Aplica correções
    optimized = fuzzy_engine.apply_corrections(optimized)
    
    # Remove palavras muito curtas (menos de 2 caracteres)
    words = optimized.split()
    meaningful_words = [word for word in words if len(word) >= 2]
    
    return ' '.join(meaningful_words)

# Funções de conveniência para uso externo
def quick_fuzzy_search(search_term: str, limit: int = 10) -> List[Dict]:
    """Busca fuzzy rápida combinando KB e banco de dados."""
    # Primeiro tenta a KB
    from knowledge.knowledge import find_product_in_kb
    
    kb_results = find_product_in_kb(search_term)
    if kb_results and len(kb_results) >= limit:
        return kb_results[:limit]
    
    # Complementa com busca no banco
    db_results = fuzzy_search_products(search_term, limit - len(kb_results))
    
    # Combina resultados, removendo duplicatas
    combined_results = list(kb_results)
    kb_codprods = {p.get('codprod') for p in kb_results}
    
    for db_product in db_results:
        if db_product.get('codprod') not in kb_codprods:
            combined_results.append(db_product)
    
    return combined_results[:limit]