# file: IA/core/session_manager.py
"""
Session Manager - Gerenciamento de Sessões do G.A.V.
"""

import os
import json
import logging
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
import redis
import re

# Configurações
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
SESSION_TTL = int(os.getenv("SESSION_TTL", 86400))  # 24 horas em segundos

# Cliente Redis (opcional)
redis_client = None
if REDIS_ENABLED:
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=False  # Usamos pickle para serialização
        )
        redis_client.ping()
        logging.info(f"Redis conectado: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logging.warning(f"Redis não disponível: {e}. Usando armazenamento em arquivo.")
        redis_client = None

# ================================================================================
# FUNÇÕES DE SESSÃO
# ================================================================================

def _get_session_file_path(session_id: str) -> str:
    """Retorna o caminho do arquivo de sessão."""
    sessions_dir = "data"
    if not os.path.exists(sessions_dir):
        os.makedirs(sessions_dir)
    
    # Sanitiza o ID da sessão para uso como nome de arquivo
    safe_id = session_id.replace(":", "_").replace("/", "_")
    return os.path.join(sessions_dir, f"session_{safe_id}.json")

def load_session(session_id: str) -> Dict:
    """Carrega dados da sessão do armazenamento."""
    default_session = {
        "customer_context": None,
        "shopping_cart": [],
        "conversation_history": [],
        "last_search_type": None,
        "last_search_params": {},
        "current_offset": 0,
        "last_shown_products": [],
        "last_bot_action": None,
        "pending_action": None,
        "pending_product_selection": None,
        "pending_quantity": None,
        "last_kb_search_term": None,
        "last_search_results": [],
        "last_search_analysis": {},
        "last_search_suggestions": [],
        "created_at": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat()
    }
    
    # Tenta carregar do Redis primeiro
    if redis_client:
        try:
            data = redis_client.get(f"session:{session_id}")
            if data:
                session = pickle.loads(data)
                logging.debug(f"[SESSION] Sessão carregada do Redis: {session_id}")
                return session
        except Exception as e:
            logging.warning(f"Erro ao carregar sessão do Redis: {e}")
    
    # Fallback para arquivo
    file_path = _get_session_file_path(session_id)
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                session = json.load(f)
                logging.debug(f"[SESSION] Sessão carregada do arquivo: {file_path}")
                
                # Garante que todos os campos necessários existam
                for key, value in default_session.items():
                    if key not in session:
                        session[key] = value
                
                return session
        except Exception as e:
            logging.error(f"Erro ao carregar sessão do arquivo: {e}")
    
    logging.info(f"[SESSION] Nova sessão criada: {session_id}")
    return default_session

def save_session(session_id: str, session_data: Dict):
    """Salva dados da sessão no armazenamento."""
    # Atualiza timestamp
    session_data["last_activity"] = datetime.now().isoformat()
    
    # Salva no Redis se disponível
    if redis_client:
        try:
            redis_client.setex(
                f"session:{session_id}",
                SESSION_TTL,
                pickle.dumps(session_data)
            )
            logging.debug(f"[SESSION] Sessão salva no Redis: {session_id}")
            return
        except Exception as e:
            logging.warning(f"Erro ao salvar sessão no Redis: {e}")
    
    # Fallback para arquivo
    file_path = _get_session_file_path(session_id)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        logging.debug(f"[SESSION] Sessão salva no arquivo: {file_path}")
    except Exception as e:
        logging.error(f"Erro ao salvar sessão no arquivo: {e}")

def clear_session(session_id: str):
    """Limpa dados da sessão."""
    # Remove do Redis se disponível
    if redis_client:
        try:
            redis_client.delete(f"session:{session_id}")
            logging.debug(f"[SESSION] Sessão removida do Redis: {session_id}")
        except Exception as e:
            logging.warning(f"Erro ao remover sessão do Redis: {e}")
    
    # Remove arquivo
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

# ================================================================================
# FORMATAÇÃO DE EXIBIÇÃO PARA WHATSAPP
# ================================================================================

def format_product_list_for_display(products: List[Dict], title: str, has_more: bool, offset: int = 0) -> str:
    """Formata lista de produtos para exibição no WhatsApp."""
    if not products:
        return f"❌ {title}\nNão achei esse item. Posso sugerir similares?"
    
    # Conta produtos reais disponíveis
    actual_count = len(products)
    limited_products = products[:min(actual_count, 3)]
    display_count = len(limited_products)

    response = f"📦 *{title}:*\n\n"

    for i, p in enumerate(limited_products, start=offset + 1):
        price = p.get('pvenda') or p.get('preco_varejo', 0.0)
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        # Compatibilidade com produtos do banco (descricao) e da KB (canonical_name)
        product_name = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')
        
        response += f"*{i}.* {product_name}\n"
        response += f"    💰 {price_str}\n\n"
    
    # Ajusta mensagem conforme quantidade exibida e offset
    if display_count == 1:
        response += f"Digite *{offset + 1}* para selecionar este produto."
    elif display_count == 2:
        response += (
            f"Qual você quer? Digite *{offset + 1}* ou *{offset + 2}*."
        )
    else:
        response += (
            f"Qual você quer? Digite *{offset + 1}*, *{offset + 2}* ou *{offset + 3}*."
        )
    
    if has_more:
        response += "\n📝 Digite *mais* para ver outros produtos!"
    
    return response

def format_cart_for_display(cart: List[Dict]) -> str:
    """Formata o carrinho para exibição no WhatsApp."""
    if not cart:
        return "🛒 Seu carrinho está vazio."
    
    response = "🛒 *SEU CARRINHO:*\n"
    response += "━━━━━━━━━━━━━━━━━━━━\n"
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
        
        response += f"*{i}.* {product_name}\n"
        response += f"   {qty_display}× {price_str} = *{subtotal_str}*\n\n"
    
    response += "━━━━━━━━━━━━━━━━━━━━\n"
    total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    response += f"💵 *Total: {total_str}*"
    
    return response

# ================================================================================
# GESTÃO DO HISTÓRICO DE CONVERSA
# ================================================================================

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

# ================================================================================
# DETECÇÃO E ANÁLISE DE INTENÇÕES
# ================================================================================

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
    greetings = ['oi', 'olá', 'ola', 'boa', 'bom dia', 'boa tarde', 'boa noite', 'e aí', 'e ai']
    if any(greeting in message_lower for greeting in greetings):
        return "GREETING"
    
    # Quantidades
    if re.search(r'\d+', message) and len(session_data.get("last_shown_products", [])) > 0:
        return "QUANTITY_SPECIFICATION"
    
    return "GENERAL"

# ================================================================================
# ESTATÍSTICAS E MÉTRICAS
# ================================================================================

def get_session_stats(session_data: Dict) -> Dict:
    """Retorna estatísticas da sessão atual."""
    stats = {
        "cart_items": len(session_data.get("shopping_cart", [])),
        "conversation_length": len(session_data.get("conversation_history", [])),
        "customer_identified": bool(session_data.get("customer_context")),
        "last_action": session_data.get("last_bot_action", "NONE"),
        "has_pending_selection": bool(session_data.get("last_shown_products")),
        "has_pending_quantity": bool(session_data.get("pending_product_selection"))
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

# ================================================================================
# AÇÕES RÁPIDAS E MENUS
# ================================================================================

def format_quick_actions(has_cart: bool = False, has_products: bool = False) -> str:
    """Gera menu de ações rápidas baseado no contexto atual para WhatsApp."""
    actions = []
    
    if has_products:
        return "Digite o número (1, 2 ou 3) do produto desejado"
    
    if has_cart:
        actions = [
            "*1* - 🔍 Buscar produtos",
            "*2* - 🛒 Ver carrinho",
            "*3* - ✅ Finalizar pedido"
        ]
    else:
        actions = [
            "🔍 Digite o nome do produto",
            "📦 Digite *produtos* para ver os mais vendidos",
            "❓ Digite *ajuda* para mais opções"
        ]
    
    return "\n".join(actions)

# ================================================================================
# ATUALIZAÇÃO DE CONTEXTO
# ================================================================================

def update_session_context(session_data: Dict, new_context: Dict):
    """Atualiza dados da sessão garantindo recálculo de métricas."""
    # Atualiza apenas os campos fornecidos, preservando os demais
    session_data.update(new_context)

    # Atualiza timestamp da última atividade
    session_data["last_activity"] = datetime.now().isoformat()

    # Recalcula estatísticas da sessão
    session_data["session_stats"] = get_session_stats(session_data)
