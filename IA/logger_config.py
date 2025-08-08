# file: logger_config.py
import logging
import sys

def setup_logger():
    """Configura o logger para salvar APENAS em arquivo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            # A única handler agora é o FileHandler. O StreamHandler foi removido.
            logging.FileHandler("chat_log.log", mode='a', encoding='utf-8')
        ]
    )