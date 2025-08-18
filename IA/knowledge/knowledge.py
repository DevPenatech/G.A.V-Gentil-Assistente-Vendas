# file: IA/knowledge/knowledge.py
"""
Base de Conhecimento Inteligente para o G.A.V.
"""

import json
import logging
import os
import sys
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import ollama

# Adiciona paths necessários
utils_path = Path(__file__).resolve().parent.parent / "utils"
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))
    
from busca_aproximada import busca_aproximada_kb, MotorBuscaAproximada, analisar_qualidade_busca

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import database

# Configurações
CAMINHO_KB = Path(__file__).resolve().parent / "knowledge_base.json"
_base_conhecimento: Optional[Dict[str, List[Dict]]] = None
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")

# Instância global do motor de busca
_motor_busca = MotorBuscaAproximada()
HOST_OLLAMA = os.getenv("OLLAMA_HOST")

def _carregar_kb() -> Dict[str, List[Dict]]:
    """Carrega a base de conhecimento do disco para a memória.

    Returns:
        A base de conhecimento.
    """
    global _base_conhecimento
    if _base_conhecimento is not None:
        return _base_conhecimento

    kb_bruto: Dict[str, Dict] = {}
    try:
        if not CAMINHO_KB.exists() or CAMINHO_KB.stat().st_size == 0:
            logging.info(f"Arquivo '{CAMINHO_KB}' inexistente ou vazio.")
            kb_bruto = {}
        else:
            with CAMINHO_KB.open("r", encoding="utf-8") as f:
                kb_bruto = json.load(f)
            if not kb_bruto:
                kb_bruto = {}
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        logging.warning(f"Erro ao carregar '{CAMINHO_KB}': {e}. Usando base vazia.")
        kb_bruto = {}

    kb_indexado = {}
    
    for nome_canonico, dados_produto in kb_bruto.items():
        codprod = dados_produto.get("codprod")
        if not codprod:
            continue
        
        produto_base = {
            "codprod": codprod,
            "canonical_name": nome_canonico,
            "source": "knowledge_base"
        }
        
        canonico_normalizado = _motor_busca.normalizar_texto(nome_canonico)
        if canonico_normalizado not in kb_indexado:
            kb_indexado[canonico_normalizado] = []
        kb_indexado[canonico_normalizado].append(produto_base)
        
        palavras_relacionadas = dados_produto.get("related_words", [])
        for palavra in palavras_relacionadas:
            palavra_normalizada = _motor_busca.normalizar_texto(palavra)
            if palavra_normalizada and palavra_normalizada not in kb_indexado:
                kb_indexado[palavra_normalizada] = []
            kb_indexado[palavra_normalizada].append(produto_base)

    _base_conhecimento = kb_indexado
    
    total_termos = len(kb_indexado)
    total_produtos = len(set(p["codprod"] for produtos in kb_indexado.values() for p in produtos))
    
    logging.info(f"Base de conhecimento '{CAMINHO_KB}' carregada com {total_produtos} produtos e {total_termos} termos.")
    
    return _base_conhecimento

def _enriquecer_produtos_kb_com_dados_db(produtos_kb: List[Dict]) -> List[Dict]:
    """Enriquece produtos da KB com dados atualizados do banco.

    Args:
        produtos_kb: A lista de produtos da base de conhecimento.

    Returns:
        A lista de produtos enriquecida.
    """
    if not produtos_kb:
        return []
    
    produtos_enriquecidos = []
    
    for produto_kb in produtos_kb:
        codprod = produto_kb.get("codprod")
        if not codprod:
            continue
        
        produto_db = database.obter_produto_por_codprod(codprod)
        
        if produto_db:
            produto_enriquecido = {
                **produto_db,
                "source": "knowledge_base_enriched",
                "canonical_name": produto_kb.get("canonical_name")
            }
            produtos_enriquecidos.append(produto_enriquecido)
        else:
            logging.warning(f"Produto {codprod} da KB não encontrado no banco")
            produtos_enriquecidos.append(produto_kb)
    
    return produtos_enriquecidos

