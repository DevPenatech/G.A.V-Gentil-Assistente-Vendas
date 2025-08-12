# file: IA/communication/twilio_client.py
"""
Cliente Twilio aprimorado para comunicação WhatsApp do G.A.V.

Melhorias:
- Rate limiting inteligente
- Retry automático com backoff
- Formatação de mensagens otimizada
- Logging detalhado
- Validação de números
- Controle de tamanho de mensagem
"""

import os
import logging
import time
from typing import Dict, List
from datetime import datetime, timedelta
import re

from twilio.rest import Client
from twilio.base.exceptions import TwilioException

# Configurações
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "whatsapp:+14155238886")  # Sandbox padrão

# Limites e configurações
MAX_MESSAGE_LENGTH = 1600  # WhatsApp tem limite de ~4096, mas deixamos margem
RATE_LIMIT_WINDOW = 60  # 1 minuto
MAX_MESSAGES_PER_WINDOW = 10  # Máximo de mensagens por minuto por usuário
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2  # segundos

class TwilioClientManager:
    """Gerenciador aprimorado do cliente Twilio com controles de rate limiting e retry."""
    
    def __init__(self):
        self.client = None
        self.message_history = {}  # Histórico de mensagens por usuário
        self.last_cleanup = datetime.now()
        
        # Inicializa cliente
        self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa o cliente Twilio com validações."""
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logging.error("Credenciais Twilio não configuradas")
            return
        
        try:
            self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            
            # Testa conexão
            account = self.client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
            logging.info(f"Cliente Twilio inicializado: {account.friendly_name}")
            
        except Exception as e:
            logging.error(f"Erro ao inicializar cliente Twilio: {e}")
            self.client = None
    
    def _cleanup_old_history(self):
        """Remove histórico antigo para manter performance."""
        if datetime.now() - self.last_cleanup < timedelta(minutes=5):
            return
        
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        for user_id in list(self.message_history.keys()):
            user_messages = self.message_history[user_id]
            # Filtra mensagens das últimas horas
            recent_messages = [
                msg for msg in user_messages 
                if msg['timestamp'] > cutoff_time
            ]
            
            if recent_messages:
                self.message_history[user_id] = recent_messages
            else:
                del self.message_history[user_id]
        
        self.last_cleanup = datetime.now()
    
    def _check_rate_limit(self, user_id: str) -> bool:
        """Verifica se usuário está dentro do rate limit."""
        self._cleanup_old_history()
        
        if user_id not in self.message_history:
            return True
        
        now = datetime.now()
        window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW)
        
        recent_messages = [
            msg for msg in self.message_history[user_id]
            if msg['timestamp'] > window_start
        ]
        
        return len(recent_messages) < MAX_MESSAGES_PER_WINDOW
    
    def _add_to_history(self, user_id: str, message_sid: str, success: bool):
        """Adiciona mensagem ao histórico do usuário."""
        if user_id not in self.message_history:
            self.message_history[user_id] = []
        
        self.message_history[user_id].append({
            'timestamp': datetime.now(),
            'message_sid': message_sid,
            'success': success
        })
    
    def _validate_phone_number(self, phone_number: str) -> bool:
        """Valida formato do número de telefone."""
        if not phone_number:
            return False
        
        # Remove prefixo whatsapp: se presente
        clean_number = phone_number.replace("whatsapp:", "")
        
        # Verifica formato básico (+5511999999999)
        pattern = r'^\+\d{10,15}$'
        return bool(re.match(pattern, clean_number))
    
    def _format_message(self, message: str) -> str:
        """Formata mensagem para melhor exibição no WhatsApp."""
        if not message:
            return ""
        
        # Remove múltiplas quebras de linha
        formatted = re.sub(r'\n{3,}', '\n\n', message)
        
        # Garante que não ultrapasse o limite
        if len(formatted) > MAX_MESSAGE_LENGTH:
            # Trunca e adiciona indicador
            formatted = formatted[:MAX_MESSAGE_LENGTH - 20] + "\n\n[continua...]"
        
        return formatted.strip()
    
    def _split_long_message(self, message: str) -> List[str]:
        """Divide mensagem longa em partes menores."""
        if len(message) <= MAX_MESSAGE_LENGTH:
            return [message]
        
        parts = []
        current_part = ""
        
        # Divide por parágrafos primeiro
        paragraphs = message.split('\n\n')
        
        for i, paragraph in enumerate(paragraphs):
            # Se o parágrafo sozinho já é muito grande
            if len(paragraph) > MAX_MESSAGE_LENGTH:
                # Adiciona parte atual se existir
                if current_part:
                    parts.append(current_part.strip())
                    current_part = ""
                
                # Divide parágrafo por frases
                sentences = paragraph.split('\n')
                for sentence in sentences:
                    if len(current_part + sentence + '\n') > MAX_MESSAGE_LENGTH:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = sentence + '\n'
                    else:
                        current_part += sentence + '\n'
            else:
                # Verifica se cabe na parte atual
                if len(current_part + paragraph + '\n\n') > MAX_MESSAGE_LENGTH:
                    if current_part:
                        parts.append(current_part.strip())
                    current_part = paragraph + '\n\n'
                else:
                    current_part += paragraph + '\n\n'
        
        # Adiciona última parte
        if current_part:
            parts.append(current_part.strip())
        
        # Adiciona indicadores de continuação
        for i in range(len(parts)):
            if i > 0:
                parts[i] = f"[{i+1}/{len(parts)}] " + parts[i]
        
        return parts
    
    def send_message(self, to_number: str, message: str, max_retries: int = RETRY_ATTEMPTS) -> bool:
        """
        Envia mensagem WhatsApp com retry automático e controles avançados.
        
        Args:
            to_number: Número de destino (formato: whatsapp:+5511999999999)
            message: Mensagem a ser enviada
            max_retries: Número máximo de tentativas
            
        Returns:
            True se enviou com sucesso, False caso contrário
        """
        if not self.client:
            logging.error("Cliente Twilio não inicializado")
            return False
        
        # Valida número
        if not self._validate_phone_number(to_number):
            logging.error(f"Número de telefone inválido: {to_number}")
            return False
        
        # Verifica rate limit
        user_id = to_number.replace("whatsapp:", "")
        if not self._check_rate_limit(user_id):
            logging.warning(f"Rate limit atingido para {user_id}")
            return False
        
        # Formata mensagem
        formatted_message = self._format_message(message)
        if not formatted_message:
            logging.warning("Mensagem vazia após formatação")
            return False
        
        # Divide mensagem se necessário
        message_parts = self._split_long_message(formatted_message)
        
        # Envia cada parte
        all_success = True
        for i, part in enumerate(message_parts):
            success = self._send_single_message(to_number, part, max_retries)
            if not success:
                all_success = False
                logging.error(f"Falha ao enviar parte {i+1}/{len(message_parts)}")
            
            # Pequeno delay entre partes para evitar flood
            if i < len(message_parts) - 1:
                time.sleep(1)
        
        return all_success
    
    def _send_single_message(self, to_number: str, message: str, max_retries: int) -> bool:
        """Envia uma única mensagem com retry."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Adiciona prefixo whatsapp: se não estiver presente
                if not to_number.startswith("whatsapp:"):
                    formatted_number = f"whatsapp:{to_number}"
                else:
                    formatted_number = to_number
                
                logging.info(f"Enviando mensagem para {formatted_number}: '{message[:50]}...'")
                
                # Envia mensagem
                message_obj = self.client.messages.create(
                    body=message,
                    from_=TWILIO_PHONE_NUMBER,
                    to=formatted_number
                )
                
                # Log de sucesso
                logging.info(f"Mensagem enviada com sucesso. SID: {message_obj.sid}")
                self._add_to_history(to_number.replace("whatsapp:", ""), message_obj.sid, True)
                
                return True
                
            except TwilioException as e:
                last_error = e
                error_code = getattr(e, 'code', 'UNKNOWN')
                error_message = getattr(e, 'msg', str(e))
                
                logging.warning(f"Tentativa {attempt + 1}/{max_retries} falhou. Código: {error_code}, Erro: {error_message}")
                
                # Alguns erros não devem ter retry
                non_retryable_codes = [21211, 21614, 20404]  # Números inválidos, etc.
                if error_code in non_retryable_codes:
                    logging.error(f"Erro não recuperável: {error_code}")
                    break
                
                # Wait com backoff exponencial
                if attempt < max_retries - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    time.sleep(wait_time)
            
            except Exception as e:
                last_error = e
                logging.error(f"Erro inesperado na tentativa {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(RETRY_DELAY)
        
        # Todas as tentativas falharam
        logging.error(f"Falha ao enviar mensagem após {max_retries} tentativas. Último erro: {last_error}")
        self._add_to_history(to_number.replace("whatsapp:", ""), None, False)
        
        return False
    
    def send_proactive_message(self, to_number: str, message: str) -> bool:
        """
        Envia mensagem proativa (iniciada pelo bot).
        Aplica controles mais rigorosos para evitar spam.
        """
        # Verifica se já enviou mensagem proativa recentemente
        user_id = to_number.replace("whatsapp:", "")
        if user_id in self.message_history:
            recent_proactive = [
                msg for msg in self.message_history[user_id]
                if (datetime.now() - msg['timestamp']).total_seconds() < 3600  # Última hora
            ]
            
            if len(recent_proactive) >= 2:  # Máximo 2 mensagens proativas por hora
                logging.warning(f"Limite de mensagens proativas atingido para {user_id}")
                return False
        
        return self.send_message(to_number, message)
    
    def get_message_history(self, user_id: str) -> List[Dict]:
        """Retorna histórico de mensagens de um usuário."""
        self._cleanup_old_history()
        return self.message_history.get(user_id, [])
    
    def get_sending_statistics(self) -> Dict:
        """Retorna estatísticas de envio."""
        self._cleanup_old_history()
        
        total_users = len(self.message_history)
        total_messages = sum(len(messages) for messages in self.message_history.values())
        
        successful_messages = 0
        failed_messages = 0
        
        for user_messages in self.message_history.values():
            for msg in user_messages:
                if msg['success']:
                    successful_messages += 1
                else:
                    failed_messages += 1
        
        success_rate = (successful_messages / total_messages * 100) if total_messages > 0 else 0
        
        return {
            "total_users": total_users,
            "total_messages": total_messages,
            "successful_messages": successful_messages,
            "failed_messages": failed_messages,
            "success_rate": success_rate,
            "last_cleanup": self.last_cleanup.isoformat()
        }
    
    def is_healthy(self) -> bool:
        """Verifica se o cliente está saudável."""
        if not self.client:
            return False
        
        try:
            # Testa conexão básica
            self.client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
            return True
        except Exception as e:
            logging.error(f"Cliente Twilio não saudável: {e}")
            return False

# Instância global do cliente
twilio_manager = TwilioClientManager()

# Funções de conveniência para compatibilidade
def send_message(to_number: str, message: str) -> bool:
    """Função de conveniência para enviar mensagem."""
    return twilio_manager.send_message(to_number, message)

def send_proactive_message(to_number: str, message: str) -> bool:
    """Função de conveniência para enviar mensagem proativa."""
    return twilio_manager.send_proactive_message(to_number, message)

def get_client_health() -> Dict:
    """Retorna informações de saúde do cliente Twilio."""
    return {
        "client_initialized": twilio_manager.client is not None,
        "client_healthy": twilio_manager.is_healthy(),
        "statistics": twilio_manager.get_sending_statistics(),
        "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
    }

def format_whatsapp_number(phone_number: str) -> str:
    """Formata número para WhatsApp (adiciona prefixo se necessário)."""
    if not phone_number:
        return ""
    
    # Remove espaços e caracteres especiais
    clean_number = re.sub(r'[^\d+]', '', phone_number)
    
    # Adiciona + se não tiver
    if not clean_number.startswith('+'):
        clean_number = '+' + clean_number
    
    # Adiciona prefixo whatsapp:
    return f"whatsapp:{clean_number}"

def validate_message_content(message: str) -> Dict:
    """Valida conteúdo da mensagem antes do envio."""
    if not message:
        return {"valid": False, "error": "Mensagem vazia"}
    
    if len(message) > MAX_MESSAGE_LENGTH * 3:  # Limite para mensagens divididas
        return {"valid": False, "error": "Mensagem muito longa"}
    
    # Verifica caracteres problemáticos
    if '\x00' in message:  # Caracteres nulos
        return {"valid": False, "error": "Caracteres inválidos detectados"}
    
    return {"valid": True, "message": "Mensagem válida"}

# Classe para logs estruturados de mensagens
class MessageLogger:
    """Logger especializado para mensagens WhatsApp."""
    
    def __init__(self):
        self.logger = logging.getLogger("twilio_messages")
    
    def log_outbound(self, to_number: str, message: str, success: bool, sid: str = None):
        """Log mensagem enviada."""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"OUTBOUND [{status}] TO:{to_number} SID:{sid} MSG:{message[:100]}...")
    
    def log_inbound(self, from_number: str, message: str, processed: bool = True):
        """Log mensagem recebida."""
        status = "PROCESSED" if processed else "IGNORED"
        self.logger.info(f"INBOUND [{status}] FROM:{from_number} MSG:{message[:100]}...")
    
    def log_rate_limit(self, user_id: str):
        """Log rate limit atingido."""
        self.logger.warning(f"RATE_LIMIT user:{user_id}")
    
    def log_error(self, error: str, context: Dict = None):
        """Log erro relacionado a mensagens."""
        context_str = f" CONTEXT:{context}" if context else ""
        self.logger.error(f"MESSAGE_ERROR {error}{context_str}")

# Instância global do logger de mensagens
message_logger = MessageLogger()

# Testa configuração na importação
if __name__ == "__main__":
    health = get_client_health()
    print(f"Twilio Client Health: {health}")
    
    if health["client_healthy"]:
        print("✅ Cliente Twilio configurado e funcionando")
    else:
        print("❌ Problema na configuração do cliente Twilio")