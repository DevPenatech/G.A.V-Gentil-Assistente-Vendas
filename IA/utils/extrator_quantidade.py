# file: IA/utils/extrator_quantidade.py
"""
Extrator de Quantidade Inteligente para o G.A.V.

Este módulo é responsável por extrair quantidades de mensagens de texto em português brasileiro,
suportando números, palavras por extenso, frações e contextos conversacionais.
"""

import re
import os
import logging
from typing import Union, Dict, List, Tuple

# Importações para IA
try:
    import ollama
    OLLAMA_DISPONIVEL = True
except ImportError:
    OLLAMA_DISPONIVEL = False
    logging.warning("Ollama não disponível para extração de quantidade por IA")

# Configurações IA
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
HOST_OLLAMA = os.getenv("OLLAMA_HOST")

# Mapeamento de palavras para números
MAPA_PALAVRAS_QUANTIDADE = {
    # Números básicos
    'um': 1, 'uma': 1,
    'dois': 2, 'duas': 2,
    'três': 3, 'tres': 3,
    'quatro': 4,
    'cinco': 5,
    'seis': 6,
    'sete': 7,
    'oito': 8,
    'nove': 9,
    'dez': 10,
    'onze': 11,
    'doze': 12,
    'treze': 13,
    'catorze': 14, 'quatorze': 14,
    'quinze': 15,
    'dezesseis': 16,
    'dezessete': 17,
    'dezoito': 18,
    'dezenove': 19,
    'vinte': 20,
    'trinta': 30,
    'quarenta': 40,
    'cinquenta': 50,
    'sessenta': 60,
    'setenta': 70,
    'oitenta': 80,
    'noventa': 90,
    'cem': 100, 'cento': 100,
    
    # Expressões comuns
    'meia dúzia': 6,
    'meia duzia': 6,
    'uma dúzia': 12,
    'uma duzia': 12,
    'dúzia': 12,
    'duzia': 12,
    'dupla': 2,
    'par': 2,
    'trio': 3,
    'meia': 0.5,
    'meio': 0.5,
    
    # Frações
    'metade': 0.5,
    'terço': 0.33,
    'quarto': 0.25,
    
    # Múltiplos
    'dezena': 10,
    'centena': 100,
    'milhar': 1000
}

# Padrões de unidades de medida
PADROES_UNIDADES = {
    'kg': ['kg', 'kilo', 'kilos', 'quilos', 'quilo'],
    'g': ['g', 'gr', 'grama', 'gramas'],
    'l': ['l', 'lt', 'litro', 'litros'],
    'ml': ['ml', 'mililitro', 'mililitros'],
    'un': ['un', 'unidade', 'unidades', 'peça', 'peças', 'peca', 'pecas'],
    'cx': ['cx', 'caixa', 'caixas'],
    'pc': ['pc', 'pacote', 'pacotes'],
    'fr': ['fr', 'frasco', 'frascos'],
    'tb': ['tb', 'tubo', 'tubos'],
    'lata': ['lata', 'latas'],
    'garrafa': ['garrafa', 'garrafas'],
    'pote': ['pote', 'potes'],
    'saco': ['saco', 'sacos'],
    'fardo': ['fardo', 'fardos']
}

def normalizar_texto(texto: str) -> str:
    """
    Normaliza texto removendo acentos e convertendo para minúsculas.
    
    Args:
        texto (str): Texto a ser normalizado.
    
    Returns:
        str: Texto normalizado sem acentos e em minúsculas.
    """
    import unicodedata
    
    if not texto:
        return ""
    
    # Remove acentos
    normalizado = unicodedata.normalize('NFD', texto.lower())
    texto_ascii = ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')
    
    # Remove pontuação extra
    texto_ascii = re.sub(r'[^\w\s.,]', ' ', texto_ascii)
    
    return texto_ascii.strip()

