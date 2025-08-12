# file: IA/utils/product_utils.py
"""
Utilitários centralizados para manipulação de produtos no G.A.V.
Remove inconsistências entre dados da KB e do banco de dados.
"""

from typing import Dict, List, Optional, Union
import decimal

def get_product_name(product: Dict) -> str:
    """
    Função única para obter nome do produto.
    Resolve inconsistência entre KB (canonical_name) e banco (descricao).
    
    Args:
        product: Dicionário com dados do produto
        
    Returns:
        str: Nome do produto ou "Produto sem nome"
    """
    if not product:
        return "Produto sem nome"
    
    # Prioriza descricao (banco) sobre canonical_name (KB)
    return product.get("descricao") or product.get("canonical_name", "Produto sem nome")

def get_product_price(product: Dict) -> float:
    """
    Função única para obter preço do produto.
    Padroniza obtenção de preço entre diferentes fontes.
    
    Args:
        product: Dicionário com dados do produto
        
    Returns:
        float: Preço do produto ou 0.0
    """
    if not product:
        return 0.0
    
    # Prioriza pvenda sobre preco_varejo
    price = product.get("pvenda") or product.get("preco_varejo", 0.0)
    
    # Converte Decimal para float se necessário
    if isinstance(price, decimal.Decimal):
        return float(price)
    
    try:
        return float(price)
    except (ValueError, TypeError):
        return 0.0

def get_product_code(product: Dict) -> int:
    """
    Função única para obter código do produto.
    
    Args:
        product: Dicionário com dados do produto
        
    Returns:
        int: Código do produto ou 0
    """
    if not product:
        return 0
    
    codprod = product.get("codprod", 0)
    
    try:
        return int(codprod)
    except (ValueError, TypeError):
        return 0

def get_product_quantity(item: Dict) -> Union[int, float]:
    """
    Função única para obter quantidade de um item do carrinho.
    
    Args:
        item: Item do carrinho
        
    Returns:
        Union[int, float]: Quantidade do item
    """
    if not item:
        return 0
    
    quantity = item.get("qt", item.get("quantidade", 0))
    
    try:
        # Se é número inteiro, retorna int
        if isinstance(quantity, float) and quantity.is_integer():
            return int(quantity)
        return float(quantity)
    except (ValueError, TypeError):
        return 0

def normalize_product_data(product: Dict) -> Dict:
    """
    Normaliza dados do produto independente da origem (KB ou banco).
    
    Args:
        product: Dados brutos do produto
        
    Returns:
        Dict: Produto com campos padronizados
    """
    if not product:
        return {}
    
    normalized = product.copy()
    
    # Garante campos padronizados
    normalized["display_name"] = get_product_name(product)
    normalized["display_price"] = get_product_price(product)
    normalized["product_code"] = get_product_code(product)
    
    # Garante que codprod é inteiro
    normalized["codprod"] = get_product_code(product)
    
    # Normaliza fonte se não existir
    if "source" not in normalized:
        if "canonical_name" in product:
            normalized["source"] = "knowledge_base"
        else:
            normalized["source"] = "database"
    
    return normalized

def format_price_display(price: Union[int, float, str]) -> str:
    """
    Formata preço para exibição amigável no WhatsApp.
    
    Args:
        price: Preço a ser formatado
        
    Returns:
        str: Preço formatado (ex: "R$ 8,50")
    """
    try:
        price_float = float(price)
        
        # Formato brasileiro: vírgula para decimal, ponto para milhares
        formatted = f"R$ {price_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
        
    except (ValueError, TypeError):
        return "R$ 0,00"

def format_quantity_display(quantity: Union[int, float]) -> str:
    """
    Formata quantidade para exibição amigável.
    
    Args:
        quantity: Quantidade a ser formatada
        
    Returns:
        str: Quantidade formatada
    """
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

def calculate_item_subtotal(item: Dict) -> float:
    """
    Calcula subtotal de um item do carrinho.
    
    Args:
        item: Item do carrinho
        
    Returns:
        float: Subtotal (preço * quantidade)
    """
    price = get_product_price(item)
    quantity = get_product_quantity(item)
    
    return price * quantity

