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
        prompt_ia = f"""Você é um especialista em identificar marcas e produtos específicos em buscas.

MENSAGEM DO USUÁRIO: "{mensagem}"

CONTEXTO DA CONVERSA:
{contexto_conversa if contexto_conversa else "Primeira interação"}

ANALISE E DETERMINE:

1. TIPO DE BUSCA:
   - "marca_especifica": SOMENTE quando o usuário menciona uma marca específica explicitamente
   - "categoria_geral": Quando o usuário quer uma categoria sem mencionar marca específica
   - "produto_especifico": Quando o usuário quer produto específico com detalhes

2. COMPONENTES:
   - marca: Nome da marca mencionada EXPLICITAMENTE (null se não houver menção direta)
   - produto: Tipo de produto base (cerveja, refrigerante, etc)
   - especificacoes: Detalhes como sabor, tamanho, embalagem
   - categoria: Categoria geral do produto

REGRAS IMPORTANTES (ABORDAGEM IA-FIRST):
- Analise TODAS as palavras da mensagem para identificar nomes comerciais/marcas
- "fini", "skol", "coca", "heineken" etc. são MARCAS ESPECÍFICAS mesmo quando acompanhadas de categoria
- Se há QUALQUER palavra que pareça nome de marca comercial = marca_especifica
- Se só menciona categoria sem marca específica = categoria_geral
- NÃO invente marcas que não foram mencionadas na mensagem
- Use seu conhecimento de marcas comerciais brasileiras para identificar nomes de empresas

EXEMPLOS CORRETOS (IA-FIRST):
- "quero cerveja" → categoria_geral: marca=null, produto=cerveja
- "cerveja" → categoria_geral: marca=null, produto=cerveja  
- "quero cerveja skol" → marca_especifica: marca=skol, produto=cerveja
- "skol" → marca_especifica: marca=skol, produto=cerveja
- "heineken lata" → marca_especifica: marca=heineken, produto=cerveja
- "quero refrigerante" → categoria_geral: marca=null, produto=refrigerante
- "bala fini" → marca_especifica: marca=fini, produto=bala  (FINI é a marca, bala é o produto!)
- "quero bala fini" → marca_especifica: marca=fini, produto=bala  (FINI é a marca!)
- "fini" → marca_especifica: marca=fini, produto=bala
- "coca cola" → marca_especifica: marca=coca cola, produto=refrigerante
- "quero omo" → marca_especifica: marca=omo, produto=detergente

ATENÇÃO ESPECIAL - IDENTIFICAÇÃO CORRETA DE MARCA:
- Em "bala fini": "fini" é a MARCA (fabricante), "bala" é o PRODUTO (categoria)
- Em "cerveja skol": "skol" é a MARCA (fabricante), "cerveja" é o PRODUTO (categoria)
- Em "quero cerveja skol": "skol" é a MARCA, "cerveja" é categoria
- Sempre identifique o nome do FABRICANTE/EMPRESA como marca, não o tipo de produto
- JAMAIS confunda categoria (cerveja, bala, refrigerante) com marca (skol, fini, coca-cola)
- Priorize nomes próprios comerciais sobre palavras genéricas de categoria

INSTRUÇÕES IA-FIRST:
- Use seu amplo conhecimento de marcas comerciais brasileiras
- Identifique qualquer palavra que seja nome de empresa/fabricante
- Seja assertivo: se reconhece uma marca, classifique como marca_especifica

RESPONDA EM JSON:
{{
  "tipo_busca": "categoria_geral",
  "marca": null,
  "produto": "cerveja",
  "especificacoes": [],
  "categoria": "bebidas",
  "prioridade_marca": false
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
                "num_predict": 150
            }
        )
        
        resposta_ia = resposta["message"]["content"].strip()
        logging.debug(f"[MARCA_PRODUTO_IA] Mensagem: '{mensagem}' → IA: '{resposta_ia}'")
        
        # Extrai JSON da resposta
        import json
        print(f">>> DEBUG: [EXTRAÇÃO_JSON] Resposta completa da IA: {resposta_ia}")
        
        try:
            # Tenta extrair JSON de várias formas
            json_match = re.search(r'\{.*?\}', resposta_ia, re.DOTALL)
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
        logging.error(f"[MARCA_PRODUTO_IA] Erro: {e}")
        return _detectar_marca_fallback(mensagem)

def _detectar_marca_fallback(mensagem: str) -> Dict:
    """
    Fallback IA-FIRST: usa heurísticas simples mas tenta detectar marcas com IA básica.
    """
    print(f">>> DEBUG: [FALLBACK] Executando fallback para: '{mensagem}'")
    mensagem_lower = mensagem.lower().strip()
    
    # Lista de marcas conhecidas (para fallback robusto)
    marcas_conhecidas = {
        "heineken": "cerveja",
        "skol": "cerveja", 
        "brahma": "cerveja",
        "antartica": "cerveja",
        "stella": "cerveja",
        "corona": "cerveja",
        "budweiser": "cerveja",
        "fini": "bala",
        "coca": "refrigerante",
        "pepsi": "refrigerante",
        "guarana": "refrigerante",
        "omo": "detergente",
        "ariel": "detergente"
    }
    
    # Verifica se alguma marca conhecida está na mensagem
    for marca, produto in marcas_conhecidas.items():
        if marca in mensagem_lower:
            print(f">>> DEBUG: [FALLBACK] ✅ Marca conhecida encontrada: {marca} ({produto})")
            return {
                "tipo_busca": "marca_especifica",
                "marca": marca,
                "produto": produto,
                "especificacoes": [],
                "categoria": "bebidas" if produto == "cerveja" else "outros",
                "prioridade_marca": True
            }
    
    # Fallback simplificado: se contém palavras que parecem marca, considera marca_especifica
    # Palavras curtas e específicas que podem ser marcas
    palavras = mensagem_lower.split()
    possivel_marca = None
    
    # Heurística simples: palavras de 3-8 caracteres que não são palavras comuns podem ser marcas
    palavras_comuns = ["quero", "preciso", "buscar", "ver", "comprar", "onde", "tem", "para", "com", "sem", "mais", "menos", "cerveja", "refrigerante", "bala"]
    
    for palavra in palavras:
        # Remove pontuação
        palavra_limpa = palavra.strip(".,!?")
        
        # Se a palavra não é comum E tem tamanho de marca típica
        if (palavra_limpa not in palavras_comuns and 
            len(palavra_limpa) >= 3 and 
            len(palavra_limpa) <= 10 and
            not palavra_limpa.isdigit()):
            possivel_marca = palavra_limpa
            print(f">>> DEBUG: [FALLBACK] Possível marca detectada: {possivel_marca}")
            break
    
    # Determina categoria baseada em contexto simples
    if any(word in mensagem_lower for word in ["cerveja", "beer"]):
        categoria = "bebidas"
        produto = "cerveja"
    elif any(word in mensagem_lower for word in ["refrigerante", "refri", "coca", "pepsi"]):
        categoria = "bebidas"
        produto = "refrigerante"
    elif any(word in mensagem_lower for word in ["bala", "doce", "chocolate", "fini"]):
        categoria = "doces"
        produto = "bala"
    elif any(word in mensagem_lower for word in ["agua", "água"]):
        categoria = "bebidas"
        produto = "agua"
    else:
        categoria = "outros"
        produto = "produto"
    
    # Se encontrou possível marca, considera marca_especifica
    if possivel_marca:
        tipo_busca = "marca_especifica"
        prioridade_marca = True
        marca_final = possivel_marca
    else:
        tipo_busca = "categoria_geral"
        prioridade_marca = False
        marca_final = None
    
    return {
        "tipo_busca": tipo_busca,
        "marca": marca_final,
        "produto": produto,
        "especificacoes": [],
        "categoria": categoria,
        "prioridade_marca": prioridade_marca
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