def extrair_quantidades_numericas(texto: str) -> List[float]:
    """
    Extrai quantidades numéricas (inteiros e decimais) do texto.
    
    Args:
        texto (str): Texto para análise.
    
    Returns:
        List[float]: Lista de quantidades numéricas encontradas.
    """
    quantidades = []
    
    # Padrões para números
    padroes = [
        r'\b(\d+(?:[.,]\d+)?)\b',  # Números decimais (1.5, 2,5)
        r'\b(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\b',  # Multiplicação (2x3, 3×1.5)
        r'(\d+(?:[.,]\d+)?)\s*(?:kg|kilo|litro|l|g|ml|un|unidade|peça|cx|pc|lata)',  # Com unidade
    ]
    
    for padrao in padroes:
        correspondencias = re.finditer(padrao, texto, re.IGNORECASE)
        for match in correspondencias:
            try:
                if len(match.groups()) == 2:  # Multiplicação
                    num1 = float(match.group(1).replace(',', '.'))
                    num2 = float(match.group(2).replace(',', '.'))
                    quantidades.append(num1 * num2)
                else:
                    num = float(match.group(1).replace(',', '.'))
                    if 0 < num <= 10000:  # Limita valores razoáveis
                        quantidades.append(num)
            except ValueError:
                continue
    
    return quantidades

def extrair_quantidades_palavras(texto: str) -> List[float]:
    """
    Extrai quantidades escritas por extenso.
    
    Args:
        texto (str): Texto para análise.
    
    Returns:
        List[float]: Lista de quantidades extraídas de palavras.
    """
    normalizado = normalizar_texto(texto)
    quantidades = []
    
    # Busca palavras de quantidade diretamente
    palavras = normalizado.split()
    
    for i, palavra in enumerate(palavras):
        if palavra in MAPA_PALAVRAS_QUANTIDADE:
            qtd_base = MAPA_PALAVRAS_QUANTIDADE[palavra]
            
            # Verifica se há modificadores na próxima palavra
            if i + 1 < len(palavras):
                proxima_palavra = palavras[i + 1]
                
                # Frações
                if proxima_palavra in ['e', 'mais'] and i + 2 < len(palavras):
                    modificador = palavras[i + 2]
                    if modificador in MAPA_PALAVRAS_QUANTIDADE:
                        qtd_base += MAPA_PALAVRAS_QUANTIDADE[modificador]
                
                # Múltiplos
                elif proxima_palavra in ['dezenas', 'centenas']:
                    if proxima_palavra == 'dezenas':
                        qtd_base *= 10
                    elif proxima_palavra == 'centenas':
                        qtd_base *= 100
            
            if 0 < qtd_base <= 10000:
                quantidades.append(float(qtd_base))
    
    # Busca expressões compostas específicas
    padroes_compostos = [
        (r'\b(?:duas?|dois)\s+(?:e\s+)?(?:meia|meio)\b', 2.5),
        (r'\b(?:três|tres)\s+(?:e\s+)?(?:meia|meio)\b', 3.5),
        (r'\b(?:quatro)\s+(?:e\s+)?(?:meia|meio)\b', 4.5),
        (r'\b(?:cinco)\s+(?:e\s+)?(?:meia|meio)\b', 5.5),
        (r'\buma\s+(?:e\s+)?(?:meia|meio)\b', 1.5),
    ]
    
    for padrao, valor in padroes_compostos:
        if re.search(padrao, normalizado):
            quantidades.append(valor)
    
    return quantidades

