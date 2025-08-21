#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Controle de Fluxo Conversacional
Implementa validação avançada de respostas do usuário para melhorar coerência conversacional
Baseado nas melhorias críticas identificadas em 21/08/2025
"""

import logging
import re
import json
from typing import Dict, List, Optional, Tuple
from enum import Enum

class TipoValidacaoFluxo(Enum):
    """Tipos de validação de fluxo conversacional."""
    VALIDACAO_RANGE_NUMERICO = "validacao_range_numerico"
    ADERENCIA_CONTEXTO = "aderencia_contexto" 
    CORRESPONDENCIA_PERGUNTA_RESPOSTA = "correspondencia_pergunta_resposta"
    CONSISTENCIA_TOPICO = "consistencia_topico"
    VALIDADE_SELECAO = "validade_selecao"

class EstadoConversa(Enum):
    """Estados possíveis da conversa."""
    SAUDACAO = "saudacao"
    BUSCA_PRODUTO = "busca_produto"
    LISTAGEM_PRODUTOS = "listagem_produtos"
    GERENCIAMENTO_CARRINHO = "gerenciamento_carrinho"
    PROCESSO_CHECKOUT = "processo_checkout"
    SELECAO_QUANTIDADE = "selecao_quantidade"
    CONFIRMACAO_NECESSARIA = "confirmacao_necessaria"
    RECUPERACAO_ERRO = "recuperacao_erro"

class ControladorFluxoConversa:
    """
    Sistema de Controle de Fluxo Conversacional.
    
    Valida se respostas do usuário estão adequadas ao contexto esperado,
    detecta incoerências e fornece redirecionamento inteligente.
    """
    
    def __init__(self):
        self._padroes_validacao = self._carregar_padroes_validacao()
        self._stats_fluxo = {
            "validacoes_realizadas": 0,
            "respostas_incoerentes_detectadas": 0,
            "redirecionamentos_aplicados": 0,
            "incompatibilidades_contexto": 0,
            "selecoes_invalidas": 0
        }
        
    def validar_resposta_usuario(self, entrada_usuario: str, contexto_esperado: str, 
                                historico_conversa: List[Dict] = None) -> Dict:
        """
        Valida se resposta do usuário está adequada ao contexto esperado.
        
        Args:
            entrada_usuario: Mensagem do usuário
            contexto_esperado: Contexto esperado da conversa
            historico_conversa: Histórico da conversa para análise adicional
            
        Returns:
            Dict: Resultado da validação com ações recomendadas
        """
        self._stats_fluxo["validacoes_realizadas"] += 1
        
        logging.debug(f"[FLUXO] Validando resposta: '{entrada_usuario}' no contexto: '{contexto_esperado[:100]}...'")
        
        # 1. Extrai estado atual da conversa
        estado_atual = self._extrair_estado_conversa(contexto_esperado)
        
        # 2. Executa validações por prioridade
        validacoes = {
            TipoValidacaoFluxo.VALIDACAO_RANGE_NUMERICO: self._verificar_range_numerico(entrada_usuario, contexto_esperado),
            TipoValidacaoFluxo.ADERENCIA_CONTEXTO: self._verificar_aderencia_contexto(entrada_usuario, contexto_esperado),
            TipoValidacaoFluxo.CORRESPONDENCIA_PERGUNTA_RESPOSTA: self._verificar_correspondencia_pergunta_resposta(entrada_usuario, contexto_esperado),
            TipoValidacaoFluxo.CONSISTENCIA_TOPICO: self._verificar_consistencia_topico(entrada_usuario, contexto_esperado),
            TipoValidacaoFluxo.VALIDADE_SELECAO: self._verificar_validade_selecao(entrada_usuario, contexto_esperado)
        }
        
        # 3. Analisa resultados e gera estratégia de ação
        orientacao_fluxo = self._gerar_orientacao_fluxo(validacoes, estado_atual, entrada_usuario)
        
        # 4. Atualiza estatísticas
        if not orientacao_fluxo["eh_coerente"]:
            self._stats_fluxo["respostas_incoerentes_detectadas"] += 1
            if orientacao_fluxo["acao"] == "redirecionar":
                self._stats_fluxo["redirecionamentos_aplicados"] += 1
        
        logging.info(f"[FLUXO] Validação: coerente={orientacao_fluxo['eh_coerente']}, "
                    f"ação={orientacao_fluxo['acao']}, confiança={orientacao_fluxo['confianca']}")
        
        return orientacao_fluxo
    
    def _extrair_estado_conversa(self, contexto: str) -> EstadoConversa:
        """Extrai o estado atual da conversa baseado em análise semântica do contexto."""
        contexto_lower = contexto.lower()
        
        # NOVA LÓGICA: Análise mais precisa baseada em evidências reais
        if "finalizar_pedido" in contexto_lower or "finalizar pedido" in contexto_lower:
            return EstadoConversa.PROCESSO_CHECKOUT
        elif "quantas unidades" in contexto_lower and "produto" in contexto_lower:
            return EstadoConversa.SELECAO_QUANTIDADE
        elif re.search(r'\d+\.\s+[^\n]+', contexto) and "escolha" in contexto_lower:
            # SÓ é LISTAGEM se há evidência REAL de lista numerada + comando de escolha
            return EstadoConversa.LISTAGEM_PRODUTOS
        elif "carrinho" in contexto_lower and ("itens" in contexto_lower or "produto" in contexto_lower):
            return EstadoConversa.GERENCIAMENTO_CARRINHO
        elif "confirmar" in contexto_lower and "pedido" in contexto_lower:
            return EstadoConversa.CONFIRMACAO_NECESSARIA
        elif "erro" in contexto_lower or "tente novamente" in contexto_lower:
            return EstadoConversa.RECUPERACAO_ERRO
        elif "bem-vindo" in contexto_lower or "como posso ajudar" in contexto_lower:
            return EstadoConversa.SAUDACAO
        else:
            # PADRÃO: Se não há evidências claras de estados específicos, assume busca livre
            return EstadoConversa.BUSCA_PRODUTO
    
    def _verificar_range_numerico(self, entrada_usuario: str, contexto: str) -> Dict:
        """
        Valida se números fornecidos estão dentro do range válido usando análise semântica.
        """
        resultado = {"valido": True, "confianca": 1.0, "problemas": []}
        
        # Extrai números da entrada do usuário
        numeros = re.findall(r'\b\d+\b', entrada_usuario.strip())
        contexto_lower = contexto.lower()
        
        if not numeros:
            # VERIFICA SE HÁ EVIDÊNCIA REAL de lista numerada no contexto
            tem_lista_numerada = bool(re.search(r'\d+\.\s+[^\n]+', contexto))
            tem_comando_selecao = "escolha um número" in contexto_lower
            
            # SÓ marca como inválido se há CLARA evidência de lista + comando de seleção
            if tem_lista_numerada and tem_comando_selecao:
                resultado = {
                    "valido": False,
                    "confianca": 0.9,
                    "problemas": ["Número esperado mas não fornecido"],
                    "acao_sugerida": "pedir_numero"
                }
            # IGNORA completamente se é saudação ou conversa geral
            elif "bem-vindo" in contexto_lower or "como posso ajudar" in contexto_lower:
                resultado = {"valido": True, "confianca": 1.0, "problemas": []}  # Sempre válido para conversa geral
            
            return resultado
        
        # Se há números, valida range baseado no contexto
        numero_usuario = int(numeros[0])
        
        # Busca por range válido no contexto
        opcao_maxima = self._extrair_opcao_maxima_do_contexto(contexto)
        
        if opcao_maxima and numero_usuario > opcao_maxima:
            resultado = {
                "valido": False,
                "confianca": 0.95,
                "problemas": [f"Número {numero_usuario} fora do range válido (1-{opcao_maxima})"],
                "acao_sugerida": "corrigir_range",
                "range_valido": f"1-{opcao_maxima}"
            }
            self._stats_fluxo["selecoes_invalidas"] += 1
        elif numero_usuario < 1:
            resultado = {
                "valido": False,
                "confianca": 0.95,
                "problemas": [f"Número {numero_usuario} inválido (deve ser positivo)"],
                "acao_sugerida": "corrigir_positivo"
            }
            self._stats_fluxo["selecoes_invalidas"] += 1
        
        return resultado
    
    def _extrair_opcao_maxima_do_contexto(self, contexto: str) -> Optional[int]:
        """Extrai o número máximo de opções disponíveis no contexto."""
        # Procura por padrões como "1. produto", "2. produto", etc.
        itens_numerados = re.findall(r'^(\d+)\.', contexto, re.MULTILINE)
        if itens_numerados:
            return max(int(num) for num in itens_numerados)
        
        # Procura por padrões como "(1-5)" ou "de 1 a 5"
        padroes_range = re.findall(r'(?:de\s+)?(\d+)(?:\s*-\s*|\s+a\s+)(\d+)', contexto.lower())
        if padroes_range:
            return max(int(fim) for inicio, fim in padroes_range)
        
        # Procura por frases como "5 produtos encontrados"
        padroes_contagem = re.findall(r'(\d+)\s+produtos?\s+encontrados?', contexto.lower())
        if padroes_contagem:
            return int(padroes_contagem[0])
        
        return None
    
    def _verificar_aderencia_contexto(self, entrada_usuario: str, contexto: str) -> Dict:
        """
        Verifica se resposta adere ao contexto atual da conversa.
        """
        usuario_lower = entrada_usuario.lower().strip()
        contexto_lower = contexto.lower()
        
        # Padrões de aderência por tipo de contexto
        padroes_aderencia = {
            "listagem_produtos": {
                "esperado": [r'^\d+$', 'mais', 'continuar', 'próximo', 'carrinho'],
                "inesperado": ['oi', 'olá', 'bom dia', 'obrigado', 'tchau']
            },
            "selecao_quantidade": {
                "esperado": [r'^\d+$', r'\d+\s*unidades?', r'\d+\s*un'],
                "inesperado": ['carrinho', 'produtos', 'buscar', 'olá']
            },
            "finalizar_pedido": {
                "esperado": ['sim', 'não', 'confirmar', 'finalizar', 'cancelar'],
                "inesperado": ['produtos', 'buscar', 'cerveja', 'adicionar']
            }
        }
        
        # Determina tipo de contexto
        tipo_contexto = "geral"
        if any(frase in contexto_lower for frase in ["produtos encontrados", "escolha um número"]):
            tipo_contexto = "listagem_produtos"
        elif any(frase in contexto_lower for frase in ["quantas unidades", "quantidade"]):
            tipo_contexto = "selecao_quantidade"
        elif any(frase in contexto_lower for frase in ["finalizar", "finalizar_pedido", "confirmar"]):
            tipo_contexto = "finalizar_pedido"
        
        resultado = {"valido": True, "confianca": 0.8, "problemas": []}
        
        if tipo_contexto in padroes_aderencia:
            padroes = padroes_aderencia[tipo_contexto]
            
            # Verifica se resposta é esperada
            eh_esperado = any(re.search(padrao, usuario_lower) for padrao in padroes["esperado"])
            
            # Verifica se resposta é inesperada
            eh_inesperado = any(palavra_chave in usuario_lower for palavra_chave in padroes["inesperado"])
            
            if eh_inesperado and not eh_esperado:
                resultado = {
                    "valido": False,
                    "confianca": 0.85,
                    "problemas": [f"Resposta '{entrada_usuario}' não adequada ao contexto de {tipo_contexto}"],
                    "acao_sugerida": "redirecionar_para_contexto",
                    "tipo_contexto": tipo_contexto
                }
                self._stats_fluxo["incompatibilidades_contexto"] += 1
        
        return resultado
    
    def _verificar_correspondencia_pergunta_resposta(self, entrada_usuario: str, contexto: str) -> Dict:
        """
        Verifica se resposta corresponde à pergunta feita.
        """
        resultado = {"valido": True, "confianca": 0.8, "problemas": []}
        
        # Detecta perguntas específicas no contexto
        padroes_pergunta = {
            "quantidade": [
                "quantas unidades", "qual quantidade", "quantos você quer",
                "digite a quantidade", "número de unidades"
            ],
            "selecao": [
                "escolha um número", "selecione", "digite o número",
                "qual produto", "qual opção"
            ],
            "confirmacao": [
                "confirma", "tem certeza", "deseja continuar",
                "finalizar pedido", "confirmar compra"
            ]
        }
        
        contexto_lower = contexto.lower()
        usuario_lower = entrada_usuario.lower().strip()
        
        for tipo_pergunta, padroes in padroes_pergunta.items():
            if any(padrao in contexto_lower for padrao in padroes):
                
                if tipo_pergunta == "quantidade":
                    # Espera número ou quantidade
                    if not re.search(r'\d+', entrada_usuario) and 'carrinho' in usuario_lower:
                        resultado = {
                            "valido": False,
                            "confianca": 0.9,
                            "problemas": ["Pergunta sobre quantidade mas resposta fala de carrinho"],
                            "acao_sugerida": "esclarecer_quantidade",
                            "tipo_resposta_esperada": "numero"
                        }
                
                elif tipo_pergunta == "selecao":
                    # Espera número para seleção
                    if not re.match(r'^\d+$', entrada_usuario.strip()) and 'carrinho' in usuario_lower:
                        resultado = {
                            "valido": False,
                            "confianca": 0.85,
                            "problemas": ["Pergunta sobre seleção mas resposta desvia o assunto"],
                            "acao_sugerida": "esclarecer_selecao",
                            "tipo_resposta_esperada": "numero_selecao"
                        }
                
                elif tipo_pergunta == "confirmacao":
                    # Espera sim/não ou confirmação
                    if not any(palavra in usuario_lower for palavra in ['sim', 'não', 'ok', 'confirma', 'finalizar', 'cancelar']):
                        if any(palavra in usuario_lower for palavra in ['produto', 'buscar', 'carrinho', 'adicionar']):
                            resultado = {
                                "valido": False,
                                "confianca": 0.8,
                                "problemas": ["Pergunta sobre confirmação mas resposta muda de assunto"],
                                "acao_sugerida": "esclarecer_confirmacao",
                                "tipo_resposta_esperada": "sim_nao"
                            }
                
                break  # Para no primeiro padrão encontrado
        
        return resultado
    
    def _verificar_consistencia_topico(self, entrada_usuario: str, contexto: str) -> Dict:
        """
        Verifica consistência do tópico da conversa.
        """
        resultado = {"valido": True, "confianca": 0.75, "problemas": []}
        
        usuario_lower = entrada_usuario.lower()
        contexto_lower = contexto.lower()
        
        # Define tópicos principais
        topicos_atuais = self._extrair_topicos_do_contexto(contexto_lower)
        topicos_usuario = self._extrair_topicos_da_entrada(usuario_lower)
        
        # Se não há tópicos em comum e o usuário mudou completamente de assunto
        if topicos_atuais and topicos_usuario:
            tem_sobreposicao = bool(set(topicos_atuais) & set(topicos_usuario))
            
            # Exceções: saudações sempre resetam conversa (válido)
            eh_saudacao = any(saudacao in usuario_lower for saudacao in ['oi', 'olá', 'bom dia', 'boa tarde', 'eai'])
            
            # Exceções: comandos diretos são válidos independente do contexto
            eh_comando_direto = any(cmd in usuario_lower for cmd in ['carrinho', 'finalizar', 'limpar', 'cancelar'])
            
            if not tem_sobreposicao and not eh_saudacao and not eh_comando_direto:
                # Detecta mudança abrupta de assunto
                if len(entrada_usuario.strip()) > 10:  # Respostas substantivas
                    resultado = {
                        "valido": False,
                        "confianca": 0.7,
                        "problemas": [f"Mudança abrupta de tópico: contexto sobre {topicos_atuais}, usuário fala de {topicos_usuario}"],
                        "acao_sugerida": "reconhecer_mudanca_topico",
                        "topicos_atuais": topicos_atuais,
                        "topicos_usuario": topicos_usuario
                    }
        
        return resultado
    
    def _extrair_topicos_do_contexto(self, contexto: str) -> List[str]:
        """Extrai tópicos principais do contexto."""
        topicos = []
        
        palavras_chave_topicos = {
            "produtos": ["produto", "item", "cerveja", "refrigerante", "limpeza"],
            "carrinho": ["carrinho", "itens", "pedido"],
            "finalizar_pedido": ["finalizar", "finalizar_pedido", "pagamento"],
            "busca": ["busca", "procurar", "encontrar"],
            "quantidade": ["quantidade", "unidades", "quantos"]
        }
        
        for topico, palavras_chave in palavras_chave_topicos.items():
            if any(palavra_chave in contexto for palavra_chave in palavras_chave):
                topicos.append(topico)
        
        return topicos
    
    def _extrair_topicos_da_entrada(self, entrada_usuario: str) -> List[str]:
        """Extrai tópicos da entrada do usuário."""
        topicos = []
        
        palavras_chave_topicos = {
            "produtos": ["cerveja", "refrigerante", "produto", "biscoito", "doce", "limpeza"],
            "carrinho": ["carrinho", "meu carrinho", "pedido"],
            "finalizar_pedido": ["finalizar", "comprar", "fechar"],
            "busca": ["quero", "procuro", "busco"],
            "saudacao": ["oi", "olá", "bom dia", "boa tarde"]
        }
        
        for topico, palavras_chave in palavras_chave_topicos.items():
            if any(palavra_chave in entrada_usuario for palavra_chave in palavras_chave):
                topicos.append(topico)
        
        return topicos
    
    def _verificar_validade_selecao(self, entrada_usuario: str, contexto: str) -> Dict:
        """
        Verifica validade de seleções numéricas em listas.
        """
        resultado = {"valido": True, "confianca": 0.9, "problemas": []}
        
        # Se entrada é um número e contexto mostra uma lista
        if re.match(r'^\d+$', entrada_usuario.strip()):
            numero_usuario = int(entrada_usuario.strip())
            
            # Verifica se contexto mostra lista numerada
            if "produtos encontrados" in contexto.lower() or "escolha um número" in contexto.lower():
                opcao_maxima = self._extrair_opcao_maxima_do_contexto(contexto)
                
                if opcao_maxima and numero_usuario > opcao_maxima:
                    resultado = {
                        "valido": False,
                        "confianca": 0.95,
                        "problemas": [f"Seleção {numero_usuario} inválida. Opções disponíveis: 1-{opcao_maxima}"],
                        "acao_sugerida": "mostrar_opcoes_validas",
                        "opcao_maxima": opcao_maxima,
                        "selecao_usuario": numero_usuario
                    }
                elif numero_usuario < 1:
                    resultado = {
                        "valido": False,
                        "confianca": 0.95,
                        "problemas": [f"Seleção {numero_usuario} inválida. Use números positivos."],
                        "acao_sugerida": "solicitar_numero_positivo"
                    }
        
        return resultado
    
    def _gerar_orientacao_fluxo(self, validacoes: Dict, estado_atual: EstadoConversa, 
                               entrada_usuario: str) -> Dict:
        """
        Gera orientação de fluxo baseada nos resultados das validações.
        """
        # Conta quantas validações falharam
        validacoes_falharam = [v for v in validacoes.values() if not v["valido"]]
        confianca_total = sum(v["confianca"] for v in validacoes.values()) / len(validacoes)
        
        # Determina se resposta é coerente
        eh_coerente = len(validacoes_falharam) == 0
        
        # Se há falhas, determina ação prioritária
        acao = "prosseguir"  # Padrão: continuar normalmente
        mensagem_orientacao = ""
        problema_prioritario = None
        
        if validacoes_falharam:
            # Prioriza por tipo de problema (ordem de criticidade)
            ordem_prioridade = [
                TipoValidacaoFluxo.VALIDACAO_RANGE_NUMERICO,
                TipoValidacaoFluxo.VALIDADE_SELECAO,
                TipoValidacaoFluxo.CORRESPONDENCIA_PERGUNTA_RESPOSTA,
                TipoValidacaoFluxo.ADERENCIA_CONTEXTO,
                TipoValidacaoFluxo.CONSISTENCIA_TOPICO
            ]
            
            for tipo_validacao in ordem_prioridade:
                if tipo_validacao in validacoes and not validacoes[tipo_validacao]["valido"]:
                    problema_prioritario = validacoes[tipo_validacao]
                    break
            
            # Define ação baseada no problema prioritário
            if problema_prioritario:
                acao_sugerida = problema_prioritario.get("acao_sugerida", "esclarecer")
                
                if acao_sugerida in ["corrigir_range", "mostrar_opcoes_validas"]:
                    acao = "corrigir_selecao"
                    opcao_maxima = problema_prioritario.get("opcao_maxima") or problema_prioritario.get("range_valido", "válido")
                    mensagem_orientacao = f"Por favor, escolha um número entre as opções disponíveis (1-{opcao_maxima})."
                
                elif acao_sugerida in ["pedir_numero", "esclarecer_quantidade"]:
                    acao = "esclarecer_entrada"
                    mensagem_orientacao = "Por favor, me informe um número para continuar."
                
                elif acao_sugerida == "esclarecer_selecao":
                    acao = "esclarecer_entrada"
                    mensagem_orientacao = "Por favor, escolha uma das opções numeradas da lista acima."
                
                elif acao_sugerida == "esclarecer_confirmacao":
                    acao = "esclarecer_entrada"
                    mensagem_orientacao = "Preciso de uma confirmação: responda 'sim' ou 'não'."
                
                elif acao_sugerida == "redirecionar_para_contexto":
                    acao = "redirecionar"
                    tipo_contexto = problema_prioritario.get("tipo_contexto", "atual")
                    mensagem_orientacao = f"Vamos focar no {tipo_contexto}. "
                
                elif acao_sugerida == "reconhecer_mudanca_topico":
                    acao = "reconhecer_mudanca"
                    mensagem_orientacao = "Entendi que você quer mudar de assunto. "
                
                else:
                    acao = "esclarecer_entrada"
                    mensagem_orientacao = "Não entendi sua resposta. Pode reformular?"
        
        return {
            "eh_coerente": eh_coerente,
            "confianca": confianca_total,
            "acao": acao,
            "mensagem_orientacao": mensagem_orientacao,
            "validacoes_falharam": len(validacoes_falharam),
            "detalhes_validacao": validacoes,
            "problema_prioritario": problema_prioritario,
            "estado_atual": estado_atual.value,
            "analise_entrada_usuario": {
                "tamanho": len(entrada_usuario),
                "contem_numeros": bool(re.search(r'\d+', entrada_usuario)),
                "eh_palavra_unica": len(entrada_usuario.split()) == 1,
                "eh_saudacao": any(s in entrada_usuario.lower() for s in ['oi', 'olá', 'bom dia'])
            }
        }
    
    def obter_sugestoes_estado_conversa(self, estado_atual: EstadoConversa) -> Dict:
        """
        Retorna sugestões específicas para cada estado da conversa.
        """
        sugestoes = {
            EstadoConversa.SAUDACAO: {
                "respostas_esperadas": ["saudação de volta", "pedido de produto", "pergunta sobre serviços"],
                "orientacao": "Seja bem-vindo! Como posso ajudar você hoje?"
            },
            EstadoConversa.BUSCA_PRODUTO: {
                "respostas_esperadas": ["nome de produto", "categoria", "marca específica"],
                "orientacao": "Me diga que tipo de produto você está procurando."
            },
            EstadoConversa.LISTAGEM_PRODUTOS: {
                "respostas_esperadas": ["número da lista", "mais produtos", "carrinho"],
                "orientacao": "Escolha um número da lista ou digite 'mais' para ver mais produtos."
            },
            EstadoConversa.GERENCIAMENTO_CARRINHO: {
                "respostas_esperadas": ["adicionar", "remover", "quantidade", "finalizar"],
                "orientacao": "Você pode adicionar/remover itens ou finalizar o pedido."
            },
            EstadoConversa.SELECAO_QUANTIDADE: {
                "respostas_esperadas": ["número", "quantidade específica"],
                "orientacao": "Digite a quantidade desejada (apenas números)."
            },
            EstadoConversa.PROCESSO_CHECKOUT: {
                "respostas_esperadas": ["confirmar", "cancelar", "sim", "não"],
                "orientacao": "Confirme se deseja finalizar o pedido."
            },
            EstadoConversa.CONFIRMACAO_NECESSARIA: {
                "respostas_esperadas": ["sim", "não", "ok", "cancelar"],
                "orientacao": "Responda 'sim' ou 'não' para continuar."
            },
            EstadoConversa.RECUPERACAO_ERRO: {
                "respostas_esperadas": ["tentar novamente", "voltar", "cancelar"],
                "orientacao": "Vamos tentar de novo. O que você gostaria de fazer?"
            }
        }
        
        return sugestoes.get(estado_atual, {
            "respostas_esperadas": ["resposta relevante ao contexto"],
            "orientacao": "Como posso ajudar você?"
        })
    
    def detectar_confusao_usuario(self, historico_conversa: List[Dict], entrada_atual: str) -> Dict:
        """
        Detecta quando usuário está confuso ou fora do fluxo.
        """
        indicadores_confusao = {
            "resposta_fora_topico": self._detectar_mudanca_topico(entrada_atual, historico_conversa),
            "selecao_invalida": self._detectar_escolha_invalida(entrada_atual, historico_conversa),
            "pergunta_ignorada": self._detectar_pergunta_ignorada(entrada_atual, historico_conversa),
            "comportamento_repetitivo": self._detectar_padroes_repetitivos(historico_conversa)
        }
        
        pontuacao_confusao = sum(1 for indicador in indicadores_confusao.values() if indicador)
        esta_confuso = pontuacao_confusao >= 2
        
        estrategia_redirecionamento = self._gerar_estrategia_redirecionamento(indicadores_confusao) if esta_confuso else None
        
        return {
            "esta_confuso": esta_confuso,
            "pontuacao_confusao": pontuacao_confusao,
            "indicadores": indicadores_confusao,
            "estrategia_redirecionamento": estrategia_redirecionamento
        }
    
    def _detectar_mudanca_topico(self, entrada_atual: str, historico_conversa: List[Dict]) -> bool:
        """Detecta mudança abrupta de tópico."""
        if not historico_conversa or len(historico_conversa) < 2:
            return False
        
        # Última mensagem do bot
        ultima_mensagem_bot = ""
        for mensagem in reversed(historico_conversa):
            if mensagem.get("role") == "assistant":
                ultima_mensagem_bot = mensagem.get("content", "")
                break
        
        if not ultima_mensagem_bot:
            return False
        
        # Verifica se há mudança dramática de contexto
        topicos_ultimos = self._extrair_topicos_do_contexto(ultima_mensagem_bot.lower())
        topicos_atuais = self._extrair_topicos_da_entrada(entrada_atual.lower())
        
        # Se não há overlap e não é saudação/comando direto
        tem_sobreposicao = bool(set(topicos_ultimos) & set(topicos_atuais))
        eh_saudacao = any(s in entrada_atual.lower() for s in ['oi', 'olá', 'bom dia'])
        eh_comando = any(c in entrada_atual.lower() for c in ['carrinho', 'finalizar', 'limpar'])
        
        return not tem_sobreposicao and not eh_saudacao and not eh_comando
    
    def _detectar_escolha_invalida(self, entrada_atual: str, historico_conversa: List[Dict]) -> bool:
        """Detecta escolhas inválidas baseadas no histórico."""
        if not re.match(r'^\d+$', entrada_atual.strip()):
            return False
        
        # Procura última lista apresentada
        for mensagem in reversed(historico_conversa):
            if mensagem.get("role") == "assistant":
                conteudo = mensagem.get("content", "")
                opcao_maxima = self._extrair_opcao_maxima_do_contexto(conteudo)
                if opcao_maxima:
                    escolha_usuario = int(entrada_atual.strip())
                    return escolha_usuario > opcao_maxima or escolha_usuario < 1
        
        return False
    
    def _detectar_pergunta_ignorada(self, entrada_atual: str, historico_conversa: List[Dict]) -> bool:
        """Detecta quando usuário ignora pergunta direta."""
        if not historico_conversa:
            return False
        
        # Última mensagem do bot
        ultima_mensagem_bot = ""
        for mensagem in reversed(historico_conversa):
            if mensagem.get("role") == "assistant":
                ultima_mensagem_bot = mensagem.get("content", "")
                break
        
        if not ultima_mensagem_bot:
            return False
        
        # Verifica se bot fez pergunta direta e usuário não respondeu adequadamente
        indicadores_pergunta = ["?", "quantas", "qual", "digite", "escolha", "confirma"]
        tem_pergunta = any(indicador in ultima_mensagem_bot.lower() for indicador in indicadores_pergunta)
        
        if tem_pergunta:
            # Verifica se resposta é adequada
            atual_lower = entrada_atual.lower()
            
            # Se pergunta sobre quantidade e resposta não tem número nem menciona quantidade
            if "quantas" in ultima_mensagem_bot.lower() or "quantidade" in ultima_mensagem_bot.lower():
                return not re.search(r'\d+', entrada_atual) and "quantidade" not in atual_lower
            
            # Se pergunta escolha e resposta não é número nem relacionada
            if "escolha" in ultima_mensagem_bot.lower() or "digite o número" in ultima_mensagem_bot.lower():
                return not re.match(r'^\d+$', entrada_atual.strip()) and atual_lower in ['carrinho', 'produtos', 'buscar']
        
        return False
    
    def _detectar_padroes_repetitivos(self, historico_conversa: List[Dict]) -> bool:
        """Detecta padrões repetitivos que indicam confusão."""
        if len(historico_conversa) < 6:  # Precisa de histórico suficiente
            return False
        
        # Analisa últimas 6 mensagens do usuário
        mensagens_usuario = [msg.get("content", "").lower().strip() 
                            for msg in historico_conversa[-6:] 
                            if msg.get("role") == "user"]
        
        if len(mensagens_usuario) < 3:
            return False
        
        # Detecta repetições exatas
        mensagens_unicas = set(mensagens_usuario)
        taxa_repeticao = 1 - (len(mensagens_unicas) / len(mensagens_usuario))
        
        return taxa_repeticao > 0.5  # Mais de 50% das mensagens são repetições
    
    def _gerar_estrategia_redirecionamento(self, indicadores_confusao: Dict) -> Dict:
        """
        Gera estratégia de redirecionamento baseada nos indicadores de confusão.
        """
        estrategias = []
        
        if indicadores_confusao["resposta_fora_topico"]:
            estrategias.append({
                "tipo": "refoco_topico",
                "mensagem": "Vamos focar no que você estava procurando. ",
                "acao": "retornar_ultimo_contexto"
            })
        
        if indicadores_confusao["selecao_invalida"]:
            estrategias.append({
                "tipo": "ajuda_selecao",
                "mensagem": "Use apenas os números da lista apresentada. ",
                "acao": "mostrar_opcoes_validas"
            })
        
        if indicadores_confusao["pergunta_ignorada"]:
            estrategias.append({
                "tipo": "esclarecimento_pergunta",
                "mensagem": "Preciso de uma resposta específica para continuar. ",
                "acao": "repetir_pergunta_simplificada"
            })
        
        if indicadores_confusao["comportamento_repetitivo"]:
            estrategias.append({
                "tipo": "reinicio_conversa",
                "mensagem": "Vamos começar de novo para eu entender melhor. ",
                "acao": "resetar_fluxo_conversa"
            })
        
        # Retorna estratégia prioritária (primeira da lista)
        if estrategias:
            return estrategias[0]
        
        return {
            "tipo": "ajuda_geral",
            "mensagem": "Como posso ajudar você melhor? ",
            "acao": "oferecer_menu_ajuda"
        }
    
    def obter_estatisticas_fluxo(self) -> Dict:
        """Retorna estatísticas do sistema de controle de fluxo."""
        return self._stats_fluxo.copy()
    
    def resetar_estatisticas(self):
        """Reseta estatísticas do sistema."""
        for chave in self._stats_fluxo:
            self._stats_fluxo[chave] = 0
    
    def _carregar_padroes_validacao(self) -> Dict:
        """Carrega padrões de validação específicos."""
        return {
            "numeros_selecao_produto": r'^\d+$',
            "expressoes_quantidade": r'\d+\s*(un|unidades?|peças?)?$',
            "respostas_sim_nao": r'^(sim|não|ok|beleza|confirmo|cancelar)$',
            "padroes_saudacao": r'^(oi|olá|bom\s+dia|boa\s+tarde|boa\s+noite|eai).*',
            "comandos_carrinho": r'.*(carrinho|pedido|finalizar|limpar|esvaziar).*',
            "padroes_busca": r'.*(quero|procuro|busco|preciso|gostaria).*'
        }


# Instância global do controlador de fluxo
_controlador_fluxo = ControladorFluxoConversa()

def obter_controlador_fluxo() -> ControladorFluxoConversa:
    """
    Retorna a instância global do controlador de fluxo conversacional.
    
    Returns:
        ControladorFluxoConversa: Controlador configurado
    """
    return _controlador_fluxo

def validar_fluxo_conversa(entrada_usuario: str, contexto_esperado: str, 
                          historico_conversa: List[Dict] = None) -> Dict:
    """
    Função utilitária para validar fluxo conversacional.
    
    Args:
        entrada_usuario: Mensagem do usuário
        contexto_esperado: Contexto esperado
        historico_conversa: Histórico da conversa
        
    Returns:
        Dict: Resultado da validação com orientações
    """
    return _controlador_fluxo.validar_resposta_usuario(entrada_usuario, contexto_esperado, historico_conversa)

def detectar_confusao_conversa(historico_conversa: List[Dict], entrada_atual: str) -> Dict:
    """
    Função utilitária para detectar confusão do usuário.
    
    Args:
        historico_conversa: Histórico da conversa
        entrada_atual: Entrada atual do usuário
        
    Returns:
        Dict: Análise de confusão com estratégias de redirecionamento
    """
    return _controlador_fluxo.detectar_confusao_usuario(historico_conversa, entrada_atual)

def obter_estatisticas_fluxo() -> Dict:
    """
    Retorna estatísticas do sistema de controle de fluxo.
    
    Returns:
        Dict: Estatísticas de validação e redirecionamento
    """
    return _controlador_fluxo.obter_estatisticas_fluxo()