#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classificador de Intenções Inteligente
Usa IA para detectar automaticamente a intenção do usuário e escolher a ferramenta certa
"""

import ollama
import json
import os
import re
import time
from typing import Dict, Optional, List

from .gav_logger import log_decisao_ia


# Importações dos novos sistemas críticos
from .controlador_fluxo_conversa import validar_fluxo_conversa, detectar_confusao_conversa
from .prevencao_invencao_dados import validar_resposta_ia, verificar_seguranca_resposta
from .redirecionamento_inteligente import (
    detectar_usuario_confuso,
    verificar_entrada_vazia_selecao,
)

from .gav_logger import log_decisao_ia


# Configurações
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
HOST_OLLAMA = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")

# Limiar padrão de confiança para sinalização
CONFIDENCE_THRESHOLD = 0.7

# Cache inteligente de intenções para performance IA-FIRST
_cache_intencao = {}
_cache_semantico = {}  # Cache por similaridade semântica

# Palavras-chave para cache semântico
_palavras_chave_cache = {
    "carrinho": ["carrinho", "meu carrinho", "pedido", "itens", "cesta"],
    "cerveja": ["cerveja", "cerva", "skol", "heineken", "brahma", "antartica"],
    "finalizar_pedido": ["finalizar", "comprar", "fechar pedido", "concluir"],
    "limpar": ["limpar", "esvaziar", "zerar", "apagar", "cancelar"],
    "mais": ["mais", "continuar", "próximos", "outros", "mostrar mais"],
    "numeros": [str(i) for i in range(1, 21)]  # Números de 1 a 20
}

def _buscar_cache_semantico(mensagem: str, contexto: str = "") -> Optional[Dict]:
    """
    Busca no cache semântico por mensagens similares (IA-FIRST).
    Retorna intenção cacheada se encontrar similaridade.
    """
    mensagem_lower = mensagem.lower().strip()
    
    # Se é só número, usa cache direto
    if mensagem_lower.isdigit():
        cache_key = f"numero_{mensagem_lower}"
        if cache_key in _cache_semantico:
            logger.debug(f"[CACHE_SEMANTICO] Hit para número: {mensagem_lower}")
            return _cache_semantico[cache_key]
    
    # Busca por palavras-chave semânticas
    for categoria, palavras in _palavras_chave_cache.items():
        for palavra in palavras:
            if palavra in mensagem_lower:
                cache_key = f"categoria_{categoria}"
                if cache_key in _cache_semantico:
                    logger.debug(f"[CACHE_SEMANTICO] Hit para categoria: {categoria}")
                    return _cache_semantico[cache_key]
    
    return None

def _salvar_cache_semantico(mensagem: str, resultado: Dict):
    """
    Salva resultado no cache semântico baseado em padrões identificados.
    """
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


def _registrar_decisao(intencao: Dict):
    """Registra decisão da IA usando logger dedicado."""
    log_decisao_ia(
        intencao.get("nome_ferramenta", "desconhecida"),
        float(intencao.get("confidence_score", 0)),
        intencao.get("decision_strategy")
    )

def _tentar_recuperacao_inteligente_ia(mensagem_original: str, contexto: str, erro_original: str) -> Optional[Dict]:
    """
    Sistema de múltiplas tentativas inteligentes IA-FIRST.
    Tenta diferentes estratégias quando a IA principal falha.
    """
    logger.info(f"[RECUPERACAO_IA] Iniciando recuperação para: '{mensagem_original}' (erro: {erro_original})")
    
    estrategias = [
        ("mensagem_simplificada", lambda: _simplificar_mensagem_ia(mensagem_original)),
        ("contexto_reduzido", lambda: _reduzir_contexto_ia(mensagem_original, contexto)),
        ("patterns_inteligentes", lambda: _tentar_patterns_ia(mensagem_original, contexto)),
        ("fallback_contextual", lambda: _criar_fallback_contextual_ia(mensagem_original, contexto))
    ]
    
    for nome_estrategia, estrategia_func in estrategias:
        try:
            logger.debug(f"[RECUPERACAO_IA] Tentando estratégia: {nome_estrategia}")
            resultado = estrategia_func()
            
            if resultado and "nome_ferramenta" in resultado:
                logger.info(f"[RECUPERACAO_IA] SUCESSO com {nome_estrategia}: {resultado['nome_ferramenta']}")
                resultado["estrategia_recuperacao"] = nome_estrategia
                resultado["recuperacao_aplicada"] = True
                return resultado
                
        except Exception as e:
            logger.debug(f"[RECUPERACAO_IA] Estratégia {nome_estrategia} falhou: {e}")
            continue
    
    logger.warning("[RECUPERACAO_IA] Todas estratégias falharam")
    return None

def _simplificar_mensagem_ia(mensagem: str) -> Optional[Dict]:
    """Estratégia 1: Simplifica mensagem removendo ruído."""
    # Remove palavras de ligação e mantém só o essencial
    mensagem_limpa = re.sub(r'\b(o|a|os|as|de|da|do|em|na|no|para|por|com)\b', '', mensagem.lower())
    mensagem_limpa = re.sub(r'\s+', ' ', mensagem_limpa).strip()
    
    if mensagem_limpa and mensagem_limpa != mensagem.lower():
        try:
            import ollama
            client = ollama.Client(host=HOST_OLLAMA)
            
            prompt_simples = f"""
Classifique esta mensagem simples em UMA ferramenta:

MENSAGEM: "{mensagem_limpa}"

FERRAMENTAS DISPONÍVEIS:
- visualizar_carrinho (para "carrinho", "itens")
- busca_inteligente_com_promocoes (para buscar produtos)
- adicionar_item_ao_carrinho (para números: 1,2,3...)
  - finalizar_pedido (para "finalizar", "comprar")
- limpar_carrinho (para "limpar", "esvaziar")
- show_more_products (para "mais")

RESPONDA APENAS EM JSON: {{"nome_ferramenta": "X", "parametros": {{}}}}
"""
            
            response = client.chat(
                model=NOME_MODELO_OLLAMA,
                messages=[{"role": "user", "content": prompt_simples}],
                options={"temperature": 0.1, "top_p": 0.3, "num_predict": 30}
            )
            
            return _extrair_json_da_resposta(response['message']['content'])
            
        except Exception as e:
            logger.debug(f"[RECUPERACAO_IA] Simplificação falhou: {e}")
            return None
    
    return None

def _reduzir_contexto_ia(mensagem: str, contexto: str) -> Optional[Dict]:
    """Estratégia 2: Usa apenas contexto essencial."""
    # Extrai só o essencial do contexto
    contexto_reduzido = ""
    if "produtos encontrados" in contexto.lower():
        contexto_reduzido = "Lista de produtos mostrada. Escolha um número."
    elif "carrinho" in contexto.lower():
        contexto_reduzido = "Gerenciando carrinho."
    elif "quantidade" in contexto.lower():
        contexto_reduzido = "Digite quantidade."
    
    try:
        import ollama
        client = ollama.Client(host=HOST_OLLAMA)
        
        prompt_reduzido = f"""
CONTEXTO: {contexto_reduzido}
MENSAGEM: "{mensagem}"

Qual ferramenta usar?
- Se número e lista: adicionar_item_ao_carrinho
- Se carrinho: visualizar_carrinho  
- Se busca: busca_inteligente_com_promocoes

JSON: {{"nome_ferramenta": "X", "parametros": {{}}}}
"""
        
        response = client.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_reduzido}],
            options={"temperature": 0.0, "num_predict": 25}
        )
        
        return _extrair_json_da_resposta(response['message']['content'])
        
    except Exception as e:
        logger.debug(f"[RECUPERACAO_IA] Contexto reduzido falhou: {e}")
        return None

def _tentar_patterns_ia(mensagem: str, contexto: str) -> Optional[Dict]:
    """Estratégia 3: Usa IA para identificar padrões específicos."""
    mensagem_lower = mensagem.lower().strip()
    
    # IA identifica padrão mais provável
    if re.match(r'^\d+$', mensagem_lower):
        return {
            "nome_ferramenta": "adicionar_item_ao_carrinho",
            "parametros": {"indice": int(mensagem_lower)}
        }
    
    elif any(palavra in mensagem_lower for palavra in ["carrinho", "itens", "pedido"]):
        return {
            "nome_ferramenta": "visualizar_carrinho",
            "parametros": {}
        }
    
    elif mensagem_lower in ["mais", "continuar", "próximos"]:
        return {
            "nome_ferramenta": "show_more_products", 
            "parametros": {}
        }
    
    elif any(palavra in mensagem_lower for palavra in ["finalizar", "comprar", "fechar pedido"]):
        return {
            "nome_ferramenta": "finalizar_pedido",
            "parametros": {},
        }
    
    elif any(palavra in mensagem_lower for palavra in ["limpar", "esvaziar", "zerar"]):
        return {
            "nome_ferramenta": "limpar_carrinho",
            "parametros": {}
        }
    
    # Se nada funcionou, assume busca
    return {
        "nome_ferramenta": "busca_inteligente_com_promocoes",
        "parametros": {"termo_busca": mensagem}
    }

def _criar_fallback_contextual_ia(mensagem: str, contexto: str) -> Dict:
    """Estratégia 4: Cria fallback inteligente baseado no contexto."""
    # Análise contextual simples para fallback
    if "produtos" in contexto.lower() or "lista" in contexto.lower():
        if re.match(r'^\d+$', mensagem.strip()):
            return {
                "nome_ferramenta": "adicionar_item_ao_carrinho",
                "parametros": {"indice": int(mensagem.strip())}
            }
    
    # Fallback: assume que é busca de produto
    return {
        "nome_ferramenta": "busca_inteligente_com_promocoes",
        "parametros": {"termo_busca": mensagem},
        "fallback_contextual": True
    }


def _get_saudacao_prompt_segment() -> str:
    return (
        "🔥 SAUDAÇÕES (PRIORIDADE CRÍTICA): \"oi\", \"olá\", \"bom dia\", \"boa tarde\", \"boa noite\", \"eai\" → lidar_conversa\n"
        "Agradecimentos, perguntas gerais → lidar_conversa\n\n"
        "🔥 SAUDAÇÕES (SEMPRE DETECTAR PRIMEIRO):\n"
        "- \"oi\" → lidar_conversa (SEMPRE, mesmo com contexto de produtos)\n"
        "- \"olá\" → lidar_conversa (SEMPRE, mesmo com contexto de produtos)\n"
        "- \"bom dia\" → lidar_conversa (SEMPRE, mesmo com contexto de produtos)\n"
        "- \"boa tarde\" → lidar_conversa (SEMPRE, mesmo com contexto de produtos)\n"
        "- \"boa noite\" → lidar_conversa (SEMPRE, mesmo com contexto de produtos)\n"
        "- \"eai\" → lidar_conversa (SEMPRE, mesmo com contexto de produtos)\n"
    )


def _get_brand_prompt_segment() -> str:
    return (
        "🚨 REGRA CRÍTICA PARA EVITAR CONFUSÃO:\n"
        "- SE A MENSAGEM CONTÉM \"FINI\" ou \"FINÍ\" → SEMPRE busca_inteligente_com_promocoes (marca de doces!)\n"
        "- SE A MENSAGEM CONTÉM APENAS \"FINALIZAR\" EXATA → finalizar_pedido\n"
        "- \"deixa eu ver fini\", \"quero fini\", \"me mostra fini\" → busca_inteligente_com_promocoes (NÃO finalizar!)\n"
        "- Se menciona marca comercial específica (fini, coca-cola, omo, heineken, nutella, etc.) → busca_inteligente_com_promocoes\n\n"
        "🎯 BUSCA POR CATEGORIA/MARCA:\n"
        "- \"quero cerveja\" → busca_inteligente_com_promocoes (categoria de produto)\n"
        "- \"quero fini\" → busca_inteligente_com_promocoes (marca específica!)\n"
        "- \"deixa eu ver fini\" → busca_inteligente_com_promocoes (marca FINI, não finalizar!)\n"
        "- \"vou querer fini\" → busca_inteligente_com_promocoes (marca FINI!)\n"
        "- \"me mostra fini\" → busca_inteligente_com_promocoes (marca FINI!)\n"
        "- \"quero nutella\" → busca_inteligente_com_promocoes (marca específica!)\n"
        "- \"quero omo\" → busca_inteligente_com_promocoes (marca específica!)\n"
        "- \"biscoito doce\" → obter_produtos_mais_vendidos_por_nome (produto sem marca específica)\n"
        "- \"promoções\" → busca_inteligente_com_promocoes (busca por ofertas)\n\n"
        "🚨 CUIDADO COM MARCAS QUE SOAM COMO \"FINALIZAR\":\n"
        "- \"deixa eu ver fini\" → busca_inteligente_com_promocoes (marca FINI, NÃO finalizar!)\n"
        "- \"quero fini\" → busca_inteligente_com_promocoes (marca FINI, NÃO finalizar!)\n"
        "- \"ver fini\" → busca_inteligente_com_promocoes (marca FINI, NÃO finalizar!)\n"
        "- \"quero ver coca\" → busca_inteligente_com_promocoes (marca COCA, NÃO finalizar!)\n\n"
        "ATENÇÃO: Qualquer nome que pareça ser uma marca comercial deve usar busca_inteligente_com_promocoes!\n"
    )

def detectar_intencao_usuario_com_ia(user_message: str, conversation_context: str = "") -> Dict:
    """
    Usa IA para detectar automaticamente a intenção do usuário e escolher a ferramenta apropriada.
    
    Args:
        user_message (str): Mensagem do usuário a ser analisada.
        conversation_context (str, optional): Contexto da conversa para melhor análise.
    
    Returns:
        Dict: Dicionário contendo 'nome_ferramenta', 'parametros' e opcionalmente
        'confidence_score'. Inclui também 'confidence_below_threshold' quando
        a confiança calculada está abaixo de ``CONFIDENCE_THRESHOLD``.
        
    Example:
        >>> detectar_intencao_usuario_com_ia("quero cerveja")
        {"nome_ferramenta": "smart_search_with_promotions", "parametros": {"termo_busca": "quero cerveja"}}
    """
    logger.debug(f"Detectando intenção do usuário com IA para a mensagem: '{user_message}'")

    # 🔄 Limpeza periódica do cache para evitar crescimento excessivo
    if len(_cache_intencao) > 100:
        limpar_cache_intencao()

    # 🚀 CACHE SEMÂNTICO IA-FIRST - Tenta cache por similaridade primeiro
    cache_result = _buscar_cache_semantico(user_message, conversation_context)
    if cache_result:
        logging.info(f"[CACHE
        score = cache_result.get("confidence_score", 0.0)
        cache_result["confidence_below_threshold"] = score < CONFIDENCE_THRESHOLD
        log_decisao_ia(cache_result.get("nome_ferramenta", "unknown"), score, cache_result.get("decision_strategy"))

        return cache_result
    
    # Cache exato (mantido para compatibilidade)
    cache_key = user_message.lower().strip()
    if not conversation_context and cache_key in _cache_intencao:

        logging.debug(f"[INTENT] Cache exato hit para: {cache_key}")
        resultado_cache = _cache_intencao[cache_key]
        score = resultado_cache.get("confidence_score", 0.0)
        resultado_cache["confidence_below_threshold"] = score < CONFIDENCE_THRESHOLD
        log_decisao_ia(resultado_cache.get("nome_ferramenta", "unknown"), score, resultado_cache.get("decision_strategy"))
        return resultado_cache
    

    try:
        # Prompt otimizado para detecção de intenção COM CONTEXTO COMPLETO
        brand_segment = _get_brand_prompt_segment()
        log_prompt_completo(brand_segment, funcao="detectar_intencao_usuario_com_ia", segmento="marcas")
        saudacao_segment = _get_saudacao_prompt_segment()
        log_prompt_completo(saudacao_segment, funcao="detectar_intencao_usuario_com_ia", segmento="saudacoes")
        intent_prompt = f"""