def extrair_quantidades_contextuais(texto: str, produtos_mostrados_recentes: List = None) -> List[float]:
    """
    Extrai quantidades baseadas no contexto da conversa.
    
    Args:
        texto (str): Texto para análise.
        produtos_mostrados_recentes (List, optional): Lista de produtos mostrados recentemente.
    
    Returns:
        List[float]: Lista de quantidades extraídas do contexto.
    """
    quantidades = []
    normalizado = normalizar_texto(texto)
    
    # Padrões contextuais
    padroes_contextuais = [
        # "quero mais 3", "adicionar mais 2"
        (r'\b(?:mais|adicionar|incluir|somar)\s+(\d+(?:[.,]\d+)?)\b', 1),
        
        # "trocar por 5", "mudar para 10"
        (r'\b(?:trocar|mudar|alterar)\s+(?:por|para)\s+(\d+(?:[.,]\d+)?)\b', 1),
        
        # "aumentar para 8", "diminuir para 2"
        (r'\b(?:aumentar|diminuir|reduzir)\s+(?:para|a)\s+(\d+(?:[.,]\d+)?)\b', 1),
        
        # "total de 15", "quantidade 6"
        (r'\b(?:total|quantidade|qtd)\s+(?:de|:)?\s*(\d+(?:[.,]\d+)?)\b', 1),
        
        # Referências a itens específicos
        (r'\b(?:o|a|do|da)\s+(?:item|produto)\s+(\d+)\b', 1),  # "o item 2"
    ]
    
    for padrao, indice_grupo in padroes_contextuais:
        correspondencias = re.finditer(padrao, normalizado, re.IGNORECASE)
        for match in correspondencias:
            try:
                num = float(match.group(indice_grupo).replace(',', '.'))
                if 0 < num <= 10000:
                    quantidades.append(num)
            except (ValueError, IndexError):
                continue
    
    # Se há produtos mostrados e número simples, pode ser seleção + quantidade
    if produtos_mostrados_recentes:
        # "3 coca cola" - pode ser quantidade 3 do produto coca cola
        padrao_produto_qtd = r'\b(\d+(?:[.,]\d+)?)\s+(?:da?|do|de)?\s*(\w+)'
        correspondencias = re.finditer(padrao_produto_qtd, normalizado)
        for match in correspondencias:
            try:
                qtd = float(match.group(1).replace(',', '.'))
                ref_produto = match.group(2)
                
                # Verifica se o produto mencionado está na lista
                for produto in produtos_mostrados_recentes:
                    nome_produto = (produto.get('descricao') or 
                                  produto.get('canonical_name', '')).lower()
                    if ref_produto in nome_produto or nome_produto in ref_produto:
                        quantidades.append(qtd)
                        break
            except ValueError:
                continue
    
    return quantidades

def detectar_modificadores_quantidade(texto: str) -> Dict:
    """
    Detecta modificadores de quantidade no texto.
    
    Args:
        texto (str): Texto para análise.
    
    Returns:
        Dict: Dicionário com ação, referência e quantidade alvo detectadas.
    """
    normalizado = normalizar_texto(texto)
    modificadores = {
        'acao': None,  # 'add', 'set', 'remove', 'clear'
        'referencia': None,  # 'all', 'item_index', 'product_name'
        'quantidade_alvo': None
    }
    
    # Ações de modificação - EXPANDIDO
    if re.search(r'\b(?:adicionar|incluir|somar|mais)\b', normalizado):
        modificadores['acao'] = 'add'
    elif re.search(r'\b(?:definir|setar|alterar|mudar|trocar)\b', normalizado):
        modificadores['acao'] = 'set'
    elif re.search(r'\b(?:remover|tirar|excluir|deletar)\b', normalizado):
        modificadores['acao'] = 'remove'
    # NOVO: Comando para esvaziar carrinho COMPLETO
    elif re.search(r'\b(?:esvaziar|limpar|zerar|resetar|apagar)\s*(?:carrinho|tudo|todos|completo)?', normalizado):
        modificadores['acao'] = 'clear'
        modificadores['referencia'] = 'all'
    # NOVO: Comandos alternativos para limpeza
    elif re.search(r'\b(?:começar\s+de\s+novo|recomeçar|reiniciar)', normalizado):
        modificadores['acao'] = 'clear'
        modificadores['referencia'] = 'all'
    
    # Referências - EXPANDIDO
    if re.search(r'\b(?:tudo|todos|todas|carrinho|completo|inteiro|total)\b', normalizado):
        modificadores['referencia'] = 'all'
    
    # Índices de item
    correspondencia_item = re.search(r'\b(?:item|produto)\s+(\d+)\b', normalizado)
    if correspondencia_item:
        modificadores['referencia'] = f"item_{correspondencia_item.group(1)}"
    
    return modificadores

