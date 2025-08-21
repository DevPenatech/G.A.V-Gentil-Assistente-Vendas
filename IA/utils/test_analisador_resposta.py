#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes para o analisador de respostas da IA."""

import sys
from pathlib import Path
import unittest

# Adiciona diretório IA ao path para permitir importações
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.analisador_resposta import extrair_json_da_resposta_ia


class TestAnalisadorResposta(unittest.TestCase):
    """Testes para o analisador de resposta."""

    def test_detecta_produtos_populares_com_palavra_isolada(self):
        """Deve mapear 'produtos' para produtos populares."""
        resultado = extrair_json_da_resposta_ia("produtos")
        self.assertEqual(resultado["nome_ferramenta"], "get_top_selling_products")
        self.assertEqual(resultado["parametros"], {})


if __name__ == "__main__":
    unittest.main()