def encontrar_produto_na_kb(termo: str) -> List[Dict]:
    """Encontra um produto na base de conhecimento com busca tolerante a erros.

    Args:
        termo: O termo de busca.

    Returns:
        Uma lista de produtos que correspondem ao termo.
    """
    if not termo:
        return []
        
    kb = _carregar_kb()
    termo_minusculo = termo.lower().strip()
    
    termo_normalizado = _motor_busca.normalizar_texto(termo)
    if termo_normalizado in kb:
        logging.info(f"[KB] Busca exata encontrou: {termo_normalizado}")
        produtos_kb = kb[termo_normalizado]
        return _enriquecer_produtos_kb_com_dados_db(produtos_kb)
    
    resultados_fuzzy = busca_aproximada_kb(termo, kb, min_similaridade=0.8)
    if resultados_fuzzy:
        logging.info(f"[KB] Busca fuzzy (alta) encontrou {len(resultados_fuzzy)} produtos para: {termo}")
        return _enriquecer_produtos_kb_com_dados_db(resultados_fuzzy)
    
    resultados_fuzzy = busca_aproximada_kb(termo, kb, min_similaridade=0.6)
    if resultados_fuzzy:
        logging.info(f"[KB] Busca fuzzy (média) encontrou {len(resultados_fuzzy)} produtos para: {termo}")
        return _enriquecer_produtos_kb_com_dados_db(resultados_fuzzy)
    
    resultados_fuzzy = busca_aproximada_kb(termo, kb, min_similaridade=0.4)
    if resultados_fuzzy:
        logging.info(f"[KB] Busca fuzzy (baixa) encontrou {len(resultados_fuzzy)} produtos para: {termo}")
        return _enriquecer_produtos_kb_com_dados_db(resultados_fuzzy)
    
    produtos_correspondentes = []
    codprods_vistos = set()
    
    termo_normalizado = _motor_busca.normalizar_texto(termo)
    termo_corrigido = _motor_busca.aplicar_correcoes(termo_normalizado)
    
    for termo_indexado, produtos in kb.items():
        indexado_normalizado = _motor_busca.normalizar_texto(termo_indexado)
        
        if (termo_corrigido in indexado_normalizado or 
            indexado_normalizado in termo_corrigido or
            termo_normalizado in indexado_normalizado):
            
            for produto in produtos:
                codprod = produto.get("codprod")
                if codprod and codprod not in codprods_vistos:
                    produtos_correspondentes.append(produto)
                    codprods_vistos.add(codprod)
    
    if produtos_correspondentes:
        logging.info(f"[KB] Busca por contenção encontrou {len(produtos_correspondentes)} produtos para: {termo}")
        return _enriquecer_produtos_kb_com_dados_db(produtos_correspondentes)
    
    logging.info(f"[KB] Nenhum produto encontrado para: {termo}")
    return []

def encontrar_produto_na_kb_com_analise(termo: str) -> Tuple[List[Dict], Dict]:
    """Busca produtos e retorna uma análise da qualidade da busca.

    Args:
        termo: O termo de busca.

    Returns:
        Uma tupla contendo a lista de produtos e a análise da busca.
    """
    produtos = encontrar_produto_na_kb(termo)
    analise = analisar_qualidade_busca(termo, produtos)
    return produtos, analise

def atualizar_kb(termo: str, produto_correto: Dict):
    """Atualiza a base de conhecimento com uma nova associação.

    Args:
        termo: O termo de busca.
        produto_correto: O produto correto associado ao termo.
    """
    if not termo or not produto_correto or not produto_correto.get("codprod"):
        logging.warning("Tentativa de atualizar KB com dados inválidos.")
        return

    termo_normalizado = _motor_busca.normalizar_texto(termo)

    try:
        with CAMINHO_KB.open("r", encoding="utf-8") as f:
            kb_bruto = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        kb_bruto = {}

    nome_canonico = produto_correto.get("descricao") or produto_correto.get("canonical_name", f"Produto {produto_correto['codprod']}")
    
    entrada = None
    chave_entrada = None
    for nome, entrada_existente in kb_bruto.items():
        if entrada_existente.get("codprod") == produto_correto["codprod"]:
            entrada = entrada_existente
            chave_entrada = nome
            break
    
    if entrada is None:
        entrada = {
            "codprod": produto_correto["codprod"],
            "canonical_name": nome_canonico,
            "related_words": [],
        }
        chave_entrada = nome_canonico
        kb_bruto[chave_entrada] = entrada

    palavras_existentes = [_motor_busca.normalizar_texto(w) for w in entrada["related_words"]]
    if termo_normalizado not in palavras_existentes:
        entrada["related_words"].append(termo)
        logging.info(f"Adicionado termo '{termo}' ao produto {nome_canonico}")

    try:
        with CAMINHO_KB.open("w", encoding="utf-8") as f:
            json.dump(kb_bruto, f, indent=2, ensure_ascii=False)
        logging.info(f"KB atualizado com novo termo relacionado '{termo}'")
    except Exception as e:
        logging.error(f"Falha ao salvar a base de conhecimento: {e}")

    global _base_conhecimento
    _base_conhecimento = None

