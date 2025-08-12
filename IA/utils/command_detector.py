# file: utils/command_detector.py
"""
Detector de Comandos Centralizados
VERSÃO CORRIGIDA: Detecção robusta de todos os comandos críticos
"""

import re
from typing import Tuple, Dict, List, Union

def is_valid_cnpj(cnpj_str: str) -> bool:
    """
    Valida se uma string contém um CNPJ válido (formato básico).
    
    Args:
        cnpj_str: String para validar
        
    Returns:
        bool: True se é um CNPJ válido
    """
    if not cnpj_str:
        return False
    
    # Remove tudo que não é dígito
    digits = re.sub(r'\D', '', cnpj_str.strip())
    
    # CNPJ deve ter exatamente 14 dígitos
    if len(digits) != 14:
        return False
    
    # Verifica se não são todos iguais (11111111111111, etc.)
    if len(set(digits)) == 1:
        return False
    
    return True

def detect_cart_clear_command(message: str) -> bool:
    """
    Detecta comandos para esvaziar/limpar carrinho.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é comando de limpeza
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    
    # Comandos explícitos de limpeza
    clear_commands = [
        'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
        'resetar carrinho', 'apagar carrinho', 'deletar carrinho',
        'esvaziar tudo', 'limpar tudo', 'zerar tudo', 
        'apagar tudo', 'deletar tudo', 'remover tudo',
        'começar de novo', 'recomeçar', 'reiniciar',
        'do zero', 'novo pedido', 'nova compra',
        'limpa', 'esvazia', 'zera', 'apaga'
    ]
    
    # Verifica comandos exatos
    for command in clear_commands:
        if command in message_lower:
            return True
    
    # Padrões regex para variações
    clear_patterns = [
        r'\b(limpar|esvaziar|zerar|apagar|deletar|remover)\s+(o\s+)?carrinho\b',
        r'\b(carrinho|tudo)\s+(limpo|vazio|zerado)\b',
        r'\bcomeca\w*\s+de\s+novo\b',
        r'\bdo\s+zero\b',
        r'\breinicia\w*\s+(carrinho|tudo|compra)\b'
    ]
    
    for pattern in clear_patterns:
        if re.search(pattern, message_lower):
            return True
    
    return False

def detect_cart_view_command(message: str) -> bool:
    """
    Detecta comandos para visualizar carrinho.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é comando para ver carrinho
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    
    view_commands = [
        'carrinho', 'meu carrinho', 'ver carrinho', 'mostrar carrinho',
        'listar carrinho', 'itens', 'meus itens', 'compras', 'pedido'
    ]
    
    # Comando exato
    if message_lower in view_commands:
        return True
    
    # Padrões regex
    view_patterns = [
        r'^\s*(ver|mostrar|listar)\s+(o\s+)?carrinho\s*$',
        r'^\s*meu\s+carrinho\s*$',
        r'^\s*carrinho\s*$'
    ]
    
    for pattern in view_patterns:
        if re.match(pattern, message_lower):
            return True
    
    return False

def detect_checkout_command(message: str) -> bool:
    """
    Detecta comandos para finalizar compra.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é comando de checkout
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    
    checkout_commands = [
        'finalizar', 'checkout', 'comprar', 'fechar pedido',
        'fechar compra', 'confirmar pedido', 'confirmar compra',
        'prosseguir', 'continuar', 'enviar pedido'
    ]
    
    # Comando exato
    if message_lower in checkout_commands:
        return True
    
    # Padrões regex
    checkout_patterns = [
        r'^\s*(finalizar|fechar|confirmar)\s+(pedido|compra)\s*$',
        r'^\s*quero\s+(comprar|finalizar)\s*$',
        r'^\s*(prosseguir|continuar)\s+(com\s+)?(pedido|compra)\s*$'
    ]
    
    for pattern in checkout_patterns:
        if re.match(pattern, message_lower):
            return True
    
    return False

def detect_products_command(message: str) -> bool:
    """
    Detecta comandos para mostrar produtos.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é comando para mostrar produtos
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    
    products_commands = [
        'produtos', 'mostrar produtos', 'ver produtos', 'listar produtos',
        'catálogo', 'catalogo', 'menu', 'opções', 'opcoes'
    ]
    
    # Comando exato
    if message_lower in products_commands:
        return True
    
    # Padrões regex
    products_patterns = [
        r'^\s*(ver|mostrar|listar)\s+produtos\s*$',
        r'^\s*que\s+produtos?\s+(tem|há|ha|vocês?\s+tem|possui)\s*$',
        r'^\s*produtos?\s+disponíveis?\s*$'
    ]
    
    for pattern in products_patterns:
        if re.match(pattern, message_lower):
            return True
    
    return False

