# file: IA/utils/busca_aproximada.py
"""
Sistema de busca aproximada tolerante a erros para o G.A.V.
"""

import re
import unicodedata
import logging
from typing import List, Dict, Tuple
from difflib import SequenceMatcher

CORRECOES_COMUNS = {
    'coca-cola': ['coca cola', 'cocacola', 'cokacola', 'coca kola'],
    'refrigerante': ['refri', 'regrigerante', 'refriferante'],
    'detergente': ['detergente', 'ditergente'],
    'sabão': ['sabao', 'xampu'],
    'açúcar': ['acucar', 'azucar'],
    'óleo': ['oleo'],
    'água': ['agua'],
    'pão': ['pao'],
    'omo': ['omô', 'homo'],
    'coca': ['koca', 'coka'],
    'pepsi': ['pepssi', 'pepci'],
    'guaraná': ['guarana', 'guaranah'],
    '2l': ['2 litros', '2lt', '2 l'],
    '350ml': ['350 ml', '350ml', 'lata'],
    'pet': ['garrafa', 'garrafa pet'],
    'lata': ['latinha', 'lt'],
    'refri': ['refrigerante', 'refriferante'],
    'zero': ['diet', 'sem açúcar', 'sem acucar'],
    'light': ['diet', 'zero'],
}