def obter_estatisticas_kb() -> Dict:
    """Retorna estatísticas da base de conhecimento.

    Returns:
        Um dicionário com as estatísticas.
    """
    kb = _carregar_kb()
    
    if not kb:
        return {
            "total_terms": 0,
            "total_products": 0,
            "coverage": 0.0,
            "avg_terms_per_product": 0.0
        }
    
    total_termos = len(kb)
    codprods_produto = set()
    contagens_termos = []
    
    for termo, produtos in kb.items():
        for produto in produtos:
            codprod = produto.get("codprod")
            if codprod:
                codprods_produto.add(codprod)
        contagens_termos.append(len(produtos))
    
    total_produtos = len(codprods_produto)
    
    contagem_produtos_db = database.get_products_count()
    cobertura = (total_produtos / contagem_produtos_db * 100) if contagem_produtos_db > 0 else 0.0
    
    media_termos = sum(contagens_termos) / len(contagens_termos) if contagens_termos else 0.0
    
    return {
        "total_terms": total_termos,
        "total_products": total_produtos,
        "total_products_in_db": contagem_produtos_db,
        "coverage_percentage": cobertura,
        "avg_terms_per_product": media_termos,
        "kb_file_size": CAMINHO_KB.stat().st_size if CAMINHO_KB.exists() else 0
    }

def otimizar_kb():
    """Otimiza a base de conhecimento removendo duplicatas e termos inválidos."""
    try:
        with CAMINHO_KB.open("r", encoding="utf-8") as f:
            kb_bruto = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.error("Não foi possível carregar KB para otimização")
        return False
    
    contagem_otimizados = 0
    
    for nome_canonico, dados_produto in kb_bruto.items():
        if "related_words" not in dados_produto:
            continue
        
        palavras_originais = dados_produto["related_words"]
        
        palavras_unicas = []
        vistos_normalizados = set()
        
        for palavra in palavras_originais:
            if not palavra or len(palavra.strip()) < 2:
                continue
            
            normalizado = _motor_busca.normalizar_texto(palavra)
            if normalizado and normalizado not in vistos_normalizados:
                palavras_unicas.append(palavra.strip())
                vistos_normalizados.add(normalizado)
        
        if len(palavras_unicas) != len(palavras_originais):
            dados_produto["related_words"] = palavras_unicas
            contagem_otimizados += 1
    
    try:
        with CAMINHO_KB.open("w", encoding="utf-8") as f:
            json.dump(kb_bruto, f, indent=2, ensure_ascii=False)
        
        logging.info(f"KB otimizada: {contagem_otimizados} produtos processados")
        
        global _base_conhecimento
        _base_conhecimento = None
        
        return True
        
    except Exception as e:
        logging.error(f"Erro ao salvar KB otimizada: {e}")
        return False

def _normalizar(texto: str) -> str:
    """Remove acentos e normaliza o texto para minúsculas.

    Args:
        texto: O texto a ser normalizado.

    Returns:
        O texto normalizado.
    """
    nfkd = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")

def _palavras_relacionadas_heuristicas(descricao: str) -> List[str]:
    """Gera variações de busca para uma descrição de produto.

    Args:
        descricao: A descrição do produto.

    Returns:
        Uma lista de variações de busca.
    """
    normalizado = _normalizar(descricao)
    tokens = [t for t in re.split(r"\W+", normalizado) if t and len(t) > 1]
    variacoes = set()

    variacoes.add(normalizado)
    variacoes.add(" ".join(tokens))
    variacoes.add("".join(tokens))
    
    for char in ["-", ".", "(", ")", "[", "]"]:
        if char in normalizado:
            versao_limpa = normalizado.replace(char, " ")
            variacoes.add(" ".join(versao_limpa.split()))
    
    for token in tokens:
        if len(token) >= 3:
            variacoes.add(token)
    
    for i in range(len(tokens) - 1):
        combo = f"{tokens[i]} {tokens[i+1]}"
        variacoes.add(combo)
    
    variacoes_filtradas = [v for v in variacoes if 2 <= len(v) <= 50]
    
    return list(set(variacoes_filtradas))[:15]

