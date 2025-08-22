# file: IA/utils/detector_marca_produto.py
"""
Detector Inteligente de Marca e Produto Específico
Identifica quando o usuário está procurando uma marca específica vs categoria geral
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
    logging.warning("Ollama não disponível para detecção de marca/produto")

# Configurações IA
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
HOST_OLLAMA = os.getenv("OLLAMA_HOST")

def detectar_marca_e_produto_ia(mensagem: str, contexto_conversa: str = "") -> Dict:
    """
    Detecta se o usuário está procurando uma marca específica ou categoria geral.
    
    Args:
        mensagem: Mensagem do usuário.
        contexto_conversa: Contexto da conversa.
    
    Returns:
        Dict: Análise com tipo_busca, marca, produto, categoria.
    """
    if not OLLAMA_DISPONIVEL:
        return _detectar_marca_fallback(mensagem)
    
    try:
        prompt_ia = """IMPORTANTE: Responda APENAS com JSON válido, sem texto adicional.

Analise: "{}"

TASK: Identifique se há nome de marca comercial na mensagem.

REGRAS:
- Se contém nome de MARCA/FABRICANTE: tipo_busca = "marca_especifica"  
- Se contém apenas CATEGORIA de produto: tipo_busca = "categoria_geral"
- Use seu conhecimento de marcas comerciais
- Palavras como "promoção", "barato", "em oferta" NÃO são marcas

EXEMPLOS:
- "quero cerveja" → {"tipo_busca": "categoria_geral", "marca": null, "produto": "cerveja", "categoria": "bebidas", "prioridade_marca": false}
- "cerveja em promoção" → {"tipo_busca": "categoria_geral", "marca": null, "produto": "cerveja", "categoria": "bebidas", "prioridade_marca": false}
- "heineken" → {"tipo_busca": "marca_especifica", "marca": "heineken", "produto": "cerveja", "categoria": "bebidas", "prioridade_marca": true}

