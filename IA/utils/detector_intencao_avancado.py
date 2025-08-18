# file: IA/utils/detector_intencao_avancado.py
"""
Detector de Intenções Avançado com IA-First
Identifica intenções complexas e contextuais do usuário
"""

import os
import re
import logging
from typing import Dict, List, Optional

# Importações para IA
try:
    import ollama
    OLLAMA_DISPONIVEL = True
except ImportError:
    OLLAMA_DISPONIVEL = False
    logging.warning("Ollama não disponível para detecção avançada de intenção")

# Configurações IA
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
HOST_OLLAMA = os.getenv("OLLAMA_HOST")

def detectar_intencao_carrinho_ia(mensagem: str, historico_conversa: str, carrinho_atual: List = None) -> Dict:
    """
    Detecta intenções relacionadas ao carrinho usando IA.
    
    Args:
        mensagem: Mensagem do usuário.
        historico_conversa: Contexto da conversa.
        carrinho_atual: Itens atuais do carrinho.
    
    Returns:
        Dict: Intenção detectada com ação e parâmetros.
    """
    if not OLLAMA_DISPONIVEL:
        return {"acao": "unknown", "parametros": {}}
    
    try:
        # Prepara contexto do carrinho
        contexto_carrinho = ""
        if carrinho_atual and len(carrinho_atual) > 0:
            itens_carrinho = []
            for i, item in enumerate(carrinho_atual[:5], 1):
                nome = item.get('descricao', item.get('canonical_name', 'Item'))
                qtd = item.get('qt', 1)
                itens_carrinho.append(f"{i}. {nome} (qtd: {qtd})")
            contexto_carrinho = f"CARRINHO ATUAL:\n" + "\n".join(itens_carrinho)
        else:
            contexto_carrinho = "CARRINHO ATUAL: Vazio"
        
        prompt_ia = f"""Você é um especialista em detectar intenções de manipulação de carrinho de compras.

MENSAGEM DO USUÁRIO: "{mensagem}"

CONTEXTO DA CONVERSA:
{historico_conversa if historico_conversa else "Primeira interação"}

{contexto_carrinho}

INTENÇÕES POSSÍVEIS:
- add_item: Adicionar novo produto
- remove_item: Remover produto específico
- update_quantity: Alterar quantidade
- replace_item: Substituir um produto por outro
- clear_cart: Limpar carrinho completo
- view_cart: Ver conteúdo do carrinho
- unknown: Não relacionado ao carrinho

EXEMPLOS:
- "tira essa coca aí" → remove_item
- "coloca mais duas" → add_item (quantidade: 2)
- "troca por heineken" → replace_item
- "deixa só uma de cada" → update_quantity
- "quero mudar tudo" → clear_cart
- "aumenta pra 5" → update_quantity
- "remove o item 2" → remove_item (índice: 2)

RESPONDA EM JSON:
{{"acao": "nome_da_acao", "parametros": {{"item_index": 1, "quantidade": 2, "produto_novo": "nome"}}}}

JSON:"""

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.1,
                "top_p": 0.3,
                "num_predict": 100
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        logging.debug(f"[INTENCAO_CARRINHO_IA] Mensagem: '{mensagem}' → IA: '{resposta_ia}'")
        
        # Extrai JSON da resposta
        import json
        try:
            json_match = re.search(r'\{.*?\}', resposta_ia, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group(0))
                if "acao" in resultado:
                    logging.info(f"[INTENCAO_CARRINHO_IA] Sucesso: {resultado['acao']}")
                    return resultado
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return {"acao": "unknown", "parametros": {}}
        
    except Exception as e:
        logging.error(f"[INTENCAO_CARRINHO_IA] Erro: {e}")
        return {"acao": "unknown", "parametros": {}}

def analisar_contexto_emocional_ia(mensagem: str, historico: str) -> Dict:
    """
    Analisa o estado emocional e urgência do cliente.
    
    Args:
        mensagem: Mensagem do usuário.
        historico: Histórico da conversa.
    
    Returns:
        Dict: Análise emocional com sentimento, urgência e sugestões.
    """
    if not OLLAMA_DISPONIVEL:
        return {"sentimento": "neutro", "urgencia": "normal", "sugestoes": []}
    
    try:
        prompt_ia = f"""Você é um especialista em análise de sentimentos para atendimento ao cliente.

MENSAGEM DO USUÁRIO: "{mensagem}"

CONTEXTO DA CONVERSA:
{historico if historico else "Primeira interação"}

ANALISE:
1. SENTIMENTO: positivo, neutro, negativo, frustrado, satisfeito
2. URGÊNCIA: baixa, normal, alta, urgente
3. INDICADORES: palavras que indicam estado emocional
4. SUGESTÕES: como melhorar a experiência

RESPONDA EM JSON:
{{
  "sentimento": "neutro",
  "urgencia": "normal",
  "indicadores": ["palavra1", "palavra2"],
  "sugestoes": ["sugestao1", "sugestao2"]
}}

JSON:"""

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.2,
                "top_p": 0.4,
                "num_predict": 150
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        
        # Extrai JSON da resposta
        import json
        try:
            json_match = re.search(r'\{.*?\}', resposta_ia, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group(0))
                logging.info(f"[CONTEXTO_EMOCIONAL_IA] Sentimento: {resultado.get('sentimento', 'neutro')}")
                return resultado
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return {"sentimento": "neutro", "urgencia": "normal", "sugestoes": []}
        
    except Exception as e:
        logging.error(f"[CONTEXTO_EMOCIONAL_IA] Erro: {e}")
        return {"sentimento": "neutro", "urgencia": "normal", "sugestoes": []}

