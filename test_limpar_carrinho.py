#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes para detecção de comandos de limpar carrinho."""

import os
import sys

# Permite importar módulos da pasta IA
sys.path.append(os.path.join(os.path.dirname(__file__), "IA"))

from core.gerenciador_sessao import detectar_comandos_limpar_carrinho
from utils.extrator_quantidade import detectar_modificadores_quantidade


def test_limpa_isso_nao_limpa_carrinho():
    """Expressões sem referência ao carrinho não devem limpar."""
    assert not detectar_comandos_limpar_carrinho("limpa isso")


def test_modificadores_limpa_isso_nao_limpa():
    """Modificador não deve interpretar "limpa isso" como limpar carrinho."""
    mods = detectar_modificadores_quantidade("limpa isso")
    assert mods["acao"] != "clear"


def test_limpa_carrinho_detectado():
    """Comando válido deve ser detectado."""
    assert detectar_comandos_limpar_carrinho("limpa o carrinho")