Você é um classificador de intenções para um assistente de vendas do WhatsApp.

FERRAMENTAS DISPONÍVEIS:
1. busca_inteligente_com_promocoes - Para busca por categoria ou promoções específicas
2. mostrar_todas_promocoes - Para ver TODAS promoções organizadas por categoria
3. obter_produtos_mais_vendidos_por_nome - Para busca de produto específico
4. atualizacao_inteligente_carrinho - Para modificar carrinho (adicionar/remover)
5. visualizar_carrinho - Para ver carrinho
6. limpar_carrinho - Para limpar carrinho
7. adicionar_item_ao_carrinho - Para selecionar item por número
8. show_more_products - Para mostrar mais produtos da mesma busca (palavra: mais)
9. finalizar_pedido - Para finalizar pedido (palavras: finalizar, comprar)
10. handle_chitchat - Para saudações e conversas que resetam estado
11. lidar_conversa - Para conversas gerais que mantêm contexto


CONTEXTO DA CONVERSA (FUNDAMENTAL PARA ANÁLISE):
{conversation_context if conversation_context else "Primeira interação"}

MENSAGEM ATUAL DO USUÁRIO: "{user_message}"

REGRAS DE CLASSIFICAÇÃO (ANALISE O CONTEXTO ANTES DE DECIDIR):

{brand_segment}
1. PRIMEIRO, analise o CONTEXTO da conversa para entender a situação atual
2. Se o bot mostrou uma lista de produtos e o usuário responde com número → adicionar_item_ao_carrinho
3. 🚀 CRÍTICO: Se usuário diz apenas "mais" após uma busca de produtos → show_more_products
4. 🎯 NOVO: Se usuário quer ver "promoções", "produtos em promoção", "ofertas" (genérico, sem categoria específica) → mostrar_todas_promocoes
5. Se o usuário quer buscar categoria (cerveja, limpeza, comida, etc.) → busca_inteligente_com_promocoes
6. Se menciona "promoção", "oferta", "desconto" → busca_inteligente_com_promocoes
7. Se busca produto genérico sem marca específica (ex: "biscoito doce", "shampoo qualquer") → obter_produtos_mais_vendidos_por_nome
8. Se fala "adiciona", "coloca", "mais", "remove", "remover", "tirar" com produto → atualizacao_inteligente_carrinho
9. Se pergunta sobre carrinho ou quer ver carrinho → visualizar_carrinho
10. Se quer limpar/esvaziar carrinho → limpar_carrinho

{saudacao_segment}
OUTROS EXEMPLOS (ANALISE SEMPRE O CONTEXTO PRIMEIRO):
- "mais" → show_more_products (PRIORIDADE MÁXIMA após busca!)
- "mais produtos" → show_more_products (continuar busca)
- "continuar" → show_more_products (mostrar mais produtos)

🛒 CARRINHO:
- "limpar carrinho" → limpar_carrinho (comando para esvaziar carrinho)
- "esvaziar carrinho" → limpar_carrinho (comando para limpar carrinho)
- "zerar carrinho" → limpar_carrinho (comando para resetar carrinho)
- "ver carrinho" → visualizar_carrinho (comando para mostrar carrinho)
- "adicionar 2 skol" → atualizacao_inteligente_carrinho (adicionar produto com quantidade)
- "remover 1 skol" → atualizacao_inteligente_carrinho (remover produto com quantidade)
- "tirar cerveja" → atualizacao_inteligente_carrinho (remover produto do carrinho)

🔥 FINALIZAÇÃO DE PEDIDO (APENAS ESTAS PALAVRAS EXATAS):
- "finalizar" → finalizar_pedido (APENAS palavra exata "finalizar")
- "finalizar pedido" → finalizar_pedido (APENAS frase exata)
- "comprar" → finalizar_pedido (APENAS palavra exata "comprar")
- "confirmar pedido" → finalizar_pedido (APENAS frase exata)

IMPORTANTÍSSIMO: Use o CONTEXTO para entender se o usuário está respondendo a uma pergunta do bot!

PARÂMETROS ESPERADOS:
- busca_inteligente_com_promocoes: {{"termo_busca": "termo_completo"}}
- obter_produtos_mais_vendidos_por_nome: {{"nome_produto": "nome_produto"}}
- adicionar_item_ao_carrinho: {{"indice": numero}}
- atualizacao_inteligente_carrinho: {{"nome_produto": "produto", "acao": "add/remove/set", "quantidade": numero}}
- lidar_conversa: {{"response_text": "resposta_natural"}}

ATENÇÃO ESPECIAL PARA AÇÕES:
- "adicionar", "colocar", "mais" → acao: "add"
- "remover", "tirar", "remove" → acao: "remove"
- "trocar para", "mudar para" → acao: "set"

🚨 IMPORTANTE: RESPONDA APENAS EM JSON VÁLIDO, SEM EXPLICAÇÕES!

EXEMPLOS DE RESPOSTA CORRETA:
Para saudações: {{"nome_ferramenta": "lidar_conversa", "parametros": {{"response_text": "GENERATE_GREETING"}}}}
Para mais produtos: {{"nome_ferramenta": "show_more_products", "parametros": {{}}}}

