# file: IA/utils/quantity_extractor.py
import re
from typing import Union, Dict, List, Tuple

# Mapeamento de palavras para números
QUANTITY_WORDS_MAP = {
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
UNIT_PATTERNS = {
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

def normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    import unicodedata
    
    if not text:
        return ""
    
    # Remove acentos
    normalized = unicodedata.normalize('NFD', text.lower())
    ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    
    # Remove pontuação extra
    ascii_text = re.sub(r'[^\w\s.,]', ' ', ascii_text)
    
    return ascii_text.strip()

def extract_numeric_quantities(text: str) -> List[float]:
    """Extrai quantidades numéricas (inteiros e decimais) do texto."""
    quantities = []
    
    # Padrões para números
    patterns = [
        r'\b(\d+(?:[.,]\d+)?)\b',  # Números decimais (1.5, 2,5)
        r'\b(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\b',  # Multiplicação (2x3, 3×1.5)
        r'(\d+(?:[.,]\d+)?)\s*(?:kg|kilo|litro|l|g|ml|un|unidade|peça|cx|pc|lata)',  # Com unidade
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                if len(match.groups()) == 2:  # Multiplicação
                    num1 = float(match.group(1).replace(',', '.'))
                    num2 = float(match.group(2).replace(',', '.'))
                    quantities.append(num1 * num2)
                else:
                    num = float(match.group(1).replace(',', '.'))
                    if 0 < num <= 10000:  # Limita valores razoáveis
                        quantities.append(num)
            except ValueError:
                continue
    
    return quantities

def extract_word_quantities(text: str) -> List[float]:
    """Extrai quantidades escritas por extenso."""
    normalized = normalize_text(text)
    quantities = []
    
    # Busca palavras de quantidade diretamente
    words = normalized.split()
    
    for i, word in enumerate(words):
        if word in QUANTITY_WORDS_MAP:
            base_qty = QUANTITY_WORDS_MAP[word]
            
            # Verifica se há modificadores na próxima palavra
            if i + 1 < len(words):
                next_word = words[i + 1]
                
                # Frações
                if next_word in ['e', 'mais'] and i + 2 < len(words):
                    modifier = words[i + 2]
                    if modifier in QUANTITY_WORDS_MAP:
                        base_qty += QUANTITY_WORDS_MAP[modifier]
                
                # Múltiplos
                elif next_word in ['dezenas', 'centenas']:
                    if next_word == 'dezenas':
                        base_qty *= 10
                    elif next_word == 'centenas':
                        base_qty *= 100
            
            if 0 < base_qty <= 10000:
                quantities.append(float(base_qty))
    
    # Busca expressões compostas específicas
    compound_patterns = [
        (r'\b(?:duas?|dois)\s+(?:e\s+)?(?:meia|meio)\b', 2.5),
        (r'\b(?:três|tres)\s+(?:e\s+)?(?:meia|meio)\b', 3.5),
        (r'\b(?:quatro)\s+(?:e\s+)?(?:meia|meio)\b', 4.5),
        (r'\b(?:cinco)\s+(?:e\s+)?(?:meia|meio)\b', 5.5),
        (r'\buma\s+(?:e\s+)?(?:meia|meio)\b', 1.5),
    ]
    
    for pattern, value in compound_patterns:
        if re.search(pattern, normalized):
            quantities.append(value)
    
    return quantities

def extract_contextual_quantities(text: str, last_shown_products: List = None) -> List[float]:
    """Extrai quantidades baseadas no contexto da conversa."""
    quantities = []
    normalized = normalize_text(text)
    
    # Padrões contextuais
    contextual_patterns = [
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
    
    for pattern, group_idx in contextual_patterns:
        matches = re.finditer(pattern, normalized, re.IGNORECASE)
        for match in matches:
            try:
                num = float(match.group(group_idx).replace(',', '.'))
                if 0 < num <= 10000:
                    quantities.append(num)
            except (ValueError, IndexError):
                continue
    
    # Se há produtos mostrados e número simples, pode ser seleção + quantidade
    if last_shown_products:
        # "3 coca cola" - pode ser quantidade 3 do produto coca cola
        product_qty_pattern = r'\b(\d+(?:[.,]\d+)?)\s+(?:da?|do|de)?\s*(\w+)'
        matches = re.finditer(product_qty_pattern, normalized)
        for match in matches:
            try:
                qty = float(match.group(1).replace(',', '.'))
                product_ref = match.group(2)
                
                # Verifica se o produto mencionado está na lista
                for product in last_shown_products:
                    product_name = (product.get('descricao') or 
                                  product.get('canonical_name', '')).lower()
                    if product_ref in product_name or product_name in product_ref:
                        quantities.append(qty)
                        break
            except ValueError:
                continue
    
    return quantities

def detect_quantity_modifiers(text: str) -> Dict:
    """Detecta modificadores de quantidade no texto."""
    normalized = normalize_text(text)
    modifiers = {
        'action': None,  # 'add', 'set', 'remove'
        'reference': None,  # 'all', 'item_index', 'product_name'
        'target_quantity': None
    }
    
    # Ações de modificação
    if re.search(r'\b(?:adicionar|incluir|somar|mais)\b', normalized):
        modifiers['action'] = 'add'
    elif re.search(r'\b(?:definir|setar|alterar|mudar|trocar)\b', normalized):
        modifiers['action'] = 'set'
    elif re.search(r'\b(?:remover|tirar|excluir|deletar)\b', normalized):
        modifiers['action'] = 'remove'
    
    # Referências
    if re.search(r'\b(?:tudo|todos|todas|carrinho|completo)\b', normalized):
        modifiers['reference'] = 'all'
    
    # Índices de item
    item_match = re.search(r'\b(?:item|produto)\s+(\d+)\b', normalized)
    if item_match:
        modifiers['reference'] = f"item_{item_match.group(1)}"
    
    return modifiers

def extract_quantity(text: str, last_shown_products: List = None, default: float = 1.0) -> float:
    """
    Função principal para extrair quantidade de um texto.
    
    Args:
        text: Texto do usuário
        last_shown_products: Lista de produtos mostrados recentemente
        default: Valor padrão se nenhuma quantidade for encontrada
        
    Returns:
        Quantidade extraída ou valor padrão
    """
    if not text or not isinstance(text, str):
        return default
    
    all_quantities = []
    
    # Extrai quantidades de diferentes formas
    all_quantities.extend(extract_numeric_quantities(text))
    all_quantities.extend(extract_word_quantities(text))
    all_quantities.extend(extract_contextual_quantities(text, last_shown_products))
    
    # Remove duplicatas e ordena
    unique_quantities = list(set(all_quantities))
    unique_quantities.sort()
    
    if not unique_quantities:
        return default
    
    # Estratégia de seleção da quantidade mais provável
    # Prioriza: 1) Valores pequenos e comuns (1-50), 2) Valores únicos
    
    # Filtra valores razoáveis para produtos comuns
    reasonable_quantities = [q for q in unique_quantities if 0.1 <= q <= 100]
    
    if reasonable_quantities:
        # Se há apenas um valor razoável, usa ele
        if len(reasonable_quantities) == 1:
            return reasonable_quantities[0]
        
        # Se há múltiplos, prioriza valores típicos (1, 2, 3, 5, 10, etc.)
        common_values = [1, 2, 3, 4, 5, 6, 10, 12, 20, 24, 30, 50]
        for common in common_values:
            if common in reasonable_quantities:
                return float(common)
        
        # Senão, pega o menor valor razoável
        return reasonable_quantities[0]
    
    # Se nenhum valor razoável, retorna o padrão
    return default

def is_valid_quantity(quantity: Union[int, float, str]) -> bool:
    """Verifica se uma quantidade é válida para adicionar ao carrinho."""
    try:
        if isinstance(quantity, str):
            # Remove vírgulas e converte
            quantity = float(quantity.replace(',', '.'))
        
        qty = float(quantity)
        
        # Verifica limites razoáveis
        return 0.01 <= qty <= 10000.0
        
    except (ValueError, TypeError):
        return False

def format_quantity_display(quantity: Union[int, float]) -> str:
    """Formata quantidade para exibição amigável."""
    try:
        qty = float(quantity)
        
        # Se é inteiro, mostra sem decimais
        if qty == int(qty):
            return str(int(qty))
        
        # Se tem decimais, formata adequadamente
        if qty < 1:
            return f"{qty:.2f}".rstrip('0').rstrip('.')
        else:
            return f"{qty:.1f}".rstrip('0').rstrip('.')
            
    except (ValueError, TypeError):
        return "1"

def parse_quantity_with_unit(text: str) -> Tuple[float, str]:
    """
    Extrai quantidade e unidade de medida do texto.
    
    Returns:
        Tupla (quantidade, unidade)
    """
    normalized = normalize_text(text)
    
    # Padrões para quantidade + unidade
    patterns = [
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
    
    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            try:
                quantity = float(match.group(1).replace(',', '.'))
                unit_text = match.group(2).lower()
                
                # Normaliza unidade
                for unit_key, unit_variants in UNIT_PATTERNS.items():
                    if unit_text in unit_variants:
                        return quantity, unit_key
                
                return quantity, unit_text
                
            except ValueError:
                continue
    
    # Se não encontrou unidade específica, extrai apenas quantidade
    quantity = extract_quantity(text)
    return quantity, "un"

def extract_multiple_quantities(text: str) -> List[Tuple[float, str]]:
    """Extrai múltiplas quantidades e produtos do texto."""
    normalized = normalize_text(text)
    results = []
    
    # Padrões para múltiplos itens
    # "2 coca cola e 3 pepsi"
    # "5 kg de arroz, 2 litros de óleo"
    
    multi_patterns = [
        r'(\d+(?:[.,]\d+)?)\s*(?:de\s+)?(\w+(?:\s+\w+)*?)(?:\s+e\s+|,\s*|$)',
        r'(\d+(?:[.,]\d+)?)\s*(kg|l|g|ml|un|unidade|cx|pc|lata)\s+(?:de\s+)?(\w+(?:\s+\w+)*?)(?:\s+e\s+|,\s*|$)',
    ]
    
    for pattern in multi_patterns:
        matches = re.finditer(pattern, normalized, re.IGNORECASE)
        for match in matches:
            try:
                if len(match.groups()) == 2:  # quantidade + produto
                    qty = float(match.group(1).replace(',', '.'))
                    product = match.group(2).strip()
                    results.append((qty, product))
                elif len(match.groups()) == 3:  # quantidade + unidade + produto
                    qty = float(match.group(1).replace(',', '.'))
                    unit = match.group(2)
                    product = match.group(3).strip()
                    results.append((qty, f"{product} ({unit})"))
            except ValueError:
                continue
    
    return results

# Função para compatibilidade com código existente
def extract_quantity_from_message(message: str, context: Dict = None) -> float:
    """Função de compatibilidade para extrair quantidade de mensagem."""
    last_products = context.get('last_shown_products', []) if context else []
    return extract_quantity(message, last_products)