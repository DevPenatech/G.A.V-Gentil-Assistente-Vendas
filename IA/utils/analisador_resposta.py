"""
Analisador de Resposta da IA para o G.A.V.

Este módulo é responsável por extrair e validar estruturas JSON das respostas da IA,
garantindo que sejam formatadas corretamente para o sistema de ferramentas.
"""

import json
import re
from typing import Dict, List, Any, Union

def extrair_json_da_resposta_ia(conteudo: Any) -> Dict:
    """
    Extrai JSON de resposta da IA mantendo flexibilidade para texto humano ou dicionários.
    
    Args:
        conteudo (Any): Conteúdo da resposta da IA (string, dict ou outro tipo).
    
    Returns:
        Dict: Dicionário com estrutura JSON válida contendo nome_ferramenta e parametros.
        
    Example:
        >>> extrair_json_da_resposta_ia('{"nome_ferramenta": "visualizar_carrinho", "parametros": {}}')
        {"nome_ferramenta": "visualizar_carrinho", "parametros": {}}
        
        >>> extrair_json_da_resposta_ia("Olá! Como posso ajudar?")
        {"nome_ferramenta": "lidar_conversa", "parametros": {"texto_resposta": "Olá! Como posso ajudar?"}}
    """
    # Se o conteúdo já for um dicionário, retorne diretamente.
    if isinstance(conteudo, dict):
        return conteudo

    # Garante que o conteúdo seja uma string para as operações seguintes.
    if not isinstance(conteudo, str):
        conteudo = str(conteudo)

    # 1. Tenta JSON direto (ideal)
    try:
        return json.loads(conteudo.strip())
    except:
        pass
    
    # 2. Procura JSON em meio a texto (IA pode explicar + dar JSON)
    padroes_json = [
        r'\{[^{}]*"nome_ferramenta"[^{}]*\}',  # JSON simples com nome_ferramenta
        r'\{[^{}]*"tool_name"[^{}]*\}',        # JSON simples com tool_name (compatibilidade)
        r'\{(?:[^{}]|{[^{}]*})*\}',            # JSON aninhado
        r'```json\s*(\{.*?\})\s*```',          # JSON em markdown
        r'(?:resposta|json|formato):\s*(\{.*?\})', # JSON após prefixos
    ]
    
    for padrao in padroes_json:
        correspondencias = re.findall(padrao, conteudo, re.DOTALL | re.IGNORECASE)
        for match in correspondencias:
            try:
                json_extraido = json.loads(match)
                # Converte chaves em inglês para português se necessário
                return _normalizar_chaves_json(json_extraido)
            except:
                continue
    
    # 3. Se não encontrou JSON, assume que IA quer conversar
    return {
        "nome_ferramenta": "lidar_conversa",
        "parametros": {
            "texto_resposta": conteudo.strip()
        }
    }

def _normalizar_chaves_json(dados_json: Dict) -> Dict:
    """
    Normaliza chaves JSON do inglês para português para compatibilidade.
    
    Args:
        dados_json (Dict): Dados JSON com chaves possivelmente em inglês.
    
    Returns:
        Dict: JSON com chaves normalizadas para português.
    """
    normalizado = {}
    
    # Mapeia chaves principais
    if "tool_name" in dados_json:
        normalizado["nome_ferramenta"] = _traduzir_nome_ferramenta(dados_json["tool_name"])
    elif "nome_ferramenta" in dados_json:
        normalizado["nome_ferramenta"] = dados_json["nome_ferramenta"]
    
    if "parameters" in dados_json:
        normalizado["parametros"] = _normalizar_parametros(dados_json["parameters"])
    elif "parametros" in dados_json:
        normalizado["parametros"] = dados_json["parametros"]
    
    # Mantém outras chaves não mapeadas
    for chave, valor in dados_json.items():
        if chave not in ["tool_name", "nome_ferramenta", "parameters", "parametros"]:
            normalizado[chave] = valor
    
    return normalizado