def extrair_especificacoes_produto_ia(mensagem: str) -> Dict:
    """
    Extrai especificações detalhadas de produtos mencionados.
    
    Args:
        mensagem: Mensagem do usuário.
    
    Returns:
        Dict: Especificações extraídas do produto.
    """
    if not OLLAMA_DISPONIVEL:
        return {}
    
    try:
        prompt_ia = f"""Você é um especialista em extrair especificações de produtos.

MENSAGEM DO USUÁRIO: "{mensagem}"

EXTRAIA:
- marca: Marca específica mencionada
- tamanho: Tamanho/volume (pequeno, grande, 350ml, 2L, etc)
- sabor: Sabor específico (zero, diet, natural, etc)
- embalagem: Tipo de embalagem (lata, garrafa, pet, pack, etc)
- temperatura: Preferência de temperatura (gelado, natural, etc)
- quantidade_sugerida: Quantidade típica para o contexto

EXEMPLOS:
- "coca zero lata" → marca: coca cola, sabor: zero, embalagem: lata
- "cerveja bem gelada" → temperatura: gelado
- "guaraná 2 litros" → tamanho: 2L
- "pack de brahma" → marca: brahma, embalagem: pack

RESPONDA EM JSON:
{{
  "marca": "nome_marca",
  "tamanho": "tamanho",
  "sabor": "sabor",
  "embalagem": "embalagem",
  "temperatura": "temperatura",
  "quantidade_sugerida": 1
}}

JSON:"""

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.1,
                "top_p": 0.3,
                "num_predict": 100
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        
        # Extrai JSON da resposta
        import json
        try:
            json_match = re.search(r'\{.*?\}', resposta_ia, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group(0))
                # Remove campos vazios
                resultado = {k: v for k, v in resultado.items() if v and v != "null" and v != ""}
                if resultado:
                    logging.info(f"[ESPECIFICACOES_IA] Extraídas: {list(resultado.keys())}")
                return resultado
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return {}
        
    except Exception as e:
        logging.error(f"[ESPECIFICACOES_IA] Erro: {e}")
        return {}

def corrigir_e_sugerir_ia(mensagem: str, produtos_encontrados: List, contexto: str = "") -> Dict:
    """
    Corrige erros de digitação e sugere melhorias.
    
    Args:
        mensagem: Mensagem original do usuário.
        produtos_encontrados: Produtos encontrados na busca.
        contexto: Contexto adicional.
    
    Returns:
        Dict: Correções e sugestões.
    """
    if not OLLAMA_DISPONIVEL:
        return {"correcoes": [], "sugestoes": []}
    
    try:
        produtos_contexto = ""
        if produtos_encontrados:
            nomes = [p.get('descricao', p.get('canonical_name', ''))[:30] for p in produtos_encontrados[:5]]
            produtos_contexto = f"PRODUTOS ENCONTRADOS: {', '.join(nomes)}"
        
        prompt_ia = f"""Você é um especialista em correção de texto e sugestões de produtos.

MENSAGEM ORIGINAL: "{mensagem}"
{produtos_contexto}

CONTEXTO:
{contexto if contexto else "Sem contexto adicional"}

TAREFAS:
1. CORREÇÕES: Identifique erros de digitação e sugira correções
2. SUGESTÕES: Baseado nos produtos encontrados, sugira:
   - Produtos complementares
   - Variações do produto
   - Promoções relacionadas
   - Quantidades típicas

EXEMPLOS:
- "coka" → correção: "coca cola"
- "cerveja" → sugestões: ["amendoim", "batata chips", "gelo"]
- "shampoo" → sugestões: ["condicionador", "sabonete"]

RESPONDA EM JSON:
{{
  "correcoes": ["termo_original → termo_corrigido"],
  "sugestoes": ["produto1", "produto2", "produto3"],
  "motivo_sugestoes": "explicação"
}}

JSON:"""

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.3,
                "top_p": 0.5,
                "num_predict": 150
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        
        # Extrai JSON da resposta
        import json
        try:
            json_match = re.search(r'\{.*?\}', resposta_ia, re.DOTALL)
            if json_match:
                resultado = json.loads(json_match.group(0))
                if resultado.get("correcoes") or resultado.get("sugestoes"):
                    logging.info(f"[CORRECAO_SUGESTAO_IA] Geradas: {len(resultado.get('sugestoes', []))} sugestões")
                return resultado
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return {"correcoes": [], "sugestoes": []}
        
    except Exception as e:
        logging.error(f"[CORRECAO_SUGESTAO_IA] Erro: {e}")
        return {"correcoes": [], "sugestoes": []}