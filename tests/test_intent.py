import os
import sys
import pytest

# Adiciona o diretório IA ao sys.path para importar app
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'IA'))
from app import _get_intent, llm_interface


def test_remove_item_triggers_update_cart_item(monkeypatch):
    session = {}
    state = {"shopping_cart": [{"descricao": "Arroz", "qt": 1}]}

    def fake_get_intent(user_message, session_data, customer_context=None, cart_items_count=0):
        assert user_message == "remover item"
        return {"tool_name": "update_cart_item", "parameters": {"index": 1}}

    monkeypatch.setattr(llm_interface, "get_intent", fake_get_intent)

    intent, response_text = _get_intent(session, state, "remover item")

    assert intent == {"tool_name": "update_cart_item", "parameters": {"index": 1}}
    assert response_text == ""
