"""Módulo de cache semântico com métricas de acerto e miss."""

import logging
from typing import Dict, Optional

# Cache semântico interno
_cache_semantico: Dict[str, Dict] = {}

# Palavras-chave para cache semântico
_palavras_chave_cache = {
    "carrinho": ["carrinho", "meu carrinho", "pedido", "itens", "cesta"],
    "cerveja": ["cerveja", "cerva", "skol", "heineken", "brahma", "antartica"],
    "finalizar_pedido": ["finalizar", "comprar", "fechar pedido", "concluir"],
    "limpar": ["limpar", "esvaziar", "zerar", "apagar", "cancelar"],
    "mais": ["mais", "continuar", "próximos", "outros", "mostrar mais"],
    "numeros": [str(i) for i in range(1, 21)]  # Números de 1 a 20
}

# Métricas simples para análise posterior
metricas_cache = {"hits": 0, "misses": 0}


def buscar_semelhante(mensagem: str, contexto: str = "") -> Optional[Dict]:
    """Busca no cache semântico por mensagens similares.

    Args:
        mensagem: Texto enviado pelo usuário.
        contexto: Contexto adicional da conversa (não utilizado no momento).

    Returns:
        O resultado previamente armazenado, caso uma correspondência seja
        encontrada; caso contrário, ``None``.
    """
    mensagem_lower = mensagem.lower().strip()

    # Se é só número, usa cache direto
    if mensagem_lower.isdigit():
        cache_key = f"numero_{mensagem_lower}"
        if cache_key in _cache_semantico:
            metricas_cache["hits"] += 1
            logging.debug(f"[CACHE_SEMANTICO] Hit para número: {mensagem_lower}")
            return _cache_semantico[cache_key]

    # Busca por palavras-chave semânticas
    for categoria, palavras in _palavras_chave_cache.items():
        for palavra in palavras:
            if palavra in mensagem_lower:
                cache_key = f"categoria_{categoria}"
                if cache_key in _cache_semantico:
                    metricas_cache["hits"] += 1
                    logging.debug(f"[CACHE_SEMANTICO] Hit para categoria: {categoria}")
                    return _cache_semantico[cache_key]

    metricas_cache["misses"] += 1
    logging.debug(f"[CACHE_SEMANTICO] Miss para mensagem: {mensagem_lower}")
    return None


def salvar_resultado(mensagem: str, resultado: Dict) -> None:
    """Salva resultado no cache semântico baseado em padrões identificados."""
    mensagem_lower = mensagem.lower().strip()

    # Cache para números
    if mensagem_lower.isdigit():
        cache_key = f"numero_{mensagem_lower}"
        _cache_semantico[cache_key] = resultado.copy()

    # Cache por categoria baseado na ferramenta resultado
    ferramenta = resultado.get("nome_ferramenta", "")
    if ferramenta == "visualizar_carrinho":
        _cache_semantico["categoria_carrinho"] = resultado.copy()
    elif ferramenta == "busca_inteligente_com_promocoes":
        if any(palavra in mensagem_lower for palavra in ["cerveja", "skol", "heineken"]):
            _cache_semantico["categoria_cerveja"] = resultado.copy()
    elif ferramenta == "finalizar_pedido":
        _cache_semantico["categoria_finalizar_pedido"] = resultado.copy()
    elif ferramenta == "limpar_carrinho":
        _cache_semantico["categoria_limpar"] = resultado.copy()
    elif ferramenta == "show_more_products":
        _cache_semantico["categoria_mais"] = resultado.copy()