def _gerar_variacoes_ia(descricao: str) -> List[str]:
    """Gera variações de busca usando IA.

    Args:
        descricao: A descrição do produto.

    Returns:
        Uma lista de variações de busca.
    """
    if not HOST_OLLAMA:
        logging.warning("OLLAMA_HOST não configurado, usando variações heurísticas")
        return _palavras_relacionadas_heuristicas(descricao)

    prompt = f"""Gere variações de busca para o produto: "{descricao}"\n\nInclua:\n- Abreviações comuns (ex: refri para refrigerante)\n- Gírias e apelidos\n- Variações de escrita\n- Termos relacionados à marca/categoria\n- Diferentes formas de escrever quantidades/medidas\n\nResponda APENAS com uma lista JSON de strings, máximo 20 variações.\nExemplo: ["variacao1", "variacao2", "variacao3"]\n\nProduto: {descricao}\nVariações:"""

    try:
        cliente = ollama.Client(host=HOST_OLLAMA)
        resposta = cliente.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "max_tokens": 300}
        )
        
        conteudo = resposta["message"]["content"].strip()
        
        match_json = re.search(r'[[.*]]', conteudo, re.DOTALL)
        if match_json:
            try:
                variacoes = json.loads(match_json.group(0))
                if isinstance(variacoes, list):
                    variacoes_validas = []
                    for var in variacoes:
                        if isinstance(var, str) and 2 <= len(var.strip()) <= 50:
                            variacoes_validas.append(var.strip().lower())
                    
                    return variacoes_validas[:20]
            except json.JSONDecodeError:
                pass
    
    except Exception as e:
        logging.warning(f"Erro ao gerar variações com IA: {e}")
    
    return _palavras_relacionadas_heuristicas(descricao)

def reconstruir_base_conhecimento():
    """Reconstrói a base de conhecimento.

    Returns:
        True se a reconstrução for bem-sucedida, False caso contrário.
    """
    logging.info("=== INICIANDO GERAÇÃO DA BASE DE CONHECIMENTO (stream) ===")

    if CAMINHO_KB.exists():
        caminho_backup = CAMINHO_KB.with_suffix(".json.backup")
        try:
            import shutil
            shutil.copy2(CAMINHO_KB, caminho_backup)
            logging.info(f"Backup criado: {caminho_backup}")
        except Exception as e:
            logging.warning(f"Falha ao criar backup: {e}")

    produtos = database.obter_todos_produtos_ativos()
    if not produtos:
        logging.error("Nenhum produto encontrado no banco de dados")
        return False

    caminho_temporario = CAMINHO_KB.with_suffix(".ndjson.tmp")
    contagem_processados = 0
    total_termos = 0

    try:
        with caminho_temporario.open("w", encoding="utf-8") as f:
            try:
                for i, produto in enumerate(produtos, 1):
                    codprod = produto.get("codprod")
                    descricao = produto.get("descricao", "")

                    if not codprod or not descricao:
                        continue

                    logging.info(f"Processando produto {i}/{len(produtos)}: {descricao}")

                    variacoes = _gerar_variacoes_ia(descricao)
                    vars_heuristicas = _palavras_relacionadas_heuristicas(descricao)
                    todas_variacoes = list(set(variacoes + vars_heuristicas))[:25]

                    entrada_kb = {
                        "codprod": codprod,
                        "canonical_name": descricao,
                        "related_words": todas_variacoes
                    }

                    f.write(json.dumps({descricao: entrada_kb}, ensure_ascii=False) + "\n")
                    f.flush()

                    contagem_processados += 1
                    total_termos += len(todas_variacoes)

            except KeyboardInterrupt:
                logging.warning("⚠ Interrupção detectada (CTRL+C). Finalizando com dados parciais...")

        from collections import ChainMap
        with caminho_temporario.open("r", encoding="utf-8") as f:
            dados_finais = dict(ChainMap(*[json.loads(line) for line in f]))

        with CAMINHO_KB.open("w", encoding="utf-8") as f:
            json.dump(dados_finais, f, indent=2, ensure_ascii=False)

        logging.info("=== BASE DE CONHECIMENTO GERADA COM SUCESSO ===")
        logging.info(f"Produtos processados: {contagem_processados}")
        logging.info(f"Total de termos relacionados: {total_termos}")

        global _base_conhecimento
        _base_conhecimento = None
        return True

    except Exception as e:
        logging.error(f"Erro ao gerar KB: {e}")
        return False
    finally:
        if caminho_temporario.exists():
            caminho_temporario.unlink()


