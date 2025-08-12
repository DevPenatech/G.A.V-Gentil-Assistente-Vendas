# file: IA/utils/fuzzy_search.py
import re
import unicodedata
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher

class FuzzySearchEngine:
    """Sistema de busca fuzzy tolerante a erros de digitação e variações."""
    
    def __init__(self):
        # Mapeamento de correções comuns
        self.common_corrections = {
            # Erros de digitação comuns
            'coka': 'coca',
            'koka': 'coca', 
            'refri': 'refrigerante',
            'detergent': 'detergente',
            'sabao': 'sabão',
            'acucar': 'açúcar',
            'cafe': 'café',
            
            # Abreviações comuns
            'dt': 'detergente',
            'po': 'pó',
            'refrig': 'refrigerante',
            'lt': 'lata',
            'pet': 'garrafa',
            'kg': 'quilograma',
            'ml': 'mililitro',
            'l': 'litro',
            
            # Variações de marca
            'nescafe': 'nescafé',
            'nescau': 'nescaú',
            
            # Plurais e gênero
            'refrigerantes': 'refrigerante',
            'detergentes': 'detergente',
            'saboes': 'sabão',
            'sabões': 'sabão'
        }
        
        # Sinônimos
        self.synonyms = {
            'refrigerante': ['refri', 'refrig', 'soda', 'bebida'],
            'detergente': ['sabão', 'sabao', 'dt', 'limpeza'],
            'coca-cola': ['coca', 'cola', 'coke'],
            'açúcar': ['acucar', 'sugar'],
            'café': ['cafe', 'coffee'],
            'leite': ['milk'],
            'água': ['agua', 'water'],
            'arroz': ['rice'],
            'feijão': ['feijao', 'beans']
        }

    def normalize_text(self, text: str) -> str:
        """Normaliza texto removendo acentos, pontuação e espaços extras."""
        if not text:
            return ""
            
        # Remove acentos
        nfkd = unicodedata.normalize('NFD', text.lower())
        text_no_accents = ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')
        
        # Remove pontuação, mas mantém espaços e hífen
        text_clean = re.sub(r'[^\w\s-]', ' ', text_no_accents)
        
        # Remove hífen e substitui por espaço
        text_clean = text_clean.replace('-', ' ')
        
        # Remove espaços extras
        text_clean = ' '.join(text_clean.split())
        
        return text_clean

    def apply_corrections(self, text: str) -> str:
        """Aplica correções automáticas de erros comuns."""
        words = text.split()
        corrected_words = []
        
        for word in words:
            # Aplica correção se existir
            corrected = self.common_corrections.get(word, word)
            corrected_words.append(corrected)
        
        return ' '.join(corrected_words)

    def expand_with_synonyms(self, text: str) -> List[str]:
        """Expande o texto com sinônimos."""
        variations = [text]
        words = text.split()
        
        for word in words:
            # Busca sinônimos para a palavra
            for main_word, synonyms in self.synonyms.items():
                if word == main_word:
                    # Substitui a palavra principal por cada sinônimo
                    for synonym in synonyms:
                        new_text = text.replace(word, synonym)
                        if new_text not in variations:
                            variations.append(new_text)
                elif word in synonyms:
                    # Substitui sinônimo pela palavra principal
                    new_text = text.replace(word, main_word)
                    if new_text not in variations:
                        variations.append(new_text)
        
        return variations

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcula similaridade entre dois textos (0.0 a 1.0)."""
        if not text1 or not text2:
            return 0.0
            
        # Normaliza ambos os textos
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)
        
        # Aplica correções
        norm1 = self.apply_corrections(norm1)
        norm2 = self.apply_corrections(norm2)
        
        # Match exato após normalização
        if norm1 == norm2:
            return 1.0
        
        # Verifica se um está contido no outro
        if norm1 in norm2 or norm2 in norm1:
            return 0.9
        
        # Calcula similaridade de sequência
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Bonus para palavras comuns
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        common_words = words1.intersection(words2)
        
        if common_words:
            # Aumenta score se há palavras em comum
            word_bonus = len(common_words) / max(len(words1), len(words2))
            similarity = min(1.0, similarity + word_bonus * 0.2)
        
        return similarity

    def fuzzy_search_in_list(self, 
                           search_term: str, 
                           items: List[Dict], 
                           field_name: str = 'descricao',
                           min_similarity: float = 0.6,
                           max_results: int = 10) -> List[Tuple[Dict, float]]:
        """
        Busca fuzzy em uma lista de dicionários.
        
        Args:
            search_term: Termo a ser buscado
            items: Lista de dicionários para buscar
            field_name: Nome do campo para comparar
            min_similarity: Similaridade mínima (0.0 a 1.0)
            max_results: Número máximo de resultados
            
        Returns:
            Lista de tuplas (item, score) ordenada por relevância
        """
        if not search_term or not items:
            return []
        
        results = []
        
        # Expande termo de busca com sinônimos
        search_variations = self.expand_with_synonyms(search_term)
        
        for item in items:
            field_value = item.get(field_name, '')
            if not field_value:
                continue
            
            best_score = 0.0
            
            # Testa cada variação do termo de busca
            for variation in search_variations:
                score = self.calculate_similarity(variation, field_value)
                best_score = max(best_score, score)
                
                # Se encontrou match muito bom, não precisa testar outras variações
                if score >= 0.95:
                    break
            
            # Só adiciona se passou do threshold
            if best_score >= min_similarity:
                results.append((item, best_score))
        
        # Ordena por score (maior primeiro) e limita resultados
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_results]

    def fuzzy_search_in_knowledge_base(self, 
                                     search_term: str,
                                     kb: Dict[str, List[Dict]],
                                     min_similarity: float = 0.7) -> List[Dict]:
        """
        Busca fuzzy na knowledge base.
        
        Args:
            search_term: Termo de busca
            kb: Knowledge base (mapeamento termo -> lista de produtos)
            min_similarity: Similaridade mínima
            
        Returns:
            Lista de produtos encontrados, sem duplicatas
        """
        if not search_term or not kb:
            return []
        
        found_products = []
        seen_codprods = set()
        
        # Expande termo com sinônimos
        search_variations = self.expand_with_synonyms(search_term)
        
        # Para cada termo indexado na KB
        for indexed_term, products in kb.items():
            best_score = 0.0
            
            # Testa cada variação do termo de busca
            for variation in search_variations:
                score = self.calculate_similarity(variation, indexed_term)
                best_score = max(best_score, score)
                
                if score >= 0.95:  # Match muito bom
                    break
            
            # Se passou do threshold, adiciona os produtos
            if best_score >= min_similarity:
                for product in products:
                    codprod = product.get('codprod')
                    if codprod and codprod not in seen_codprods:
                        found_products.append((product, best_score))
                        seen_codprods.add(codprod)
        
        # Ordena por score e retorna apenas os produtos
        found_products.sort(key=lambda x: x[1], reverse=True)
        return [product for product, score in found_products]

# Instância global para reuso
fuzzy_engine = FuzzySearchEngine()

def fuzzy_search_products(search_term: str, 
                         products: List[Dict], 
                         min_similarity: float = 0.6,
                         max_results: int = 10) -> List[Dict]:
    """Função helper para busca fuzzy em produtos."""
    results = fuzzy_engine.fuzzy_search_in_list(
        search_term, products, 'descricao', min_similarity, max_results
    )
    return [product for product, score in results]

def fuzzy_search_kb(search_term: str, 
                   kb: Dict[str, List[Dict]],
                   min_similarity: float = 0.7) -> List[Dict]:
    """Função helper para busca fuzzy na knowledge base."""
    return fuzzy_engine.fuzzy_search_in_knowledge_base(search_term, kb, min_similarity)

# Teste direto se executado
if __name__ == "__main__":
    engine = FuzzySearchEngine()
    
    # Produtos de exemplo
    test_products = [
        {"codprod": 1, "descricao": "REFRIG.COCA-COLA PET 2L"},
        {"codprod": 2, "descricao": "REFRIG.COCA-COLA LT 350ML"},
        {"codprod": 3, "descricao": "DT.PO OMO LAVAGEM PERFEITA 1.6KG"},
        {"codprod": 4, "descricao": "AÇÚCAR CRISTAL UNIÃO 1KG"},
        {"codprod": 5, "descricao": "CAFÉ PILÃO TRADICIONAL 500G"}
    ]
    
    # Testes de busca
    test_cases = [
        "coca cola",      # Exato
        "coka",           # Erro de digitação
        "refri coca",     # Sinônimo
        "detergent omo",  # Erro + marca
        "acucar",         # Sem acento
        "cafe",           # Sem acento
    ]
    
    print("🔍 TESTE DE BUSCA FUZZY")
    print("=" * 60)
    
    for search_term in test_cases:
        print(f"\n🔎 Buscando: '{search_term}'")
        results = fuzzy_search_products(search_term, test_products, min_similarity=0.5)
        
        if results:
            for i, product in enumerate(results[:3], 1):
                score = engine.calculate_similarity(search_term, product['descricao'])
                print(f"  {i}. {product['descricao']} (score: {score:.2f})")
        else:
            print("  Nenhum resultado encontrado")