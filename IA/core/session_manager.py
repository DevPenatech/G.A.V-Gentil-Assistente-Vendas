# file: session_manager.py
import json
import logging
import os
import re
from typing import List, Dict, Optional
from datetime import datetime

import redis


_redis_password = os.getenv("REDIS_PASSWORD", "").strip()
_redis_config = {
    "host": os.getenv("REDIS_HOST", "redis"),  # Use "redis" como padrão (nome do serviço)
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": 0,
    "decode_responses": True,
}


# Só adiciona senha se ela existir e não for vazia
if _redis_password and _redis_password not in ["", "<password>"]:
    _redis_config["password"] = _redis_password

try:
    redis_client = redis.Redis(**_redis_config)
    redis_client.ping()  # Testa a conexão imediatamente
    logging.info("[SESSION] Redis conectado com sucesso")
except Exception as e:
    logging.warning(f"[SESSION] Redis não disponível, usando fallback para arquivo: {e}")
    redis_client = None


def get_redis_client() -> Optional[redis.Redis]:
    """Retorna o cliente Redis global se a conexão estiver ativa."""
    global redis_client
    try:
        redis_client.ping()
        return redis_client
    except Exception as e:
        logging.error(f"[SESSION] Falha ao conectar-se ao Redis: {e}")
        return None


def save_session(session_id: str, data: Dict):
    """Salva os dados da sessão no Redis com TTL de 1 hora e fallback para arquivo."""
    if not session_id or not data:
        logging.warning("[SESSION] Tentativa de salvar sessão com dados inválidos")
        return
        
    try:
        client = get_redis_client()
        if client:
            client.set(session_id, json.dumps(data), ex=3600)
            logging.debug(f"[SESSION] Sessão salva no Redis: {session_id}")
        else:
            # Fallback para arquivo se Redis não estiver disponível
            _save_session_to_file(session_id, data)
            
    except Exception as e:
        logging.error(f"[SESSION] Erro ao salvar sessão no Redis: {e}")
        # Fallback para arquivo
        _save_session_to_file(session_id, data)


def load_session(session_id: str) -> Dict:
    """Carrega os dados da sessão do Redis com fallback para arquivo."""
    if not session_id:
        logging.warning("[SESSION] Tentativa de carregar sessão sem ID")
        return {}
        
    try:
        client = get_redis_client()
        if client:
            raw = client.get(session_id)
            if raw:
                data = json.loads(raw)
                logging.debug(f"[SESSION] Sessão carregada do Redis: {session_id}")
                return data
        
        # Fallback para arquivo se não encontrar no Redis
        return _load_session_from_file(session_id)
        
    except Exception as e:
        logging.error(f"[SESSION] Erro ao carregar sessão do Redis: {e}")
        # Fallback para arquivo
        return _load_session_from_file(session_id)


def clear_session(session_id: str):
    """Remove os dados da sessão do Redis e arquivo."""
    if not session_id:
        return
        
    try:
        client = get_redis_client()
        if client:
            client.delete(session_id)
            logging.debug(f"[SESSION] Sessão removida do Redis: {session_id}")
        
        # Remove também do arquivo
        _clear_session_file(session_id)
        
    except Exception as e:
        logging.error(f"[SESSION] Erro ao limpar sessão: {e}")
        # Tenta remover do arquivo mesmo se Redis falhar
        _clear_session_file(session_id)

# Funções de fallback para arquivo
def _get_session_file_path(session_id: str) -> str:
    """Retorna caminho do arquivo de sessão."""
    # Sanitiza o session_id para nome de arquivo seguro
    safe_id = re.sub(r'[^\w\-_.]', '_', session_id)
    return f"data/session_{safe_id}.json"

def _save_session_to_file(session_id: str, data: Dict):
    """Salva sessão em arquivo como fallback."""
    try:
        os.makedirs("data", exist_ok=True)
        file_path = _get_session_file_path(session_id)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logging.info(f"[SESSION] Sessão salva em arquivo (fallback): {file_path}")
        
    except Exception as e:
        logging.error(f"[SESSION] Erro ao salvar sessão em arquivo: {e}")

def _load_session_from_file(session_id: str) -> Dict:
    """Carrega sessão de arquivo como fallback."""
    try:
        file_path = _get_session_file_path(session_id)
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logging.info(f"[SESSION] Sessão carregada de arquivo (fallback): {file_path}")
            return data
            
    except Exception as e:
        logging.error(f"[SESSION] Erro ao carregar sessão de arquivo: {e}")
    
    return {}

def _clear_session_file(session_id: str):
    """Remove arquivo de sessão."""
    try:
        file_path = _get_session_file_path(session_id)
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.debug(f"[SESSION] Arquivo de sessão removido: {file_path}")
    except Exception as e:
        logging.error(f"[SESSION] Erro ao remover arquivo de sessão: {e}")
    
def format_product_list_for_display(products: List[Dict], title: str, has_more: bool, offset: int = 0) -> str:
    if not products:
        return f"🤖 {title}\nNenhum produto encontrado com esse critério."
    
    response = f"🤖 {title}\n"
    for i, p in enumerate(products, 1 + offset):
        price = p.get('pvenda') or 0.0
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # 🆕 CORREÇÃO: Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')
        
        response += f"{i}. {product_name} - {price_str}\n"
    
    response += "Me diga o nome ou o número do item que deseja adicionar.\n"
    if has_more:
        response += "Ou digite 'mais' para ver outros resultados!"
    return response

