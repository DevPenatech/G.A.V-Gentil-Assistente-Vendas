# file: IA/utils/command_detector.py
"""
Detecção centralizada de comandos críticos para o G.A.V.
Consolida todas as funções de detecção que estavam duplicadas.
"""

import re
from typing import Dict, Optional, Tuple, List

def is_valid_cnpj(cnpj: str) -> bool:
    """
    Função única para validação de CNPJ - remove duplicação entre arquivos.
    
    Args:
        cnpj: String contendo CNPJ a ser validado
        
    Returns:
        bool: True se CNPJ é válido, False caso contrário
    """
    if not cnpj:
        return False
    
    # Remove caracteres não numéricos
    cnpj_digits = re.sub(r'\D', '', cnpj)
    
    # Verifica se tem 14 dígitos
    if len(cnpj_digits) != 14:
        return False
    
    # Verifica se não são todos iguais (ex: 11111111111111)
    if cnpj_digits == cnpj_digits[0] * 14:
        return False
    
    try:
        # Valida primeiro dígito verificador
        sequence = [int(cnpj_digits[i]) for i in range(12)]
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum1 = sum(sequence[i] * weights1[i] for i in range(12))
        digit1 = ((sum1 % 11) < 2) and 0 or (11 - (sum1 % 11))
        
        if digit1 != int(cnpj_digits[12]):
            return False
        
        # Valida segundo dígito verificador
        sequence.append(digit1)
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        sum2 = sum(sequence[i] * weights2[i] for i in range(13))
        digit2 = ((sum2 % 11) < 2) and 0 or (11 - (sum2 % 11))
        
        return digit2 == int(cnpj_digits[13])
        
    except (ValueError, IndexError):
        return False

def detect_cart_clear_command(message: str) -> bool:
    """
    Função única para detectar comandos de limpeza de carrinho.
    Consolida detection de session_manager.py, llm_interface.py e app.py
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é comando de limpeza de carrinho
    """
    if not message:
        return False
        
    message_lower = message.lower().strip()
    
    # Comandos explícitos - PRIORIDADE MÁXIMA
    explicit_commands = [
        'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
        'resetar carrinho', 'apagar carrinho', 'deletar carrinho',
        'esvaziar tudo', 'limpar tudo', 'zerar tudo',
        'apagar tudo', 'deletar tudo', 'remover tudo',
        'começar de novo', 'recomeçar', 'reiniciar',
        'do zero', 'novo pedido', 'nova compra',
        'limpa carrinho', 'esvazia carrinho', 'zera carrinho'
    ]
    
    # Verifica comandos exatos primeiro
    for command in explicit_commands:
        if command in message_lower:
            return True
    
    # Padrões com regex mais flexíveis
    patterns = [
        r'\b(esvaziar|limpar|zerar|apagar|deletar|remover)\s+(o\s+)?carrinho\b',
        r'\b(carrinho|tudo)\s+(vazio|limpo|zerado)\b',
        r'\bcomeca\w*\s+de\s+novo\b',
        r'\bdo\s+zero\b',
        r'\breinicia\w*\s+(carrinho|tudo|compra)\b',
        r'\b(esvazia|limpa|zera)\s+(carrinho|tudo)?\b'
    ]
    
    for pattern in patterns:
        if re.search(pattern, message_lower):
            return True
    
    return False

def detect_numeric_selection(message: str) -> Optional[int]:
    """
    Extração limpa de seleção numérica (1, 2 ou 3).
    
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
    
    # 3. PRIORIDADE MÉDIA: Seleção numérica
    numeric_selection = detect_numeric_selection(message_clean)
    if numeric_selection and session_data.get('last_shown_products'):
        return 'add_item_to_cart', {'index': numeric_selection}
    
    # 4. Comandos diretos simples
    message_lower = message_clean.lower()
    
    if any(cmd in message_lower for cmd in ['carrinho', 'ver carrinho']):
        return 'view_cart', {}
    
    if any(cmd in message_lower for cmd in ['finalizar', 'fechar', 'checkout']):
        return 'checkout', {}
    
    if any(cmd in message_lower for cmd in ['produtos', 'mais vendidos', 'populares']):
        return 'get_top_selling_products', {}
    
    if message_lower in ['mais', 'proximo', 'próximo']:
        return 'show_more_products', {}
    
    # 5. Comandos de remoção
    if any(word in message_lower for word in ['remover', 'tirar', 'excluir', 'deletar']):
        # Verifica se especifica item
        index_match = re.search(r'\b(\d+)\b', message_clean)
        if index_match:
            return 'update_cart_item', {'action': 'remove', 'index': int(index_match.group(1))}
        else:
            return 'update_cart_item', {'action': 'remove'}
    
    # 6. Busca de produto (fallback)
    if len(message_clean) > 2:
        return 'get_top_selling_products_by_name', {'product_name': message_clean}
    
    return 'unknown', {}

def detect_simple_greetings(message: str) -> bool:
    """
    Detecta saudações simples.
    
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
        'boa noite', 'e aí', 'e ai', 'hello', 'hi'
    ]
    
    return any(greeting in message_lower for greeting in greetings)

def detect_help_requests(message: str) -> bool:
    """
    Detecta pedidos de ajuda.
    
    Args:
        message: Mensagem do usuário
        
    Returns:
        bool: True se é pedido de ajuda
    """
    if not message:
        return False
    
    message_lower = message.lower().strip()
    help_keywords = [
        'ajuda', 'help', 'como', 'funciona', 'não entendi', 
        'nao entendi', 'socorro', 'o que', 'que posso'
    ]
    
    return any(keyword in message_lower for keyword in help_keywords)

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
    
    return {
        'command': command_type,
        'parameters': parameters,
        'confidence': confidence
    }