def detect_numeric_selection(message: str) -> Union[int, None]:
    """
    Detecta seleção numérica (1, 2 ou 3).
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        int: Número selecionado (1-3) ou None
    """
    if not message:
        return None
    
    # Busca números 1, 2 ou 3 isolados
    match = re.match(r'^\s*([123])\s*$', message.strip())
    if match:
        return int(match.group(1))
    
    return None

def detect_product_search(message: str) -> Union[str, None]:
    """
    Detecta busca por produtos específicos.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        str: Termo de busca ou None
    """
    if not message:
        return None
    
    message_lower = message.lower().strip()
    
    # Palavras que indicam busca por produto
    search_indicators = [
        'quero', 'preciso', 'busco', 'procuro', 'tem', 'há', 'ha',
        'vende', 'vendo', 'comprar', 'onde está', 'onde esta'
    ]
    
    # Produtos comuns no vocabulário
    product_keywords = [
        'coca', 'cola', 'refrigerante', 'sabão', 'sabao', 'detergente',
        'omo', 'bebida', 'limpeza', 'produto'
    ]
    
    # Se contém indicador + produto, extrai termo
    has_indicator = any(indicator in message_lower for indicator in search_indicators)
    has_product = any(keyword in message_lower for keyword in product_keywords)
    
    if has_indicator or has_product:
        # Remove indicadores e retorna o termo limpo
        cleaned = message_lower
        for indicator in search_indicators:
            cleaned = re.sub(f'\\b{indicator}\\b', '', cleaned)
        
        # Remove palavras de ligação
        cleaned = re.sub(r'\b(o|a|os|as|um|uma|de|da|do|des|das|para|por)\b', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        if cleaned:
            return cleaned
    
    # Se não detectou padrão específico, mas contém palavra-chave de produto
    if any(keyword in message_lower for keyword in product_keywords):
        return message.strip()
    
    return None

def detect_greetings(message: str) -> bool:
    """
    Detecta saudações.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é saudação
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    greetings = [
        'oi', 'olá', 'ola', 'boa', 'bom dia', 'boa tarde', 
        'boa noite', 'e aí', 'e ai', 'hello', 'hi', 'eae'
    ]
    
    # Saudação simples
    if message_lower in greetings:
        return True
    
    # Padrões de saudação
    greeting_patterns = [
        r'^\s*(oi|olá|ola)\s*[!.]*\s*$',
        r'^\s*bom\s+dia\s*[!.]*\s*$',
        r'^\s*boa\s+(tarde|noite)\s*[!.]*\s*$'
    ]
    
    for pattern in greeting_patterns:
        if re.match(pattern, message_lower):
            return True
    
    return False

def detect_checkout_context_by_history(conversation_history: List[Dict]) -> Dict[str, bool]:
    """
    Detecta contexto de checkout baseado no histórico da conversa.
    
    Args:
        conversation_history: Lista do histórico de mensagens
        
    Returns:
        Dict com flags de contexto de checkout
    """
    context = {
        'awaiting_cnpj': False,
        'last_request_was_cnpj': False,
        'checkout_initiated': False
    }
    
    if not conversation_history:
        return context
    
    # Analisa últimas 3 mensagens do bot
    recent_bot_messages = []
    for msg in reversed(conversation_history):
        if msg.get('role') == 'assistant':
            recent_bot_messages.append(msg.get('message', '').lower())
            if len(recent_bot_messages) >= 3:
                break
    
    if not recent_bot_messages:
        return context
    
    # Última mensagem do bot
    last_bot_msg = recent_bot_messages[0]
    
    # Palavras-chave que indicam solicitação de CNPJ
    cnpj_keywords = ['cnpj', 'finalizar', 'checkout', 'compra', 'identificar']
    
    if any(keyword in last_bot_msg for keyword in cnpj_keywords):
        context['awaiting_cnpj'] = True
        context['last_request_was_cnpj'] = True
    
    # Verifica se checkout foi iniciado recentemente
    for msg in recent_bot_messages:
        if any(word in msg for word in ['finalizar', 'checkout', 'cnpj']):
            context['checkout_initiated'] = True
            break
    
    return context

def analyze_critical_command(message: str, session_data: Dict) -> Tuple[str, Dict]:
    """
    Análise centralizada de comandos críticos com priorização.
    Esta é a função principal que deve ser usada em todos os lugares.
    
    Args:
        message: Mensagem do usuário
        session_data: Dados da sessão atual
        
    Returns:
        Tuple: (command_type, parameters)
    """
    if not message:
        return 'unknown', {}
    
    message_clean = message.strip()
    
    # 1. PRIORIDADE MÁXIMA: Comandos de limpeza de carrinho
    if detect_cart_clear_command(message_clean):
        return 'clear_cart', {}
    
    # 2. PRIORIDADE ALTA: CNPJ em contexto de checkout
    if is_valid_cnpj(message_clean):
        checkout_context = detect_checkout_context_by_history(
            session_data.get('conversation_history', [])
        )
        
        if checkout_context['awaiting_cnpj'] or checkout_context['checkout_initiated']:
            return 'find_customer_by_cnpj', {'cnpj': re.sub(r'\D', '', message_clean)}
    
    # 3. SELEÇÃO NUMÉRICA (alta prioridade se há produtos mostrados)
    numeric_selection = detect_numeric_selection(message_clean)
    if numeric_selection is not None:
        last_shown = session_data.get('last_shown_products', [])
        if last_shown:
            return 'add_item_to_cart', {'product_index': numeric_selection - 1}
    
    # 4. COMANDOS EXPLÍCITOS
    if detect_cart_view_command(message_clean):
        return 'view_cart', {}
    
    if detect_checkout_command(message_clean):
        return 'checkout', {}
    
    if detect_products_command(message_clean):
        return 'get_top_selling_products', {}
    
    # 5. BUSCA POR PRODUTOS
    search_term = detect_product_search(message_clean)
    if search_term:
        return 'get_top_selling_products_by_name', {'search_term': search_term}
    
    # 6. SAUDAÇÕES
    if detect_greetings(message_clean):
        return 'handle_chitchat', {'response_text': 'Olá! Como posso ajudar você hoje?'}
    
    # Comando não reconhecido
    return 'unknown', {}

def get_command_confidence(message: str, session_data: Dict) -> Dict:
    """
    Retorna nível de confiança da detecção de comando.
    
    Args:
        message: Mensagem do usuário
        session_data: Dados da sessão
        
    Returns:
        Dict com comando e nível de confiança
    """
    command_type, parameters = analyze_critical_command(message, session_data)
    
    # Calcula confiança baseada em critérios
    confidence = 0.5  # Base
    
    if command_type == 'clear_cart':
        confidence = 0.95 if detect_cart_clear_command(message) else 0.5
    elif command_type == 'find_customer_by_cnpj':
        confidence = 0.9 if is_valid_cnpj(message) else 0.5
    elif command_type == 'add_item_to_cart':
        confidence = 0.95 if detect_numeric_selection(message) else 0.5
    elif command_type in ['view_cart', 'checkout', 'get_top_selling_products']:
        confidence = 0.8
    elif command_type == 'get_top_selling_products_by_name':
        confidence = 0.6
    elif command_type == 'handle_chitchat':
        confidence = 0.7 if detect_greetings(message) else 0.5
    
    return {
        'command': command_type,
        'parameters': parameters,
        'confidence': confidence
    }