def format_cart_for_display(cart: List[Dict]) -> str:
    if not cart:
        return "🤖 Seu carrinho de compras está vazio."
    
    response = "🛒 Seu Carrinho de Compras:\n"
    total = 0.0
    for item in cart:
        price = item.get('pvenda') or 0.0
        qt = item.get('qt', 0)
        subtotal = price * qt
        total += subtotal
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # 🆕 CORREÇÃO: Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = item.get('descricao') or item.get('canonical_name', 'Produto sem nome')
        
        response += f"- {product_name} (Qtd: {qt}) - Unit: {price_str} - Subtotal: {subtotal_str}\n"
    
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"-----------------------------------\nTOTAL DO PEDIDO: {total_str}"
    return response


def add_item_to_cart(cart: List[Dict], item: Dict, qt: float) -> None:
    """Adiciona um item ao carrinho ou incrementa a quantidade se ele já existir."""
    if qt <= 0:
        return

    for existing in cart:
        if (
            (item.get("codprod") and existing.get("codprod") == item.get("codprod"))
            or (item.get("canonical_name") and existing.get("canonical_name") == item.get("canonical_name"))
        ):
            existing["qt"] = existing.get("qt", 0) + qt
            return

    cart.append({**item, "qt": qt})


def remove_item_from_cart(cart: List[Dict], index: int) -> bool:
    """Remove um item do carrinho pelo índice (baseado em 0)."""
    if 0 <= index < len(cart):
        cart.pop(index)
        return True
    return False


def update_item_quantity(cart: List[Dict], index: int, qt: float) -> bool:
    """Atualiza a quantidade de um item específico do carrinho."""
    if 0 <= index < len(cart) and qt > 0:
        cart[index]["qt"] = qt
        return True
    return False


def add_quantity_to_item(cart: List[Dict], index: int, qt: float) -> bool:
    """Adiciona quantidade extra a um item existente no carrinho."""
    if 0 <= index < len(cart) and qt > 0:
        cart[index]["qt"] = cart[index].get("qt", 0) + qt
        return True
    return False

def add_message_to_history(session_data: Dict, role: str, message: str, action_type: str = None):
    """
    Adiciona uma mensagem ao histórico da conversa.
    
    Args:
        session_data: Dados da sessão
        role: 'user' ou 'assistant'
        message: Conteúdo da mensagem
        action_type: Tipo de ação realizada (opcional)
    """
    if 'conversation_history' not in session_data:
        session_data['conversation_history'] = []
    
    # Limita o histórico a 20 mensagens (10 pares) para não sobrecarregar a IA
    if len(session_data['conversation_history']) >= 20:
        session_data['conversation_history'] = session_data['conversation_history'][-18:]
    
    message_entry = {
        'role': role,
        'message': message,
        'timestamp': datetime.now().isoformat(),
    }
    
    if action_type:
        message_entry['action_type'] = action_type
        
    session_data['conversation_history'].append(message_entry)

def get_conversation_context(session_data: Dict, max_messages: int = 10) -> str:
    """
    Formata o histórico da conversa para enviar à IA.
    
    Args:
        session_data: Dados da sessão
        max_messages: Máximo de mensagens a incluir
        
    Returns:
        String formatada com o contexto da conversa
    """
    history = session_data.get('conversation_history', [])
    
    if not history:
        return "Esta é a primeira interação com o cliente."
    
    # Pega as últimas N mensagens
    recent_history = history[-max_messages:] if len(history) > max_messages else history
    
    context_lines = ["**HISTÓRICO DA CONVERSA (mensagens recentes):**"]
    
    for entry in recent_history:
        role_icon = "👤" if entry['role'] == 'user' else "🤖"
        message = entry['message']
        
        # Trunca mensagens muito longas
        if len(message) > 200:
            message = message[:200] + "..."
            
        context_lines.append(f"{role_icon} {entry['role'].upper()}: {message}")
        
        # Adiciona informação sobre ação realizada, se houver
        if entry.get('action_type'):
            context_lines.append(f"   ↳ Ação: {entry['action_type']}")
    
    context_lines.append("**FIM DO HISTÓRICO**")
    context_lines.append("")
    
    return "\n".join(context_lines)

def get_session_context_summary(session_data: Dict) -> str:
    """
    Cria um resumo do estado atual da sessão para a IA.
    """
    lines = []
    
    # Informações do carrinho
    cart = session_data.get('shopping_cart', [])
    if cart:
        lines.append(f"🛒 CARRINHO: {len(cart)} itens")
        for i, item in enumerate(cart[:3], 1):  # Mostra apenas os 3 primeiros
            product_name = item.get('descricao', item.get('canonical_name', 'Produto'))
            qt = item.get('qt', 0)
            lines.append(f"   {i}. {product_name} (Qtd: {qt})")
        if len(cart) > 3:
            lines.append(f"   ... e mais {len(cart) - 3} itens")
    else:
        lines.append("🛒 CARRINHO: vazio")
    
    # Última busca realizada
    last_search = session_data.get('last_search_params', {})
    if last_search:
        search_term = last_search.get('product_name', '')
        if search_term:
            lines.append(f"🔍 ÚLTIMA BUSCA: '{search_term}'")
    
    # Cliente identificado
    customer = session_data.get('customer_context')
    if customer:
        lines.append(f"👤 CLIENTE: {customer.get('nome', 'Identificado')}")
    else:
        lines.append("👤 CLIENTE: não identificado")
    
    # Ação pendente
    pending = session_data.get('pending_action')
    if pending:
        lines.append(f"⏳ AGUARDANDO: {pending}")
    
    return "\n".join(lines)