def extrair_quantidade_com_ia(texto: str, produtos_mostrados_recentes: List = None, contexto_conversa: str = "") -> float:
    """
    Extrai quantidade usando IA para maior precisão e compreensão contextual.
    
    Args:
        texto: Texto do usuário para análise.
        produtos_mostrados_recentes: Lista de produtos mostrados recentemente.
        contexto_conversa: Contexto da conversa para melhor interpretação.
        
    Returns:
        float: Quantidade extraída ou 1.0 como padrão.
        
    Examples:
        >>> extrair_quantidade_com_ia("quero uma coca e meia de guaraná")
        1.5
        >>> extrair_quantidade_com_ia("duas dúzias menos três")
        21.0
        >>> extrair_quantidade_com_ia("o dobro do que pedi antes", contexto_conversa="Última compra: 3 cervejas")
        6.0
    """
    if not OLLAMA_DISPONIVEL:
        # Fallback para método tradicional
        return extrair_quantidade(texto, produtos_mostrados_recentes, 1.0)
    
    try:
        # Prepara contexto para IA
        contexto_produtos = ""
        if produtos_mostrados_recentes:
            nomes_produtos = [p.get('descricao', p.get('canonical_name', '')) for p in produtos_mostrados_recentes[:5]]
            contexto_produtos = f"Produtos na tela: {', '.join(nomes_produtos)}"
        
        # Prompt otimizado para extração de quantidade
        prompt_ia = f"""Você é um especialista em extrair quantidades de texto em português brasileiro.

TEXTO DO USUÁRIO: "{texto}"

CONTEXTO DA CONVERSA:
{contexto_conversa if contexto_conversa else "Primeira interação"}

{contexto_produtos}

INSTRUÇÕES:
1. Extraia APENAS a quantidade numérica mencionada no texto
2. Considere expressões brasileiras comuns:
   - "uma coca e meia" = 1.5
   - "duas dúzias" = 24
   - "meia dúzia" = 6
   - "um pacotinho" = 1
   - "bastante" = 5 (quantidade moderada)
   - "muito" = 10
   - "pouco" = 2
   - "alguns" = 3
   - "várias" = 4
3. Para expressões matemáticas: "duas dúzias menos três" = 21
4. Para referências contextuais: "o dobro", "a metade", "o mesmo"
5. Se não houver quantidade explícita, retorne 1
6. Valores entre 0.1 e 1000 são válidos

RESPONDA APENAS COM O NÚMERO (exemplo: 2.5):"""

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.1,  # Baixa para ser determinístico
                "top_p": 0.3,
                "num_predict": 10,
                "stop": ["\n", " ", ".", ","]
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        logging.debug(f"[QUANTIDADE_IA] Texto: '{texto}' → IA: '{resposta_ia}'")
        
        # Extrai número da resposta
        try:
            quantidade = float(resposta_ia.replace(',', '.'))
            if 0.1 <= quantidade <= 1000:
                logging.info(f"[QUANTIDADE_IA] Sucesso: '{texto}' → {quantidade}")
                return quantidade
        except ValueError:
            pass
        
        # Se IA falhou, usa método tradicional
        logging.warning(f"[QUANTIDADE_IA] Falhou, usando fallback para: '{texto}'")
        return extrair_quantidade(texto, produtos_mostrados_recentes, 1.0)
        
    except Exception as e:
        logging.error(f"[QUANTIDADE_IA] Erro: {e}")
        return extrair_quantidade(texto, produtos_mostrados_recentes, 1.0)

