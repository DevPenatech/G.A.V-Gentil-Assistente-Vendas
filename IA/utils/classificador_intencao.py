#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classificador de Intenções Inteligente
Usa IA para detectar automaticamente a intenção do usuário e escolher a ferramenta certa
"""

import logging
import ollama
import json
import os
import re
from typing import Dict, Optional

# Configurações
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
HOST_OLLAMA = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")

# Cache de intenções para performance
_cache_intencao = {}

def detectar_intencao_usuario_com_ia(user_message: str, conversation_context: str = "") -> Dict:
    """
    Usa IA para detectar automaticamente a intenção do usuário e escolher a ferramenta apropriada.
    
    Args:
        user_message (str): Mensagem do usuário a ser analisada.
        conversation_context (str, optional): Contexto da conversa para melhor análise.
    
    Returns:
        Dict: Dicionário contendo 'nome_ferramenta' e 'parametros' da ferramenta selecionada.
        
    Example:
        >>> detectar_intencao_usuario_com_ia("quero cerveja")
        {"nome_ferramenta": "smart_search_with_promotions", "parametros": {"termo_busca": "quero cerveja"}}
    """
    logging.debug(f"Detectando intenção do usuário com IA para a mensagem: '{user_message}'")
    
    # Cache apenas para mensagens sem contexto (primeira interação)
    # CORRIGIDO: Não usa cache quando há contexto, pois a mesma mensagem pode ter intenções diferentes
    cache_key = user_message.lower().strip()
    if not conversation_context and cache_key in _cache_intencao:
        logging.debug(f"[INTENT] Cache hit para: {cache_key}")
        return _cache_intencao[cache_key]
    
    try:
        # Prompt otimizado para detecção de intenção COM CONTEXTO COMPLETO
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
9. checkout - Para finalizar pedido (palavras: finalizar, checkout, comprar)
10. handle_chitchat - Para saudações e conversas que resetam estado  
11. lidar_conversa - Para conversas gerais que mantêm contexto

CONTEXTO DA CONVERSA (FUNDAMENTAL PARA ANÁLISE):
{conversation_context if conversation_context else "Primeira interação"}

MENSAGEM ATUAL DO USUÁRIO: "{user_message}"

REGRAS DE CLASSIFICAÇÃO (ANALISE O CONTEXTO ANTES DE DECIDIR):
1. PRIMEIRO, analise o CONTEXTO da conversa para entender a situação atual
2. Se o bot mostrou uma lista de produtos e o usuário responde com número → adicionar_item_ao_carrinho
3. 🚀 CRÍTICO: Se usuário diz apenas "mais" após uma busca de produtos → show_more_products
4. 🎯 NOVO: Se usuário quer ver "promoções", "produtos em promoção", "ofertas" (genérico, sem categoria específica) → mostrar_todas_promocoes  
5. Se o usuário quer buscar categoria (cerveja, limpeza, comida, etc.) → busca_inteligente_com_promocoes
5. Se menciona "promoção", "oferta", "desconto" → busca_inteligente_com_promocoes  
6. IMPORTANTE: Se menciona marca comercial específica (fini, coca-cola, omo, heineken, nutella, etc.) → busca_inteligente_com_promocoes
7. Se busca produto genérico sem marca específica (ex: "biscoito doce", "shampoo qualquer") → obter_produtos_mais_vendidos_por_nome
8. Se fala "adiciona", "coloca", "mais", "remove", "remover", "tirar" com produto → atualizacao_inteligente_carrinho
9. Se pergunta sobre carrinho ou quer ver carrinho → visualizar_carrinho
10. Se quer limpar/esvaziar carrinho → limpar_carrinho
11. 🔥 SAUDAÇÕES (PRIORIDADE CRÍTICA): "oi", "olá", "bom dia", "boa tarde", "boa noite", "eai" → handle_chitchat
12. Agradecimentos, perguntas gerais → lidar_conversa

EXEMPLOS IMPORTANTES:
🔥 SAUDAÇÕES (SEMPRE DETECTAR PRIMEIRO):
- "oi" → handle_chitchat (SEMPRE, mesmo com contexto de produtos)
- "olá" → handle_chitchat (SEMPRE, mesmo com contexto de produtos)  
- "bom dia" → handle_chitchat (SEMPRE, mesmo com contexto de produtos)
- "boa tarde" → handle_chitchat (SEMPRE, mesmo com contexto de produtos)
- "boa noite" → handle_chitchat (SEMPRE, mesmo com contexto de produtos)
- "eai" → handle_chitchat (SEMPRE, mesmo com contexto de produtos)

OUTROS EXEMPLOS:
- "mais" → show_more_products (PRIORIDADE MÁXIMA após busca!)
- "mais produtos" → show_more_products (continuar busca)
- "continuar" → show_more_products (mostrar mais produtos)
- "quero cerveja" → busca_inteligente_com_promocoes (categoria de produto)
- "quero fini" → busca_inteligente_com_promocoes (marca específica!)
- "quero nutella" → busca_inteligente_com_promocoes (marca específica!)
- "quero omo" → busca_inteligente_com_promocoes (marca específica!)
- "biscoito doce" → obter_produtos_mais_vendidos_por_nome (produto sem marca específica)
- "promoções" → busca_inteligente_com_promocoes (busca por ofertas)
- "limpar carrinho" → limpar_carrinho (comando para esvaziar carrinho)
- "esvaziar carrinho" → limpar_carrinho (comando para limpar carrinho)
- "zerar carrinho" → limpar_carrinho (comando para resetar carrinho)
- "ver carrinho" → visualizar_carrinho (comando para mostrar carrinho)
- "adicionar 2 skol" → atualizacao_inteligente_carrinho (adicionar produto com quantidade)
- "remover 1 skol" → atualizacao_inteligente_carrinho (remover produto com quantidade)
- "tirar cerveja" → atualizacao_inteligente_carrinho (remover produto do carrinho)
- "finalizar" → checkout (finalizar pedido)
- "finalizar pedido" → checkout (finalizar pedido)
- "checkout" → checkout (finalizar pedido)
- "comprar" → checkout (finalizar pedido)

ATENÇÃO: Qualquer nome que pareça ser uma marca comercial deve usar busca_inteligente_com_promocoes!

IMPORTANTÍSSIMO: Use o CONTEXTO para entender se o usuário está respondendo a uma pergunta do bot!

PARÂMETROS ESPERADOS:
- busca_inteligente_com_promocoes: {{"termo_busca": "termo_completo"}}
- obter_produtos_mais_vendidos_por_nome: {{"nome_produto": "nome_produto"}}
- adicionar_item_ao_carrinho: {{"indice": numero}}
- atualizacao_inteligente_carrinho: {{"nome_produto": "produto", "acao": "add/remove/set", "quantidade": numero}}
- handle_chitchat: {{"response_text": "GENERATE_GREETING"}} (SEMPRE para saudações)
- lidar_conversa: {{"response_text": "resposta_natural"}}

ATENÇÃO ESPECIAL PARA AÇÕES:
- "adicionar", "colocar", "mais" → acao: "add"
- "remover", "tirar", "remove" → acao: "remove"
- "trocar para", "mudar para" → acao: "set"

🚨 IMPORTANTE: RESPONDA APENAS EM JSON VÁLIDO, SEM EXPLICAÇÕES!

EXEMPLOS DE RESPOSTA CORRETA:
Para saudações: {{"nome_ferramenta": "handle_chitchat", "parametros": {{"response_text": "GENERATE_GREETING"}}}}
Para mais produtos: {{"nome_ferramenta": "show_more_products", "parametros": {{}}}}

🔥 NÃO ESCREVA TEXTO EXPLICATIVO! APENAS JSON!
"""

        logging.debug(f"[INTENT] Classificando intenção para: {user_message}")
        
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
        print(f">>> 🔍 [CLASSIFICADOR_IA] Mensagem: '{user_message}'")
        print(f">>> 🔍 [CLASSIFICADOR_IA] IA respondeu: {ai_response}")
        
        # Extrai JSON da resposta
        intent_data = _extrair_json_da_resposta(ai_response)
        print(f">>> 🔍 [CLASSIFICADOR_IA] JSON extraído: {intent_data}")
        
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
                "checkout",
                "handle_chitchat",
                "lidar_conversa"
            ]
            
            if intent_data["nome_ferramenta"] in ferramentas_validas:
                # Cache apenas se não há contexto (primeira interação)
                if not conversation_context:
                    _cache_intencao[cache_key] = intent_data
                logging.info(f"[INTENT] Intenção detectada: {intent_data['nome_ferramenta']}")
                return intent_data
        
        # Fallback se a IA não retornou JSON válido
        logging.warning(f"[INTENT] IA não retornou intenção válida, usando fallback")
        return _criar_intencao_fallback(user_message, conversation_context)
        
    except Exception as e:
        logging.error(f"[INTENT] Erro na detecção de intenção: {e}")
        return _criar_intencao_fallback(user_message, conversation_context)