def _traduzir_nome_ferramenta(nome_ferramenta: str) -> str:
    """
    Traduz nomes de ferramentas do inglês para português.
    
    Args:
        nome_ferramenta (str): Nome da ferramenta em inglês.
    
    Returns:
        str: Nome da ferramenta em português.
    """
    traducoes = {
        "smart_search_with_promotions": "busca_inteligente_com_promocoes",
        "get_top_selling_products_by_name": "obter_produtos_mais_vendidos_por_nome",
        "smart_cart_update": "atualizacao_inteligente_carrinho",
        "view_cart": "visualizar_carrinho",
        "clear_cart": "limpar_carrinho",
        "add_item_to_cart": "adicionar_item_ao_carrinho",
        "handle_chitchat": "lidar_conversa"
    }
    
    return traducoes.get(nome_ferramenta, nome_ferramenta)

def _normalizar_parametros(parametros: Dict) -> Dict:
    """
    Normaliza parâmetros do inglês para português.
    
    Args:
        parametros (Dict): Parâmetros com chaves possivelmente em inglês.
    
    Returns:
        Dict: Parâmetros com chaves normalizadas.
    """
    mapeamento_parametros = {
        "search_term": "termo_busca",
        "product_name": "nome_produto", 
        "index": "indice",
        "action": "acao",
        "quantity": "quantidade",
        "response_text": "texto_resposta",
        "user_id": "id_usuario",
        "session_id": "id_sessao"
    }
    
    parametros_normalizados = {}
    
    for chave, valor in parametros.items():
        chave_normalizada = mapeamento_parametros.get(chave, chave)
        parametros_normalizados[chave_normalizada] = valor
    
    return parametros_normalizados

def validar_estrutura_json(json_analisado: Dict, ferramentas_disponiveis: List[str]) -> bool:
    """
    Valida se o JSON tem estrutura mínima necessária.
    
    Args:
        json_analisado (Dict): JSON a ser validado.
        ferramentas_disponiveis (List[str]): Lista de ferramentas válidas.
    
    Returns:
        bool: True se a estrutura for válida, False caso contrário.
        
    Example:
        >>> validar_estrutura_json({"nome_ferramenta": "visualizar_carrinho", "parametros": {}}, ["visualizar_carrinho"])
        True
        >>> validar_estrutura_json({"nome_ferramenta": "ferramenta_invalida"}, ["visualizar_carrinho"])
        False
    """
    
    if not isinstance(json_analisado, dict):
        return False
        
    if "nome_ferramenta" not in json_analisado:
        return False
        
    if "parametros" not in json_analisado:
        return False
        
    nome_ferramenta = json_analisado["nome_ferramenta"]
    if nome_ferramenta not in ferramentas_disponiveis:
        return False
        
    # Validações específicas por ferramenta
    parametros = json_analisado["parametros"]
    
    if nome_ferramenta == "lidar_conversa" and "texto_resposta" not in parametros:
        return False
        
    if nome_ferramenta == "atualizacao_inteligente_carrinho":
        obrigatorios = ["nome_produto", "acao", "quantidade"]
        if not all(chave in parametros for chave in obrigatorios):
            return False
    
    if nome_ferramenta == "busca_inteligente_com_promocoes":
        if "termo_busca" not in parametros:
            return False
    
    if nome_ferramenta == "obter_produtos_mais_vendidos_por_nome":
        if "nome_produto" not in parametros:
            return False
    
    if nome_ferramenta == "adicionar_item_ao_carrinho":
        if "indice" not in parametros:
            return False
            
    return True

def sanitizar_resposta_ia(resposta: str) -> str:
    """
    Remove caracteres desnecessários e sanitiza a resposta da IA.
    
    Args:
        resposta (str): Resposta bruta da IA.
    
    Returns:
        str: Resposta sanitizada.
    """
    if not isinstance(resposta, str):
        return str(resposta)
    
    # Remove marcações markdown desnecessárias
    resposta = re.sub(r'```json\s*', '', resposta)
    resposta = re.sub(r'\s*```', '', resposta)
    
    # Remove espaços extras
    resposta = resposta.strip()
    
    # Remove quebras de linha desnecessárias dentro de JSON
    if resposta.startswith('{') and resposta.endswith('}'):
        resposta = re.sub(r'\n\s*', ' ', resposta)
    
    return resposta