SINONIMOS = {
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

class MotorBuscaAproximada:
    """Motor de busca aproximada com correções automáticas e sinônimos."""
    
    def __init__(self):
        self.cache_correcao = {}
        self.cache_similaridade = {}
        
    def normalizar_texto(self, texto: str) -> str:
        """Normaliza o texto removendo acentos, pontuação e padronizando.

        Args:
            texto: O texto a ser normalizado.

        Returns:
            O texto normalizado.
        """
        if not texto:
            return ""
        
        nfkd = unicodedata.normalize('NFD', texto.lower())
        texto_ascii = ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')
        
        limpo = re.sub(r'[^\w\s]', ' ', texto_ascii)
        
        limpo = ' '.join(limpo.split())
        
        return limpo.strip()
    
    def calcular_similaridade(self, texto1: str, texto2: str) -> float:
        """Calcula a similaridade entre dois textos (0-1).

        Args:
            texto1: O primeiro texto.
            texto2: O segundo texto.

        Returns:
            A similaridade entre os textos.
        """
        if not texto1 or not texto2:
            return 0.0
        
        chave_cache = f"{texto1}|||{texto2}"
        if chave_cache in self.cache_similaridade:
            return self.cache_similaridade[chave_cache]
        
        norm1 = self.normalizar_texto(texto1)
        norm2 = self.normalizar_texto(texto2)
        
        if norm1 == norm2:
            similaridade = 1.0
        else:
            sim_seq = SequenceMatcher(None, norm1, norm2).ratio()
            
            palavras1 = set(norm1.split())
            palavras2 = set(norm2.split())
            if palavras1 or palavras2:
                sim_jaccard = len(palavras1 & palavras2) / len(palavras1 | palavras2)
            else:
                sim_jaccard = 0.0
            
            if norm1 in norm2 or norm2 in norm1:
                sim_contencao = 0.8
            else:
                sim_contencao = 0.0
            
            sim_prefixo = 0.0
            if len(norm1) >= 3 and len(norm2) >= 3:
                if norm1[:3] == norm2[:3]:
                    sim_prefixo = 0.3
                if norm1[-3:] == norm2[-3:]:
                    sim_prefixo += 0.2
            
            similaridade = (
                sim_seq * 0.4 +
                sim_jaccard * 0.3 +
                sim_contencao * 0.2 +
                sim_prefixo * 0.1
            )
        
        self.cache_similaridade[chave_cache] = similaridade
        return similaridade
    
    def aplicar_correcoes(self, texto: str) -> str:
        """Aplica correções automáticas para erros comuns.

        Args:
            texto: O texto a ser corrigido.

        Returns:
            O texto corrigido.
        """
        if not texto:
            return texto
        
        if texto in self.cache_correcao:
            return self.cache_correcao[texto]
        
        normalizado = self.normalizar_texto(texto)
        corrigido = normalizado
        
        for termo_correto, variacoes in CORRECOES_COMUNS.items():
            for variacao in variacoes:
                if self.normalizar_texto(variacao) == normalizado:
                    corrigido = termo_correto
                    break
            if corrigido != normalizado:
                break
        
        if corrigido == normalizado:
            corrigido = re.sub(r'\b(\d+)\s*l\b', r'\1 litros', corrigido)
            corrigido = re.sub(r'\b(\d+)\s*ml\b', r'\1ml', corrigido)
            corrigido = re.sub(r'\b(\d+)\s*kg\b', r'\1kg', corrigido)
            
            corrigido = re.sub(r'\b(\w+)\s+\1\b', r'\1', corrigido)
            
            corrigido = re.sub(r'\bcoca\s+cola\b', 'coca cola', corrigido)
            corrigido = re.sub(r'\bomô\b', 'omo', corrigido)
        
        self.cache_correcao[texto] = corrigido
        return corrigido
    
    def expandir_com_sinonimos(self, texto: str) -> List[str]:
        """Expande um termo com sinônimos relacionados.

        Args:
            texto: O texto a ser expandido.

        Returns:
            Uma lista de sinônimos.
        """
        if not texto:
            return []
        
        normalizado = self.normalizar_texto(texto)
        expansoes = [normalizado]
        
        for termo_base, lista_sinonimos in SINONIMOS.items():
            if self.normalizar_texto(termo_base) == normalizado:
                expansoes.extend(lista_sinonimos)
                break
            
            for sinonimo in lista_sinonimos:
                if self.normalizar_texto(sinonimo) == normalizado:
                    expansoes.append(termo_base)
                    expansoes.extend([s for s in lista_sinonimos if s != sinonimo])
                    break
        
        palavras = normalizado.split()
        for palavra in palavras:
            if len(palavra) >= 4:
                for termo_base, lista_sinonimos in SINONIMOS.items():
                    if palavra in self.normalizar_texto(termo_base):
                        expansoes.extend(lista_sinonimos)
        
        expansoes_unicas = []
        vistos = set()
        for exp in expansoes:
            norm_exp = self.normalizar_texto(exp)
            if norm_exp and norm_exp not in vistos:
                expansoes_unicas.append(exp)
                vistos.add(norm_exp)
        
        return expansoes_unicas[:5]
    
    def gerar_variacoes_busca(self, texto: str) -> List[str]:
        """Gera variações de busca para um termo.

        Args:
            texto: O texto a ser variado.

        Returns:
            Uma lista de variações de busca.
        """
        if not texto:
            return []
        
        variacoes = []
        normalizado = self.normalizar_texto(texto)
        
        variacoes.append(normalizado)
        
        corrigido = self.aplicar_correcoes(texto)
        if corrigido != normalizado:
            variacoes.append(corrigido)
        
        sinonimos = self.expandir_com_sinonimos(texto)
        variacoes.extend(sinonimos)
        
        palavras = normalizado.split()
        if len(palavras) > 1:
            variacoes.extend(palavras)
            
            for i in range(len(palavras) - 1):
                variacoes.append(f"{palavras[i]} {palavras[i+1]}")
        
        variacoes_unicas = []
        vistos = set()
        for var in variacoes:
            norm_var = self.normalizar_texto(var)
            if norm_var and norm_var not in vistos and len(norm_var) >= 2:
                variacoes_unicas.append(var)
                vistos.add(norm_var)
        
        return variacoes_unicas
    
    def encontrar_melhores_correspondencias(self, termo_busca: str, lista_candidatos: List[str], 
                                           min_similaridade: float = 0.6, max_resultados: int = 5) -> List[Tuple[str, float]]:
        """Encontra as melhores correspondências em uma lista de candidatos.

        Args:
            termo_busca: O termo de busca.
            lista_candidatos: A lista de candidatos.
            min_similaridade: A similaridade mínima.
            max_resultados: O número máximo de resultados.

        Returns:
            Uma lista de tuplas com as melhores correspondências e suas similaridades.
        """
        if not termo_busca or not lista_candidatos:
            return []
        
        correspondencias = []
        for candidato in lista_candidatos:
            similaridade = self.calcular_similaridade(termo_busca, candidato)
            if similaridade >= min_similaridade:
                correspondencias.append((candidato, similaridade))
        
        correspondencias.sort(key=lambda x: x[1], reverse=True)
        
        return correspondencias[:max_resultados]

motor_busca_aproximada = MotorBuscaAproximada()

def busca_aproximada_kb(termo_busca: str, base_conhecimento: Dict, min_similaridade: float = 0.6) -> List[Dict]:
    """Busca aproximada na base de conhecimento.

    Args:
        termo_busca: O termo de busca.
        base_conhecimento: A base de conhecimento.
        min_similaridade: A similaridade mínima.

    Returns:
        Uma lista de produtos correspondentes.
    """
    if not termo_busca or not base_conhecimento:
        return []
    
    logging.info(f"[FUZZY] Iniciando busca aproximada para: '{termo_busca}'")
    
    variacoes_busca = motor_busca_aproximada.gerar_variacoes_busca(termo_busca)
    
    produtos_correspondentes = []
    codprods_vistos = set()
    
    for variacao in variacoes_busca:
        variacao_normalizada = motor_busca_aproximada.normalizar_texto(variacao)
        
        if variacao_normalizada in base_conhecimento:
            produtos = base_conhecimento[variacao_normalizada]
            for produto in produtos:
                codprod = produto.get("codprod")
                if codprod and codprod not in codprods_vistos:
                    produtos_correspondentes.append(produto)
                    codprods_vistos.add(codprod)
        
        for termo_kb, produtos in base_conhecimento.items():
            similaridade = motor_busca_aproximada.calcular_similaridade(variacao_normalizada, termo_kb)
            
            if similaridade >= min_similaridade:
                for produto in produtos:
                    codprod = produto.get("codprod")
                    if codprod and codprod not in codprods_vistos:
                        produto_com_score = produto.copy()
                        produto_com_score["fuzzy_score"] = similaridade
                        produto_com_score["matched_term"] = termo_kb
                        produtos_correspondentes.append(produto_com_score)
                        codprods_vistos.add(codprod)
    
    produtos_correspondentes.sort(key=lambda p: p.get("fuzzy_score", 0), reverse=True)
    
    logging.info(f"[FUZZY] Encontrados {len(produtos_correspondentes)} produtos com similaridade >= {min_similaridade}")
    
    return produtos_correspondentes

def busca_aproximada_produtos(termo_busca: str, limite: int = 10) -> List[Dict]:
    """Busca aproximada diretamente no banco de dados.

    Args:
        termo_busca: O termo de busca.
        limite: O número máximo de resultados.

    Returns:
        Uma lista de produtos encontrados.
    """
    from db.database import obter_todos_produtos_ativos
    
    if not termo_busca or len(termo_busca.strip()) < 2:
        return []
    
    logging.info(f"[FUZZY] Busca aproximada no banco para: '{termo_busca}'")
    
    todos_produtos = obter_todos_produtos_ativos()
    if not todos_produtos:
        return []
    
    variacoes_busca = motor_busca_aproximada.gerar_variacoes_busca(termo_busca)
    
    produtos_pontuados = []
    codprods_vistos = set()
    
    for produto in todos_produtos:
        nome_produto = produto.get('descricao', '')
        if not nome_produto:
            continue
        
        codprod = produto.get('codprod')
        if codprod in codprods_vistos:
            continue
        
        max_similaridade = 0.0
        melhor_variacao_correspondente = ""
        
        for variacao in variacoes_busca:
            similaridade = motor_busca_aproximada.calcular_similaridade(variacao, nome_produto)
            if similaridade > max_similaridade:
                max_similaridade = similaridade
                melhor_variacao_correspondente = variacao
        
        if max_similaridade >= 0.4:
            produto_com_score = produto.copy()
            produto_com_score["fuzzy_score"] = max_similaridade
            produto_com_score["matched_variation"] = melhor_variacao_correspondente
            produtos_pontuados.append(produto_com_score)
            codprods_vistos.add(codprod)
    
    produtos_pontuados.sort(key=lambda p: p["fuzzy_score"], reverse=True)
    
    resultado = produtos_pontuados[:limite]
    
    logging.info(f"[FUZZY] Retornando {len(resultado)} produtos do banco")
    
    return resultado

def sugerir_correcoes(termo_busca: str, max_sugestoes: int = 3) -> List[str]:
    """Sugere correções para um termo de busca.

    Args:
        termo_busca: O termo de busca.
        max_sugestoes: O número máximo de sugestões.

    Returns:
        Uma lista de sugestões.
    """
    if not termo_busca:
        return []
    
    sugestoes = []
    
    corrigido = motor_busca_aproximada.aplicar_correcoes(termo_busca)
    if corrigido != motor_busca_aproximada.normalizar_texto(termo_busca):
        sugestoes.append(corrigido)
    
    sinonimos = motor_busca_aproximada.expandir_com_sinonimos(termo_busca)
    sugestoes.extend(sinonimos[:2])
    
    sugestoes_unicas = []
    vistos = set()
    for sugestao in sugestoes:
        norm_sugg = motor_busca_aproximada.normalizar_texto(sugestao)
        if norm_sugg and norm_sugg not in vistos:
            sugestoes_unicas.append(sugestao)
            vistos.add(norm_sugg)
    
    return sugestoes_unicas[:max_sugestoes]

def analisar_qualidade_busca(termo_busca: str, produtos_encontrados: List[Dict]) -> Dict:
    """Analisa a qualidade dos resultados de uma busca.

    Args:
        termo_busca: O termo de busca.
        produtos_encontrados: A lista de produtos encontrados.

    Returns:
        Um dicionário com a análise da qualidade da busca.
    """
    if not termo_busca:
        return {"quality": "invalid", "details": "Termo de busca vazio"}
    
    if not produtos_encontrados:
        return {
            "quality": "no_results",
            "details": "Nenhum produto encontrado",
            "suggestions": sugerir_correcoes(termo_busca)
        }
    
    similaridades = []
    for produto in produtos_encontrados:
        if "fuzzy_score" in produto:
            similaridades.append(produto["fuzzy_score"])
        else:
            nome_produto = produto.get('descricao') or produto.get('canonical_name', '')
            if nome_produto:
                similaridade = motor_busca_aproximada.calcular_similaridade(termo_busca, nome_produto)
                similaridades.append(similaridade)
    
    if not similaridades:
        return {"quality": "unknown", "details": "Não foi possível calcular similaridade"}
    
    media_similaridade = sum(similaridades) / len(similaridades)
    max_similaridade = max(similaridades)
    
    if max_similaridade >= 0.9:
        qualidade = "excellent"
    elif max_similaridade >= 0.7:
        qualidade = "good"
    elif max_similaridade >= 0.5:
        qualidade = "fair"
    else:
        qualidade = "poor"
    
    analise = {
        "quality": qualidade,
        "max_similarity": max_similaridade,
        "avg_similarity": media_similaridade,
        "total_results": len(produtos_encontrados),
        "details": f"Melhor correspondência: {max_similaridade:.2f}"
    }
    
    if qualidade in ["fair", "poor"]:
        analise["suggestions"] = sugerir_correcoes(termo_busca)
    
    return analise

def otimizar_termo_busca(termo_busca: str) -> str:
    """Otimiza um termo de busca aplicando as melhores práticas.

    Args:
        termo_busca: O termo de busca.

    Returns:
        O termo de busca otimizado.
    """
    if not termo_busca:
        return ""
    
    otimizado = motor_busca_aproximada.normalizar_texto(termo_busca)
    
    otimizado = motor_busca_aproximada.aplicar_correcoes(otimizado)
    
    palavras = otimizado.split()
    palavras_significativas = [palavra for palavra in palavras if len(palavra) >= 2]
    
    return ' '.join(palavras_significativas)

def busca_rapida_aproximada(termo_busca: str, limite: int = 10) -> List[Dict]:
    """Busca aproximada rápida combinando base de conhecimento e banco de dados.

    Args:
        termo_busca: O termo de busca.
        limite: O número máximo de resultados.

    Returns:
        Uma lista de produtos encontrados.
    """
    from knowledge.knowledge import find_product_in_kb
    
    resultados_kb = find_product_in_kb(termo_busca)
    if resultados_kb and len(resultados_kb) >= limite:
        return resultados_kb[:limite]
    
    resultados_db = busca_aproximada_produtos(termo_busca, limite - len(resultados_kb))
    
    resultados_combinados = list(resultados_kb)
    codprods_kb = {p.get('codprod') for p in resultados_kb}
    
    for produto_db in resultados_db:
        if produto_db.get('codprod') not in codprods_kb:
            resultados_combinados.append(produto_db)
    
    return resultados_combinados[:limite]
