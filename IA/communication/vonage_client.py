# === Encontradas na parte de Messages Sandbox do site ====
# API Key - a3a25a7a
# API Secret -  RIoRzUgBljOla5q2
# Signature Secret / JWT token - UjL1GlSAOQYyfU4UOiF73PMZ3xZz4Yp3SaXfV6qPdK3tv1GNWF


import requests

WHATSAPP_SENDER_ID = '14157386102'
MESSAGES_TO_NUMBER = '5511940726493'
VONAGE_API_KEY = 'a3a25a7a'
VONAGE_API_SECRET = 'RIoRzUgBljOla5q2'
ENDPOINT = "https://messages-sandbox.nexmo.com/v1/messages"
VONAGE_APPLICATION_ID = '2f4fde7f-5a20-41dd-b944-e9914f8e6520'

def enviar_whatsapp(mensagem: str) -> dict:
    payload = {
        "from": WHATSAPP_SENDER_ID,
        "to": MESSAGES_TO_NUMBER,
        "message_type": "text",
        "text": mensagem,
        "channel": "whatsapp"
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.post(
        ENDPOINT,
        auth=(VONAGE_API_KEY, VONAGE_API_SECRET),  # Basic Auth
        json=payload,
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
