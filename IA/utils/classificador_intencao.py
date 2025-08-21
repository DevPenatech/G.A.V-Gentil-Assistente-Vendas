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
                # 🚀 NOVO: Sistema de Confiança e Score de Decisão
                confidence_score = _confidence_system.analyze_intent_confidence(
                    intent_data, user_message, conversation_context
                )
                decision_strategy = _confidence_system.get_decision_strategy(confidence_score)
                
                # Adiciona dados de confiança ao resultado
                intent_data["confidence_score"] = confidence_score
                intent_data["decision_strategy"] = decision_strategy
                
                logging.info(f"[INTENT] Intenção: {intent_data['nome_ferramenta']}, "
                           f"Confiança: {confidence_score:.3f}, "
                           f"Estratégia: {decision_strategy}")
                
                # Cache apenas se não há contexto (primeira interação)
                if not conversation_context:
                    _cache_intencao[cache_key] = intent_data
                
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
    
    def _add_confidence_to_intent(intent_data: Dict) -> Dict:
        """Adiciona dados de confiança a qualquer intenção."""
        confidence_score = _confidence_system.analyze_intent_confidence(
            intent_data, user_message, conversation_context
        )
        decision_strategy = _confidence_system.get_decision_strategy(confidence_score)
        
        intent_data["confidence_score"] = confidence_score
        intent_data["decision_strategy"] = decision_strategy
        
        logging.debug(f"[FALLBACK] {intent_data['nome_ferramenta']}: confiança={confidence_score:.3f}, estratégia={decision_strategy}")
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
                "nome_ferramenta": "checkout",
                "parametros": {}
            })
        # TERCEIRO: Se não é finalizar pedido nem atualização, é seleção de produto da lista
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
    if any(word in message_lower for word in ['finalizar', 'checkout', 'concluir', 'fechar pedido', 'comprar']):
        return _add_confidence_to_intent({
            "nome_ferramenta": "checkout",
            "parametros": {"force_checkout": True}  # Força checkout independente do estado
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
    
    # Adiciona confiança ao fallback (geralmente menor)
    confidence_score = _confidence_system.analyze_intent_confidence(
        fallback_intent, user_message, conversation_context
    )
    decision_strategy = _confidence_system.get_decision_strategy(confidence_score)
    
    fallback_intent["confidence_score"] = confidence_score
    fallback_intent["decision_strategy"] = decision_strategy
    
    logging.info(f"[FALLBACK] Intenção: {fallback_intent['nome_ferramenta']}, "
               f"Confiança: {confidence_score:.3f}, "
               f"Estratégia: {decision_strategy}")
    
    return fallback_intent

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
        {"tamanho_cache": 5, "intencoes_cache": ["oi", "carrinho"]}
    """
    logging.debug("Obtendo estatísticas do classificador de intenções.")
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
            "checkout": 0.70,
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
        logging.debug(f"[CONFIDENCE] Analisando confiança para: {intent_data.get('nome_ferramenta', 'unknown')}")
        
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
        
        logging.debug(f"[CONFIDENCE] Fatores: {confidence_factors}")
        logging.debug(f"[CONFIDENCE] Score final: {confidence:.3f}")
        
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
        
        if "finalizar" in context.lower() or "checkout" in context.lower():
            if tool_name == "checkout":
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
            "handle_chitchat": ["response_text"],
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
            "checkout": ["finalizar", "checkout", "comprar", "fechar pedido"],
            "adicionar_item_ao_carrinho": [r'^\d+$'],  # Números isolados
            "show_more_products": ["mais", "continuar", "próximos"],
            "handle_chitchat": ["oi", "olá", "bom dia", "boa tarde", "obrigado"]
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
        logging.debug(f"[CONFIDENCE] Taxa de sucesso atualizada para {tool_name}: {new_rate:.3f}")


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
    logging.info(f"[CONFIDENCE] Feedback registrado para {tool_name}: {'sucesso' if success else 'falha'}")

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