def extrair_quantidade(texto: str, produtos_mostrados_recentes: List = None, padrao: float = 1.0) -> float:
    """
    Função principal para extrair quantidade de um texto.
    
    Args:
        texto (str): Texto do usuário para análise.
        produtos_mostrados_recentes (List, optional): Lista de produtos mostrados recentemente.
        padrao (float): Valor padrão se nenhuma quantidade for encontrada.
        
    Returns:
        float: Quantidade extraída ou valor padrão.
        
    Example:
        >>> extrair_quantidade("quero 3 cervejas")
        3.0
        >>> extrair_quantidade("adiciona duas coca cola")
        2.0
    """
    if not texto or not isinstance(texto, str):
        return padrao
    
    todas_quantidades = []
    
    # Extrai quantidades de diferentes formas
    todas_quantidades.extend(extrair_quantidades_numericas(texto))
    todas_quantidades.extend(extrair_quantidades_palavras(texto))
    todas_quantidades.extend(extrair_quantidades_contextuais(texto, produtos_mostrados_recentes))
    
    # Remove duplicatas e ordena
    quantidades_unicas = list(set(todas_quantidades))
    quantidades_unicas.sort()
    
    if not quantidades_unicas:
        return padrao
    
    # Estratégia de seleção da quantidade mais provável
    # Prioriza: 1) Valores pequenos e comuns (1-50), 2) Valores únicos
    
    # Filtra valores razoáveis para produtos comuns
    quantidades_razoaveis = [q for q in quantidades_unicas if 0.1 <= q <= 100]
    
    if quantidades_razoaveis:
        # Se há apenas um valor razoável, usa ele
        if len(quantidades_razoaveis) == 1:
            return quantidades_razoaveis[0]
        
        # Se há múltiplos, prioriza valores típicos (1, 2, 3, 5, 10, etc.)
        valores_comuns = [1, 2, 3, 4, 5, 6, 10, 12, 20, 24, 30, 50]
        for comum in valores_comuns:
            if comum in quantidades_razoaveis:
                return float(comum)
        
        # Senão, pega o menor valor razoável
        return quantidades_razoaveis[0]
    
    # Se nenhum valor razoável, retorna o padrão
    return padrao

def e_quantidade_valida(quantidade: Union[int, float, str]) -> bool:
    """
    Verifica se uma quantidade é válida para adicionar ao carrinho.
    
    Args:
        quantidade (Union[int, float, str]): Quantidade a ser validada.
    
    Returns:
        bool: True se a quantidade for válida, False caso contrário.
        
    Example:
        >>> e_quantidade_valida(5)
        True
        >>> e_quantidade_valida(-1)
        False
        >>> e_quantidade_valida("2.5")
        True
    """
    try:
        if isinstance(quantidade, str):
            # Remove vírgulas e converte
            quantidade = float(quantidade.replace(',', '.'))
        
        qtd = float(quantidade)
        
        # Verifica limites razoáveis
        return 0.01 <= qtd <= 10000.0
        
    except (ValueError, TypeError):
        return False

def formatar_quantidade_exibicao(quantidade: Union[int, float]) -> str:
    """
    Formata quantidade para exibição amigável.
    
    Args:
        quantidade (Union[int, float]): Quantidade a ser formatada.
    
    Returns:
        str: Quantidade formatada para exibição.
        
    Example:
        >>> formatar_quantidade_exibicao(5.0)
        "5"
        >>> formatar_quantidade_exibicao(2.5)
        "2.5"
    """
    try:
        qtd = float(quantidade)
        
        # Se é inteiro, mostra sem decimais
        if qtd == int(qtd):
            return str(int(qtd))
        
        # Se tem decimais, formata adequadamente
        if qtd < 1:
            return f"{qtd:.2f}".rstrip('0').rstrip('.')
        else:
            return f"{qtd:.1f}".rstrip('0').rstrip('.')
            
    except (ValueError, TypeError):
        return "1"

