# file: IA/core/session_manager.py
import json
import logging
import os
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta

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
        if redis_client:
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
    
def clear_old_sessions():
    """Remove sessões antigas (mais de 7 dias)."""
    if redis_client:
        try:
            # Redis já expira automaticamente com TTL
            logging.info("Redis gerencia expiração automaticamente")
        except Exception as e:
            logging.warning(f"Erro ao limpar sessões Redis: {e}")
    
    # Limpa arquivos antigos
    sessions_dir = "data"
    if os.path.exists(sessions_dir):
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for filename in os.listdir(sessions_dir):
            if filename.startswith("session_"):
                filepath = os.path.join(sessions_dir, filename)
                
                try:
                    # Verifica data de modificação
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_time < cutoff_date:
                        os.remove(filepath)
                        logging.info(f"Sessão antiga removida: {filename}")
                except Exception as e:
                    logging.warning(f"Erro ao processar {filename}: {e}")    
    
def format_product_list_for_display(products: List[Dict], title: str, has_more: bool, offset: int = 0) -> str:
    """Formata lista de produtos para exibição com estilo direto e objetivo."""
    if not products:
        return f"{title}\nNão achei esse item. Posso sugerir similares?"
    
    # Limita a 3 produtos conforme especificação
    limited_products = products[:3]
    
    response = f"{title}:\n"
    for i, p in enumerate(limited_products, 1):
        price = p.get('pvenda') or p.get('preco_varejo', 0.0)
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')
        
        response += f"{i}. {product_name} — {price_str}\n"
    
    response += "Qual você quer? Responda 1, 2 ou 3."
    if has_more:
        response += "\nOu digite 'mais' para ver outros resultados!"
    return response

def format_cart_for_display(cart: List[Dict]) -> str:
    """Formata o carrinho para exibição com estilo direto."""
    if not cart:
        return "Seu carrinho está vazio."
    
    response = "**SEU CARRINHO:**\n"
    response += "-" * 25 + "\n"
    total = 0.0
    
    for i, item in enumerate(cart, 1):
        price = item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        subtotal = price * qt
        total += subtotal
        
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        subtotal_str = f"R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        # Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = item.get('descricao') or item.get('canonical_name', 'Produto sem nome')
        
        # Formata quantidade para exibição
        if isinstance(qt, float):
            qty_display = f"{qt:.1f}".rstrip('0').rstrip('.')
        else:
            qty_display = str(qt)
        
        response += f"{i}. {product_name}\n"
        response += f"   {qty_display}× {price_str} = {subtotal_str}\n"
    
    response += "-" * 25 + "\n"
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"**Total: {total_str}**"
    
    return response

def add_message_to_history(session_data: Dict, role: str, message: str, action_type: str = ""):
    """Adiciona mensagem ao histórico da conversa com contexto aprimorado."""
    if "conversation_history" not in session_data:
        session_data["conversation_history"] = []
    
    # Limita histórico a últimas 20 mensagens para performance
    if len(session_data["conversation_history"]) >= 20:
        session_data["conversation_history"] = session_data["conversation_history"][-19:]
    
    session_data["conversation_history"].append({
        "role": role,
        "message": message[:500],  # Limita tamanho da mensagem
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type
    })

def get_conversation_context(session_data: Dict, max_messages: int = 10) -> str:
    """Retorna contexto resumido da conversa para o LLM."""
    history = session_data.get("conversation_history", [])
    if not history:
        return "Primeira interação com o cliente."
    
    # Pega as últimas mensagens
    recent_history = history[-max_messages:]
    
    context = "HISTÓRICO RECENTE:\n"
    for msg in recent_history:
        role = "Cliente" if msg['role'] == 'user' else "G.A.V."
        context += f"{role}: {msg['message'][:100]}...\n"
    
    return context

def get_session_stats(session_data: Dict) -> Dict:
    """Retorna estatísticas da sessão atual."""
    stats = {
        "cart_items": len(session_data.get("shopping_cart", [])),
        "conversation_length": len(session_data.get("conversation_history", [])),
        "customer_identified": bool(session_data.get("customer_context")),
        "last_action": session_data.get("last_bot_action", "NONE"),
        "has_pending_selection": bool(session_data.get("last_shown_products"))
    }
    
    # Calcula valor total do carrinho
    cart = session_data.get("shopping_cart", [])
    total_value = 0.0
    for item in cart:
        price = item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        total_value += price * qt
    
    stats["cart_total_value"] = total_value
    
    return stats

def format_quick_actions(has_cart: bool = False, has_products: bool = False) -> str:
    """Gera menu de ações rápidas baseado no contexto atual."""
    actions = []
    
    if has_products:
        actions.extend(["1 Selecionar", "2 Ver mais"])
    
    if has_cart:
        actions.extend(["Ver carrinho", "Finalizar"])
    else:
        actions.append("Ver produtos")
    
    if not actions:
        actions = ["Ver produtos", "Buscar item"]
    
    # Limita a 3 opções conforme especificação
    limited_actions = actions[:3]
    
    menu = "Opções: "
    for i, action in enumerate(limited_actions, 1):
        menu += f"[{i} {action}] "
    
    return menu.strip()

def detect_user_intent_type(message: str, session_data: Dict) -> str:
    """Detecta tipo de intenção do usuário para melhor contexto."""
    message_lower = message.lower().strip()
    
    # Comandos numéricos diretos
    if re.match(r'^\s*[123]\s*$', message_lower):
        return "NUMERIC_SELECTION"
    
    # Comandos de carrinho
    cart_commands = ['carrinho', 'ver carrinho', 'mostrar carrinho']
    if any(cmd in message_lower for cmd in cart_commands):
        return "VIEW_CART"
    
    # Comandos de finalização
    checkout_commands = ['finalizar', 'fechar pedido', 'checkout', 'comprar']
    if any(cmd in message_lower for cmd in checkout_commands):
        return "CHECKOUT"
    
    # Comandos de busca
    if any(word in message_lower for word in ['quero', 'buscar', 'procurar', 'produto']):
        return "SEARCH_PRODUCT"
    
    # Saudações
    greetings = ['oi', 'olá', 'boa', 'bom dia', 'boa tarde', 'boa noite']
    if any(greeting in message_lower for greeting in greetings):
        return "GREETING"
    
    # Quantidades
    if re.search(r'\d+', message) and len(session_data.get("last_shown_products", [])) > 0:
        return "QUANTITY_SPECIFICATION"
    
    return "GENERAL"

def update_session_context(session_data: Dict, new_context: Dict):
    """Atualiza contexto da sessão de forma inteligente."""
    # Preserva dados importantes
    important_keys = [
        "customer_context", 
        "shopping_cart", 
        "conversation_history",
        "last_shown_products",
        "current_offset",
        "last_search_type",
        "last_search_params"
    ]
    
    for key in important_keys:
        if key in new_context:
            session_data[key] = new_context[key]
    
    # Atualiza timestamp da última atividade
    session_data["last_activity"] = datetime.now().isoformat()
    
    # Calcula métricas da sessão
    session_data["session_stats"] = get_session_stats(session_data)