def _extrair_json_da_resposta(response: str) -> Optional[Dict]:
    """
    Extrai dados JSON da resposta da IA.
    
    Args:
        response (str): Resposta da IA para análise.
    
    Returns:
        Optional[Dict]: Dados JSON extraídos ou None se não encontrados.
    """
    logging.debug(f"Extraindo JSON da resposta da IA: '{response}'")
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
        logging.debug(f"[INTENT] Erro ao extrair JSON: {e}")
        return None

def _criar_intencao_fallback(user_message: str, conversation_context: str = "") -> Dict:
    """
    Cria intenção de fallback baseada em regras simples quando a IA falha.
    
    Args:
        user_message (str): Mensagem do usuário para análise.
    
    Returns:
        Dict: Intenção de fallback com nome_ferramenta e parametros.
    """
    logging.debug(f"Criando intenção de fallback para a mensagem: '{user_message}'")
    
    message_lower = user_message.lower().strip()
    
    # Regras de fallback simples com CONTEXTO IA-FIRST
    if re.match(r'^\d+$', message_lower):
        # PRIMEIRO: Verifica se há ação pendente de atualização inteligente 
        if "AWAITING_SMART_UPDATE_SELECTION" in conversation_context:
            return {
                "nome_ferramenta": "selecionar_item_para_atualizacao",
                "parametros": {"indice": int(message_lower)}
            }
        # SEGUNDO: Verifica se é resposta à opção de finalizar pedido
        elif ("Finalizar Pedido" in conversation_context and user_message.strip() == "1"):
            return {
                "nome_ferramenta": "checkout",
                "parametros": {}
            }
        # TERCEIRO: Se não é finalizar pedido nem atualização, é seleção de produto da lista
        else:
            return {
                "nome_ferramenta": "adicionar_item_ao_carrinho", 
                "parametros": {"indice": int(message_lower)}
            }
    
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
        
        return {
            "nome_ferramenta": "atualizacao_inteligente_carrinho",
            "parametros": {"acao": acao, "quantidade": quantidade, "nome_produto": nome_produto}
        }
    
    # SEGUNDA PRIORIDADE: Comandos de finalização de pedido (PRIORIDADE ALTA - limpa estado pendente)
    if any(word in message_lower for word in ['finalizar', 'checkout', 'concluir', 'fechar pedido', 'comprar']):
        return {
            "nome_ferramenta": "checkout",
            "parametros": {"force_checkout": True}  # Força checkout independente do estado
        }
    
    # TERCEIRA PRIORIDADE: Comandos de limpeza de carrinho
    if any(word in message_lower for word in ['limpar', 'esvaziar', 'zerar']):
        return {
            "nome_ferramenta": "limpar_carrinho",
            "parametros": {}
        }
    
    # QUARTA PRIORIDADE: Visualizar carrinho (somente quando não há ação específica)  
    if any(word in message_lower for word in ['carrinho', 'meu carrinho']) and not any(word in message_lower for word in ['adiciona', 'coloca', 'mais', 'remove', 'remover', 'tirar', 'limpar', 'esvaziar', 'zerar']):
        return {
            "nome_ferramenta": "visualizar_carrinho", 
            "parametros": {}
        }
    
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
        logging.debug(f"Detectando marca com IA para a mensagem: '{mensagem}'")
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
            logging.debug(f"[IA-MARCA] '{mensagem}' → IA disse: '{resposta}' → resultado: {resultado}")
            return resultado
        except Exception as e:
            logging.warning(f"[IA-MARCA] Erro na detecção para '{mensagem}': {e}")
            # Fallback: se IA falhar, assume que é marca se não for categoria óbvia
            palavras_categoria_obvias = ['cerveja', 'refrigerante', 'doce', 'bala', 'sabão', 'detergente']
            fallback_resultado = not any(cat in mensagem.lower() for cat in palavras_categoria_obvias)
            logging.debug(f"[IA-MARCA] Fallback para '{mensagem}': {fallback_resultado}")
            return fallback_resultado
    
    # Se contém categoria ou é marca detectada pela IA, usa busca inteligente
    if (any(keyword in message_lower for keyword in palavras_categoria) or
        _detectar_marca_com_ia(user_message)):
        return {
            "nome_ferramenta": "busca_inteligente_com_promocoes",
            "parametros": {"termo_busca": user_message}
        }
    
    # Saudações e conversas gerais
    saudacoes = ['oi', 'olá', 'boa', 'como', 'obrigado', 'tchau']
    if any(greeting in message_lower for greeting in saudacoes):
        return {
            "nome_ferramenta": "lidar_conversa",
            "parametros": {"texto_resposta": "Olá! Como posso te ajudar hoje?"}
        }
    
    # Default: busca por produto específico
    return {
        "nome_ferramenta": "obter_produtos_mais_vendidos_por_nome",
        "parametros": {"nome_produto": user_message}
    }

def limpar_cache_intencao():
    """
    Limpa o cache de intenções para liberar memória.
    
    Note:
        Deve ser chamada periodicamente para evitar acúmulo excessivo de cache.
    """
    global _cache_intencao
    _cache_intencao.clear()
    logging.info("[INTENT] Cache de intenções limpo")

def obter_estatisticas_intencao() -> Dict:
    """
    Retorna estatísticas do classificador de intenções.
    
    Returns:
        Dict: Estatísticas contendo tamanho do cache e intenções armazenadas.
        
    Example:
        >>> obter_estatisticas_intencao()
        {"tamanho_cache": 5, "intencoes_cache": ["oi", "cerveja", "carrinho"]}
    """
    logging.debug("Obtendo estatísticas do classificador de intenções.")
    return {
        "tamanho_cache": len(_cache_intencao),
        "intencoes_cache": list(_cache_intencao.keys())[:10]  # Mostra primeiras 10
    }