def analisar_quantidade_com_unidade(texto: str) -> Tuple[float, str]:
    """
    Extrai quantidade e unidade de medida do texto.
    
    Args:
        texto (str): Texto para análise.
    
    Returns:
        Tuple[float, str]: Tupla contendo (quantidade, unidade).
        
    Example:
        >>> analisar_quantidade_com_unidade("2 kg de arroz")
        (2.0, "kg")
        >>> analisar_quantidade_com_unidade("5 unidades")
        (5.0, "un")
    """
    normalizado = normalizar_texto(texto)
    
    # Padrões para quantidade + unidade
    padroes = [
        r'(\d+(?:[.,]\d+)?)\s*(kg|kilo|kilos|quilos|quilo)',
        r'(\d+(?:[.,]\d+)?)\s*(l|lt|litro|litros)',
        r'(\d+(?:[.,]\d+)?)\s*(g|gr|grama|gramas)',
        r'(\d+(?:[.,]\d+)?)\s*(ml|mililitro|mililitros)',
        r'(\d+(?:[.,]\d+)?)\s*(un|unidade|unidades|peça|peças|peca|pecas)',
        r'(\d+(?:[.,]\d+)?)\s*(cx|caixa|caixas)',
        r'(\d+(?:[.,]\d+)?)\s*(pc|pacote|pacotes)',
        r'(\d+(?:[.,]\d+)?)\s*(lata|latas)',
        r'(\d+(?:[.,]\d+)?)\s*(garrafa|garrafas)',
    ]
    
    for padrao in padroes:
        correspondencia = re.search(padrao, normalizado, re.IGNORECASE)
        if correspondencia:
            try:
                quantidade = float(correspondencia.group(1).replace(',', '.'))
                texto_unidade = correspondencia.group(2).lower()
                
                # Normaliza unidade
                for chave_unidade, variantes_unidade in PADROES_UNIDADES.items():
                    if texto_unidade in variantes_unidade:
                        return quantidade, chave_unidade
                
                return quantidade, texto_unidade
                
            except ValueError:
                continue
    
    # Se não encontrou unidade específica, extrai apenas quantidade
    quantidade = extrair_quantidade(texto)
    return quantidade, "un"

def processar_pedido_complexo_ia(texto: str, contexto_conversa: str = "") -> List[Dict]:
    """
    Processa pedidos complexos com múltiplos itens usando IA.
    
    Args:
        texto: Texto contendo múltiplos itens.
        contexto_conversa: Contexto da conversa.
    
    Returns:
        List[Dict]: Lista de dicionários com 'quantidade', 'produto', 'especificacoes'.
        
    Examples:
        >>> processar_pedido_complexo_ia("2 coca, 1 guaraná e 3 cervejas skol")
        [{'quantidade': 2.0, 'produto': 'coca cola', 'especificacoes': {}},
         {'quantidade': 1.0, 'produto': 'guaraná', 'especificacoes': {}},
         {'quantidade': 3.0, 'produto': 'cerveja skol', 'especificacoes': {}}]
    """
    if not OLLAMA_DISPONIVEL:
        # Fallback para método tradicional
        multiplos = extrair_multiplas_quantidades(texto)
        return [{'quantidade': qtd, 'produto': prod, 'especificacoes': {}} for qtd, prod in multiplos]
    
    try:
        prompt_ia = f"""Você é um especialista em processar pedidos de compras em português brasileiro.

TEXTO DO PEDIDO: "{texto}"

CONTEXTO DA CONVERSA:
{contexto_conversa if contexto_conversa else "Primeira interação"}

INSTRUÇÕES:
1. Identifique TODOS os produtos mencionados no texto
2. Extraia a quantidade para cada produto
3. Normalize os nomes dos produtos (ex: "coca" → "coca cola")
4. Identifique especificações como marca, tamanho, sabor

EXEMPLOS:
- "2 coca e 3 guaraná" → 2 coca cola, 3 guaraná
- "uma cerveja skol lata" → 1 cerveja skol (lata)
- "pack de 6 brahma" → 6 cerveja brahma (pack)
- "meio quilo de arroz" → 0.5 arroz (kg)

RESPONDA EM JSON com esta estrutura:
[
  {{"quantidade": 2.0, "produto": "coca cola", "especificacoes": {{}}}},
  {{"quantidade": 3.0, "produto": "guaraná", "especificacoes": {{}}}}
]

JSON:"""

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.1,
                "top_p": 0.3,
                "num_predict": 200
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        logging.debug(f"[PEDIDO_COMPLEXO_IA] Texto: '{texto}' → IA: '{resposta_ia}'")
        
        # Tenta extrair JSON da resposta
        import json
        try:
            # Procura por JSON na resposta
            import re
            json_match = re.search(r'\[.*?\]', resposta_ia, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group(0))
                if isinstance(resultado, list) and len(resultado) > 0:
                    logging.info(f"[PEDIDO_COMPLEXO_IA] Sucesso: {len(resultado)} itens extraídos")
                    return resultado
        except (json.JSONDecodeError, AttributeError):
            pass
        
        # Se IA falhou, usa método tradicional
        logging.warning(f"[PEDIDO_COMPLEXO_IA] Falhou, usando fallback para: '{texto}'")
        multiplos = extrair_multiplas_quantidades(texto)
        return [{'quantidade': qtd, 'produto': prod, 'especificacoes': {}} for qtd, prod in multiplos]
        
    except Exception as e:
        logging.error(f"[PEDIDO_COMPLEXO_IA] Erro: {e}")
        multiplos = extrair_multiplas_quantidades(texto)
        return [{'quantidade': qtd, 'produto': prod, 'especificacoes': {}} for qtd, prod in multiplos]