🔥 NÃO ESCREVA TEXTO EXPLICATIVO! APENAS JSON!
"""
        log_prompt_completo(intent_prompt, funcao="detectar_intencao_usuario_com_ia", segmento="completo")

        logger.debug(f"[INTENT] Classificando intenção para: {user_message}")
        
        client = ollama.Client(host=HOST_OLLAMA)
        response = client.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[
                {"role": "system", "content": "Você DEVE responder APENAS em JSON válido. NÃO escreva explicações."},
                {"role": "user", "content": intent_prompt}
            ],
            options={
                "temperature": 0.0,  # Zero para máximo determinismo
                "top_p": 0.1,
                "num_predict": 50,  # Menos tokens para forçar JSON conciso
                "stop": ["\n\n", "**", "Análise"]  # Para parar se começar a explicar
            }
        )
        
        ai_response = response['message']['content'].strip()

        logger.debug(f">>> [CLASSIFICADOR_IA] Mensagem: '{user_message}'")
        logger.debug(f">>> [CLASSIFICADOR_IA] IA respondeu: {ai_response}")
        
        # Extrai JSON da resposta
        intent_data = _extrair_json_da_resposta(ai_response)
        logger.debug(f">>> [CLASSIFICADOR_IA] JSON extraído: {intent_data}")

        
        if intent_data and "nome_ferramenta" in intent_data:
            # Valida se a ferramenta existe
            ferramentas_validas = [
                "busca_inteligente_com_promocoes",
                "obter_produtos_mais_vendidos_por_nome", 
                "atualizacao_inteligente_carrinho",
                "visualizar_carrinho",
                "limpar_carrinho", 
                "adicionar_item_ao_carrinho",
                "show_more_products",
                "finalizar_pedido",
                "handle_chitchat",
                "lidar_conversa"
            ]
            
            if intent_data["nome_ferramenta"] in ferramentas_validas:
                # 🚀 NOVO: Sistema de Validação Proativa de Parâmetros
                intent_data = _parameter_validator.pre_validate_intent(
                    intent_data, user_message, conversation_context
                )
                
                # 🚀 Sistema de Confiança e Score de Decisão
                confidence_score = _confidence_system.analyze_intent_confidence(
                    intent_data, user_message, conversation_context
                )
                decision_strategy = _confidence_system.get_decision_strategy(confidence_score)
                
                # Adiciona dados de confiança ao resultado
                intent_data["confidence_score"] = confidence_score
                intent_data["decision_strategy"] = decision_strategy

                intent_data["confidence_below_threshold"] = confidence_score < CONFIDENCE_THRESHOLD

                log_decisao_ia(
                    intent_data.get("nome_ferramenta", "unknown"),
                    confidence_score,
                    decision_strategy,
                )

                logging.info(
                    f"[INTENT] Intenção: {intent_data['nome_ferramenta']}, "
                    f"Confiança: {confidence_score:.3f}, "
                    f"Estratégia: {decision_strategy}, "
                    f"Validação: {intent_data.get('validation_status', 'N/A')}")

                
                # Cache apenas se não há contexto (primeira interação)
                if not conversation_context:
                    _cache_intencao[cache_key] = intent_data

                # 🚀 CACHE SEMÂNTICO IA-FIRST - Salva sempre no cache semântico
                _salvar_cache_semantico(user_message, intent_data)

                return intent_data
        
        # 🚀 MÚLTIPLAS TENTATIVAS IA-FIRST - Se IA falhou, tenta recuperação inteligente
        logger.warning(f"[INTENT] IA não retornou intenção válida, tentando recuperação inteligente")
        recuperacao_result = _tentar_recuperacao_inteligente_ia(user_message, conversation_context, "json_invalido")
        if recuperacao_result:
            score = recuperacao_result.get("confidence_score", 0.0)
            recuperacao_result["confidence_below_threshold"] = score < CONFIDENCE_THRESHOLD
            log_decisao_ia(recuperacao_result.get("nome_ferramenta", "unknown"), score, recuperacao_result.get("decision_strategy"))
            # Salva no cache semântico o resultado recuperado
            _salvar_cache_semantico(user_message, recuperacao_result)
            _registrar_decisao(recuperacao_result)
            return recuperacao_result

        logging.warning(f"[INTENT] Recuperação falhou, usando fallback final")
        fallback = _criar_intencao_fallback(user_message, conversation_context)
        _registrar_decisao(fallback)
        return fallback

        
    except Exception as e:
        logger.error(f"[INTENT] Erro na detecção de intenção: {e}")
        
        # 🚀 MÚLTIPLAS TENTATIVAS IA-FIRST - Mesmo com erro, tenta recuperação
        try:
            recuperacao_result = _tentar_recuperacao_inteligente_ia(user_message, conversation_context, str(e))
            if recuperacao_result:
                logging.info(f"[RECUPERACAO_IA] Recuperação bem-sucedida após erro: {recuperacao_result['nome_ferramenta']}")
                score = recuperacao_result.get("confidence_score", 0.0)
                recuperacao_result["confidence_below_threshold"] = score < CONFIDENCE_THRESHOLD
                log_decisao_ia(recuperacao_result.get("nome_ferramenta", "unknown"), score, recuperacao_result.get("decision_strategy"))

                _salvar_cache_semantico(user_message, recuperacao_result)
                _registrar_decisao(recuperacao_result)
                return recuperacao_result
        except Exception as e2:

            logging.debug(f"[RECUPERACAO_IA] Recuperação também falhou: {e2}")

        fallback = _criar_intencao_fallback(user_message, conversation_context)
        _registrar_decisao(fallback)
        return fallback


def _extrair_json_da_resposta(response: str) -> Optional[Dict]:
    """
    Extrai dados JSON da resposta da IA.
    
    Args:
        response (str): Resposta da IA para análise.
    
    Returns:
        Optional[Dict]: Dados JSON extraídos ou None se não encontrados.
    """
    logger.debug(f"Extraindo JSON da resposta da IA: '{response}'")
    try:
        # Procura por JSON na resposta
        json_pattern = r'\{.*?\}'
        matches = re.findall(json_pattern, response, re.DOTALL)
        
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        # Se não encontrou JSON, tenta a resposta inteira
        return json.loads(response)
        
    except Exception as e:
        logger.debug(f"[INTENT] Erro ao extrair JSON: {e}")
        return None

def _criar_intencao_fallback(user_message: str, conversation_context: str = "") -> Dict:
    """
    Cria intenção de fallback baseada em regras simples quando a IA falha.
    
    Args:
        user_message (str): Mensagem do usuário para análise.
    
    Returns:
        Dict: Intenção de fallback com nome_ferramenta e parametros.
    """
    logger.debug(f"Criando intenção de fallback para a mensagem: '{user_message}'")
    
    message_lower = user_message.lower().strip()
    
    def _add_confidence_to_intent(intent_data: Dict) -> Dict:
        """Adiciona validação e dados de confiança a qualquer intenção."""
        # Aplica validação
        intent_data = _parameter_validator.pre_validate_intent(
            intent_data, user_message, conversation_context
        )
        
        # Calcula confiança
        confidence_score = _confidence_system.analyze_intent_confidence(
            intent_data, user_message, conversation_context
        )
        decision_strategy = _confidence_system.get_decision_strategy(confidence_score)
        below_threshold = confidence_score < CONFIDENCE_THRESHOLD

        intent_data["confidence_score"] = confidence_score
        intent_data["decision_strategy"] = decision_strategy

        intent_data["confidence_below_threshold"] = below_threshold

        log_decisao_ia(
            intent_data.get("nome_ferramenta", "unknown"),
            confidence_score,
            decision_strategy,
        )

        logging.debug(
            f"[FALLBACK] {intent_data['nome_ferramenta']}: "
            f"confiança={confidence_score:.3f}, estratégia={decision_strategy}, "
            f"validação={intent_data.get('validation_status', 'N/A')}")

        return intent_data
    
    # Regras de fallback simples com CONTEXTO IA-FIRST
    if re.match(r'^\d+$', message_lower):
        # PRIMEIRO: Verifica se há ação pendente de atualização inteligente 
        if "AWAITING_SMART_UPDATE_SELECTION" in conversation_context:
            return _add_confidence_to_intent({
                "nome_ferramenta": "selecionar_item_para_atualizacao",
                "parametros": {"indice": int(message_lower)}
            })
        # SEGUNDO: Verifica se é resposta à opção de finalizar pedido
        elif ("Finalizar Pedido" in conversation_context and user_message.strip() == "1"):
            return _add_confidence_to_intent({
                "nome_ferramenta": "finalizar_pedido",
                "parametros": {},
            })
        else:
            return _add_confidence_to_intent({
                "nome_ferramenta": "adicionar_item_ao_carrinho", 
                "parametros": {"indice": int(message_lower)}
            })
    
    # PRIMEIRA PRIORIDADE: Ações específicas de carrinho (deve vir ANTES da verificação genérica de 'carrinho')
    if any(word in message_lower for word in ['adiciona', 'coloca', 'mais', 'remove', 'remover', 'tirar', 'trocar', 'mudar', 'alterar']):
        # Detecta a ação correta com IA-FIRST
        if any(word in message_lower for word in ['remove', 'remover', 'tirar', 'tira']):
            acao = "remove"
        elif any(word in message_lower for word in ['trocar', 'mudar', 'alterar']) and 'para' in message_lower:
            acao = "set"  # Para definir quantidade específica
        else:
            acao = "add"
        
        # Extrai quantidade de números na mensagem
        quantidade = 1
        numeros = re.findall(r'\d+', user_message)
        if numeros:
            quantidade = int(numeros[0])
        
        # Limpa nome do produto removendo ações, números e referências ao carrinho
        nome_produto = user_message
        palavras_para_remover = ['remover', 'remove', 'tirar', 'tira', 'adicionar', 'adiciona', 'coloca', 'mais', 'trocar', 'mudar', 'alterar', 'para', 'carrinho', 'no', 'do', 'da', 'ao', 'na']
        for palavra in palavras_para_remover:
            nome_produto = re.sub(rf'\b{palavra}\b', '', nome_produto, flags=re.IGNORECASE)
        nome_produto = re.sub(r'\d+', '', nome_produto)  # Remove números
        nome_produto = re.sub(r'\s+', ' ', nome_produto).strip()  # Limpa espaços extras
        
        return _add_confidence_to_intent({
            "nome_ferramenta": "atualizacao_inteligente_carrinho",
            "parametros": {"acao": acao, "quantidade": quantidade, "nome_produto": nome_produto}
        })
    
    # SEGUNDA PRIORIDADE: Comandos de finalização de pedido (PRIORIDADE ALTA - limpa estado pendente)
    if any(word in message_lower for word in ['finalizar', 'concluir', 'fechar pedido', 'comprar', 'finalizar pedido']):
        return _add_confidence_to_intent({
            "nome_ferramenta": "finalizar_pedido",
            "parametros": {"force_finalizar_pedido": True}  # Força finalização independente do estado
        })
    
    # TERCEIRA PRIORIDADE: Comandos de limpeza de carrinho
    if any(word in message_lower for word in ['limpar', 'esvaziar', 'zerar']):
        return _add_confidence_to_intent({
            "nome_ferramenta": "limpar_carrinho",
            "parametros": {}
        })
    
    # QUARTA PRIORIDADE: Visualizar carrinho (somente quando não há ação específica)  
    if any(word in message_lower for word in ['carrinho', 'meu carrinho']) and not any(word in message_lower for word in ['adiciona', 'coloca', 'mais', 'remove', 'remover', 'tirar', 'limpar', 'esvaziar', 'zerar']):
        return _add_confidence_to_intent({
            "nome_ferramenta": "visualizar_carrinho", 
            "parametros": {}
        })
    
    # Detecta se é busca por categoria ou promoção
    palavras_categoria = [
        'cerveja', 'bebida', 'refrigerante', 'suco',
        'limpeza', 'detergente', 'sabão', 
        'higiene', 'shampoo', 'sabonete',
        'comida', 'alimento', 'arroz', 'feijão',
        'promoção', 'oferta', 'desconto', 'barato'
    ]
    
    # 🆕 IA-FIRST: Detecta automaticamente se é uma marca conhecida usando IA
    def _detectar_marca_com_ia(mensagem: str) -> bool:
        """Usa IA para detectar se a mensagem contém uma marca conhecida."""
        logger.debug(f"Detectando marca com IA para a mensagem: '{mensagem}'")
        try:
            import ollama
            prompt_marca = f"""Analise se esta mensagem contém uma MARCA ESPECÍFICA de produto comercial:

MENSAGEM: "{mensagem}"

MARCAS ESPECÍFICAS SÃO:
- Nomes comerciais conhecidos de empresas/fabricantes
- Exemplos: coca-cola, fini, omo, heineken, dove, nutella, skol, pantene
- Palavras que soam como nomes de marca comercial

NÃO SÃO MARCAS:
- Categorias de produtos: cerveja, doce, sabão, refrigerante
- Descrições genéricas: biscoito doce, água gelada
- Tipos de produto: shampoo, detergente (sem nome específico)

Se a mensagem menciona qualquer palavra que pode ser uma marca comercial, responda SIM.
Se é apenas categoria ou descrição genérica, responda NAO.

