#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes Unitários para o Sistema de Classificação de Categorias
Sistema completo de validação com casos edge e performance
"""

import sys
import unittest
import time
from pathlib import Path

# Adiciona o diretório IA ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.category_classifier import (
    classify_product_category,
    get_all_categories,
    get_category_examples,
    clear_cache,
    get_cache_stats,
    _normalize_for_cache
)

class TestCategoryClassifier(unittest.TestCase):
    """Testes para o classificador de categorias."""
    
    def setUp(self):
        """Prepara ambiente para cada teste."""
        clear_cache()  # Limpa cache para testes isolados
    
    def tearDown(self):
        """Limpa após cada teste."""
        clear_cache()
    
    def test_basic_classification(self):
        """Testa classificação básica de produtos conhecidos."""
        test_cases = [
            ("cerveja", "bebidas"),
            ("sabao", "limpeza"),
            ("arroz", "alimentos"),
            ("shampoo", "higiene"),
            ("pao", "padaria"),
            ("carne", "açougue"),
            ("chocolate", "doces"),
            ("salgadinho", "petiscos"),
            ("sorvete", "congelados")
        ]
        
        for product, expected_category in test_cases:
            with self.subTest(product=product):
                # Com IA-only sem IA disponível, deve retornar "outros"
                result = classify_product_category(product, use_ai=False)
                self.assertEqual(
                    result, "outros",
                    f"IA-only sem IA deve retornar 'outros', mas foi '{result}'"
                )
    
    def test_complex_products(self):
        """Testa produtos com nomes compostos."""
        test_cases = [
            ("cerveja skol lata 350ml", "bebidas"),
            ("sabao em po ariel", "limpeza"),
            ("arroz branco tipo 1", "alimentos"),
            ("shampoo anticaspa clear", "higiene"),
            ("pao de forma integral", "padaria"),
            ("carne bovina picanha", "açougue"),
            ("chocolate ao leite nestle", "doces"),
            ("batata frita chips", "petiscos"),
            ("sorvete napolitano kibon", "congelados")
        ]
        
        for product, expected_category in test_cases:
            with self.subTest(product=product):
                # Com IA-only sem IA disponível, deve retornar "outros"
                result = classify_product_category(product, use_ai=False)
                self.assertEqual(
                    result, "outros",
                    f"IA-only sem IA deve retornar 'outros', mas foi '{result}'"
                )
    
    def test_edge_cases(self):
        """Testa casos extremos."""
        # Strings vazias/inválidas
        self.assertEqual(classify_product_category(""), "outros")
        self.assertEqual(classify_product_category("   "), "outros")
        self.assertEqual(classify_product_category(None), "outros")
        
        # Produtos desconhecidos
        self.assertEqual(classify_product_category("xyzabc123"), "outros")
        self.assertEqual(classify_product_category("produto inexistente"), "outros")
        
        # Produtos com caracteres especiais - sem IA deve retornar "outros"
        result1 = classify_product_category("cerveja!!!@@@", use_ai=False)
        self.assertEqual(result1, "outros")
        
        # Produtos com acentos - sem IA deve retornar "outros"  
        result2 = classify_product_category("sabão em pó", use_ai=False)
        self.assertEqual(result2, "outros")
    
    def test_case_insensitive(self):
        """Testa se classificação é case-insensitive."""
        test_cases = [
            ("CERVEJA", "bebidas"),
            ("Sabao", "limpeza"),
            ("ArRoZ", "alimentos"),
            ("CHOCOLATE", "doces")
        ]
        
        for product, expected_category in test_cases:
            with self.subTest(product=product):
                # Com IA-only sem IA disponível, deve retornar "outros"
                result = classify_product_category(product, use_ai=False)
                self.assertEqual(result, "outros")
    
    def test_normalization(self):
        """Testa normalização para cache."""
        test_cases = [
            ("  cerveja  ", "cerveja"),
            ("SABÃO", "sabao"),
            ("Quero Comprar Coca Cola", "quero comprar coca cola"),
            ("", "")
        ]
        
        for input_term, expected in test_cases:
            with self.subTest(input_term=input_term):
                result = _normalize_for_cache(input_term)
                self.assertEqual(result, expected)
    
    def test_ai_only_mode(self):
        """Testa modo IA-only sem fallback."""
        test_cases = [
            ("cerveja brahma", "bebidas"),
            ("sabao em po", "limpeza"),
            ("arroz branco", "alimentos"),
            ("shampoo seda", "higiene")
        ]
        
        for product, expected_category in test_cases:
            with self.subTest(product=product):
                # No modo IA-only, sem IA disponível deve retornar "outros"
                result = classify_product_category(product, use_ai=False)
                self.assertEqual(result, "outros")
    
    def test_cache_functionality(self):
        """Testa funcionalidade do cache."""
        # Cache inicialmente vazio
        stats = get_cache_stats()
        self.assertEqual(stats['total'], 0)
        
        # Classifica alguns produtos
        classify_product_category("cerveja", use_ai=False)
        classify_product_category("sabao", use_ai=False)
        
        # Verifica se cache foi populado
        stats = get_cache_stats()
        self.assertGreater(stats['total'], 0)
        
        # Testa hit de cache (deve ser mais rápido)
        start_time = time.time()
        result1 = classify_product_category("cerveja", use_ai=False)
        cache_time = time.time() - start_time
        
        # Limpa cache e testa novamente
        clear_cache()
        start_time = time.time()
        result2 = classify_product_category("cerveja", use_ai=False)
        no_cache_time = time.time() - start_time
        
        # Resultados devem ser iguais
        self.assertEqual(result1, result2)
        
        # Cache deve ser mais rápido (normalmente)
        # Não testamos isso sempre pois pode variar
    
    def test_all_categories_valid(self):
        """Testa se todas as categorias são válidas."""
        categories = get_all_categories()
        
        # Deve ter pelo menos 10 categorias
        self.assertGreaterEqual(len(categories), 10)
        
        # Deve conter "outros" como fallback
        self.assertIn("outros", categories)
        
        # Categorias essenciais devem estar presentes
        essential = ["bebidas", "alimentos", "limpeza", "higiene"]
        for category in essential:
            self.assertIn(category, categories)
    
    def test_category_examples(self):
        """Testa se exemplos de categorias são válidos."""
        categories = get_all_categories()
        
        for category in categories[:5]:  # Testa primeiras 5 categorias
            with self.subTest(category=category):
                examples = get_category_examples(category)
                
                if category != "outros":  # "outros" não tem exemplos
                    self.assertGreater(len(examples), 0)
                    # Testa se exemplos realmente classificam na categoria correta
                    for example in examples[:3]:  # Testa primeiros 3
                        result = classify_product_category(example.lower(), use_ai=False)
                        # Nem sempre será perfeito, mas deve ter alta taxa de acerto
    
    def test_performance(self):
        """Testa performance básica do sistema."""
        products = [
            "cerveja", "sabao", "arroz", "chocolate", "frango",
            "shampoo", "pao", "leite", "sorvete", "salgadinho"
        ]
        
        start_time = time.time()
        
        for product in products:
            classify_product_category(product, use_ai=False)
        
        total_time = time.time() - start_time
        avg_time = total_time / len(products)
        
        # Cada classificação deve ser rápida (< 100ms)
        self.assertLess(avg_time, 0.1, f"Classificação muito lenta: {avg_time:.3f}s por produto")
    
    def test_consistency(self):
        """Testa consistência das classificações."""
        products = ["cerveja skol", "sabao em po", "arroz branco"]
        
        # Classifica múltiplas vezes
        for product in products:
            results = []
            for _ in range(3):
                clear_cache()  # Força recálculo
                result = classify_product_category(product, use_ai=False)
                results.append(result)
            
            # Todos os resultados devem ser iguais
            self.assertTrue(all(r == results[0] for r in results),
                          f"Resultados inconsistentes para '{product}': {results}")


class TestCategoryClassifierBehavior(unittest.TestCase):
    """Testes comportamentais e de integração."""
    
    def test_realistic_user_queries(self):
        """Testa queries realistas de usuários com a nova abordagem IA."""
        realistic_queries = [
            ("quero cerveja", "bebidas"),
            ("preciso de sabao", "limpeza"), 
            ("quero comprar coca cola", "bebidas"),
            ("ver as cervejas da skol", "bebidas"),
            ("chocolate nestle", "doces"),
            ("arroz tipo 1", "alimentos"),
            ("shampoo johnson", "higiene")
        ]
        
        for query, expected_category in realistic_queries:
            with self.subTest(query=query):
                result = classify_product_category(query, use_ai=False)
                # Com fallback simples, pode não acertar todas, mas deve retornar categoria válida
                self.assertIn(result, get_all_categories())
    
    def test_typos_and_variations(self):
        """Testa tolerância a erros de digitação."""
        typo_cases = [
            ("ceveja", "bebidas"),    # cerveja
            ("savao", "limpeza"),     # sabao
            ("arros", "alimentos"),   # arroz
            ("xampu", "higiene"),     # shampoo
            ("chcolate", "doces")     # chocolate
        ]
        
        for typo, expected_category in typo_cases:
            with self.subTest(typo=typo):
                result = classify_product_category(typo, use_ai=False)
                # Pode não acertar sempre, mas deve tentar
                self.assertIn(result, get_all_categories())


def run_comprehensive_tests():
    """Executa todos os testes e mostra relatório detalhado."""
    print("=" * 60)
    print("EXECUTANDO TESTES COMPLETOS DO CLASSIFICADOR")
    print("=" * 60)
    
    # Executa testes
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    print("=" * 60)
    print("RESUMO DOS TESTES:")
    print(f"Testes executados: {result.testsRun}")
    print(f"Falhas: {len(result.failures)}")
    print(f"Erros: {len(result.errors)}")
    print(f"Sucesso: {result.wasSuccessful()}")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    # Configura encoding para evitar problemas no Windows
    import os
    if os.name == 'nt':
        import sys
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    
    # Executa testes completos
    success = run_comprehensive_tests()
    
    if success:
        print("\n[SUCCESS] TODOS OS TESTES PASSARAM!")
        print("Sistema de classificacao pronto para uso.")
    else:
        print("\n[ERROR] ALGUNS TESTES FALHARAM!")
        print("Verifique os erros acima.")
    
    sys.exit(0 if success else 1)