def validar_integridade_kb() -> Dict:
    """Valida a integridade da base de conhecimento.

    Returns:
        Um dicionário com o resultado da validação.
    """
    try:
        with CAMINHO_KB.open("r", encoding="utf-8") as f:
            kb_bruto = json.load(f)
    except Exception as e:
        return {"valid": False, "error": f"Erro ao carregar KB: {e}"}
    
    problemas = []
    entradas_validas = 0
    total_entradas = len(kb_bruto)
    
    for nome_canonico, dados_produto in kb_bruto.items():
        problemas_entrada = []
        
        if not isinstance(dados_produto, dict):
            problemas_entrada.append("Entrada não é um dicionário")
            continue
        
        if "codprod" not in dados_produto:
            problemas_entrada.append("Campo 'codprod' ausente")
        elif not isinstance(dados_produto["codprod"], int):
            problemas_entrada.append("Campo 'codprod' não é inteiro")
        
        if "related_words" not in dados_produto:
            problemas_entrada.append("Campo 'related_words' ausente")
        elif not isinstance(dados_produto["related_words"], list):
            problemas_entrada.append("Campo 'related_words' não é lista")
        
        if "codprod" in dados_produto:
            produto_db = database.get_product_by_codprod(dados_produto["codprod"])
            if not produto_db:
                problemas_entrada.append(f"Produto {dados_produto['codprod']} não encontrado no banco")
        
        if problemas_entrada:
            problemas.append({
                "canonical_name": nome_canonico,
                "issues": problemas_entrada
            })
        else:
            entradas_validas += 1
    
    return {
        "valid": len(problemas) == 0,
        "total_entries": total_entradas,
        "valid_entries": entradas_validas,
        "invalid_entries": len(problemas),
        "issues": problemas[:10],
        "integrity_score": (entradas_validas / total_entradas * 100) if total_entradas > 0 else 0
    }

def buscar_kb_com_sugestoes(termo: str) -> Dict:
    """Busca na base de conhecimento com sugestões automáticas.

    Args:
        termo: O termo de busca.

    Returns:
        Um dicionário com os resultados da busca.
    """
    produtos = encontrar_produto_na_kb(termo)
    
    resultado = {
        "products": produtos,
        "suggestions": [],
        "search_quality": "unknown"
    }
    
    if produtos:
        analise = analisar_qualidade_busca(termo, produtos)
        resultado["search_quality"] = analise.get("quality", "unknown")
        
        if analise.get("quality") in ["fair", "poor"]:
            resultado["suggestions"] = analise.get("suggestions", [])
    else:
        corrigido = _motor_busca.aplicar_correcoes(termo)
        if corrigido != _motor_busca.normalizar_texto(termo):
            resultado["suggestions"].append(corrigido)
        
        sinonimos = _motor_busca.expandir_com_sinonimos(termo)
        resultado["suggestions"].extend(sinonimos[:2])
        
        resultado["search_quality"] = "no_results"
    
    return resultado

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler('knowledge_generation.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    sucesso = reconstruir_base_conhecimento()
    
    if sucesso:
        validacao = validar_integridade_kb()
        if validacao["valid"]:
            logging.info("✅ Base de conhecimento gerada e validada com sucesso!")
        else:
            logging.warning(f"⚠️ Base gerada com {validacao['invalid_entries']} problemas")
            
        estatisticas = obter_estatisticas_kb()
        logging.info(f"📊 Estatísticas: {estatisticas['total_products']} produtos, {estatisticas['total_terms']} termos, {estatisticas['coverage_percentage']:.1f}% cobertura")
    else:
        logging.error("❌ Falha na geração da base de conhecimento")
        sys.exit(1)
