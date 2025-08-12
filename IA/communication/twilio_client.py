# file: IA/communication/twilio_client.py
import os
import logging
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886'

# Validação das credenciais
if not all([ACCOUNT_SID, AUTH_TOKEN]):
    logging.error("Credenciais da Twilio não encontradas no .env")
    logging.error("Certifique-se de que TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN estão definidos")
    client = None
else:
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        logging.info("Cliente Twilio inicializado com sucesso")
    except Exception as e:
        logging.error(f"Erro ao inicializar cliente Twilio: {e}")
        client = None

def send_whatsapp_message(to: str, body: str):
    """
    Envia uma mensagem do WhatsApp via API da Twilio.
    
    Args:
        to: Número de telefone no formato 'whatsapp:+5511999999999'
        body: Texto da mensagem a ser enviada
    """
    if not client:
        logging.warning("Cliente Twilio não inicializado. Impossível enviar mensagem.")
        logging.warning("Verifique as credenciais TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN no arquivo .env")
        return False
    
    if not to or not body:
        logging.warning("Parâmetros inválidos para envio de mensagem")
        return False
    
    # Garante que o número está no formato correto
    if not to.startswith('whatsapp:'):
        to = f'whatsapp:{to}'
    
    try:
        logging.info(f"Enviando mensagem proativa para {to}: '{body[:100]}{'...' if len(body) > 100 else ''}'")
        print(f">>>> [RESPONDENDO]: Enviando mensagem proativa para {to}: '{body[:80]}{'...' if len(body) > 80 else ''}'")
        
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=to
        )
        
        logging.info(f"Mensagem enviada com sucesso. SID: {message.sid}")
        return True
        
    except Exception as e:
        logging.error(f"Falha ao enviar mensagem via API da Twilio: {e}")
        
        # Log específico para diferentes tipos de erro
        if "429" in str(e):
            logging.error("Limite de mensagens diário atingido")
        elif "401" in str(e):
            logging.error("Credenciais inválidas - verifique TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN")
        elif "400" in str(e):
            logging.error("Formato de mensagem inválido")
        
        return False

def test_twilio_connection():
    """
    Testa a conexão com a API da Twilio.
    
    Returns:
        bool: True se a conexão está funcionando, False caso contrário
    """
    if not client:
        logging.error("Cliente Twilio não inicializado")
        return False
    
    try:
        # Tenta buscar informações da conta para validar as credenciais
        account = client.api.accounts(ACCOUNT_SID).fetch()
        logging.info(f"Conexão Twilio OK. Status da conta: {account.status}")
        return True
    except Exception as e:
        logging.error(f"Falha no teste de conexão Twilio: {e}")
        return False

def get_account_info():
    """
    Retorna informações básicas da conta Twilio.
    
    Returns:
        dict: Informações da conta ou None em caso de erro
    """
    if not client:
        return None
    
    try:
        account = client.api.accounts(ACCOUNT_SID).fetch()
        return {
            "sid": account.sid,
            "friendly_name": account.friendly_name,
            "status": account.status,
            "type": account.type
        }
    except Exception as e:
        logging.error(f"Erro ao buscar informações da conta: {e}")
        return None