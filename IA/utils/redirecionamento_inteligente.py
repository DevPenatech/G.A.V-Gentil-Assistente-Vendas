#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Redirecionamento Inteligente
Detecta usuários confusos ou perdidos e fornece orientação contextual
Baseado nas melhorias críticas identificadas em 21/08/2025
"""

import logging
import re
import json
from typing import Dict, List, Optional, Tuple
from enum import Enum

class TipoConfusao(Enum):
    """Tipos de confusão do usuário detectados."""
    IGNORAR_OPCOES = "ignorar_opcoes"
    MUDANCA_ASSUNTO_ABRUPTA = "mudanca_assunto_abrupta"
    RESPOSTA_INADEQUADA = "resposta_inadequada"
    COMPORTAMENTO_REPETITIVO = "comportamento_repetitivo"
    SELECAO_INVALIDA = "selecao_invalida"
    FALTA_GUIDANCE = "falta_guidance"

class EstrategiaRedirecionamento(Enum):
    """Estratégias de redirecionamento disponíveis."""
    SIMPLIFICAR_OPCOES = "simplificar_opcoes"
    REPETIR_PERGUNTA = "repetir_pergunta"
    OFERECER_AJUDA = "oferecer_ajuda"
    RESETAR_CONTEXTO = "resetar_contexto"
    GUIAR_PASSO_PASSO = "guiar_passo_passo"
    MENU_PRINCIPAL = "menu_principal"

class RedirecionadorInteligente:
    """
    Sistema de Redirecionamento Inteligente.
    
    Detecta quando usuários estão confusos ou perdidos e fornece 
    guidance apropriada para retomar o fluxo conversacional.
    """
    
    def __init__(self):
        self._padroes_confusao = self._carregar_padroes_confusao()
        self._estrategias_resposta = self._carregar_estrategias_resposta()
        self._historico_guidance = []
        self._stats_redirecionamento = {
            "confusoes_detectadas": 0,
            "redirecionamentos_aplicados": 0,
            "sucessos_redirecionamento": 0,
            "usuarios_perdidos_recuperados": 0,
            "tipos_confusao_detectados": {}
        }
        
    def detectar_confusao_usuario(self, entrada_atual: str, contexto_conversa: str,
                                 historico_conversa: List[Dict] = None) -> Dict:
        """
        Detecta confusão do usuário e determina estratégia de redirecionamento.
        
        Args:
            entrada_atual: Mensagem atual do usuário
            contexto_conversa: Contexto atual da conversa
            historico_conversa: Histórico completo da conversa
            
        Returns:
            Dict: Análise de confusão com estratégia de redirecionamento
        """
        logging.debug(f"[REDIRECT] Analisando confusão para: '{entrada_atual}' no contexto: '{contexto_conversa[:50]}...'")
        
        # 1. Detecta tipos de confusão
        confusoes_detectadas = self._analisar_tipos_confusao(
            entrada_atual, contexto_conversa, historico_conversa
        )
        
        # 2. Calcula nível de confusão
        nivel_confusao = self._calcular_nivel_confusao(confusoes_detectadas, historico_conversa)
        
        # 3. Determina se necessita redirecionamento
        necessita_redirecionamento = nivel_confusao >= 0.6
        
        # 4. Gera estratégia de redirecionamento se necessário
        estrategia = None
        if necessita_redirecionamento:
            estrategia = self._gerar_estrategia_redirecionamento(
                confusoes_detectadas, contexto_conversa, historico_conversa
            )
            self._stats_redirecionamento["redirecionamentos_aplicados"] += 1
        
        # 5. Atualiza estatísticas
        if confusoes_detectadas:
            self._stats_redirecionamento["confusoes_detectadas"] += 1
            for confusao in confusoes_detectadas:
                tipo = confusao["tipo"]
                if tipo not in self._stats_redirecionamento["tipos_confusao_detectados"]:
                    self._stats_redirecionamento["tipos_confusao_detectados"][tipo] = 0
                self._stats_redirecionamento["tipos_confusao_detectados"][tipo] += 1
        
        resultado = {
            "esta_confuso": necessita_redirecionamento,
            "nivel_confusao": nivel_confusao,
            "confusoes_detectadas": confusoes_detectadas,
            "estrategia_redirecionamento": estrategia,
            "historico_guidance": self._historico_guidance[-3:],  # Últimas 3 orientações
            "recomendacoes": self._gerar_recomendacoes_contextuais(contexto_conversa)
        }
        
        logging.info(f"[REDIRECT] Confusão detectada: {necessita_redirecionamento}, "
                    f"nível: {nivel_confusao:.2f}, estratégia: {estrategia['tipo'] if estrategia else 'nenhuma'}")
        
        return resultado
    
    def _analisar_tipos_confusao(self, entrada_atual: str, contexto_conversa: str,
                                historico_conversa: List[Dict]) -> List[Dict]:
        """
        Analisa diferentes tipos de confusão do usuário.
        """
        confusoes = []
        entrada_lower = entrada_atual.lower().strip()
        contexto_lower = contexto_conversa.lower()
        
        # 1. Detecta ignorar opções apresentadas
        if self._detectar_ignorar_opcoes(entrada_atual, contexto_conversa):
            confusoes.append({
                "tipo": TipoConfusao.IGNORAR_OPCOES.value,
                "descricao": "Usuário ignora opções numeradas apresentadas",
                "confianca": 0.9,
                "evidencia": f"Contexto mostra opções mas usuário respondeu: '{entrada_atual}'"
            })
        
        # 2. Detecta mudança abrupta de assunto
        if self._detectar_mudanca_assunto(entrada_atual, contexto_conversa, historico_conversa):
            confusoes.append({
                "tipo": TipoConfusao.MUDANCA_ASSUNTO_ABRUPTA.value,
                "descricao": "Usuário muda de assunto sem finalizar ação pendente",
                "confianca": 0.8,
                "evidencia": "Mudança de tópico detectada"
            })
        
        # 3. Detecta resposta inadequada
        if self._detectar_resposta_inadequada(entrada_atual, contexto_conversa):
            confusoes.append({
                "tipo": TipoConfusao.RESPOSTA_INADEQUADA.value,
                "descricao": "Resposta não corresponde ao que foi perguntado",
                "confianca": 0.7,
                "evidencia": f"Resposta '{entrada_atual}' inadequada ao contexto"
            })
        
        # 4. Detecta comportamento repetitivo
        if self._detectar_comportamento_repetitivo(historico_conversa):
            confusoes.append({
                "tipo": TipoConfusao.COMPORTAMENTO_REPETITIVO.value,
                "descricao": "Usuário repete ações ou frases indicando confusão",
                "confianca": 0.8,
                "evidencia": "Padrão repetitivo detectado no histórico"
            })
        
        # 5. Detecta seleção inválida
        if self._detectar_selecao_invalida(entrada_atual, contexto_conversa):
            confusoes.append({
                "tipo": TipoConfusao.SELECAO_INVALIDA.value,
                "descricao": "Usuário escolheu opção que não existe",
                "confianca": 0.95,
                "evidencia": f"Seleção '{entrada_atual}' fora do range válido"
            })
        
        # 6. Detecta falta de guidance
        if self._detectar_falta_guidance(entrada_atual, contexto_conversa):
            confusoes.append({
                "tipo": TipoConfusao.FALTA_GUIDANCE.value,
                "descricao": "Usuário parece perdido, sem saber como proceder",
                "confianca": 0.6,
                "evidencia": "Sinais de desorientação detectados"
            })
        
        return confusoes
    
    def _detectar_ignorar_opcoes(self, entrada: str, contexto: str) -> bool:
        """
        🚀 100% IA-FIRST: Usa IA para detectar se é confusão real VS comando legítimo.
        """
        # Verifica se contexto apresenta opções numeradas
        tem_opcoes_numeradas = bool(re.search(r'\d+\.', contexto))
        
        if not tem_opcoes_numeradas:
            return False
        
        # Verifica se usuário não escolheu um número
        entrada_eh_numero = re.match(r'^\d+$', entrada.strip())
        
        if entrada_eh_numero:
            return False
        
        # 🧠 USA IA PARA DETECTAR SE É CONFUSÃO OU COMANDO VÁLIDO
        return self._ia_detectar_confusao_vs_comando_valido(entrada, contexto)
    
    def _ia_detectar_confusao_vs_comando_valido(self, entrada: str, contexto: str) -> bool:
        """
        🧠 IA-FIRST: Usa IA para distinguir entre confusão real e comandos legítimos.
        """
        try:
            import ollama
            
            prompt = f'''Você é um especialista em análise de intenções de usuários.

SITUAÇÃO: O usuário viu uma lista numerada de opções mas não escolheu um número.

CONTEXTO MOSTRADO AO USUÁRIO:
{contexto[-500:]}

RESPOSTA DO USUÁRIO: "{entrada}"

PERGUNTA: O usuário está CONFUSO/PERDIDO ou fez um COMANDO LEGÍTIMO?

Exemplos de COMANDOS LEGÍTIMOS (mesmo sem escolher número):
- "meu carrinho" = quer ver carrinho
- "limpar carrinho" = quer limpar carrinho  
- "quero cerveja" = mudou de ideia, quer buscar cerveja
- "finalizar" = quer finalizar pedido
- "obrigado" = polidez/agradecimento

Exemplos de CONFUSÃO REAL:
- "???" = não entendeu
- "como assim" = confuso
- mensagens aleatórias/sem sentido

RESPONDA APENAS: true (se confuso) ou false (se comando legítimo)'''

            response = ollama.chat(model='llama3.1', messages=[{'role': 'user', 'content': prompt}])
            resposta = response['message']['content']
            
            print(f">>> DEBUG: [IA_CONFUSAO] Entrada: '{entrada}' | Resposta IA completa: {resposta}")
            
            # Extrai boolean da resposta
            if 'true' in resposta.lower():
                print(f">>> DEBUG: [IA_CONFUSAO] ✅ IA detectou CONFUSÃO REAL")
                return True
            elif 'false' in resposta.lower():
                print(f">>> DEBUG: [IA_CONFUSAO] ✅ IA detectou COMANDO LEGÍTIMO")
                return False
            else:
                print(f">>> DEBUG: [IA_CONFUSAO] ⚠️ IA não decidiu, assumindo comando legítimo")
                return False
                
        except Exception as e:
            print(f">>> DEBUG: [IA_CONFUSAO] Erro na IA: {e}")
            # Fallback: Em caso de erro, assume comando legítimo (menos restritivo)
            return False
    
    def _detectar_mudanca_assunto(self, entrada: str, contexto: str, historico: List[Dict]) -> bool:
        """
        🚀 IA-FIRST: Detecta mudança abrupta DE ASSUNTO usando IA semântica.
        """
        if not historico or len(historico) < 2:
            return False
        
        # 🧠 USA IA PARA DETECTAR MUDANÇA ABRUPTA REAL
        return self._ia_detectar_mudanca_abrupta(entrada, contexto, historico)
    
    def _ia_detectar_mudanca_abrupta(self, entrada: str, contexto: str, historico: List[Dict]) -> bool:
        """
        🧠 IA-FIRST: Usa IA para detectar se mudança de assunto é problemática.
        """
        try:
            import ollama
            
            # Pega últimas 3 mensagens do usuário para contexto
            ultimas_msgs = [msg.get("content", "") for msg in historico[-3:] if msg.get("role") == "user"]
            historico_user = " → ".join(ultimas_msgs[-2:]) if len(ultimas_msgs) >= 2 else ""
            
            prompt = f'''Você é um especialista em análise de fluxo conversacional.

HISTÓRICO RECENTE DO USUÁRIO:
{historico_user}

CONTEXTO ATUAL DA CONVERSA:
{contexto[-400:]}

NOVA MENSAGEM DO USUÁRIO: "{entrada}"

PERGUNTA: O usuário fez uma mudança ABRUPTA/PROBLEMÁTICA de assunto ou é uma mudança NATURAL/VÁLIDA?

Mudanças NATURAIS/VÁLIDAS (não problemáticas):
- "quero cerveja" após ver produtos → mudança natural de preferência
- "meu carrinho" a qualquer momento → comando sempre válido  
- "finalizar" a qualquer momento → comando sempre válido
- Saudações educadas → polidez natural

Mudanças ABRUPTAS/PROBLEMÁTICAS (problemáticas):
- Falar de assunto completamente diferente sem motivo
- Ignorar perguntas diretas com assunto aleatório
- Confusão clara sobre o contexto

RESPONDA APENAS: true (se problemática) ou false (se natural/válida)'''

            response = ollama.chat(model='llama3.1', messages=[{'role': 'user', 'content': prompt}])
            resposta = response['message']['content']
            
            print(f">>> DEBUG: [IA_MUDANCA] Entrada: '{entrada}' | Resposta IA completa: {resposta}")
            
            # Extrai boolean da resposta
            if 'true' in resposta.lower():
                print(f">>> DEBUG: [IA_MUDANCA] ✅ IA detectou mudança PROBLEMÁTICA")
                return True
            elif 'false' in resposta.lower():
                print(f">>> DEBUG: [IA_MUDANCA] ✅ IA detectou mudança NATURAL/VÁLIDA")
                return False
            else:
                print(f">>> DEBUG: [IA_MUDANCA] ⚠️ IA não decidiu, assumindo mudança natural")
                return False
                
        except Exception as e:
            print(f">>> DEBUG: [IA_MUDANCA] Erro na IA: {e}")
            # Fallback: Em caso de erro, assume mudança natural (menos restritivo)
            return False
    
    def _extrair_topicos(self, texto: str) -> List[str]:
        """Extrai tópicos principais de um texto."""
        topicos = []
        
        palavras_topicos = {
            "produtos": ["produto", "item", "cerveja", "refrigerante", "limpeza", "comida"],
            "carrinho": ["carrinho", "pedido", "itens"],
            "busca": ["buscar", "procurar", "quero", "preciso"],
            "quantidade": ["quantidade", "unidades", "quantos"],
            "finalizar": ["finalizar", "checkout", "comprar"],
            "selecao": ["escolher", "selecionar", "número", "opção"]
        }
        
        for topico, palavras in palavras_topicos.items():
            if any(palavra in texto for palavra in palavras):
                topicos.append(topico)
        
        return topicos
    
    def _detectar_resposta_inadequada(self, entrada: str, contexto: str) -> bool:
        """Detecta resposta inadequada ao contexto."""
        contexto_lower = contexto.lower()
        entrada_lower = entrada.lower().strip()
        
        # Se contexto pede número mas resposta não é número
        if any(frase in contexto_lower for frase in ["escolha um número", "digite o número", "selecione"]):
            if not re.match(r'^\d+$', entrada.strip()) and 'carrinho' in entrada_lower:
                return True
        
        # Se contexto pede quantidade mas resposta fala de outra coisa
        if any(frase in contexto_lower for frase in ["quantas unidades", "quantidade"]):
            if not re.search(r'\d+', entrada) and any(palavra in entrada_lower for palavra in ['carrinho', 'produtos', 'buscar']):
                return True
        
        # Se contexto pede confirmação mas resposta muda assunto
        if any(frase in contexto_lower for frase in ["confirma", "tem certeza", "finalizar pedido"]):
            if not any(palavra in entrada_lower for palavra in ['sim', 'não', 'ok', 'confirma', 'finalizar']):
                if any(palavra in entrada_lower for palavra in ['produto', 'buscar', 'carrinho']):
                    return True
        
        return False
    
    def _detectar_comportamento_repetitivo(self, historico: List[Dict]) -> bool:
        """Detecta comportamento repetitivo."""
        if not historico or len(historico) < 8:  # ← AUMENTADO de 6 para 8
            return False
        
        # Analisa últimas mensagens do usuário
        mensagens_usuario = [
            msg.get("content", "").lower().strip() 
            for msg in historico[-8:]  # ← AUMENTADO de 6 para 8
            if msg.get("role") == "user"
        ]
        
        if len(mensagens_usuario) < 4:  # ← AUMENTADO de 3 para 4
            return False
        
        # 🚀 MELHORADO: Filtra intenções válidas de negócio antes de detectar repetição
        intencoes_validas_negocio = [
            'cerveja', 'produto', 'quero', 'buscar', 'procurar', 'carrinho', 
            'finalizar', 'pedido', 'comprar', 'adicionar', 'ver', 'mostrar'
        ]
        
        # Se todas as mensagens são intenções de negócio válidas, não é comportamento repetitivo
        todas_sao_intencoes_validas = all(
            any(intencao in msg for intencao in intencoes_validas_negocio) 
            for msg in mensagens_usuario
        )
        
        if todas_sao_intencoes_validas:
            return False  # Usuário está fazendo pedidos legítimos, não está confuso
        
        # Verifica repetições exatas apenas para mensagens não-comerciais
        mensagens_unicas = set(mensagens_usuario)
        taxa_repeticao = 1 - (len(mensagens_unicas) / len(mensagens_usuario))
        
        # Verifica padrões de tentativas falhadas apenas com números
        tentativas_numero = sum(1 for msg in mensagens_usuario if re.match(r'^\d+$', msg.strip()))
        
        # 🚀 MELHORADO: Critério mais rigoroso para evitar falsos positivos
        return taxa_repeticao > 0.6 or tentativas_numero >= 4
    
    def _detectar_selecao_invalida(self, entrada: str, contexto: str) -> bool:
        """Detecta seleção de número inválido."""
        if not re.match(r'^\d+$', entrada.strip()):
            return False
        
        numero_escolhido = int(entrada.strip())
        
        # Extrai número máximo de opções do contexto
        opcoes_numeradas = re.findall(r'^(\d+)\.', contexto, re.MULTILINE)
        if opcoes_numeradas:
            opcao_maxima = max(int(num) for num in opcoes_numeradas)
            return numero_escolhido > opcao_maxima or numero_escolhido < 1
        
        # Se contexto menciona range específico
        match_range = re.search(r'(?:de\s+)?(\d+)(?:\s*-\s*|\s+a\s+)(\d+)', contexto.lower())
        if match_range:
            inicio, fim = int(match_range.group(1)), int(match_range.group(2))
            return numero_escolhido < inicio or numero_escolhido > fim
        
        return False
    
    def _detectar_falta_guidance(self, entrada: str, contexto: str) -> bool:
        """Detecta quando usuário está perdido, considerando contexto de produtos."""
        entrada_lower = entrada.lower().strip()
        
        # 🆕 NÃO DETECTA FALTA DE GUIDANCE SE É SAUDAÇÃO COM PRODUTOS ATIVOS
        # Verifica se há produtos sendo exibidos no contexto
        tem_produtos_ativos = "AWAITING_PRODUCT_SELECTION" in contexto or "produtos" in contexto.lower()
        eh_saudacao_simples = entrada_lower in ['oi', 'olá', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'e aí', 'e ai']
        
        # Se é saudação simples e tem produtos ativos, NÃO é falta de guidance
        if eh_saudacao_simples and tem_produtos_ativos:
            return False
        
        # Sinais claros de desorientação
        sinais_perdido = [
            "não entendi", "como", "o que", "ajuda", "não sei", "perdido",
            "não consegui", "confuso", "como faço", "me ajuda"
        ]
        
        # Perguntas genéricas que indicam desorientação (mas não saudações)
        perguntas_vagas = [
            "e agora", "o que mais", "que mais", "como continuo"
        ]
        
        # Detecta apenas sinais claros de confusão
        return (any(sinal in entrada_lower for sinal in sinais_perdido) or
                any(pergunta in entrada_lower for pergunta in perguntas_vagas))
    
    def _calcular_nivel_confusao(self, confusoes: List[Dict], historico: List[Dict]) -> float:
        """
        Calcula nível geral de confusão do usuário (0.0-1.0).
        """
        if not confusoes:
            return 0.0
        
        # Peso base das confusões detectadas
        peso_confusoes = {
            TipoConfusao.SELECAO_INVALIDA.value: 0.9,
            TipoConfusao.IGNORAR_OPCOES.value: 0.8,
            TipoConfusao.RESPOSTA_INADEQUADA.value: 0.7,
            TipoConfusao.COMPORTAMENTO_REPETITIVO.value: 0.8,
            TipoConfusao.MUDANCA_ASSUNTO_ABRUPTA.value: 0.6,
            TipoConfusao.FALTA_GUIDANCE.value: 0.5
        }
        
        # Calcula score baseado nas confusões e suas confianças
        score_total = 0.0
        for confusao in confusoes:
            tipo = confusao["tipo"]
            confianca = confusao["confianca"]
            peso = peso_confusoes.get(tipo, 0.5)
            score_total += peso * confianca
        
        # Normaliza pelo número de confusões (máximo 1.0)
        score_normalizado = min(1.0, score_total / max(1, len(confusoes)))
        
        # Ajusta baseado no histórico (confusão recorrente aumenta nível)
        if historico and len(historico) >= 4:
            mensagens_recentes = historico[-4:]
            interacoes_problematicas = sum(
                1 for msg in mensagens_recentes 
                if msg.get("role") == "user" and len(msg.get("content", "")) < 5
            )
            
            if interacoes_problematicas >= 2:
                score_normalizado = min(1.0, score_normalizado + 0.2)
        
        return round(score_normalizado, 2)
    
    def _gerar_estrategia_redirecionamento(self, confusoes: List[Dict], contexto: str,
                                         historico: List[Dict]) -> Dict:
        """
        Gera estratégia de redirecionamento baseada nas confusões detectadas.
        """
        # Prioriza estratégia baseada no tipo de confusão mais crítico
        if not confusoes:
            return None
        
        # Ordena confusões por criticidade
        confusoes_ordenadas = sorted(confusoes, key=lambda x: x["confianca"], reverse=True)
        confusao_principal = confusoes_ordenadas[0]
        
        tipo_confusao = confusao_principal["tipo"]
        
        # Seleciona estratégia baseada no tipo
        estrategias_por_tipo = {
            TipoConfusao.SELECAO_INVALIDA.value: EstrategiaRedirecionamento.SIMPLIFICAR_OPCOES,
            TipoConfusao.IGNORAR_OPCOES.value: EstrategiaRedirecionamento.REPETIR_PERGUNTA,
            TipoConfusao.RESPOSTA_INADEQUADA.value: EstrategiaRedirecionamento.GUIAR_PASSO_PASSO,
            TipoConfusao.COMPORTAMENTO_REPETITIVO.value: EstrategiaRedirecionamento.RESETAR_CONTEXTO,
            TipoConfusao.MUDANCA_ASSUNTO_ABRUPTA.value: EstrategiaRedirecionamento.OFERECER_AJUDA,
            TipoConfusao.FALTA_GUIDANCE.value: EstrategiaRedirecionamento.MENU_PRINCIPAL
        }
        
        estrategia_escolhida = estrategias_por_tipo.get(
            tipo_confusao, EstrategiaRedirecionamento.OFERECER_AJUDA
        )
        
        # Gera mensagem específica para a estratégia
        mensagem_redirecionamento = self._gerar_mensagem_redirecionamento(
            estrategia_escolhida, confusao_principal, contexto
        )
        
        # Registra no histórico
        guidance = {
            "tipo": estrategia_escolhida.value,
            "mensagem": mensagem_redirecionamento,
            "motivo": confusao_principal["descricao"],
            "timestamp": "agora"  # Em produção, usar timestamp real
        }
        
        self._historico_guidance.append(guidance)
        
        return guidance
    
    def _gerar_mensagem_redirecionamento(self, estrategia: EstrategiaRedirecionamento,
                                       confusao: Dict, contexto: str) -> str:
        """
        Gera mensagem específica para cada estratégia de redirecionamento.
        """
        mensagens = {
            EstrategiaRedirecionamento.SIMPLIFICAR_OPCOES: self._criar_mensagem_simplificar_opcoes(contexto),
            EstrategiaRedirecionamento.REPETIR_PERGUNTA: self._criar_mensagem_repetir_pergunta(contexto),
            EstrategiaRedirecionamento.GUIAR_PASSO_PASSO: self._criar_mensagem_guiar_passo_passo(contexto),
            EstrategiaRedirecionamento.RESETAR_CONTEXTO: self._criar_mensagem_resetar_contexto(),
            EstrategiaRedirecionamento.OFERECER_AJUDA: self._criar_mensagem_oferecer_ajuda(contexto),
            EstrategiaRedirecionamento.MENU_PRINCIPAL: self._criar_mensagem_menu_principal()
        }
        
        return mensagens.get(estrategia, "Como posso ajudar você?")
    
    def _criar_mensagem_simplificar_opcoes(self, contexto: str) -> str:
        """Cria mensagem para simplificar opções."""
        # Extrai opções do contexto
        opcoes = re.findall(r'^(\d+)\.\s*(.+)', contexto, re.MULTILINE)
        
        if opcoes and len(opcoes) > 3:
            # Se há muitas opções, mostra apenas as primeiras 3
            opcoes_simplificadas = opcoes[:3]
            mensagem = "🎯 Vou simplificar as opções para você:\n\n"
            for num, desc in opcoes_simplificadas:
                mensagem += f"{num}. {desc[:50]}...\n"
            mensagem += "\n📝 Escolha um número de 1 a 3, ou digite 'mais' para ver outras opções."
        else:
            mensagem = "🎯 Por favor, escolha uma das opções numeradas acima. Digite apenas o número da sua escolha."
        
        return mensagem
    
    def _criar_mensagem_repetir_pergunta(self, contexto: str) -> str:
        """Cria mensagem para repetir pergunta de forma mais clara."""
        if "escolha" in contexto.lower():
            return "🔢 Por favor, escolha UMA das opções digitando apenas o número correspondente."
        elif "quantidade" in contexto.lower():
            return "🔢 Preciso saber a quantidade. Digite apenas um número (ex: 2)."
        elif "confirma" in contexto.lower():
            return "❓ Preciso de uma confirmação. Responda apenas 'sim' ou 'não'."
        else:
            return "❓ Não entendi sua resposta. Pode tentar novamente seguindo as instruções?"
    
    def _criar_mensagem_guiar_passo_passo(self, contexto: str) -> str:
        """Cria mensagem para guiar passo a passo."""
        return ("🎯 Vamos por partes:\n\n"
                "1️⃣ Primeiro, vou te mostrar as opções disponíveis\n"
                "2️⃣ Depois, você escolhe digitando o número\n"
                "3️⃣ Confirmo sua escolha e prosseguimos\n\n"
                "Está pronto? Vamos começar! 🚀")
    
    def _criar_mensagem_resetar_contexto(self) -> str:
        """Cria mensagem para resetar contexto."""
        return ("🔄 Vamos recomeçar para evitar confusão!\n\n"
                "Como posso ajudar você hoje?\n"
                "• 🔍 Buscar produtos\n"
                "• 🛒 Ver meu carrinho\n"
                "• 🏷️ Ver promoções\n\n"
                "Digite o que você precisa ou escolha uma opção!")
    
    def _criar_mensagem_oferecer_ajuda(self, contexto: str) -> str:
        """Cria mensagem para oferecer ajuda."""
        return ("🤝 Percebo que você pode estar com dúvidas. \n\n"
                "Posso ajudar você de várias formas:\n"
                "• 📋 Explicar as opções disponíveis\n"
                "• 🎯 Simplificar o processo\n"
                "• 🔄 Começar de novo\n\n"
                "O que seria mais útil para você?")
    
    def _criar_mensagem_menu_principal(self) -> str:
        """Cria mensagem de menu principal."""
        return ("🏠 Menu Principal - O que você gostaria de fazer?\n\n"
                "1️⃣ Buscar produtos\n"
                "2️⃣ Ver promoções\n"
                "3️⃣ Ver meu carrinho\n"
                "4️⃣ Finalizar pedido\n\n"
                "Digite o número da opção ou me diga o que precisa! 😊")
    
    def _gerar_recomendacoes_contextuais(self, contexto: str) -> List[str]:
        """
        Gera recomendações baseadas no contexto atual.
        """
        recomendacoes = []
        contexto_lower = contexto.lower()
        
        if "produtos encontrados" in contexto_lower:
            recomendacoes.extend([
                "Use apenas números para escolher produtos",
                "Digite 'mais' para ver mais produtos",
                "Digite 'carrinho' para ver seus itens"
            ])
        
        elif "quantidade" in contexto_lower:
            recomendacoes.extend([
                "Digite apenas números (ex: 2)",
                "Use números de 1 a 10 para quantidade"
            ])
        
        elif "carrinho" in contexto_lower:
            recomendacoes.extend([
                "Digite 'finalizar' para concluir pedido",
                "Digite 'limpar' para esvaziar carrinho",
                "Use números para adicionar mais produtos"
            ])
        
        elif "finalizar" in contexto_lower:
            recomendacoes.extend([
                "Responda 'sim' para confirmar",
                "Responda 'não' para cancelar",
                "Revise seu pedido antes de confirmar"
            ])
        
        else:
            recomendacoes.extend([
                "Use comandos simples e diretos",
                "Digite números quando solicitado",
                "Digite 'ajuda' se estiver perdido"
            ])
        
        return recomendacoes[:3]  # Máximo 3 recomendações
    
    def obter_estatisticas_redirecionamento(self) -> Dict:
        """Retorna estatísticas do sistema de redirecionamento."""
        return self._stats_redirecionamento.copy()
    
    def resetar_estatisticas(self):
        """Reseta estatísticas do sistema."""
        for chave in self._stats_redirecionamento:
            if isinstance(self._stats_redirecionamento[chave], dict):
                self._stats_redirecionamento[chave] = {}
            else:
                self._stats_redirecionamento[chave] = 0
    
    def registrar_sucesso_redirecionamento(self):
        """Registra que um redirecionamento foi bem-sucedido."""
        self._stats_redirecionamento["sucessos_redirecionamento"] += 1
        self._stats_redirecionamento["usuarios_perdidos_recuperados"] += 1
        logging.info("[REDIRECT] Sucesso de redirecionamento registrado")
    
    def _carregar_padroes_confusao(self) -> Dict:
        """Carrega padrões para detectar confusão."""
        return {
            "respostas_vagas": ["ok", "certo", "sim", "não sei", "tanto faz"],
            "mudancas_assunto": ["quero", "buscar", "produto", "cerveja", "refrigerante"],
            "sinais_perdido": ["ajuda", "como", "não entendi", "perdido", "confuso"],
            "repetições": ["mesma coisa", "de novo", "novamente", "outra vez"]
        }
    
    def _carregar_estrategias_resposta(self) -> Dict:
        """Carrega estratégias de resposta."""
        return {
            "simplificar": "Vou simplificar as opções para você",
            "repetir": "Vou repetir a pergunta de forma mais clara",
            "guiar": "Vou te guiar passo a passo",
            "resetar": "Vamos começar de novo",
            "ajudar": "Como posso te ajudar melhor?",
            "menu": "Aqui estão suas opções principais"
        }


# Instância global do redirecionador
_redirecionador_inteligente = RedirecionadorInteligente()

def obter_redirecionador_inteligente() -> RedirecionadorInteligente:
    """
    Retorna a instância global do redirecionador inteligente.
    
    Returns:
        RedirecionadorInteligente: Redirecionador configurado
    """
    return _redirecionador_inteligente

def detectar_usuario_confuso(entrada_atual: str, contexto_conversa: str,
                           historico_conversa: List[Dict] = None) -> Dict:
    """
    Função utilitária para detectar confusão do usuário.
    
    Args:
        entrada_atual: Mensagem atual do usuário
        contexto_conversa: Contexto atual da conversa
        historico_conversa: Histórico da conversa
        
    Returns:
        Dict: Análise de confusão com estratégia de redirecionamento
    """
    return _redirecionador_inteligente.detectar_confusao_usuario(
        entrada_atual, contexto_conversa, historico_conversa
    )



def registrar_sucesso_guidance():
    """Registra que uma orientação foi bem-sucedida."""
    _redirecionador_inteligente.registrar_sucesso_redirecionamento()


def obter_estatisticas_redirecionamento() -> Dict:
    """Retorna estatísticas do sistema de redirecionamento."""
    return _redirecionador_inteligente.obter_estatisticas_redirecionamento()


def verificar_entrada_vazia_selecao(entrada_atual: str, last_bot_action: Optional[str]) -> Optional[str]:
    """Detecta quando usuário envia entrada vazia ou '?' durante uma etapa de seleção.

    Args:
        entrada_atual: Texto enviado pelo usuário.
        last_bot_action: Última ação do bot registrada na sessão.

    Returns:
        Mensagem de orientação se a condição for atendida, caso contrário ``None``.
    """
    acoes_selecao = {
        'AWAITING_PRODUCT_SELECTION',
        'AWAITING_MENU_SELECTION',
        'AWAITING_CORRECTION_SELECTION',
    }

    if last_bot_action in acoes_selecao and entrada_atual.strip() in ('', '?'):
        return "Digite o número do item ou 'ajuda' para ver opções"
    return None
