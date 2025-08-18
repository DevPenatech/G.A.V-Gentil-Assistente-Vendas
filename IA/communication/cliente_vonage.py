# === Encontradas na parte de Messages Sandbox do site ====
# API Key - a3a25a7a
# API Secret -  RIoRzUgBljOla5q2
# Signature Secret / JWT token - UjL1GlSAOQYyfU4UOiF73PMZ3xZz4Yp3SaXfV6qPdK3tv1GNWF


import requests

ID_REMETENTE_WHATSAPP = '14157386102'
NUMERO_DESTINO_MENSAGENS = '5511940726493'
CHAVE_API_VONAGE = 'a3a25a7a'
SEGREDO_API_VONAGE = 'RIoRzUgBljOla5q2'
ENDPOINT = "https://messages-sandbox.nexmo.com/v1/messages"
ID_APLICACAO_VONAGE = '2f4fde7f-5a20-41dd-b944-e9914f8e6520'

def enviar_whatsapp(mensagem: str) -> dict:
    """Envia uma mensagem de WhatsApp usando a API do Vonage.

    Args:
        mensagem: A mensagem a ser enviada.

    Returns:
        A resposta da API do Vonage.
    """
    carga_util = {
        "from": ID_REMETENTE_WHATSAPP,
        "to": NUMERO_DESTINO_MENSAGENS,
        "message_type": "text",
        "text": mensagem,
        "channel": "whatsapp"
    }
    cabecalhos = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resposta = requests.post(
        ENDPOINT,
        auth=(CHAVE_API_VONAGE, SEGREDO_API_VONAGE),  # Autenticação Básica
        json=carga_util,
        headers=cabecalhos,
        timeout=10,
    )
    resposta.raise_for_status()
    return resposta.json()