def validate_product_data(product: Dict) -> bool:
    """
    Valida se dados do produto estão completos e corretos.
    
    Args:
        product: Dados do produto
        
    Returns:
        bool: True se produto é válido
    """
    if not product or not isinstance(product, dict):
        return False
    
    # Verifica campos essenciais
    has_name = bool(get_product_name(product) and get_product_name(product) != "Produto sem nome")
    has_code = get_product_code(product) > 0
    has_price = get_product_price(product) >= 0
    
    return has_name and has_code and has_price

def enrich_product_list(products: List[Dict]) -> List[Dict]:
    """
    Enriquece lista de produtos com campos padronizados.
    
    Args:
        products: Lista de produtos
        
    Returns:
        List[Dict]: Lista de produtos enriquecidos
    """
    if not products:
        return []
    
    enriched = []
    for product in products:
        if validate_product_data(product):
            enriched.append(normalize_product_data(product))
    
    return enriched

def find_product_in_list(products: List[Dict], search_criteria: Dict) -> Optional[Dict]:
    """
    Encontra produto em lista baseado em critérios de busca.
    
    Args:
        products: Lista de produtos
        search_criteria: Critérios de busca (ex: {"codprod": 123})
        
    Returns:
        Dict: Produto encontrado ou None
    """
    if not products or not search_criteria:
        return None
    
    for product in products:
        match = True
        for key, value in search_criteria.items():
            if key == "codprod":
                if get_product_code(product) != value:
                    match = False
                    break
            elif key == "name":
                if value.lower() not in get_product_name(product).lower():
                    match = False
                    break
            elif product.get(key) != value:
                match = False
                break
        
        if match:
            return product
    
    return None

def sort_products_by_relevance(products: List[Dict], search_term: str = "") -> List[Dict]:
    """
    Ordena produtos por relevância baseado no termo de busca.
    
    Args:
        products: Lista de produtos
        search_term: Termo de busca usado
        
    Returns:
        List[Dict]: Produtos ordenados por relevância
    """
    if not products:
        return []
    
    if not search_term:
        # Se não há termo de busca, ordena por preço
        return sorted(products, key=lambda p: get_product_price(p))
    
    # Ordena por relevância do nome
    search_lower = search_term.lower()
    
    def relevance_score(product):
        name = get_product_name(product).lower()
        
        # Pontuação baseada em correspondência
        if search_lower == name:
            return 1000  # Correspondência exata
        elif name.startswith(search_lower):
            return 900   # Começa com termo
        elif search_lower in name:
            return 800   # Contém termo
        else:
            return 0     # Sem correspondência
    
    return sorted(products, key=relevance_score, reverse=True)

def get_cart_summary(cart_items: List[Dict]) -> Dict:
    """
    Calcula resumo do carrinho de compras.
    
    Args:
        cart_items: Lista de itens do carrinho
        
    Returns:
        Dict: Resumo com totais e estatísticas
    """
    if not cart_items:
        return {
            "total_items": 0,
            "total_quantity": 0,
            "total_value": 0.0,
            "average_price": 0.0,
            "unique_products": 0
        }
    
    total_quantity = 0
    total_value = 0.0
    unique_codes = set()
    
    for item in cart_items:
        quantity = get_product_quantity(item)
        subtotal = calculate_item_subtotal(item)
        
        total_quantity += quantity
        total_value += subtotal
        unique_codes.add(get_product_code(item))
    
    return {
        "total_items": len(cart_items),
        "total_quantity": total_quantity,
        "total_value": total_value,
        "average_price": total_value / total_quantity if total_quantity > 0 else 0.0,
        "unique_products": len(unique_codes)
    }

def merge_duplicate_cart_items(cart_items: List[Dict]) -> List[Dict]:
    """
    Mescla itens duplicados no carrinho (mesmo codprod).
    
    Args:
        cart_items: Lista de itens do carrinho
        
    Returns:
        List[Dict]: Carrinho com itens mesclados
    """
    if not cart_items:
        return []
    
    merged = {}
    
    for item in cart_items:
        code = get_product_code(item)
        
        if code in merged:
            # Soma quantidades
            existing_qty = get_product_quantity(merged[code])
            new_qty = get_product_quantity(item)
            merged[code]["qt"] = existing_qty + new_qty
        else:
            merged[code] = item.copy()
    
    return list(merged.values())