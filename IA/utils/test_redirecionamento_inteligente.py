#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes para redirecionamento quando usuário envia '?' em seleção."""

import unittest
import sys
from pathlib import Path

# Adiciona diretório IA ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.classificador_intencao import detectar_intencao_com_sistemas_criticos
from utils.redirecionamento_inteligente import verificar_entrada_vazia_selecao


class TestRedirecionamentoAjuda(unittest.TestCase):
    """Verifica se '?' aciona mensagem de ajuda durante seleção."""

    def test_question_mark_triggers_help(self):
        dados_sessao = {"messages": [], "last_bot_action": "AWAITING_PRODUCT_SELECTION"}
        resultado = detectar_intencao_com_sistemas_criticos(
            entrada_usuario="?",
            contexto_conversa="Produtos:\n1. Item A\n2. Item B\nEscolha um número:",
            dados_sessao=dados_sessao,
        )
        self.assertEqual(
            resultado["parametros"]["response_text"],
            "Digite o número do item ou 'ajuda' para ver opções",
        )
        self.assertTrue(resultado["necessita_redirecionamento"])
        self.assertEqual(resultado["tipo_resposta"], "redirecionamento_guidance")

    def test_empty_input_triggers_help(self):
        mensagem = verificar_entrada_vazia_selecao("", "AWAITING_PRODUCT_SELECTION")
        self.assertEqual(mensagem, "Digite o número do item ou 'ajuda' para ver opções")

    def test_no_help_outside_selection(self):
        mensagem = verificar_entrada_vazia_selecao("?", "AWAITING_CHECKOUT_CONFIRMATION")
        self.assertIsNone(mensagem)


if __name__ == "__main__":
    unittest.main()
