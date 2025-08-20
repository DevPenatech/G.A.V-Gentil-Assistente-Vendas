# file: IA/communication/twilio_client.py
from twilio.rest import Client
import os
from dotenv import load_dotenv
import sys
from pathlib import Path

# Adiciona utils ao path
utils_path = Path(__file__).resolve().parent.parent / "utils"
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

from gav_logger import obter_logger, log_whatsapp_error, log_info, log_error, log_debug, log_performance
import time

load_dotenv()

# Configurações do Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# Inicializa cliente Twilio
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    log_info("Cliente Twilio inicializado com sucesso", categoria="TWILIO_INIT")
else:
    log_error("Credenciais do Twilio não encontradas", categoria="TWILIO_INIT")

@log_performance
def send_whatsapp_message(to: str, body: str, user_id: str = None) -> bool:
    """
    Envia mensagem WhatsApp via Twilio com logging completo e sem truncamento.
    
    Args:
        to: Número de destino (formato: whatsapp:+5511999999999)
        body: Texto completo da mensagem
        user_id: ID do usuário (opcional)
    
    Returns:
        bool: True se enviou com sucesso, False caso contrário
    """
    if not twilio_client:
        log_error("Cliente Twilio não inicializado", user_id=user_id, categoria="TWILIO_SEND")
        return False
    
    if not to or not body:
        log_error("Parâmetros inválidos para envio", user_id=user_id, 
                 to=to, body_length=len(body) if body else 0, categoria="TWILIO_SEND")
        return False
    
    # Garante formato correto do número
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    
    try:
        inicio = time.time()
        
        log_debug(f"Enviando mensagem completa para {to}", user_id=user_id, 
                 mensagem_completa=body, mensagem_length=len(body), categoria="TWILIO_SEND")
        
        message = twilio_client.messages.create(
            body=body,
            from_=TWILIO_WHATSAPP_FROM,
            to=to
        )
        
        tempo_envio = time.time() - inicio
        
        log_info(f"Mensagem enviada com sucesso", 
                user_id=user_id,
                message_sid=message.sid,
                tempo_envio=tempo_envio,
                destinatario=to,
                tamanho_mensagem=len(body),
                mensagem_completa=body,
                categoria="TWILIO_SUCCESS")
        
        return True
        
    except Exception as e:
        tempo_erro = time.time() - inicio
        error_code = getattr(e, 'code', None)
        error_status = getattr(e, 'status', None)
        
        log_whatsapp_error(
            f"Falha ao enviar mensagem completa: {str(e)}",
            error_code=error_code,
            user_id=user_id,
            destinatario=to,
            tempo_erro=tempo_erro,
            error_status=error_status,
            mensagem_que_falhou=body,
            categoria="TWILIO_ERROR"
        )
        
        return False

def get_client_status() -> dict:
    """Retorna status completo do cliente Twilio."""
    status = {
        "client_initialized": twilio_client is not None,
        "account_sid_configured": bool(TWILIO_ACCOUNT_SID),
        "auth_token_configured": bool(TWILIO_AUTH_TOKEN),
        "whatsapp_from": TWILIO_WHATSAPP_FROM
    }
    
    log_info("Status do cliente Twilio verificado", **status, categoria="TWILIO_STATUS")
    return status

def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Valida formato completo de número de telefone.
    
    Returns:
        tuple: (is_valid, formatted_number)
    """
    if not phone:
        log_debug("Número de telefone vazio fornecido", categoria="PHONE_VALIDATION")
        return False, ""
    
    # Remove espaços e caracteres especiais
    clean_phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    log_debug(f"Validando número de telefone completo: {phone} -> {clean_phone}", 
             numero_original=phone, numero_limpo=clean_phone, categoria="PHONE_VALIDATION")
    
    # Adiciona código do país se não tiver
    if not clean_phone.startswith("+"):
        if clean_phone.startswith("55"):
            clean_phone = f"+{clean_phone}"
        else:
            clean_phone = f"+55{clean_phone}"
    
    # Verifica formato básico (Brasil: +5511999999999)
    is_valid = len(clean_phone) >= 13 and clean_phone.startswith("+55")
    formatted = f"whatsapp:{clean_phone}" if is_valid else clean_phone
    
    log_info(f"Número de telefone validado", 
            numero_original=phone,
            numero_formatado=formatted,
            is_valid=is_valid,
            categoria="PHONE_VALIDATION")
    
    return is_valid, formatted