Responda SOMENTE o JSON:""".format(mensagem)

        if HOST_OLLAMA:
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            cliente_ollama = ollama
        
        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt_ia}],
            options={
                "temperature": 0.0,  # Máxima determinismo para JSON consistente
                "top_p": 0.1,        # Foco nas respostas mais prováveis
                "num_predict": 100,  # Limite menor para JSON compacto
                "stop": ["}"]        # Para quando terminar o JSON
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        logging.debug(f"[MARCA_PRODUTO_IA] Mensagem: '{mensagem}' → IA: '{resposta_ia}'")
        
        # Extrai JSON da resposta
        import json
        print(f">>> DEBUG: [EXTRAÇÃO_JSON] Resposta completa da IA: {resposta_ia}")
        
        try:
            # Se a resposta não começa com {, adiciona }
            if not resposta_ia.strip().endswith('}') and '{' in resposta_ia:
                resposta_ia = resposta_ia.strip() + '}'
                
            # Tenta extrair JSON de várias formas
            json_match = re.search(r'\{[^{}]*\}', resposta_ia, re.DOTALL)
            if json_match:
                json_texto = json_match.group(0)
                print(f">>> DEBUG: [EXTRAÇÃO_JSON] JSON extraído: {json_texto}")
                resultado = json.loads(json_texto)
                
                print(f">>> DEBUG: [EXTRAÇÃO_JSON] JSON parsed: {resultado}")
                
                # Valida resultado
                if resultado.get("tipo_busca") in ["marca_especifica", "categoria_geral", "produto_especifico"]:
                    print(f">>> DEBUG: [EXTRAÇÃO_JSON] ✅ JSON válido - tipo: {resultado.get('tipo_busca')}, marca: {resultado.get('marca')}")
                    logging.info(f"[MARCA_PRODUTO_IA] Detectado: {resultado.get('tipo_busca')} - {resultado.get('marca', 'sem marca')}")
                    return resultado
                else:
                    print(f">>> DEBUG: [EXTRAÇÃO_JSON] ❌ JSON inválido - tipo_busca não reconhecido: {resultado.get('tipo_busca')}")
            else:
                print(f">>> DEBUG: [EXTRAÇÃO_JSON] ❌ Nenhum JSON encontrado na resposta")
        except (json.JSONDecodeError, AttributeError) as e:
            print(f">>> DEBUG: [EXTRAÇÃO_JSON] ❌ Erro ao parsear JSON: {e}")
            
            # Tenta extrair dados manualmente da resposta
            print(f">>> DEBUG: [EXTRAÇÃO_JSON] Tentando extração manual...")
            try:
                # Busca por padrões específicos na resposta
                tipo_match = re.search(r'tipo_busca["\s:]*["\s]*(\w+)', resposta_ia)
                marca_match = re.search(r'marca["\s:]*["\s]*(\w+)', resposta_ia)
                produto_match = re.search(r'produto["\s:]*["\s]*(\w+)', resposta_ia)
                
                if tipo_match:
                    tipo_busca = tipo_match.group(1)
                    marca = marca_match.group(1) if marca_match else None
                    produto = produto_match.group(1) if produto_match else None
                    
                    print(f">>> DEBUG: [EXTRAÇÃO_MANUAL] tipo: {tipo_busca}, marca: {marca}, produto: {produto}")
                    
                    if tipo_busca in ["marca_especifica", "categoria_geral", "produto_especifico"]:
                        resultado_manual = {
                            "tipo_busca": tipo_busca,
                            "marca": marca,
                            "produto": produto,
                            "especificacoes": [],
                            "categoria": "bebidas" if produto == "cerveja" else "outros",
                            "prioridade_marca": tipo_busca == "marca_especifica"
                        }
                        print(f">>> DEBUG: [EXTRAÇÃO_MANUAL] ✅ Resultado manual: {resultado_manual}")
                        return resultado_manual
            except Exception as manual_error:
                print(f">>> DEBUG: [EXTRAÇÃO_MANUAL] ❌ Erro na extração manual: {manual_error}")
        
        # Fallback se IA falhou
        return _detectar_marca_fallback(mensagem)
        
    except Exception as e:
        logging.error(f"[MARCA_PRODUTO_IA] Erro: {str(e)}")
        print(f">>> DEBUG: [ERRO_IA] Exceção completa: {repr(e)}")
        return _detectar_marca_fallback(mensagem)

def _detectar_marca_fallback(mensagem: str) -> Dict:
    """
    🚀 FALLBACK 100% IA-FIRST: Usa apenas contexto semântico, sem listas pré-definidas.
    """
    print(f">>> DEBUG: [FALLBACK] Executando fallback IA-FIRST para: '{mensagem}'")
    mensagem_lower = mensagem.lower().strip()
    
    # 🧠 ANÁLISE SEMÂNTICA: Detecta se é comando de carrinho vs busca de produto
    # Padrões semânticos de comandos de carrinho
    if any(padrão in mensagem_lower for padrão in [
        "meu carrinho", "ver carrinho", "carrinho", "limpar carrinho", "esvaziar carrinho",
        "finalizar", "total", "pedido", "compra"
    ]):
        print(f">>> DEBUG: [FALLBACK] 🛒 Comando de carrinho detectado, retornando categoria_geral")
        return {
            "tipo_busca": "categoria_geral", 
            "marca": None,
            "produto": "acao_carrinho",  # Sinaliza que é ação, não produto
            "especificacoes": [],
            "categoria": "sistema",
            "prioridade_marca": False
        }
    
    # 🧠 ANÁLISE SEMÂNTICA: Detecta intenção de busca vs marca específica
    # Se mensagem é muito curta e específica, provavelmente é marca
    palavras = mensagem_lower.split()
    
    # Detecta padrões de busca geral vs marca específica usando contexto
    if len(palavras) == 1:
        # Uma palavra só: provavelmente categoria geral
        produto_inferido = palavras[0]
        print(f">>> DEBUG: [FALLBACK] 🎯 Palavra única '{produto_inferido}' = categoria_geral")
        return {
            "tipo_busca": "categoria_geral",
            "marca": None,
            "produto": produto_inferido,
            "especificacoes": [],
            "categoria": "bebidas" if any(termo in produto_inferido for termo in ["cerveja", "beer", "refri"]) else "outros",
            "prioridade_marca": False
        }
    
    elif len(palavras) == 2:
        # Duas palavras: analisa padrão semântico
        if palavras[0] in ["quero", "preciso", "buscar", "comprar"]:
            # "quero cerveja" = categoria_geral
            produto_inferido = palavras[1]
            print(f">>> DEBUG: [FALLBACK] 🎯 Padrão 'verbo + produto' = categoria_geral")
            return {
                "tipo_busca": "categoria_geral",
                "marca": None,
                "produto": produto_inferido,
                "especificacoes": [],
                "categoria": "bebidas" if any(termo in produto_inferido for termo in ["cerveja", "beer", "refri"]) else "outros",
                "prioridade_marca": False
            }
        else:
            # "cerveja heineken" = marca_especifica
            produto_inferido = palavras[0] if len(palavras[0]) > len(palavras[1]) else palavras[1]
            marca_inferida = palavras[1] if produto_inferido == palavras[0] else palavras[0]
            print(f">>> DEBUG: [FALLBACK] 🏷️ Padrão 'produto + marca' detectado: {produto_inferido} + {marca_inferida}")
            return {
                "tipo_busca": "marca_especifica",
                "marca": marca_inferida,
                "produto": produto_inferido,
                "especificacoes": [],
                "categoria": "bebidas" if any(termo in produto_inferido for termo in ["cerveja", "beer", "refri"]) else "outros",
                "prioridade_marca": True
            }
    
    # 🧠 FALLBACK FINAL: Múltiplas palavras = categoria_geral (busca ampla)
    print(f">>> DEBUG: [FALLBACK] 🌐 Múltiplas palavras = categoria_geral")
    return {
        "tipo_busca": "categoria_geral",
        "marca": None,
        "produto": mensagem.strip(),  # Usa a mensagem completa como termo de busca
        "especificacoes": [],
        "categoria": "outros",
        "prioridade_marca": False
    }

def filtrar_produtos_por_marca(produtos: List[Dict], marca_desejada: str, produto_tipo: str = "") -> List[Dict]:
    """
    Filtra produtos por marca específica.
    
    Args:
        produtos: Lista de produtos.
        marca_desejada: Marca que o usuário quer.
        produto_tipo: Tipo de produto (cerveja, refrigerante, etc).
    
    Returns:
        List[Dict]: Produtos filtrados pela marca.
    """
    print(f">>> DEBUG: [FILTRO_MARCA] Iniciando filtro por marca '{marca_desejada}' em {len(produtos)} produtos")
    
    if not marca_desejada or not produtos:
        print(f">>> DEBUG: [FILTRO_MARCA] Retornando sem filtrar - marca_desejada: {marca_desejada}, produtos: {len(produtos) if produtos else 0}")
        return produtos
    
    marca_lower = marca_desejada.lower()
    produtos_filtrados = []
    
    print(f">>> DEBUG: [FILTRO_MARCA] Procurando por marca: '{marca_lower}'")
    
    for i, produto in enumerate(produtos):
        descricao = produto.get('descricao', '').lower()
        canonical_name = produto.get('canonical_name', '').lower()
        marca_produto = produto.get('marca', '').lower()
        
        # Verifica se a marca está no campo marca, descrição ou nome do produto
        match_marca = marca_lower in marca_produto
        match_desc = marca_lower in descricao
        match_canonical = marca_lower in canonical_name
        
        print(f">>> DEBUG: [FILTRO_{i+1}] Produto: {produto.get('descricao')}")
        print(f">>> DEBUG: [FILTRO_{i+1}] - Marca produto: '{marca_produto}' | Match: {match_marca}")
        print(f">>> DEBUG: [FILTRO_{i+1}] - Descrição: '{descricao}' | Match: {match_desc}")
        print(f">>> DEBUG: [FILTRO_{i+1}] - Canonical: '{canonical_name}' | Match: {match_canonical}")
        
        # Verifica também similaridade
        similar_desc = _marca_similar_no_texto(marca_lower, descricao)
        similar_canonical = _marca_similar_no_texto(marca_lower, canonical_name)
        similar_marca = _marca_similar_no_texto(marca_lower, marca_produto)
        
        print(f">>> DEBUG: [FILTRO_{i+1}] - Similar desc: {similar_desc}, Similar canonical: {similar_canonical}, Similar marca: {similar_marca}")
        
        if (match_desc or match_canonical or match_marca or similar_desc or similar_canonical or similar_marca):
            print(f">>> DEBUG: [FILTRO_{i+1}] ✅ INCLUÍDO: {produto.get('descricao')}")
            produtos_filtrados.append(produto)
        else:
            print(f">>> DEBUG: [FILTRO_{i+1}] ❌ EXCLUÍDO: {produto.get('descricao')}")
    
    logging.info(f"[FILTRO_MARCA] Filtrados {len(produtos_filtrados)} de {len(produtos)} produtos para marca '{marca_desejada}'")
    return produtos_filtrados

def _marca_similar_no_texto(marca: str, texto: str) -> bool:
    """
    Verifica se a marca está presente no texto com variações.
    """
    if not marca or not texto:
        return False
    
    # Mapeamento de variações de marca
    variacoes_marca = {
        "coca": ["coca cola", "coke"],
        "guarana": ["guaraná", "guarana", "guar"],
        "patagonia": ["patagon", "stella artois"],  # Patagonia está cadastrada como Stella Artois
        "heineken": ["heinek"],
        "budweiser": ["bud"],
        "stella": ["stella artois", "patagonia"],  # Mapeamento bidirecional
        "antarctica": ["antarct"]
    }
    
    # Verifica marca exata
    if marca in texto:
        return True
    
    # Verifica variações
    if marca in variacoes_marca:
        for variacao in variacoes_marca[marca]:
            if variacao in texto:
                return True
    
    # Verifica se alguma variação da marca está no mapeamento reverso
    for marca_key, variacoes in variacoes_marca.items():
        if marca in variacoes and marca_key in texto:
            return True
    
    return False

def gerar_busca_otimizada(analise_marca: Dict) -> str:
    """
    Gera termo de busca otimizado baseado na análise de marca.
    
    Args:
        analise_marca: Resultado da análise de marca.
    
    Returns:
        str: Termo de busca otimizado.
    """
    tipo_busca = analise_marca.get("tipo_busca")
    marca = analise_marca.get("marca")
    produto = analise_marca.get("produto")
    especificacoes = analise_marca.get("especificacoes", [])
    
    if tipo_busca == "marca_especifica" and marca:
        # Busca focada na marca
        termo = marca
        if produto and produto != "produto":
            termo = f"{produto} {marca}"
    elif tipo_busca == "produto_especifico" and marca:
        # Busca com marca e especificações
        termo = marca
        if especificacoes:
            termo += " " + " ".join(especificacoes)
    else:
        # Busca geral por categoria
        termo = produto if produto != "produto" else "todos produtos"
    
    logging.info(f"[BUSCA_OTIMIZADA] '{analise_marca}' → termo: '{termo}'")
    return termo