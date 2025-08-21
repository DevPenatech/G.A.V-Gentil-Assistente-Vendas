#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste do Sistema de Confiança e Score de Decisão
Testa casos reais dos logs para verificar o funcionamento
"""

import sys
import os

# Adiciona o diretório IA ao path para importar módulos
sys.path.append(os.path.join(os.path.dirname(__file__), 'IA'))

from utils.classificador_intencao import detectar_intencao_usuario_com_ia, get_confidence_statistics

def test_confidence_system():
    """Testa o sistema de confiança com casos reais dos logs."""
    
    print("TESTE DO SISTEMA DE CONFIANCA E SCORE DE DECISAO")
    print("=" * 60)
    
    # Casos reais extraídos dos logs
    test_cases = [
        # Casos de alta confiança esperada
        {"message": "carrinho", "context": "", "expected_confidence": "> 0.8"},
        {"message": "3", "context": "lista de produtos mostrada", "expected_confidence": "> 0.9"},
        {"message": "finalizar", "context": "itens no carrinho", "expected_confidence": "> 0.8"},
        {"message": "limpar carrinho", "context": "", "expected_confidence": "> 0.9"},
        
        # Casos reais dos logs com média confiança
        {"message": "tem cerveja?", "context": "", "expected_confidence": "0.7-0.9"},
        {"message": "tem promoção?", "context": "", "expected_confidence": "0.7-0.9"},
        {"message": "voce tem?", "context": "conversa sobre produtos", "expected_confidence": "0.5-0.8"},
        
        # Casos de baixa confiança esperada
        {"message": "meu cnpj", "context": "", "expected_confidence": "< 0.7"},
        {"message": "abc xyz", "context": "", "expected_confidence": "< 0.6"},
        {"message": "", "context": "", "expected_confidence": "< 0.5"},
        
        # Casos contextuais
        {"message": "2", "context": "Bot: Escolha um produto: 1. Skol 2. Heineken", "expected_confidence": "> 0.9"},
        {"message": "mais", "context": "Lista de produtos exibida anteriormente", "expected_confidence": "> 0.8"},
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTESTE {i}: '{test_case['message']}'")
        print(f"   Contexto: {test_case['context'] or 'Nenhum'}")
        print(f"   Confianca esperada: {test_case['expected_confidence']}")
        
        try:
            # Detecta intenção com sistema de confiança
            result = detectar_intencao_usuario_com_ia(
                test_case['message'], 
                test_case['context']
            )
            
            # Mostra resultados
            confidence = result.get('confidence_score', 0.0)
            strategy = result.get('decision_strategy', 'unknown')
            tool = result.get('nome_ferramenta', 'unknown')
            
            print(f"   Ferramenta: {tool}")
            print(f"   Confianca: {confidence:.3f}")
            print(f"   Estrategia: {strategy}")
            
            # Avalia se a confiança está no range esperado
            expected = test_case['expected_confidence']
            if "> 0.9" in expected and confidence > 0.9:
                print(f"   CORRETO: Confianca alta como esperado")
            elif "> 0.8" in expected and confidence > 0.8:
                print(f"   CORRETO: Confianca alta como esperado")
            elif "0.7-0.9" in expected and 0.7 <= confidence <= 0.9:
                print(f"   CORRETO: Confianca media como esperado")
            elif "0.5-0.8" in expected and 0.5 <= confidence <= 0.8:
                print(f"   CORRETO: Confianca media-baixa como esperado")
            elif "< 0.7" in expected and confidence < 0.7:
                print(f"   CORRETO: Confianca baixa como esperado")
            elif "< 0.6" in expected and confidence < 0.6:
                print(f"   CORRETO: Confianca baixa como esperado")
            elif "< 0.5" in expected and confidence < 0.5:
                print(f"   CORRETO: Confianca muito baixa como esperado")
            else:
                print(f"   INESPERADO: Confianca fora do esperado")
                
        except Exception as e:
            print(f"   ERRO: {e}")
    
    # Mostra estatísticas do sistema
    print(f"\nESTATISTICAS DO SISTEMA DE CONFIANCA")
    print("=" * 50)
    stats = get_confidence_statistics()
    
    print("Taxa de sucesso historica por ferramenta:")
    for tool, rate in stats['historical_success_rates'].items():
        print(f"   {tool}: {rate:.1%}")
    
    print(f"\nCache de intencoes: {stats['cache_stats']['tamanho_cache']} entradas")

if __name__ == "__main__":
    test_confidence_system()