def extrair_intencao_fallback(texto: str) -> Dict:
    """
    Cria uma intenção de fallback baseada em análise simples do texto.
    
    Args:
        texto (str): Texto para análise.
    
    Returns:
        Dict: Estrutura JSON com ferramenta de fallback.
    """
    texto_minusculo = texto.lower().strip()
    
    # Detecta números simples (seleção de item)
    if re.match(r'^\d+$', texto_minusculo):
        return {
            "nome_ferramenta": "adicionar_item_ao_carrinho",
            "parametros": {"indice": int(texto_minusculo)}
        }
    
    # Detecta comandos de carrinho
    if any(palavra in texto_minusculo for palavra in ['carrinho', 'cart']):
        return {
            "nome_ferramenta": "visualizar_carrinho",
            "parametros": {}
        }
    
    # Detecta comandos de limpeza
    if any(palavra in texto_minusculo for palavra in ['limpar', 'esvaziar', 'clear']):
        return {
            "nome_ferramenta": "limpar_carrinho",
            "parametros": {}
        }
    
    # Detecta saudações
    if any(palavra in texto_minusculo for palavra in ['oi', 'olá', 'hello', 'boa']):
        return {
            "nome_ferramenta": "lidar_conversa",
            "parametros": {"texto_resposta": "Olá! Como posso te ajudar hoje?"}
        }
    
    # Default: busca de produto
    return {
        "nome_ferramenta": "obter_produtos_mais_vendidos_por_nome",
        "parametros": {"nome_produto": texto}
    }

def validar_parametros_ferramenta(nome_ferramenta: str, parametros: Dict) -> bool:
    """
    Valida os parâmetros específicos de cada ferramenta.
    
    Args:
        nome_ferramenta (str): Nome da ferramenta.
        parametros (Dict): Parâmetros a serem validados.
    
    Returns:
        bool: True se os parâmetros forem válidos.
    """
    validacoes = {
        "busca_inteligente_com_promocoes": lambda p: "termo_busca" in p and isinstance(p["termo_busca"], str),
        "obter_produtos_mais_vendidos_por_nome": lambda p: "nome_produto" in p and isinstance(p["nome_produto"], str),
        "atualizacao_inteligente_carrinho": lambda p: all(k in p for k in ["nome_produto", "acao", "quantidade"]),
        "visualizar_carrinho": lambda p: True,  # Não requer parâmetros específicos
        "limpar_carrinho": lambda p: True,  # Não requer parâmetros específicos
        "adicionar_item_ao_carrinho": lambda p: "indice" in p and isinstance(p["indice"], (int, str)),
        "lidar_conversa": lambda p: "texto_resposta" in p and isinstance(p["texto_resposta"], str)
    }
    
    validador = validacoes.get(nome_ferramenta)
    if not validador:
        return False
    
    try:
        return validador(parametros)
    except Exception:
        return False

def obter_estatisticas_parsing() -> Dict:
    """
    Retorna estatísticas sobre o parsing de respostas (para debugging).
    
    Returns:
        Dict: Estatísticas de parsing.
    """
    return {
        "ferramentas_suportadas": [
            "busca_inteligente_com_promocoes",
            "obter_produtos_mais_vendidos_por_nome", 
            "atualizacao_inteligente_carrinho",
            "visualizar_carrinho",
            "limpar_carrinho",
            "adicionar_item_ao_carrinho",
            "lidar_conversa"
        ],
        "padroes_json_suportados": [
            "JSON direto",
            "JSON em markdown",
            "JSON com prefixos",
            "Fallback para texto livre"
        ],
        "mapeamento_chaves": {
            "tool_name": "nome_ferramenta",
            "parameters": "parametros",
            "search_term": "termo_busca",
            "product_name": "nome_produto",
            "response_text": "texto_resposta"
        },
        "traducao_ferramentas": {
            "smart_search_with_promotions": "busca_inteligente_com_promocoes",
            "get_top_selling_products_by_name": "obter_produtos_mais_vendidos_por_nome",
            "smart_cart_update": "atualizacao_inteligente_carrinho",
            "view_cart": "visualizar_carrinho",
            "clear_cart": "limpar_carrinho",
            "add_item_to_cart": "adicionar_item_ao_carrinho",
            "handle_chitchat": "lidar_conversa"
        }
    }