def extrair_multiplas_quantidades(texto: str) -> List[Tuple[float, str]]:
    """
    Extrai múltiplas quantidades e produtos do texto.
    
    Args:
        texto (str): Texto contendo múltiplos itens.
    
    Returns:
        List[Tuple[float, str]]: Lista de tuplas (quantidade, produto).
        
    Example:
        >>> extrair_multiplas_quantidades("2 coca cola e 3 pepsi")
        [(2.0, "coca cola"), (3.0, "pepsi")]
    """
    normalizado = normalizar_texto(texto)
    resultados = []
    
    # Padrões para múltiplos itens
    # "2 coca cola e 3 pepsi"
    # "5 kg de arroz, 2 litros de óleo"
    
    padroes_multiplos = [
        r'(\d+(?:[.,]\d+)?)\s*(?:de\s+)?(\w+(?:\s+\w+)*?)(?:\s+e\s+|,\s*|$)',
        r'(\d+(?:[.,]\d+)?)\s*(kg|l|g|ml|un|unidade|cx|pc|lata)\s+(?:de\s+)?(\w+(?:\s+\w+)*?)(?:\s+e\s+|,\s*|$)',
    ]
    
    for padrao in padroes_multiplos:
        correspondencias = re.finditer(padrao, normalizado, re.IGNORECASE)
        for match in correspondencias:
            try:
                if len(match.groups()) == 2:  # quantidade + produto
                    qtd = float(match.group(1).replace(',', '.'))
                    produto = match.group(2).strip()
                    resultados.append((qtd, produto))
                elif len(match.groups()) == 3:  # quantidade + unidade + produto
                    qtd = float(match.group(1).replace(',', '.'))
                    unidade = match.group(2)
                    produto = match.group(3).strip()
                    resultados.append((qtd, f"{produto} ({unidade})"))
            except ValueError:
                continue
    
    return resultados

# Função para compatibilidade com código existente
def extrair_quantidade_da_mensagem(mensagem: str, contexto: Dict = None) -> float:
    """
    Função de compatibilidade para extrair quantidade de mensagem.
    
    Args:
        mensagem (str): Mensagem do usuário.
        contexto (Dict, optional): Contexto da conversa.
    
    Returns:
        float: Quantidade extraída.
    """
    produtos_recentes = contexto.get('last_shown_products', []) if contexto else []
    return extrair_quantidade(mensagem, produtos_recentes)