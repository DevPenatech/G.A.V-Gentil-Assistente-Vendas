#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes para o contexto resumido da conversa."""

import os
import sys

# Permite importar módulos da pasta IA
sys.path.append(os.path.join(os.path.dirname(__file__), "IA"))

from core.gerenciador_sessao import obter_contexto_conversa_resumido


def test_obter_contexto_conversa_resumido_limita_tamanhos():
    dados_sessao = {
        "resumo_conversa": "a" * 1500,
        "historico_conversa": [
            {"role": "user" if i % 2 == 0 else "assistant", "message": "m" * 250}
            for i in range(25)
        ],
    }

    contexto = obter_contexto_conversa_resumido(dados_sessao, max_mensagens=10)

    assert len(contexto["resumo"]) == 1000
    assert len(contexto["mensagens_recentes"]) == 10
    for msg in contexto["mensagens_recentes"]:
        assert len(msg) <= 220