RESPONDA APENAS: SIM ou NAO"""

            client = ollama.Client(host=HOST_OLLAMA)
            response = client.chat(
                model=NOME_MODELO_OLLAMA,
                messages=[{"role": "user", "content": prompt_marca}],
                options={"temperature": 0.1, "top_p": 0.3, "num_predict": 10}
            )
            
            resposta = response['message']['content'].strip().upper()
            resultado = "SIM" in resposta
            logger.debug(f"[IA-MARCA] '{mensagem}' → IA disse: '{resposta}' → resultado: {resultado}")
            return resultado
        except Exception as e:
            logger.warning(f"[IA-MARCA] Erro na detecção para '{mensagem}': {e}")
            # Fallback: se IA falhar, assume que é marca se não for categoria óbvia
            palavras_categoria_obvias = ['cerveja', 'refrigerante', 'doce', 'bala', 'sabão', 'detergente']
            fallback_resultado = not any(cat in mensagem.lower() for cat in palavras_categoria_obvias)
            logger.debug(f"[IA-MARCA] Fallback para '{mensagem}': {fallback_resultado}")
            return fallback_resultado
    
    # Se contém categoria ou é marca detectada pela IA, usa busca inteligente
    if (any(keyword in message_lower for keyword in palavras_categoria) or
        _detectar_marca_com_ia(user_message)):
        return _add_confidence_to_intent({
            "nome_ferramenta": "busca_inteligente_com_promocoes",
            "parametros": {"termo_busca": user_message}
        })
    
    # Saudações e conversas gerais
    saudacoes = ['oi', 'olá', 'boa', 'como', 'obrigado', 'tchau']
    if any(greeting in message_lower for greeting in saudacoes):
        return _add_confidence_to_intent({
            "nome_ferramenta": "lidar_conversa",
            "parametros": {"texto_resposta": "Olá! Como posso te ajudar hoje?"}
        })
    
    # Default: busca por produto específico
    fallback_intent = {
        "nome_ferramenta": "obter_produtos_mais_vendidos_por_nome",
        "parametros": {"nome_produto": user_message}
    }
    
    # Aplica validação ao fallback também
    fallback_intent = _parameter_validator.pre_validate_intent(
        fallback_intent, user_message, conversation_context
    )
    
    # Adiciona confiança ao fallback (geralmente menor)
    confidence_score = _confidence_system.analyze_intent_confidence(
        fallback_intent, user_message, conversation_context
    )
    decision_strategy = _confidence_system.get_decision_strategy(confidence_score)
    
    fallback_intent["confidence_score"] = confidence_score
    fallback_intent["decision_strategy"] = decision_strategy
    
    logger.info(f"[FALLBACK] Intenção: {fallback_intent['nome_ferramenta']}, "
               f"Confiança: {confidence_score:.3f}, "
               f"Estratégia: {decision_strategy}, "
               f"Validação: {fallback_intent.get('validation_status', 'N/A')}")
    
    return fallback_intent

def limpar_cache_intencao():
    """
    Limpa o cache de intenções para liberar memória.
    
    Note:
        Deve ser chamada periodicamente para evitar acúmulo excessivo de cache.
    """
    global _cache_intencao
    _cache_intencao.clear()
    logger.info("[INTENT] Cache de intenções limpo")

def obter_estatisticas_intencao() -> Dict:
    """
    Retorna estatísticas do classificador de intenções.
    
    Returns:
        Dict: Estatísticas contendo tamanho do cache e intenções armazenadas.
        
    Example:
        >>> obter_estatisticas_intencao()
        {"tamanho_cache": 5, "intencoes_cache": ["oi", "carrinho"]}
    """
    logger.debug("Obtendo estatísticas do classificador de intenções.")
    return {
        "tamanho_cache": len(_cache_intencao),
        "intencoes_cache": list(_cache_intencao.keys())[:10]  # Mostra primeiras 10
    }


class IntentConfidenceSystem:
    """
    Sistema de Confiança e Score de Decisão para melhorar precisão da IA.
    
    Calcula score de confiança 0.0-1.0 baseado em múltiplos fatores para 
    decidir estratégia de execução (imediata, validação, confirmação ou fallback).
    """
    
    def __init__(self):
        # Histórico de sucesso por ferramenta (será alimentado ao longo do tempo)
        self._historical_success = {
            "busca_inteligente_com_promocoes": 0.85,
            "obter_produtos_mais_vendidos_por_nome": 0.80,
            "atualizacao_inteligente_carrinho": 0.75,
            "visualizar_carrinho": 0.95,
            "limpar_carrinho": 0.95,
            "adicionar_item_ao_carrinho": 0.90,
            "show_more_products": 0.85,
            "finalizar_pedido": 0.70,
            "handle_chitchat": 0.90,
            "lidar_conversa": 0.85

        }
        
    def analyze_intent_confidence(self, intent_data: Dict, user_message: str, context: str = "") -> float:
        """
        Calcula score de confiança 0.0-1.0 baseado em múltiplos fatores.
        
        Args:
            intent_data: Dados da intenção detectada pela IA
            user_message: Mensagem original do usuário
            context: Contexto da conversa
            
        Returns:
            float: Score de confiança entre 0.0-1.0
        """
        logger.debug(f"[CONFIDENCE] Analisando confiança para: {intent_data.get('nome_ferramenta', 'unknown')}")
        
        confidence_factors = {
            "context_alignment": self._check_context_match(intent_data, context),
            "parameter_completeness": self._validate_parameters_completeness(intent_data),
            "conversation_flow": self._analyze_conversation_flow(context, user_message),
            "linguistic_patterns": self._analyze_linguistic_confidence(intent_data, user_message),
            "historical_success": self._get_historical_success_rate(intent_data.get("nome_ferramenta", ""))
        }
        
        # Pesos para cada fator (soma = 1.0)
        weights = {
            "context_alignment": 0.25,
            "parameter_completeness": 0.20,
            "conversation_flow": 0.20,
            "linguistic_patterns": 0.20,
            "historical_success": 0.15
        }
        
        # Calcula média ponderada
        confidence = sum(confidence_factors[factor] * weights[factor] 
                        for factor in confidence_factors)
        
        logger.debug(f"[CONFIDENCE] Fatores: {confidence_factors}")
        logger.debug(f"[CONFIDENCE] Score final: {confidence:.3f}")
        
        return round(confidence, 3)
    
    def get_decision_strategy(self, confidence: float) -> str:
        """
        Determina estratégia de execução baseada no score de confiança.
        
        Args:
            confidence: Score de confiança 0.0-1.0
            
        Returns:
            str: Estratégia de execução
        """
        if confidence >= 0.9:
            return "execute_immediately"      # 0.9-1.0: Execute imediatamente
        elif confidence >= 0.7:
            return "execute_with_validation"  # 0.7-0.9: Execute com validação
        elif confidence >= 0.5:
            return "ask_confirmation"         # 0.5-0.7: Peça confirmação
        else:
            return "use_smart_fallback"       # 0.0-0.5: Use fallback inteligente
    
    def _check_context_match(self, intent_data: Dict, context: str) -> float:
        """Verifica alinhamento com contexto da conversa."""
        if not context:
            return 0.7  # Neutro se não há contexto
            
        tool_name = intent_data.get("nome_ferramenta", "")
        
        # Verifica padrões contextuais específicos
        if "lista de produtos" in context.lower() or "produtos encontrados" in context.lower():
            if tool_name == "adicionar_item_ao_carrinho":
                return 0.95  # Alta confiança para seleção após listagem
            elif tool_name in ["busca_inteligente_com_promocoes", "obter_produtos_mais_vendidos_por_nome"]:
                return 0.6   # Média confiança, pode ser nova busca
        
        if "carrinho" in context.lower():
            if tool_name in ["visualizar_carrinho", "atualizacao_inteligente_carrinho", "limpar_carrinho"]:
                return 0.9   # Alta confiança para ações de carrinho
        
        if "finalizar" in context.lower() or "finalizar_pedido" in context.lower():
            if tool_name == "finalizar_pedido":
                return 0.95  # Alta confiança para finalização
        
        return 0.75  # Confiança média por padrão
    
    def _validate_parameters_completeness(self, intent_data: Dict) -> float:
        """Verifica completude e qualidade dos parâmetros."""
        parametros = intent_data.get("parametros", {})
        tool_name = intent_data.get("nome_ferramenta", "")
        
        # Ferramentas que não precisam de parâmetros específicos
        no_params_tools = ["visualizar_carrinho", "limpar_carrinho", "show_more_products"]
        if tool_name in no_params_tools:
            return 0.95
        
        # Verifica parâmetros obrigatórios por ferramenta
        required_params = {
            "busca_inteligente_com_promocoes": ["termo_busca"],
            "obter_produtos_mais_vendidos_por_nome": ["nome_produto"], 
            "atualizacao_inteligente_carrinho": ["acao"],
            "adicionar_item_ao_carrinho": ["indice"],
            "lidar_conversa": ["response_text"]
        }
        
        required = required_params.get(tool_name, [])
        if not required:
            return 0.8  # Ferramenta não reconhecida
        
        # Verifica se todos os parâmetros obrigatórios estão presentes e não vazios
        missing_params = []
        for param in required:
            if param not in parametros or not str(parametros[param]).strip():
                missing_params.append(param)
        
        if not missing_params:
            return 0.95  # Todos parâmetros presentes
        elif len(missing_params) < len(required):
            return 0.6   # Alguns parâmetros faltando
        else:
            return 0.3   # Muitos parâmetros faltando
    
    def _analyze_conversation_flow(self, context: str, user_message: str) -> float:
        """Analisa fluência da conversa e transição entre intenções."""
        if not context:
            return 0.8  # Primeira interação
        
        # Detecta padrões de fluência conversacional
        user_lower = user_message.lower().strip()
        
        # Respostas simples/diretas têm alta confiança
        if re.match(r'^\d+$', user_lower):  # Números isolados
            return 0.95
        
        if user_lower in ['sim', 'não', 'ok', 'beleza', 'certo']:
            return 0.9  # Confirmações simples
        
        # Comandos diretos têm alta confiança
        direct_commands = ['carrinho', 'limpar', 'finalizar', 'mais']
        if any(cmd in user_lower for cmd in direct_commands):
            return 0.85
        
        # Perguntas diretas têm boa confiança
        if user_message.strip().endswith('?'):
            return 0.8
        
        return 0.75  # Confiança média por padrão
    
    def _analyze_linguistic_confidence(self, intent_data: Dict, user_message: str) -> float:
        """Analisa confiança baseada em padrões linguísticos."""
        user_lower = user_message.lower().strip()
        tool_name = intent_data.get("nome_ferramenta", "")
        
        # Palavras-chave que indicam alta confiança para cada ferramenta
        high_confidence_patterns = {
            "visualizar_carrinho": ["carrinho", "meu carrinho", "ver carrinho"],
            "limpar_carrinho": ["limpar", "esvaziar", "zerar", "apagar"],
            "finalizar_pedido": ["finalizar", "comprar", "fechar pedido"],
            "adicionar_item_ao_carrinho": [r'^\d+$'],  # Números isolados
            "show_more_products": ["mais", "continuar", "próximos"],
            "lidar_conversa": ["oi", "olá", "bom dia", "boa tarde", "obrigado"]
        }
        
        patterns = high_confidence_patterns.get(tool_name, [])
        for pattern in patterns:
            if re.search(pattern, user_lower):
                return 0.9
        
        # Verifica se há inconsistências linguísticas
        if len(user_message.strip()) < 2:
            return 0.4  # Mensagens muito curtas
        
        if len(user_message.strip()) > 200:
            return 0.6  # Mensagens muito longas podem ser confusas
        
        return 0.75  # Confiança média
    
    def _get_historical_success_rate(self, tool_name: str) -> float:
        """Retorna taxa histórica de sucesso da ferramenta."""
        return self._historical_success.get(tool_name, 0.7)
    
    def update_historical_success(self, tool_name: str, success: bool):
        """Atualiza taxa histórica de sucesso baseada em feedback."""
        if tool_name not in self._historical_success:
            self._historical_success[tool_name] = 0.7
        
        # Atualização incremental com peso menor para mudanças graduais
        current_rate = self._historical_success[tool_name]
        adjustment = 0.02 if success else -0.02
        new_rate = max(0.1, min(0.98, current_rate + adjustment))
        
        self._historical_success[tool_name] = new_rate
        logger.debug(f"[CONFIDENCE] Taxa de sucesso atualizada para {tool_name}: {new_rate:.3f}")


class SmartParameterValidator:
    """
    Sistema de Validação Proativa de Parâmetros com Correção Automática.
    
    Valida e enriquece parâmetros ANTES da execução para prevenir erros e 
    melhorar a qualidade das ações executadas pela IA.
    """
    
    def __init__(self):
        # Esquemas de validação por ferramenta
        self._validation_schemas = {
            "busca_inteligente_com_promocoes": {
                "required": ["termo_busca"],
                "optional": {},
                "validations": {
                    "termo_busca": {"type": str, "min_length": 1, "max_length": 200}
                }
            },
            "obter_produtos_mais_vendidos_por_nome": {
                "required": ["nome_produto"],
                "optional": {},
                "validations": {
                    "nome_produto": {"type": str, "min_length": 1, "max_length": 100}
                }
            },
            "atualizacao_inteligente_carrinho": {
                "required": ["acao"],
                "optional": ["nome_produto", "quantidade"],
                "validations": {
                    "acao": {"type": str, "allowed": ["add", "remove", "set"]},
                    "quantidade": {"type": int, "min": 1, "max": 10000},
                    "nome_produto": {"type": str, "min_length": 1, "max_length": 100}
                }
            },
            "adicionar_item_ao_carrinho": {
                "required": ["indice"],
                "optional": ["quantidade"],
                "validations": {
                    "indice": {"type": int, "min": 1, "max": 50},
                    "quantidade": {"type": int, "min": 1, "max": 10000}
                }
            },
            "visualizar_carrinho": {
                "required": [],
                "optional": {},
                "validations": {}
            },
            "limpar_carrinho": {
                "required": [],
                "optional": {},
                "validations": {}
            },
            "show_more_products": {
                "required": [],
                "optional": {},
                "validations": {}
            },
            "finalizar_pedido": {
                "required": [],
                "optional": ["cnpj", "force_finalizar_pedido"],
                "validations": {
                    "cnpj": {"type": str, "pattern": r"^\d{14}$"},
                    "force_finalizar_pedido": {"type": bool}
                }
            },
            "lidar_conversa": {
                "required": ["response_text"],
                "optional": {},
                "validations": {
                    "response_text": {"type": str, "min_length": 1, "max_length": 1000}
                }
            }
        }
        
        # Contadores para métricas
        self._validation_stats = {
            "validations_performed": 0,
            "corrections_made": 0,
            "errors_prevented": 0,
            "parameter_enrichments": 0
        }
    
    def pre_validate_intent(self, intent_data: Dict, user_message: str, context: str = "") -> Dict:
        """
        Valida e enriquece parâmetros ANTES da execução.
        
        Args:
            intent_data: Dados da intenção detectada
            user_message: Mensagem original do usuário
            context: Contexto da conversa
            
        Returns:
            Dict: Intent com parâmetros validados e corrigidos
        """
        self._validation_stats["validations_performed"] += 1
        
        tool_name = intent_data.get("nome_ferramenta", "")
        parametros = intent_data.get("parametros", {}).copy()
        
        logger.debug(f"[VALIDATOR] Validando {tool_name} com parâmetros: {parametros}")
        
        # 1. Validação de Schema
        validation_result = self._validate_schema(tool_name, parametros)
        if not validation_result["valid"]:
            parametros = self._correct_parameters(tool_name, parametros, validation_result["errors"])
            self._validation_stats["corrections_made"] += 1
        
        # 2. Validação Contextual
        contextual_corrections = self._validate_contextual_consistency(
            tool_name, parametros, context
        )
        if contextual_corrections:
            parametros.update(contextual_corrections)
            self._validation_stats["corrections_made"] += 1
        
        # 3. Enriquecimento de Parâmetros
        enrichments = self._enrich_parameters(tool_name, parametros, user_message, context)
        if enrichments:
            parametros.update(enrichments)
            self._validation_stats["parameter_enrichments"] += 1
        
        # 4. Validação Final
        final_validation = self._final_validation_check(tool_name, parametros)
        if not final_validation["valid"]:
            # Se ainda há problemas críticos, marca para fallback
            intent_data["validation_status"] = "failed"
            intent_data["validation_errors"] = final_validation["errors"]
            self._validation_stats["errors_prevented"] += 1
        else:
            intent_data["validation_status"] = "passed"
        
        # Atualiza parâmetros validados
        intent_data["parametros"] = parametros
        
        logger.debug(f"[VALIDATOR] Resultado: {tool_name} - status: {intent_data.get('validation_status')} - parâmetros: {parametros}")
        
        return intent_data
    
    def _validate_schema(self, tool_name: str, parametros: Dict) -> Dict:
        """Valida parâmetros contra schema da ferramenta."""
        schema = self._validation_schemas.get(tool_name, {})
        errors = []
        
        # Verifica parâmetros obrigatórios
        required = schema.get("required", [])
        for param in required:
            if param not in parametros or parametros[param] is None or parametros[param] == "":
                errors.append(f"Parâmetro obrigatório '{param}' faltando")
        
        # Valida tipos e restrições
        validations = schema.get("validations", {})
        for param, rules in validations.items():
            if param in parametros:
                value = parametros[param]
                
                # Validação de tipo
                expected_type = rules.get("type")
                if expected_type and not isinstance(value, expected_type):
                    errors.append(f"Parâmetro '{param}' deve ser {expected_type.__name__}")
                
                # Validações específicas
                if expected_type == str:
                    if "min_length" in rules and len(str(value)) < rules["min_length"]:
                        errors.append(f"Parâmetro '{param}' muito curto")
                    if "max_length" in rules and len(str(value)) > rules["max_length"]:
                        errors.append(f"Parâmetro '{param}' muito longo")
                    if "pattern" in rules:
                        import re
                        if not re.match(rules["pattern"], str(value)):
                            errors.append(f"Parâmetro '{param}' formato inválido")
                    if "allowed" in rules and value not in rules["allowed"]:
                        errors.append(f"Parâmetro '{param}' valor não permitido")
                
                elif expected_type in [int, float]:
                    if "min" in rules and value < rules["min"]:
                        errors.append(f"Parâmetro '{param}' menor que mínimo")
                    if "max" in rules and value > rules["max"]:
                        errors.append(f"Parâmetro '{param}' maior que máximo")
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    def _correct_parameters(self, tool_name: str, parametros: Dict, errors: List[str]) -> Dict:
        """Corrige automaticamente parâmetros com problemas."""
        corrected = parametros.copy()
        
        for error in errors:
            if "faltando" in error:
                # Adiciona parâmetros obrigatórios faltando
                if "termo_busca" in error:
                    corrected["termo_busca"] = "produtos"
                elif "nome_produto" in error:
                    corrected["nome_produto"] = "produto"
                elif "acao" in error:
                    corrected["acao"] = "add"
                elif "response_text" in error:
                    corrected["response_text"] = "Como posso ajudar?"
                elif "indice" in error:
                    corrected["indice"] = 1
            
            elif "deve ser int" in error:
                # Converte strings para inteiros
                for param in corrected:
                    if isinstance(corrected[param], str) and corrected[param].isdigit():
                        corrected[param] = int(corrected[param])
            
            elif "deve ser str" in error:
                # Converte valores para string
                for param in corrected:
                    if not isinstance(corrected[param], str):
                        corrected[param] = str(corrected[param])
            
            elif "muito longo" in error:
                # Trunca strings longas
                for param in corrected:
                    if isinstance(corrected[param], str) and len(corrected[param]) > 200:
                        corrected[param] = corrected[param][:200]
            
            elif "menor que mínimo" in error:
                # Ajusta valores mínimos
                if "quantidade" in corrected and corrected["quantidade"] < 1:
                    corrected["quantidade"] = 1
                if "indice" in corrected and corrected["indice"] < 1:
                    corrected["indice"] = 1
            
            elif "maior que máximo" in error:
                # Ajusta valores máximos
                if "quantidade" in corrected and corrected["quantidade"] > 10000:
                    corrected["quantidade"] = 10000
                if "indice" in corrected and corrected["indice"] > 50:
                    corrected["indice"] = 50
        
        return corrected
    
    def _validate_contextual_consistency(self, tool_name: str, parametros: Dict, context: str) -> Dict:
        """Valida consistência com contexto da conversa."""
        corrections = {}
        
        if not context:
            return corrections
        
        context_lower = context.lower()
        
        # Validações contextuais específicas
        if tool_name == "adicionar_item_ao_carrinho":
            # Se contexto menciona lista mas índice parece inválido
            if "lista" in context_lower or "produtos" in context_lower:
                indice = parametros.get("indice", 1)
                if indice > 20:  # Listas raramente têm mais de 20 itens
                    corrections["indice"] = min(indice, 10)
        
        elif tool_name == "atualizacao_inteligente_carrinho":
            # Se contexto sugere carrinho vazio mas está tentando remover
            if "carrinho vazio" in context_lower and parametros.get("acao") == "remove":
                corrections["acao"] = "add"
        
        elif tool_name == "busca_inteligente_com_promocoes":
            # Se busca muito genérica e contexto sugere categoria específica
            termo = parametros.get("termo_busca", "")
            if len(termo) < 3:
                if "cerveja" in context_lower:
                    corrections["termo_busca"] = "cerveja"
                elif "limpeza" in context_lower:
                    corrections["termo_busca"] = "limpeza"
                elif "bebida" in context_lower:
                    corrections["termo_busca"] = "bebidas"
        
        return corrections
    
    def _enrich_parameters(self, tool_name: str, parametros: Dict, user_message: str, context: str) -> Dict:
        """Enriquece parâmetros com informações implícitas."""
        enrichments = {}
        
        # Enriquecimento baseado na mensagem do usuário
        user_lower = user_message.lower()
        
        if tool_name == "atualizacao_inteligente_carrinho":
            # Detecta quantidade implícita na mensagem
            if "quantidade" not in parametros:
                import re
                nums = re.findall(r'\b(\d+)\b', user_message)
                if nums:
                    try:
                        qty = int(nums[0])
                        if 1 <= qty <= 10000:
                            enrichments["quantidade"] = qty
                    except ValueError:
                        pass
                
                if "quantidade" not in enrichments:
                    enrichments["quantidade"] = 1
        
        elif tool_name == "adicionar_item_ao_carrinho":
            # Adiciona quantidade padrão se não especificada
            if "quantidade" not in parametros:
                enrichments["quantidade"] = 1
        
        elif tool_name == "lidar_conversa":
            # Enriquece resposta baseada no tipo de saudação
            if "response_text" in parametros and parametros["response_text"] == "GENERATE_GREETING":
                if "bom dia" in user_lower:
                    enrichments["response_text"] = "Bom dia! Como posso ajudar você hoje?"
                elif "boa tarde" in user_lower:
                    enrichments["response_text"] = "Boa tarde! O que você precisa?"
                elif "boa noite" in user_lower:
                    enrichments["response_text"] = "Boa noite! Em que posso ajudar?"
                else:
                    enrichments["response_text"] = "Olá! Sou o G.A.V., como posso ajudar?"
        
        return enrichments
    
    def _final_validation_check(self, tool_name: str, parametros: Dict) -> Dict:
        """Validação final para garantir que parâmetros estão corretos."""
        critical_errors = []
        
        # Verificações críticas que não podem ser corrigidas automaticamente
        if tool_name == "adicionar_item_ao_carrinho":
            indice = parametros.get("indice")
            if not isinstance(indice, int) or indice < 1:
                critical_errors.append("Índice inválido para seleção")
        
        elif tool_name == "finalizar_pedido":
            cnpj = parametros.get("cnpj")
            if cnpj and len(str(cnpj).replace("-", "").replace(".", "").replace("/", "")) != 14:
                critical_errors.append("CNPJ inválido")
        
        return {"valid": len(critical_errors) == 0, "errors": critical_errors}
    
    def get_validation_statistics(self) -> Dict:
        """Retorna estatísticas de validação."""
        return self._validation_stats.copy()
    
    def reset_statistics(self):
        """Reseta estatísticas de validação."""
        for key in self._validation_stats:
            self._validation_stats[key] = 0


# Instância global do sistema de validação
_parameter_validator = SmartParameterValidator()

# Instância global do sistema de confiança
_confidence_system = IntentConfidenceSystem()

def get_confidence_system() -> IntentConfidenceSystem:
    """
    Retorna a instância global do sistema de confiança.
    
    Returns:
        IntentConfidenceSystem: Sistema de confiança configurado
    """
    return _confidence_system

def update_intent_success(tool_name: str, success: bool):
    """
    Atualiza o histórico de sucesso de uma ferramenta.
    
    Args:
        tool_name: Nome da ferramenta que foi executada
        success: Se a execução foi bem-sucedida
    """
    _confidence_system.update_historical_success(tool_name, success)
    logger.info(f"[CONFIDENCE] Feedback registrado para {tool_name}: {'sucesso' if success else 'falha'}")

def get_confidence_statistics() -> Dict:
    """
    Retorna estatísticas do sistema de confiança.
    
    Returns:
        Dict: Estatísticas incluindo taxas de sucesso por ferramenta
    """
    return {
        "historical_success_rates": _confidence_system._historical_success.copy(),
        "cache_stats": obter_estatisticas_intencao()
    }

def get_parameter_validator() -> SmartParameterValidator:
    """
    Retorna a instância global do sistema de validação.
    
    Returns:
        SmartParameterValidator: Sistema de validação configurado
    """
    return _parameter_validator

def get_validation_statistics() -> Dict:
    """
    Retorna estatísticas do sistema de validação.
    
    Returns:
        Dict: Estatísticas de validação e correção de parâmetros
    """
    return _parameter_validator.get_validation_statistics()

def validate_intent_manually(intent_data: Dict, user_message: str, context: str = "") -> Dict:
    """
    Valida manualmente uma intenção (útil para testes).
    
    Args:
        intent_data: Dados da intenção para validar
        user_message: Mensagem original do usuário
        context: Contexto da conversa
        
    Returns:
        Dict: Intent validado e enriquecido
    """
    return _parameter_validator.pre_validate_intent(intent_data, user_message, context)

def get_combined_statistics() -> Dict:
    """
    Retorna estatísticas combinadas de todos os sistemas.
    
    Returns:
        Dict: Estatísticas completas do classificador
    """
    return {
        "confidence_system": get_confidence_statistics(),
        "validation_system": get_validation_statistics(),
        "cache_system": obter_estatisticas_intencao()
    }

def detectar_intencao_com_sistemas_criticos(entrada_usuario: str, contexto_conversa: str = "", 
                                          historico_conversa: List[Dict] = None,
                                          dados_disponiveis: Dict = None,
                                          dados_sessao: Dict = None) -> Dict:
    """
    Função principal integrada com todos os sistemas críticos implementados.
    
    Integra:
    1. Sistema de Controle de Fluxo Conversacional
    2. Sistema de Prevenção de Invenção de Dados  
    3. Sistema de Redirecionamento Inteligente
    4. Sistema de Confiança e Validação (já existentes)
    5. 🚀 NOVO: Sistema de Gestão Inteligente de Contexto IA-FIRST
    
    Args:
        entrada_usuario: Mensagem do usuário
        contexto_conversa: Contexto atual da conversa
        historico_conversa: Histórico completo da conversa
        dados_disponiveis: Dados disponíveis no sistema para validação factual
        dados_sessao: Dados da sessão para otimização de contexto
        
    Returns:
        Dict: Resultado completo com intenção, validações e orientações
    """
    logger.info(f"[SISTEMAS_CRITICOS] Processando entrada: '{entrada_usuario}' com contexto: '{contexto_conversa[:50]}...'")
    
    # Inicializa dados se não fornecidos
    if dados_disponiveis is None:
        dados_disponiveis = {}
    if historico_conversa is None:
        historico_conversa = []
    if dados_sessao is None:
        dados_sessao = {"messages": []}  # Estrutura básica para otimização de contexto

    # 🆕 Verifica se estamos aguardando seleção e usuário enviou entrada vazia ou '?'
    last_bot_action = dados_sessao.get("last_bot_action")
    mensagem_ajuda = verificar_entrada_vazia_selecao(entrada_usuario, last_bot_action)
    if mensagem_ajuda:
        return {
            "nome_ferramenta": "lidar_conversa",
            "parametros": {"response_text": mensagem_ajuda},
            "tipo_resposta": "redirecionamento_guidance",
            "sistemas_criticos_ativo": True,
            "necessita_redirecionamento": True,
            "validacao_fluxo": {
                "eh_coerente": False,
                "acao": "esclarecer_entrada",
                "mensagem_orientacao": mensagem_ajuda,
            },
            "analise_confusao": {
                "esta_confuso": True,
                "motivo": "entrada_vazia_selecao",
            },
        }
    
    # 🚀 FASE 0: Otimização Inteligente de Contexto IA-FIRST
    logger.debug("[FASE 0] Otimizando contexto inteligentemente...")
    contexto_otimizado = _context_manager.optimize_context_window(dados_sessao, entrada_usuario)
    memoria_trabalho = _context_manager.maintain_working_memory(dados_sessao, entrada_usuario)
    
    # Usa contexto otimizado se disponível, senão usa contexto original
    contexto_para_analise = contexto_otimizado.get("optimized_text", contexto_conversa) or contexto_conversa
    
    logger.info(f"[SISTEMAS_CRITICOS] Contexto otimizado: {len(contexto_conversa)} → {len(contexto_para_analise)} chars, "
                f"qualidade: {contexto_otimizado.get('context_quality_score', 0):.2f}, "
                f"estado_conversa: {memoria_trabalho.get('conversation_state', 'unknown')}")
    
    # FASE 1: Validação de Fluxo Conversacional
    logger.debug("[FASE 1] Validando fluxo conversacional...")
    validacao_fluxo = validar_fluxo_conversa(entrada_usuario, contexto_para_analise, historico_conversa)
    
    # FASE 2: Detecção de Confusão do Usuário
    logger.debug("[FASE 2] Detectando confusão do usuário...")
    analise_confusao = detectar_usuario_confuso(entrada_usuario, contexto_para_analise, historico_conversa)

    # 🔍 Análise adicional de confusão baseada no histórico da conversa
    analise_fluxo_conversa = detectar_confusao_conversa(historico_conversa, entrada_usuario)
    if analise_fluxo_conversa.get("esta_confuso"):
        analise_confusao["esta_confuso"] = True
        if not analise_confusao.get("estrategia_redirecionamento") and \
                analise_fluxo_conversa.get("estrategia_redirecionamento"):
            analise_confusao["estrategia_redirecionamento"] = analise_fluxo_conversa["estrategia_redirecionamento"]
    analise_confusao["analise_fluxo_conversa"] = analise_fluxo_conversa
    
    # 🚀 ENRIQUECIMENTO: Usa informações da memória de trabalho para melhorar análise
    produtos_ativos = memoria_trabalho.get("active_products", [])
    acoes_pendentes = memoria_trabalho.get("pending_actions", [])
    estado_conversa = memoria_trabalho.get("conversation_state", "unknown")
    
    # Ajusta detecção de confusão baseado no estado da conversa
    if estado_conversa == "selecting_products" and not entrada_usuario.strip().isdigit():
        analise_confusao["esta_confuso"] = True
        analise_confusao["motivo_confusao"] = "Expected product selection but got text"
    
    if estado_conversa == "finalizing_purchase" and "carrinho" not in entrada_usuario.lower():
        # Se está finalizando mas pergunta sobre carrinho, não é confusão
        analise_confusao["esta_confuso"] = False
    
    # FASE 3: Decisão sobre como proceder
    deve_redirecionar = (not validacao_fluxo["eh_coerente"] and 
                        validacao_fluxo["acao"] in ["redirecionar", "esclarecer_entrada"]) or \
                       analise_confusao["esta_confuso"]
    
    if deve_redirecionar:
        logger.info("[SISTEMAS_CRITICOS] Usuário necessita redirecionamento - aplicando guidance")
        
        # 🚀 NOVO: Usa memória de trabalho para contextualizar redirecionamento
        if acoes_pendentes:
            acao_pendente = acoes_pendentes[0]
            if acao_pendente["task_type"] == "produto_sem_adicao":
                mensagem_guidance = "Vejo que você estava vendo produtos. Digite o número do produto que deseja adicionar ao carrinho! 🛒"
            elif acao_pendente["task_type"] == "carrinho_sem_finalizacao":
                mensagem_guidance = "Você tem itens no carrinho. Digite 'finalizar' para concluir seu pedido ou 'carrinho' para revisar! 📋"
            else:
                mensagem_guidance = validacao_fluxo.get("mensagem_orientacao", "Como posso ajudar você melhor? 🤝")
        elif validacao_fluxo["mensagem_orientacao"]:
            mensagem_guidance = validacao_fluxo["mensagem_orientacao"]
        elif analise_confusao["estrategia_redirecionamento"]:
            mensagem_guidance = analise_confusao["estrategia_redirecionamento"]["mensagem"]
        else:
            mensagem_guidance = "Como posso ajudar você melhor? 🤝"

        # ✅ Validação final da mensagem de orientação
        validacao_final = aplicar_sistemas_criticos_pos_resposta(mensagem_guidance, dados_disponiveis)
        if validacao_final.get("foi_corrigida"):
            mensagem_guidance = validacao_final["resposta_validada"]

        resultado_redirecionamento = {
            "nome_ferramenta": "lidar_conversa",
            "parametros": {
                "response_text": mensagem_guidance
            },
            "tipo_resposta": "redirecionamento_guidance",
            "validacao_fluxo": validacao_fluxo,
            "analise_confusao": analise_confusao,
            "gestao_contexto": contexto_otimizado,
            "memoria_trabalho": memoria_trabalho,
            "sistemas_criticos_ativo": True,
            "necessita_redirecionamento": True,
            "confidence_score": 0.95,  # Alta confiança no redirecionamento
            "confidence_below_threshold": False,
            "decision_strategy": "execute_immediately",
            "validacao_pos_resposta": validacao_final
        }

        log_decisao_ia(
            resultado_redirecionamento["nome_ferramenta"],
            resultado_redirecionamento["confidence_score"],
            resultado_redirecionamento["decision_strategy"],
        )

        return resultado_redirecionamento
    
    # FASE 4: Detecção Normal de Intenção (se não precisa redirecionamento)
    logger.debug("[FASE 4] Detectando intenção com contexto otimizado...")
    intencao_detectada = detectar_intencao_usuario_com_ia(entrada_usuario, contexto_para_analise)
    
    # 🚀 NOVO: Atualiza memória de trabalho com a intenção detectada
    memoria_trabalho_atualizada = _context_manager.maintain_working_memory(
        dados_sessao, entrada_usuario, intencao_detectada
    )
    
    # FASE 5: Validação Anti-Invenção de Dados e Segurança
    logger.debug("[FASE 5] Validando resposta final...")

    ferramentas_com_resposta_textual = ["lidar_conversa"]
    if intencao_detectada.get("nome_ferramenta") in ferramentas_com_resposta_textual:
        resposta_texto = intencao_detectada.get("parametros", {}).get("response_text", "")
        if resposta_texto and resposta_texto != "GENERATE_GREETING":
            validacao_final = aplicar_sistemas_criticos_pos_resposta(resposta_texto, dados_disponiveis)
            if validacao_final.get("foi_corrigida"):
                logger.warning("[SISTEMAS_CRITICOS] Resposta corrigida para segurança/invenção")
                intencao_detectada["parametros"]["response_text"] = validacao_final["resposta_validada"]
            intencao_detectada["validacao_pos_resposta"] = validacao_final
    
    # FASE 6: Enriquecimento com dados dos sistemas críticos
    intencao_detectada.update({
        "validacao_fluxo": validacao_fluxo,
        "analise_confusao": analise_confusao,
        "gestao_contexto": contexto_otimizado,
        "memoria_trabalho": memoria_trabalho_atualizada,
        "sistemas_criticos_ativo": True,
        "necessita_redirecionamento": deve_redirecionar,
        "recomendacoes_contextuais": analise_confusao.get("recomendacoes", []),
        "contexto_otimizado_usado": True,
        "qualidade_contexto": contexto_otimizado.get("context_quality_score", 0)
    })
    
    logger.info(f"[SISTEMAS_CRITICOS] Intenção final: {intencao_detectada['nome_ferramenta']}, "
                f"confiança: {intencao_detectada.get('confidence_score', 0):.2f}, "
                f"fluxo_coerente: {validacao_fluxo['eh_coerente']}, "
                f"contexto_qualidade: {contexto_otimizado.get('context_quality_score', 0):.2f}, "
                f"estado: {memoria_trabalho_atualizada.get('conversation_state', 'unknown')}")

    log_decisao_ia(
        intencao_detectada.get("nome_ferramenta", "unknown"),
        intencao_detectada.get("confidence_score", 0.0),
        intencao_detectada.get("decision_strategy"),
    )

    return intencao_detectada

def aplicar_sistemas_criticos_pos_resposta(resposta_gerada: str, dados_disponiveis: Dict = None) -> Dict:
    """
    Aplica sistemas críticos APÓS a geração de resposta (para validação final).
    
    Args:
        resposta_gerada: Resposta gerada pelo sistema
        dados_disponiveis: Dados disponíveis para validação factual
        
    Returns:
        Dict: Resultado da validação com resposta corrigida se necessário
    """
    logger.debug("[POS_RESPOSTA] Aplicando validação final...")
    
    if dados_disponiveis is None:
        dados_disponiveis = {}
    
    # Validação anti-invenção de dados
    validacao_final = validar_resposta_ia(resposta_gerada, dados_disponiveis)
    resposta_validada = validacao_final["resposta_corrigida"]

    # Verificação de segurança da resposta
    resposta_segura = verificar_seguranca_resposta(resposta_validada)

    return {
        "resposta_original": resposta_gerada,
        "resposta_validada": resposta_validada,
        "foi_corrigida": validacao_final["foi_corrigida"],
        "confiabilidade": validacao_final["confiabilidade"],
        "resposta_segura": resposta_segura,
        "alertas": validacao_final.get("alertas", []),
        "validacao_detalhes": validacao_final
    }

class IntelligentContextManager:
    """
    Sistema de Gestão Inteligente de Contexto e Memória IA-FIRST.
    
    Otimiza janela de contexto para máxima relevância, mantém memória de trabalho
    focada em informações críticas e melhora significativamente a precisão contextual.
    """
    
    def __init__(self):
        # Cache de contexto otimizado por sessão
        self._context_cache = {}
        
        # Memória de trabalho atual
        self._working_memory = {
            "active_products": [],
            "user_preferences": {},
            "pending_actions": [],
            "conversation_state": "initial",
            "discussed_topics": [],
            "current_search_context": None,
            "cart_operations_history": []
        }
        
        # Estatísticas de otimização
        self._optimization_stats = {
            "contexts_optimized": 0,
            "redundant_info_removed": 0,
            "relevant_history_extracted": 0,
            "working_memory_updates": 0,
            "context_compression_ratio": 0.0
        }
        
        # Palavras-chave por relevância contextual
        self._relevance_keywords = {
            "high_priority": ["carrinho", "finalizar", "finalizar pedido", "pedido", "comprar"],
            "medium_priority": ["produto", "buscar", "mostrar", "adicionar", "remover"],
            "low_priority": ["olá", "obrigado", "tchau", "como", "vai"]
        }
    
    def optimize_context_window(self, session_data: Dict, current_message: str, 
                               max_context_length: int = 2000) -> Dict:
        """
        Otimiza janela de contexto para máxima relevância IA-FIRST.
        
        Args:
            session_data: Dados da sessão com histórico completo
            current_message: Mensagem atual do usuário
            max_context_length: Tamanho máximo do contexto otimizado
            
        Returns:
            Dict: Contexto otimizado com informações mais relevantes
        """
        self._optimization_stats["contexts_optimized"] += 1
        logger.debug(f"[CONTEXT_MANAGER] Otimizando contexto para: '{current_message[:50]}...'")
        
        # 1. Extração de histórico relevante
        relevant_history = self._extract_relevant_history_ia(session_data, current_message)
        
        # 2. Compressão de informações redundantes
        compressed_info = self._compress_redundant_information_ia(relevant_history)
        self._optimization_stats["redundant_info_removed"] += len(relevant_history) - len(compressed_info)
        
        # 3. Priorização de informações críticas
        prioritized_context = self._highlight_critical_context_ia(compressed_info, current_message)
        
        # 4. Aplicação de peso por recência e relevância
        weighted_context = self._weight_by_recency_and_relevance_ia(prioritized_context, current_message)
        
        # 5. Construção do contexto otimizado
        optimized_context = self._build_optimized_context_ia(weighted_context, max_context_length)
        
        # 6. Atualização de cache
        session_id = session_data.get("session_id", "default")
        self._context_cache[session_id] = optimized_context
        
        # Cálculo da razão de compressão
        original_length = sum(len(str(item)) for item in session_data.get("messages", []))
        optimized_length = len(optimized_context.get("optimized_text", ""))
        if original_length > 0:
            self._optimization_stats["context_compression_ratio"] = optimized_length / original_length
        
        logger.info(f"[CONTEXT_MANAGER] Contexto otimizado: {original_length} → {optimized_length} chars "
                    f"({self._optimization_stats['context_compression_ratio']:.2%} compressão)")
        
        return optimized_context
    
    def maintain_working_memory(self, session_data: Dict, current_message: str, 
                               current_intent: Dict = None) -> Dict:
        """
        Mantém memória de trabalho focada em informações críticas IA-FIRST.
        
        Args:
            session_data: Dados da sessão atual
            current_message: Mensagem atual do usuário
            current_intent: Intenção detectada (opcional)
            
        Returns:
            Dict: Memória de trabalho atualizada
        """
        self._optimization_stats["working_memory_updates"] += 1
        logger.debug(f"[CONTEXT_MANAGER] Atualizando memória de trabalho...")
        
        # 1. Rastreamento de produtos discutidos
        active_products = self._track_discussed_products_ia(session_data, current_message)
        self._working_memory["active_products"] = active_products
        
        # 2. Extração de preferências declaradas
        user_preferences = self._extract_stated_preferences_ia(session_data, current_message)
        self._working_memory["user_preferences"].update(user_preferences)
        
        # 3. Identificação de ações pendentes
        pending_actions = self._identify_incomplete_tasks_ia(session_data, current_intent)
        self._working_memory["pending_actions"] = pending_actions
        
        # 4. Determinação do estado da conversa
        conversation_state = self._determine_current_state_ia(session_data, current_message, current_intent)
        self._working_memory["conversation_state"] = conversation_state
        
        # 5. Atualização de contexto de busca atual
        if current_intent and "busca" in current_intent.get("nome_ferramenta", ""):
            search_term = current_intent.get("parametros", {}).get("termo_busca", current_message)
            self._working_memory["current_search_context"] = {
                "search_term": search_term,
                "timestamp": time.time()
            }
        
        # 6. Registro de operações de carrinho
        if current_intent and "carrinho" in current_intent.get("nome_ferramenta", ""):
            self._working_memory["cart_operations_history"].append({
                "operation": current_intent.get("nome_ferramenta"),
                "message": current_message,
                "timestamp": time.time()
            })
            # Mantém apenas últimas 10 operações
            if len(self._working_memory["cart_operations_history"]) > 10:
                self._working_memory["cart_operations_history"] = \
                    self._working_memory["cart_operations_history"][-10:]
        
        logger.debug(f"[CONTEXT_MANAGER] Memória atualizada: estado={conversation_state}, "
                     f"produtos_ativos={len(active_products)}, ações_pendentes={len(pending_actions)}")
        
        return self._working_memory.copy()
    
    def _extract_relevant_history_ia(self, session_data: Dict, current_message: str) -> List[Dict]:
        """Extrai histórico relevante usando IA para análise contextual."""
        messages = session_data.get("messages", [])
        current_lower = current_message.lower()
        relevant_messages = []
        
        # IA identifica mensagens relacionadas por contexto semântico
        for msg_data in messages[-20:]:  # Analisa últimas 20 mensagens
            msg_text = str(msg_data.get("content", "")).lower()
            
            # 1. Relevância por palavras-chave contextuais
            relevance_score = 0
            
            # Analisa sobreposição de palavras-chave
            current_words = set(current_lower.split())
            msg_words = set(msg_text.split())
            word_overlap = len(current_words.intersection(msg_words)) / max(len(current_words), 1)
            relevance_score += word_overlap * 0.3
            
            # 2. Relevância por tópicos relacionados
            if any(keyword in msg_text for keyword in self._relevance_keywords["high_priority"]):
                if any(keyword in current_lower for keyword in self._relevance_keywords["high_priority"]):
                    relevance_score += 0.5
            
            # 3. Relevância por sequência conversacional
            if "produto" in msg_text and any(word in current_lower for word in ["adicionar", "carrinho", "comprar"]):
                relevance_score += 0.4
            
            if "carrinho" in msg_text and any(word in current_lower for word in ["finalizar", "finalizar pedido", "ver"]):
                relevance_score += 0.4
            
            # 4. Relevância por números (seleções de produtos)
            if any(char.isdigit() for char in current_message) and any(char.isdigit() for char in msg_text):
                relevance_score += 0.2
            
            # Incluir mensagens com relevância > 0.3
            if relevance_score > 0.3:
                msg_data["relevance_score"] = relevance_score
                relevant_messages.append(msg_data)
        
        # Ordena por relevância
        relevant_messages.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        self._optimization_stats["relevant_history_extracted"] += len(relevant_messages)
        return relevant_messages[:10]  # Top 10 mais relevantes
    
    def _compress_redundant_information_ia(self, relevant_history: List[Dict]) -> List[Dict]:
        """Comprime informações redundantes usando IA para detectar duplicações."""
        if not relevant_history:
            return relevant_history
        
        compressed = []
        seen_patterns = set()
        
        for msg_data in relevant_history:
            msg_text = str(msg_data.get("content", "")).lower()
            
            # IA detecta padrões redundantes
            pattern_hash = self._generate_semantic_pattern_hash_ia(msg_text)
            
            if pattern_hash not in seen_patterns:
                compressed.append(msg_data)
                seen_patterns.add(pattern_hash)
            else:
                # Mantém apenas se tiver informação adicional significativa
                if len(msg_text) > 50 and "produto" in msg_text:
                    compressed.append(msg_data)
        
        return compressed
    
    def _generate_semantic_pattern_hash_ia(self, text: str) -> str:
        """Gera hash semântico para detectar padrões similares com IA."""
        # Remove números específicos e mantém padrão geral
        import re
        normalized = re.sub(r'\d+', 'N', text)  # Substitui números por 'N'
        normalized = re.sub(r'\s+', ' ', normalized.strip())  # Normaliza espaços
        
        # Extrai padrão semântico principal
        key_patterns = []
        if "carrinho" in normalized: key_patterns.append("cart")
        if "produto" in normalized: key_patterns.append("product")
        if "busca" in normalized: key_patterns.append("search")
        if "finalizar" in normalized: key_patterns.append("finalizar_pedido")
        if "N" in normalized: key_patterns.append("selection")
        
        return "_".join(sorted(key_patterns)) if key_patterns else normalized[:20]
    
    def _highlight_critical_context_ia(self, compressed_info: List[Dict], current_message: str) -> List[Dict]:
        """Destaca informações críticas usando IA para priorização."""
        current_lower = current_message.lower()
        
        for msg_data in compressed_info:
            msg_text = str(msg_data.get("content", "")).lower()
            priority = "normal"
            
            # IA determina prioridade contextual
            if any(keyword in msg_text for keyword in self._relevance_keywords["high_priority"]):
                if any(keyword in current_lower for keyword in self._relevance_keywords["high_priority"]):
                    priority = "critical"
            
            # Prioridade alta para números se usuário está selecionando
            if current_lower.isdigit() and any(char.isdigit() for char in msg_text):
                priority = "high"
            
            # Prioridade crítica para últimas ações de carrinho
            if "carrinho" in msg_text and "finalizar" in current_lower:
                priority = "critical"
            
            msg_data["context_priority"] = priority
        
        return compressed_info
    
    def _weight_by_recency_and_relevance_ia(self, prioritized_context: List[Dict], current_message: str) -> List[Dict]:
        """Aplica peso por recência e relevância usando IA."""
        now = time.time()
        
        for i, msg_data in enumerate(prioritized_context):
            # Peso por recência (mensagens mais recentes têm peso maior)
            recency_weight = 1.0 - (i * 0.1)  # Decai 10% para cada posição anterior
            
            # Peso por relevância
            relevance_weight = msg_data.get("relevance_score", 0.5)
            
            # Peso por prioridade
            priority = msg_data.get("context_priority", "normal")
            priority_weights = {"critical": 1.0, "high": 0.8, "normal": 0.5, "low": 0.3}
            priority_weight = priority_weights.get(priority, 0.5)
            
            # Peso combinado
            combined_weight = (recency_weight * 0.3) + (relevance_weight * 0.4) + (priority_weight * 0.3)
            msg_data["context_weight"] = round(combined_weight, 3)
        
        # Ordena por peso combinado
        prioritized_context.sort(key=lambda x: x.get("context_weight", 0), reverse=True)
        return prioritized_context
    
    def _build_optimized_context_ia(self, weighted_context: List[Dict], max_length: int) -> Dict:
        """Constrói contexto otimizado respeitando limite de tamanho."""
        optimized_parts = []
        current_length = 0
        included_messages = []
        
        for msg_data in weighted_context:
            msg_content = str(msg_data.get("content", ""))
            msg_length = len(msg_content)
            
            if current_length + msg_length <= max_length:
                optimized_parts.append(msg_content)
                current_length += msg_length
                included_messages.append(msg_data)
            else:
                # Se não cabe inteiro, tenta incluir versão resumida
                if msg_data.get("context_priority") == "critical":
                    summary = msg_content[:100] + "..." if len(msg_content) > 100 else msg_content
                    if current_length + len(summary) <= max_length:
                        optimized_parts.append(summary)
                        current_length += len(summary)
                        msg_data["was_summarized"] = True
                        included_messages.append(msg_data)
        
        # Constrói contexto final
        optimized_text = "\n".join(optimized_parts[-10:])  # Últimas 10 mensagens mais relevantes
        
        return {
            "optimized_text": optimized_text,
            "included_messages": included_messages,
            "total_length": current_length,
            "compression_achieved": True,
            "context_quality_score": sum(msg.get("context_weight", 0) for msg in included_messages) / max(len(included_messages), 1)
        }
    
    def _track_discussed_products_ia(self, session_data: Dict, current_message: str) -> List[Dict]:
        """Rastreia produtos discutidos usando IA para extração semântica."""
        products = []
        messages = session_data.get("messages", [])
        current_lower = current_message.lower()
        
        # IA extrai produtos mencionados
        product_keywords = ["cerveja", "skol", "heineken", "brahma", "coca", "produto", "item"]
        
        for msg_data in messages[-10:]:  # Últimas 10 mensagens
            msg_text = str(msg_data.get("content", "")).lower()
            
            # Detecta menção de produtos
            if any(keyword in msg_text for keyword in product_keywords):
                # Extrai contexto do produto
                product_context = {
                    "mentioned_in": msg_text[:100],
                    "relevance_to_current": self._calculate_product_relevance_ia(msg_text, current_lower),
                    "message_timestamp": msg_data.get("timestamp", 0)
                }
                
                if product_context["relevance_to_current"] > 0.3:
                    products.append(product_context)
        
        # Remove duplicados e ordena por relevância
        unique_products = []
        seen_contexts = set()
        
        for product in products:
            context_key = product["mentioned_in"][:50]
            if context_key not in seen_contexts:
                unique_products.append(product)
                seen_contexts.add(context_key)
        
        unique_products.sort(key=lambda x: x["relevance_to_current"], reverse=True)
        return unique_products[:5]  # Top 5 mais relevantes
    
    def _calculate_product_relevance_ia(self, product_text: str, current_text: str) -> float:
        """Calcula relevância de produto mencionado com mensagem atual usando IA."""
        relevance = 0.0
        
        # Sobreposição de palavras
        product_words = set(product_text.split())
        current_words = set(current_text.split())
        overlap = len(product_words.intersection(current_words))
        relevance += overlap * 0.1
        
        # Contexto de ações relacionadas
        action_words = ["adicionar", "carrinho", "comprar", "remover", "finalizar"]
        if any(word in current_text for word in action_words):
            relevance += 0.4
        
        # Contexto numérico (seleções)
        if any(char.isdigit() for char in current_text):
            relevance += 0.2
        
        return min(relevance, 1.0)
    
    def _extract_stated_preferences_ia(self, session_data: Dict, current_message: str) -> Dict:
        """Extrai preferências declaradas pelo usuário usando IA."""
        preferences = {}
        messages = session_data.get("messages", [])
        
        # IA identifica padrões de preferência
        preference_patterns = {
            "cerveja_preferida": [r"gosto.*cerveja", r"prefiro.*cerveja", r"quero.*cerveja"],
            "categoria_interesse": [r"interesse.*em", r"quero.*categoria", r"busco.*tipo"],
            "quantidade_usual": [r"sempre.*compro", r"geralmente.*levo", r"costumo.*pegar"]
        }
        
        for msg_data in messages:
            msg_text = str(msg_data.get("content", "")).lower()
            
            for pref_type, patterns in preference_patterns.items():
                for pattern in patterns:
                    import re
                    if re.search(pattern, msg_text):
                        preferences[pref_type] = {
                            "stated_in": msg_text[:50],
                            "confidence": 0.8,
                            "timestamp": msg_data.get("timestamp", 0)
                        }
        
        return preferences
    
    def _identify_incomplete_tasks_ia(self, session_data: Dict, current_intent: Dict = None) -> List[Dict]:
        """Identifica tarefas incompletas usando IA para análise de fluxo."""
        pending = []
        messages = session_data.get("messages", [])
        
        # IA detecta fluxos incompletos
        incomplete_patterns = {
            "produto_sem_adicao": {"trigger": "mostrar produtos", "missing": "adicionar carrinho"},
            "carrinho_sem_finalizacao": {"trigger": "visualizar carrinho", "missing": "finalizar pedido"},
            "busca_sem_selecao": {"trigger": "busca produtos", "missing": "selecionar item"}
        }
        
        for msg_data in messages[-5:]:  # Últimas 5 mensagens
            msg_text = str(msg_data.get("content", "")).lower()
            
            # Verifica padrões de tarefas incompletas
            if "produtos encontrados" in msg_text and not any(
                "adicionado" in str(m.get("content", "")).lower() 
                for m in messages[messages.index(msg_data):]
            ):
                pending.append({
                    "task_type": "produto_sem_adicao",
                    "description": "Produtos mostrados mas não adicionados ao carrinho",
                    "priority": "medium",
                    "detected_in": msg_text[:50]
                })
            
            if "carrinho" in msg_text and "finalizar" not in msg_text:
                pending.append({
                    "task_type": "carrinho_sem_finalizacao",
                    "description": "Carrinho visualizado mas pedido não finalizado",
                    "priority": "high",
                    "detected_in": msg_text[:50]
                })
        
        # Remove duplicados
        unique_pending = []
        seen_tasks = set()
        for task in pending:
            task_key = task["task_type"] + task["detected_in"]
            if task_key not in seen_tasks:
                unique_pending.append(task)
                seen_tasks.add(task_key)
        
        return unique_pending
    
    def _determine_current_state_ia(self, session_data: Dict, current_message: str, current_intent: Dict = None) -> str:
        """Determina estado atual da conversa usando IA."""
        current_lower = current_message.lower()
        
        # IA analisa estado baseado em padrões conversacionais
        if current_intent:
            tool_name = current_intent.get("nome_ferramenta", "")
            
            state_mapping = {
                "busca_inteligente_com_promocoes": "searching_products",
                "adicionar_item_ao_carrinho": "selecting_products",
                "visualizar_carrinho": "reviewing_cart",
                "atualizacao_inteligente_carrinho": "modifying_cart",
                "finalizar_pedido": "finalizing_purchase",
                "handle_chitchat": "greeting",
                "lidar_conversa": "general_conversation"
            }
            
            detected_state = state_mapping.get(tool_name, "unknown_intent")
        else:
            # Fallback: análise por padrões na mensagem
            if any(word in current_lower for word in ["oi", "olá", "bom dia"]):
                detected_state = "greeting"
            elif any(word in current_lower for word in ["produto", "busca", "procuro"]):
                detected_state = "searching_products"
            elif current_lower.isdigit():
                detected_state = "selecting_products"
            elif "carrinho" in current_lower:
                detected_state = "reviewing_cart"
            elif "finalizar" in current_lower:
                detected_state = "finalizing_purchase"
            else:
                detected_state = "general_conversation"
        
        return detected_state
    
    def get_optimization_statistics(self) -> Dict:
        """Retorna estatísticas de otimização do contexto."""
        return {
            "optimization_stats": self._optimization_stats.copy(),
            "working_memory_size": len(str(self._working_memory)),
            "context_cache_size": len(self._context_cache),
            "current_conversation_state": self._working_memory.get("conversation_state", "unknown"),
            "active_products_count": len(self._working_memory.get("active_products", [])),
            "pending_actions_count": len(self._working_memory.get("pending_actions", []))
        }
    
    def reset_working_memory(self):
        """Reseta memória de trabalho (útil para nova sessão)."""
        self._working_memory = {
            "active_products": [],
            "user_preferences": {},
            "pending_actions": [],
            "conversation_state": "initial",
            "discussed_topics": [],
            "current_search_context": None,
            "cart_operations_history": []
        }
        logger.info("[CONTEXT_MANAGER] Memória de trabalho resetada")
    
    def get_current_working_memory(self) -> Dict:
        """Retorna cópia atual da memória de trabalho."""
        return self._working_memory.copy()


# Instância global do gerenciador de contexto IA-FIRST
_context_manager = IntelligentContextManager()

def get_context_manager() -> IntelligentContextManager:
    """
    Retorna a instância global do gerenciador de contexto.
    
    Returns:
        IntelligentContextManager: Gerenciador de contexto configurado
    """
    return _context_manager

def optimize_context_for_intent(session_data: Dict, current_message: str, 
                               max_context_length: int = 2000) -> Dict:
    """
    Otimiza contexto para detecção de intenção IA-FIRST.
    
    Args:
        session_data: Dados da sessão com histórico
        current_message: Mensagem atual do usuário
        max_context_length: Tamanho máximo do contexto
        
    Returns:
        Dict: Contexto otimizado para máxima relevância
    """
    return _context_manager.optimize_context_window(session_data, current_message, max_context_length)

def update_working_memory(session_data: Dict, current_message: str, 
                         current_intent: Dict = None) -> Dict:
    """
    Atualiza memória de trabalho com informações da sessão atual.
    
    Args:
        session_data: Dados da sessão atual
        current_message: Mensagem atual do usuário
        current_intent: Intenção detectada (opcional)
        
    Returns:
        Dict: Memória de trabalho atualizada
    """
    return _context_manager.maintain_working_memory(session_data, current_message, current_intent)

def get_context_optimization_stats() -> Dict:
    """
    Retorna estatísticas de otimização de contexto.
    
    Returns:
        Dict: Estatísticas completas do sistema de contexto
    """
    return _context_manager.get_optimization_statistics()

def obter_estatisticas_sistemas_criticos() -> Dict:
    """
    Retorna estatísticas combinadas de todos os sistemas críticos.
    
    Returns:
        Dict: Estatísticas completas dos sistemas implementados
    """
    try:
        from .controlador_fluxo_conversa import obter_estatisticas_fluxo
        from .prevencao_invencao_dados import obter_estatisticas_prevencao  
        from .redirecionamento_inteligente import obter_estatisticas_redirecionamento
        
        return {
            "classificador_intencao": get_combined_statistics(),
            "gestao_contexto": get_context_optimization_stats(),
            "fluxo_conversacional": obter_estatisticas_fluxo(),
            "prevencao_invencao": obter_estatisticas_prevencao(),
            "redirecionamento_inteligente": obter_estatisticas_redirecionamento(),
            "sistemas_criticos_ativo": True,
            "versao_sistemas": "1.1.0_21082025"
        }
    except ImportError as e:
        logger.warning(f"[SISTEMAS_CRITICOS] Erro ao importar estatísticas: {e}")
        return {
            "classificador_intencao": get_combined_statistics(),
            "gestao_contexto": get_context_optimization_stats(),
            "sistemas_criticos_ativo": False,
            "erro": str(e)
        }
