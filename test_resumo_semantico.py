#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes para o resumo semântico da conversa."""

import os
import sys

# Permite importar módulos da pasta IA
sys.path.append(os.path.join(os.path.dirname(__file__), "IA"))

from core.gerenciador_sessao import (
    _resumir_mensagens_antigas,
    obter_contexto_conversa_resumido,
)


def test_resumo_semantico_preserva_metadados():
    msg_usuario = (
        "Eu quero comprar arroz. Também gostaria de feijão. Pode ajudar?"
    )
    msg_bot = "Temos arroz integral e feijão carioca disponíveis."

    dados_sessao = {
        "historico_conversa": [
            {
                "role": "user",
                "message": msg_usuario,
                "action_type": "pedido",
            },
            {
                "role": "assistant",
                "message": msg_bot,
                "action_type": "resposta",
            },
        ],
        "resumo_conversa": [],
    }

    _resumir_mensagens_antigas(dados_sessao, max_historico=1, manter_recentes=0)

    resumo = dados_sessao["resumo_conversa"]
    assert isinstance(resumo, list)
    assert resumo[0]["role"] == "user"
    assert resumo[0]["action_type"] == "pedido"
    assert "arroz" in resumo[0]["summary"].lower()
    assert len(resumo[0]["summary"]) < len(msg_usuario)

    contexto = obter_contexto_conversa_resumido(dados_sessao, max_mensagens=5)
    assert "Cliente" in contexto["resumo"]
    assert "arroz" in contexto["resumo"].lower()
    assert "G.A.V." in contexto["resumo"]
