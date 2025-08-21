#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Prevenção de Invenção de Dados
Valida e filtra respostas da IA para evitar invenção de informações falsas
Baseado nas melhorias críticas identificadas em 21/08/2025
"""

import logging
import re
import json
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

class TipoConteudoProibido(Enum):
    """Tipos de conteúdo que não devem ser inventados."""
    INFORMACOES_ENTREGA = "informacoes_entrega"
    FORMAS_PAGAMENTO = "formas_pagamento"
    PRAZOS_DELIVERY = "prazos_delivery"
    PROMOCOES_INEXISTENTES = "promocoes_inexistentes"
    PRECOS_INVENTADOS = "precos_inventados"
    POLITICAS_LOJA = "politicas_loja"
    INFORMACOES_CONTATO = "informacoes_contato"
    DISPONIBILIDADE_ESTOQUE = "disponibilidade_estoque"

class PreventorInvencaoDados:
    """
    Sistema de Prevenção de Invenção de Dados.
    
    Valida e filtra respostas geradas pela IA para garantir que apenas 
    informações factualmente corretas sejam comunicadas ao usuário.
    """
    
    def __init__(self):
        self._termos_proibidos = self._carregar_termos_proibidos()
        self._dados_permitidos = self._carregar_dados_permitidos()
        self._padroes_deteccao = self._criar_padroes_deteccao()
        self._stats_prevencao = {
            "respostas_analisadas": 0,
            "conteudo_inventado_detectado": 0,
            "conteudo_filtrado": 0,
            "respostas_corrigidas": 0,
            "alertas_criticos": 0
        }
        
    def validar_conteudo_resposta(self, resposta_gerada: str, dados_disponiveis: Dict) -> Dict:
        """
        Valida e filtra resposta para evitar invenção de dados.
        
        Args:
            resposta_gerada: Texto da resposta gerada pela IA
            dados_disponiveis: Dados reais disponíveis no sistema
            
        Returns:
            Dict: Resultado da validação com resposta corrigida se necessário
        """
        self._stats_prevencao["respostas_analisadas"] += 1
        
        logging.debug(f"[PREVENCAO] Analisando resposta: '{resposta_gerada[:100]}...'")
        
        # 1. Detecta conteúdo inventado
        deteccoes = self._detectar_conteudo_inventado(resposta_gerada, dados_disponiveis)
        
        # 2. Filtra conteúdo problemático
        resposta_filtrada = self._filtrar_conteudo_proibido(resposta_gerada, deteccoes)
        
        # 3. Verifica precisão factual
        verificacao_factual = self._verificar_precisao_factual(resposta_filtrada, dados_disponiveis)
        
        # 4. Gera resposta final segura
        resposta_final = self._gerar_resposta_segura(
            resposta_filtrada, verificacao_factual, dados_disponiveis
        )
        
        # 5. Atualiza estatísticas
        foi_corrigida = resposta_final != resposta_gerada
        if foi_corrigida:
            self._stats_prevencao["respostas_corrigidas"] += 1
        
        if deteccoes:
            self._stats_prevencao["conteudo_inventado_detectado"] += 1
            if any(d["criticidade"] == "alta" for d in deteccoes):
                self._stats_prevencao["alertas_criticos"] += 1
        
        resultado = {
            "resposta_original": resposta_gerada,
            "resposta_corrigida": resposta_final,
            "foi_corrigida": foi_corrigida,
            "deteccoes": deteccoes,
            "verificacao_factual": verificacao_factual,
            "confiabilidade": self._calcular_confiabilidade(deteccoes, verificacao_factual),
            "alertas": self._gerar_alertas(deteccoes)
        }
        
        logging.info(f"[PREVENCAO] Validação: corrigida={foi_corrigida}, "
                    f"detecções={len(deteccoes)}, confiabilidade={resultado['confiabilidade']}")
        
        return resultado
    
    def _detectar_conteudo_inventado(self, resposta: str, dados_disponiveis: Dict) -> List[Dict]:
        """
        Detecta conteúdo potencialmente inventado na resposta.
        """
        deteccoes = []
        resposta_lower = resposta.lower()
        
        # Verifica cada tipo de conteúdo proibido
        for tipo_proibido, padroes in self._padroes_deteccao.items():
            for padrao in padroes:
                matches = re.finditer(padrao["regex"], resposta_lower)
                for match in matches:
                    # Verifica se a informação é permitida nos dados disponíveis
                    eh_permitido = self._verificar_se_eh_permitido(
                        match.group(), tipo_proibido, dados_disponiveis
                    )
                    
                    if not eh_permitido:
                        deteccoes.append({
                            "tipo": tipo_proibido.value,
                            "conteudo_detectado": match.group(),
                            "posicao": (match.start(), match.end()),
                            "criticidade": padrao["criticidade"],
                            "descricao": padrao["descricao"],
                            "acao_recomendada": padrao["acao"]
                        })
        
        return deteccoes
    
    def _verificar_se_eh_permitido(self, conteudo: str, tipo: TipoConteudoProibido, 
                                  dados_disponiveis: Dict) -> bool:
        """
        Verifica se o conteúdo detectado é permitido baseado nos dados disponíveis.
        """
        dados_permitidos = self._dados_permitidos.get(tipo.value, [])
        
        # Verifica se o conteúdo está na lista de permitidos
        for item_permitido in dados_permitidos:
            if isinstance(item_permitido, str) and item_permitido.lower() in conteudo:
                return True
        
        # Verifica se está nos dados disponíveis do sistema
        if tipo == TipoConteudoProibido.PRECOS_INVENTADOS:
            # Só permite preços se estão nos dados de produtos
            produtos = dados_disponiveis.get("produtos", [])
            for produto in produtos:
                if produto.get("preco") and str(produto["preco"]) in conteudo:
                    return True
        
        elif tipo == TipoConteudoProibido.DISPONIBILIDADE_ESTOQUE:
            # Só permite informações de estoque se estão nos dados
            produtos = dados_disponiveis.get("produtos", [])
            for produto in produtos:
                if "estoque" in produto and str(produto["estoque"]) in conteudo:
                    return True
        
        elif tipo == TipoConteudoProibido.PROMOCOES_INEXISTENTES:
            # Só permite promoções que existem nos dados
            promocoes = dados_disponiveis.get("promocoes", [])
            for promocao in promocoes:
                if promocao.get("descricao", "").lower() in conteudo:
                    return True
        
        return False
    
    def _filtrar_conteudo_proibido(self, resposta: str, deteccoes: List[Dict]) -> str:
        """
        Remove ou substitui conteúdo proibido da resposta.
        """
        resposta_filtrada = resposta
        
        # Ordena detecções por posição (do final para o início para não afetar índices)
        deteccoes_ordenadas = sorted(deteccoes, key=lambda x: x["posicao"][0], reverse=True)
        
        for deteccao in deteccoes_ordenadas:
            inicio, fim = deteccao["posicao"]
            acao = deteccao["acao_recomendada"]
            
            if acao == "remover":
                # Remove completamente o conteúdo
                resposta_filtrada = resposta_filtrada[:inicio] + resposta_filtrada[fim:]
                self._stats_prevencao["conteudo_filtrado"] += 1
                
            elif acao == "substituir":
                # Substitui por texto neutro
                substituto = self._obter_substituto_neutro(deteccao["tipo"])
                resposta_filtrada = resposta_filtrada[:inicio] + substituto + resposta_filtrada[fim:]
                self._stats_prevencao["conteudo_filtrado"] += 1
                
            elif acao == "alertar":
                # Mantém mas registra alerta (para conteúdo menos crítico)
                logging.warning(f"[PREVENCAO] Conteúdo questionável detectado: {deteccao['conteudo_detectado']}")
        
        return resposta_filtrada.strip()
    
    def _obter_substituto_neutro(self, tipo_conteudo: str) -> str:
        """
        Retorna texto neutro para substituir conteúdo proibido.
        """
        substitutos = {
            "informacoes_entrega": "",
            "formas_pagamento": "",
            "prazos_delivery": "",
            "promocoes_inexistentes": "",
            "precos_inventados": "",
            "politicas_loja": "consulte nossa equipe para mais informações",
            "informacoes_contato": "",
            "disponibilidade_estoque": ""
        }
        
        return substitutos.get(tipo_conteudo, "")
    
    def _verificar_precisao_factual(self, resposta: str, dados_disponiveis: Dict) -> Dict:
        """
        Verifica se a resposta contém apenas informações factualmente corretas.
        """
        verificacao = {
            "eh_factual": True,
            "problemas_encontrados": [],
            "nivel_confianca": 1.0
        }
        
        resposta_lower = resposta.lower()
        
        # Verifica afirmações específicas sobre produtos
        if "produto" in resposta_lower or "item" in resposta_lower:
            produtos_mencionados = self._extrair_produtos_mencionados(resposta, dados_disponiveis)
            for produto_info in produtos_mencionados:
                if not self._validar_informacao_produto(produto_info, dados_disponiveis):
                    verificacao["eh_factual"] = False
                    verificacao["problemas_encontrados"].append(f"Informação incorreta sobre produto: {produto_info}")
        
        # Verifica afirmações sobre serviços da loja
        servicos_mencionados = self._extrair_servicos_mencionados(resposta)
        for servico in servicos_mencionados:
            if not self._validar_servico(servico, dados_disponiveis):
                verificacao["eh_factual"] = False
                verificacao["problemas_encontrados"].append(f"Serviço não confirmado: {servico}")
        
        # Calcula nível de confiança baseado nos problemas encontrados
        if verificacao["problemas_encontrados"]:
            num_problemas = len(verificacao["problemas_encontrados"])
            verificacao["nivel_confianca"] = max(0.0, 1.0 - (num_problemas * 0.2))
        
        return verificacao
    
    def _extrair_produtos_mencionados(self, resposta: str, dados_disponiveis: Dict) -> List[str]:
        """
        Extrai nomes de produtos mencionados na resposta.
        """
        produtos_disponiveis = dados_disponiveis.get("produtos", [])
        produtos_mencionados = []
        
        for produto in produtos_disponiveis:
            nome_produto = produto.get("descricao", "").lower()
            if nome_produto and nome_produto in resposta.lower():
                produtos_mencionados.append(nome_produto)
        
        return produtos_mencionados
    
    def _extrair_servicos_mencionados(self, resposta: str) -> List[str]:
        """
        Extrai serviços mencionados na resposta.
        """
        servicos_potenciais = [
            "entrega", "delivery", "frete", "pagamento", "cartão", "dinheiro", 
            "pix", "desconto", "promoção", "oferta", "garantia"
        ]
        
        servicos_encontrados = []
        resposta_lower = resposta.lower()
        
        for servico in servicos_potenciais:
            if servico in resposta_lower:
                servicos_encontrados.append(servico)
        
        return servicos_encontrados
    
    def _validar_informacao_produto(self, info_produto: str, dados_disponiveis: Dict) -> bool:
        """
        Valida se informação sobre produto está correta.
        """
        produtos = dados_disponiveis.get("produtos", [])
        
        for produto in produtos:
            if produto.get("descricao", "").lower() == info_produto.lower():
                return True  # Produto existe, informação válida
        
        return False
    
    def _validar_servico(self, servico: str, dados_disponiveis: Dict) -> bool:
        """
        Valida se serviço mencionado é realmente oferecido.
        """
        servicos_confirmados = dados_disponiveis.get("servicos", [])
        
        # Lista de serviços que sabemos que NÃO são oferecidos
        servicos_nao_oferecidos = [
            "entrega rápida", "entrega expressa", "frete grátis", 
            "pagamento cartão", "parcelamento", "garantia estendida"
        ]
        
        if servico.lower() in [s.lower() for s in servicos_nao_oferecidos]:
            return False
        
        if servico.lower() in [s.lower() for s in servicos_confirmados]:
            return True
        
        # Para serviços não listados, assume como não confirmado
        return False
    
    def _gerar_resposta_segura(self, resposta_filtrada: str, verificacao_factual: Dict, 
                              dados_disponiveis: Dict) -> str:
        """
        Gera resposta final garantindo segurança factual.
        """
        if verificacao_factual["eh_factual"] and verificacao_factual["nivel_confianca"] >= 0.8:
            return resposta_filtrada
        
        # Se há problemas factuais, cria resposta mais conservadora
        resposta_segura = resposta_filtrada
        
        # Remove afirmações questionáveis
        frases_problematicas = [
            r'.*entrega.*rápid.*',
            r'.*frete.*grát.*',
            r'.*pagamento.*cart.*',
            r'.*desconto.*especial.*',
            r'.*promoção.*limitad.*',
            r'.*garantia.*'
        ]
        
        for padrao in frases_problematicas:
            resposta_segura = re.sub(padrao, '', resposta_segura, flags=re.IGNORECASE)
        
        # Limpa espaços extras e pontuação órfã
        resposta_segura = re.sub(r'\s+', ' ', resposta_segura).strip()
        resposta_segura = re.sub(r'[.]{2,}', '.', resposta_segura)
        resposta_segura = re.sub(r'^[,.]', '', resposta_segura)
        
        return resposta_segura
    
    def _calcular_confiabilidade(self, deteccoes: List[Dict], verificacao_factual: Dict) -> float:
        """
        Calcula score de confiabilidade da resposta (0.0-1.0).
        """
        confiabilidade_base = 1.0
        
        # Reduz confiabilidade para cada detecção
        for deteccao in deteccoes:
            if deteccao["criticidade"] == "alta":
                confiabilidade_base -= 0.3
            elif deteccao["criticidade"] == "media":
                confiabilidade_base -= 0.2
            else:  # baixa
                confiabilidade_base -= 0.1
        
        # Combina com verificação factual
        confiabilidade_final = min(confiabilidade_base, verificacao_factual["nivel_confianca"])
        
        return max(0.0, confiabilidade_final)
    
    def _gerar_alertas(self, deteccoes: List[Dict]) -> List[str]:
        """
        Gera alertas baseados nas detecções.
        """
        alertas = []
        
        for deteccao in deteccoes:
            if deteccao["criticidade"] == "alta":
                alertas.append(f"⚠️ CRÍTICO: {deteccao['descricao']}")
            elif deteccao["criticidade"] == "media":
                alertas.append(f"⚡ ATENÇÃO: {deteccao['descricao']}")
        
        return alertas
    
    def _carregar_termos_proibidos(self) -> Dict[str, List[str]]:
        """
        Carrega lista de termos que não devem ser inventados.
        """
        return {
            "entrega": [
                "entrega rápida", "entrega expressa", "entrega no mesmo dia",
                "entrega em 30 minutos", "entrega garantida", "frete grátis",
                "entrega gratuita", "sem taxa de entrega"
            ],
            "pagamento": [
                "aceita cartão", "pagamento no cartão", "parcelamento",
                "aceita pix", "pagamento online", "cartão de crédito",
                "cartão de débito", "boleto bancário"
            ],
            "prazos": [
                "prazo de entrega", "chega em", "entregue em", "disponível em",
                "tempo de preparo", "processamento em"
            ],
            "promocoes": [
                "promoção especial", "oferta limitada", "desconto exclusivo",
                "preço promocional", "super desconto", "mega promoção",
                "liquidação", "queima de estoque"
            ],
            "politicas": [
                "política de troca", "garantia de", "devolução gratuita",
                "sem taxa de", "política da empresa", "regras da loja"
            ],
            "contato": [
                "telefone", "whatsapp", "endereço", "email", "site",
                "facebook", "instagram", "localização"
            ]
        }
    
    def _carregar_dados_permitidos(self) -> Dict[str, List[str]]:
        """
        Carrega dados que são permitidos mencionar (confirmados).
        """
        return {
            "informacoes_entrega": [
                # Adicionar apenas informações confirmadas sobre entrega
            ],
            "formas_pagamento": [
                "dinheiro", "à vista"  # Apenas formas confirmadas
            ],
            "promocoes_inexistentes": [
                # Adicionar apenas promoções realmente ativas
            ],
            "politicas_loja": [
                # Adicionar apenas políticas confirmadas
            ]
        }
    
    def _criar_padroes_deteccao(self) -> Dict[TipoConteudoProibido, List[Dict]]:
        """
        Cria padrões regex para detectar conteúdo inventado.
        """
        return {
            TipoConteudoProibido.INFORMACOES_ENTREGA: [
                {
                    "regex": r"entrega.*?(?:rápid|express|grát|no mesmo dia|30\s*minut)",
                    "criticidade": "alta",
                    "descricao": "Informação de entrega não confirmada",
                    "acao": "remover"
                },
                {
                    "regex": r"frete.*?(?:grát|sem custo|incluso)",
                    "criticidade": "alta", 
                    "descricao": "Informação de frete não confirmada",
                    "acao": "remover"
                }
            ],
            TipoConteudoProibido.FORMAS_PAGAMENTO: [
                {
                    "regex": r"(?:aceit|pag).*?(?:cartão|cart|pix|boleto|parcel)",
                    "criticidade": "alta",
                    "descricao": "Forma de pagamento não confirmada",
                    "acao": "remover"
                }
            ],
            TipoConteudoProibido.PRAZOS_DELIVERY: [
                {
                    "regex": r"(?:prazo|chega|entregue|disponível).*?(?:em|de).*?(?:\d+.*?(?:hora|dia|minut))",
                    "criticidade": "alta",
                    "descricao": "Prazo de entrega não confirmado",
                    "acao": "remover"
                }
            ],
            TipoConteudoProibido.PROMOCOES_INEXISTENTES: [
                {
                    "regex": r"(?:promoção|oferta|desconto).*?(?:especial|exclusiv|limitad|mega|super)",
                    "criticidade": "media",
                    "descricao": "Promoção não confirmada",
                    "acao": "remover"
                }
            ],
            TipoConteudoProibido.POLITICAS_LOJA: [
                {
                    "regex": r"(?:política|garantia|troca|devolução).*?(?:de|gratuita|grátis)",
                    "criticidade": "media",
                    "descricao": "Política da loja não confirmada",
                    "acao": "substituir"
                }
            ],
            TipoConteudoProibido.INFORMACOES_CONTATO: [
                {
                    "regex": r"(?:telefone|whatsapp|email|endereço|site).*?(?:é|:|nosso)",
                    "criticidade": "alta",
                    "descricao": "Informação de contato inventada",
                    "acao": "remover"
                }
            ]
        }
    
    def verificar_resposta_segura(self, resposta: str) -> bool:
        """
        Verificação rápida se resposta é segura (sem invenções óbvias).
        
        Args:
            resposta: Texto da resposta para verificar
            
        Returns:
            bool: True se resposta parece segura, False se há problemas
        """
        termos_criticos = [
            "entrega rápida", "frete grátis", "aceita cartão", "pagamento no cartão",
            "entrega garantida", "promoção especial", "desconto exclusivo",
            "política de troca", "garantia de", "nosso telefone", "nosso endereço"
        ]
        
        resposta_lower = resposta.lower()
        for termo in termos_criticos:
            if termo in resposta_lower:
                logging.warning(f"[PREVENCAO] Termo crítico detectado: '{termo}' na resposta")
                return False
        
        return True
    
    def obter_estatisticas_prevencao(self) -> Dict:
        """Retorna estatísticas do sistema de prevenção."""
        return self._stats_prevencao.copy()
    
    def resetar_estatisticas(self):
        """Reseta estatísticas do sistema."""
        for chave in self._stats_prevencao:
            self._stats_prevencao[chave] = 0
    
    def adicionar_dados_permitidos(self, tipo: str, novos_dados: List[str]):
        """
        Adiciona novos dados à lista de permitidos.
        
        Args:
            tipo: Tipo de dados (ex: "formas_pagamento")
            novos_dados: Lista de novos dados permitidos
        """
        if tipo not in self._dados_permitidos:
            self._dados_permitidos[tipo] = []
        
        self._dados_permitidos[tipo].extend(novos_dados)
        logging.info(f"[PREVENCAO] Adicionados {len(novos_dados)} itens permitidos para {tipo}")
    
    def atualizar_dados_sistema(self, dados_sistema: Dict):
        """
        Atualiza dados do sistema para validação factual.
        
        Args:
            dados_sistema: Dados atualizados do sistema
        """
        # Extrai informações confirmadas dos dados do sistema
        if "produtos" in dados_sistema:
            logging.debug(f"[PREVENCAO] Dados de produtos atualizados: {len(dados_sistema['produtos'])} produtos")
        
        if "promocoes" in dados_sistema:
            logging.debug(f"[PREVENCAO] Dados de promoções atualizados: {len(dados_sistema['promocoes'])} promoções")
        
        if "servicos" in dados_sistema:
            logging.debug(f"[PREVENCAO] Dados de serviços atualizados: {len(dados_sistema['servicos'])} serviços")


# Instância global do preventor de invenção
_preventor_invencao = PreventorInvencaoDados()

def obter_preventor_invencao() -> PreventorInvencaoDados:
    """
    Retorna a instância global do preventor de invenção de dados.
    
    Returns:
        PreventorInvencaoDados: Preventor configurado
    """
    return _preventor_invencao

def validar_resposta_ia(resposta_gerada: str, dados_disponiveis: Dict = None) -> Dict:
    """
    Função utilitária para validar resposta da IA.
    
    Args:
        resposta_gerada: Texto gerado pela IA
        dados_disponiveis: Dados disponíveis no sistema
        
    Returns:
        Dict: Resultado da validação com resposta corrigida
    """
    if dados_disponiveis is None:
        dados_disponiveis = {}
    
    return _preventor_invencao.validar_conteudo_resposta(resposta_gerada, dados_disponiveis)

def verificar_seguranca_resposta(resposta: str) -> bool:
    """
    Função utilitária para verificação rápida de segurança.
    
    Args:
        resposta: Texto da resposta para verificar
        
    Returns:
        bool: True se resposta é segura, False caso contrário
    """
    return _preventor_invencao.verificar_resposta_segura(resposta)

def obter_estatisticas_prevencao() -> Dict:
    """
    Retorna estatísticas do sistema de prevenção.
    
    Returns:
        Dict: Estatísticas de detecção e correção
    """
    return _preventor_invencao.obter_estatisticas_prevencao()