# file: twilio_client.py
import os
import logging
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886'

if not all([ACCOUNT_SID, AUTH_TOKEN]):
    logging.error("Credenciais da Twilio não encontradas no .env")
    client = None
else:
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_whatsapp_message(to: str, body: str):
    if not client:
        logging.warning("Cliente Twilio não inicializado. Impossível enviar mensagem.")
        return
    try:
        logging.info(f"Enviando mensagem proativa para {to}: '{body}'")
        print(f">>>> [RESPONDENDO]: Enviando mensagem proativa para {to}: '{body}'")
        client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=to
        )
    except Exception as e:
        logging.error(f"Falha ao enviar mensagem via API da Twilio: {e}")