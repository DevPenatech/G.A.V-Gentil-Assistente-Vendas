# file: IA/utils/classificador_categoria.py
"""
Sistema de Classificação Inteligente de Categorias de Produtos
"""

import os
import re
import logging
import json
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    import ollama
    OLLAMA_DISPONIVEL = True
except ImportError:
    OLLAMA_DISPONIVEL = False
    logging.warning("Ollama não disponível - usando apenas fallback de regras")

# Configurações
NOME_MODELO_OLLAMA = os.getenv("OLLAMA_MODEL_NAME", "llama3.1")
HOST_OLLAMA = os.getenv("OLLAMA_HOST")
ARQUIVO_CACHE = Path(__file__).parent / "category_cache.json"

_cache_categoria: Dict[str, str] = {}
_cache_carregado = False

CATEGORIAS_PRINCIPAIS = [
    "bebidas",
    "alimentos",
    "limpeza",
    "higiene",
    "padaria",
    "açougue",
    "frios",
    "hortifruti",
    "petiscos",
    "doces",
    "laticínios",
    "congelados",
    "outros"
]

EXEMPLOS_CATEGORIA = {
    "bebidas": ["cerveja skol", "coca cola", "água mineral", "suco de laranja", "guaraná antartica"],
    "alimentos": ["arroz tipo 1", "feijão preto", "macarrão grano duro", "óleo de soja", "açúcar cristal"],
    "limpeza": ["sabão em pó omo", "detergente ypê", "água sanitária", "amaciante downy", "desinfetante pinho sol"],
    "higiene": ["shampoo seda", "sabonete dove", "creme dental colgate", "desodorante rexona", "papel higiênico neve"],
    "padaria": ["pão francês", "pão de forma", "biscoito cream cracker", "bolo de chocolate", "rosca doce"],
    "açougue": ["carne bovina picanha", "frango inteiro", "linguiça calabresa", "peixe tilápia", "bacon fatiado"],
    "frios": ["queijo mussarela", "presunto cozido", "mortadela bologna", "salame italiano", "requeijão cremoso"],
    "hortifruti": ["banana prata", "tomate salada", "batata inglesa", "alface crespa", "laranja pera"],
    "petiscos": ["salgadinho doritos", "amendoim japonês", "pipoca doce", "batata chips", "castanha de caju"],
    "doces": ["chocolate ao leite", "bala fini", "brigadeiro", "paçoca rolha", "chiclete trident"],
    "laticínios": ["leite integral", "iogurte natural", "manteiga sem sal", "creme de leite", "queijo cottage"],
    "congelados": ["sorvete kibon", "pizza congelada", "hambúrguer congelado", "açaí polpa", "lasanha congelada"]
}

def _carregar_cache() -> Dict[str, str]:
    """Carrega o cache de classificações anteriores.

    Returns:
        O cache de categorias.
    """
    global _cache_categoria, _cache_carregado
    
    if _cache_carregado:
        return _cache_categoria
        
    try:
        if ARQUIVO_CACHE.exists():
            with ARQUIVO_CACHE.open("r", encoding="utf-8") as f:
                _cache_categoria = json.load(f)
            logging.debug(f"Cache de categorias carregado: {len(_cache_categoria)} entradas")
        else:
            _cache_categoria = {}
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logging.warning(f"Erro ao carregar cache de categorias: {e}")
        _cache_categoria = {}
    
    _cache_carregado = True
    return _cache_categoria

def _salvar_cache():
    """Salva o cache atualizado no disco."""
    try:
        with ARQUIVO_CACHE.open("w", encoding="utf-8") as f:
            json.dump(_cache_categoria, f, ensure_ascii=False, indent=2)
        logging.debug(f"Cache de categorias salvo: {len(_cache_categoria)} entradas")
    except Exception as e:
        logging.error(f"Erro ao salvar cache de categorias: {e}")

def _normalizar_para_cache(termo: str) -> str:
    """Normaliza um termo para uso como chave de cache.

    Args:
        termo: O termo a ser normalizado.

    Returns:
        O termo normalizado.
    """
    if not termo:
        return ""
    
    import unicodedata
    termo = unicodedata.normalize('NFD', termo)
    termo = ''.join(c for c in termo if unicodedata.category(c) != 'Mn')
    
    return re.sub(r'\s+', ' ', termo.lower().strip())

def _classificar_por_ia_com_contexto(termo_busca: str, contexto_conversa: str = "") -> Optional[str]:
    """Classifica a categoria de um termo de busca usando IA com contexto.

    Args:
        termo_busca: O termo de busca.
        contexto_conversa: Contexto da conversa.

    Returns:
        A categoria classificada ou None em caso de erro.
    """
    if not OLLAMA_DISPONIVEL:
        return None
    
    try:
        if HOST_OLLAMA:
            import ollama
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            import ollama
            cliente_ollama = ollama
        
        info_categorias = []
        for categoria in CATEGORIAS_PRINCIPAIS[:-1]:
            exemplos = ', '.join(EXEMPLOS_CATEGORIA[categoria][:3])
            info_categorias.append(f"{categoria}: {exemplos}")
        
        texto_categorias = '\n'.join(info_categorias)
        
        # Prompt melhorado com contexto
        prompt = f"""Você é um classificador inteligente de produtos para um supermercado brasileiro. 

FRASE DO USUÁRIO: "{termo_busca}"

CONTEXTO DA CONVERSA:
{contexto_conversa if contexto_conversa else "Primeira interação"}

CATEGORIAS DISPONÍVEIS:
{texto_categorias}

INSTRUÇÕES AVANÇADAS:
- Analise o CONTEXTO da conversa para entender melhor a intenção
- Entenda frases coloquiais brasileiras:
  • "quero cerveja" → bebidas (não "outros")
  • "cervejinha gelada" → bebidas
  • "uma latinha" → bebidas (se contexto menciona bebida)
  • "pra limpeza" → limpeza
  • "comida pro jantar" → alimentos
  • "coisa doce" → doces
  • "produto de higiene" → higiene

- Ignore palavras como "quero", "preciso", "comprar", "ver", "buscar"
- Foque no PRODUTO principal mencionado
- Use o contexto para disambiguar termos vagos
- Se há dúvida entre duas categorias, escolha a mais específica

RESPONDA APENAS o nome da categoria (ex: bebidas, alimentos, limpeza).
Se não conseguir classificar com certeza, responda "outros".

CATEGORIA:"""

        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,  # Mais determinístico que antes
                "num_predict": 15,
                "stop": ["\n", ".", ",", " "]
            }
        )
        
        categoria_ia = resposta["message"]["content"].strip().lower()
        
        if categoria_ia in CATEGORIAS_PRINCIPAIS:
            logging.info(f"IA-CONTEXTO classificou '{termo_busca}' → '{categoria_ia}'")
            return categoria_ia
        else:
            logging.warning(f"IA-CONTEXTO retornou '{categoria_ia}' inválido para '{termo_busca}'")
            return None
            
    except Exception as e:
        logging.error(f"Erro na classificação por IA com contexto: {e}")
        return None

def _classificar_por_ia(termo_busca: str) -> Optional[str]:
    """Classifica a categoria de um termo de busca usando IA.

    Args:
        termo_busca: O termo de busca.

    Returns:
        A categoria classificada ou None em caso de erro.
    """
    if not OLLAMA_DISPONIVEL:
        return None
    
    try:
        if HOST_OLLAMA:
            import ollama
            cliente_ollama = ollama.Client(host=HOST_OLLAMA)
        else:
            import ollama
            cliente_ollama = ollama
        
        info_categorias = []
        for categoria in CATEGORIAS_PRINCIPAIS[:-1]:
            exemplos = ', '.join(EXEMPLOS_CATEGORIA[categoria][:3])
            info_categorias.append(f"{categoria}: {exemplos}")
        
        texto_categorias = '\n'.join(info_categorias)
        
        prompt = f"""Você é um classificador inteligente de produtos. Analise o que o usuário está dizendo e identifique a categoria do produto.

FRASE DO USUÁRIO: "{termo_busca}"

CATEGORIAS E EXEMPLOS:
{texto_categorias}

INSTRUÇÕES:
- Entenda frases como \"quero comprar coca cola\", \"preciso de sabão\", \"cerveja heineken\"
- Ignore palavras como \"quero\", \"preciso\", \"comprar\", \"ver\", \"marca\", etc.
- Foque no PRODUTO principal da frase
- Responda APENAS o nome da categoria
- Se não conseguir identificar, responda \"outros\"

EXEMPLOS:
- \"quero comprar cerveja skol\" → bebidas
- \"preciso de sabão em pó\" → limpeza  
- \"chocolate ao leite nestle\" → doces
- \"arroz tipo 1\" → alimentos
- \"ver as cervejas da heineken\" → bebidas

CATEGORIA:"""

        resposta = cliente_ollama.chat(
            model=NOME_MODELO_OLLAMA,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.2,
                "num_predict": 15,
                "stop": ["\n", ".", ",", " "]
            }
        )
        
        categoria_ia = resposta["message"]["content"].strip().lower()
        
        if categoria_ia in CATEGORIAS_PRINCIPAIS:
            logging.info(f"IA classificou '{termo_busca}' → '{categoria_ia}'")
            return categoria_ia
        else:
            logging.warning(f"IA retornou '{categoria_ia}' inválido para '{termo_busca}'")
            return None
            
    except Exception as e:
        logging.error(f"Erro na classificação por IA: {e}")
        return None

def classificar_categoria_com_contexto_ia(termo_busca: str, contexto_conversa: str = "", usar_ia: bool = True) -> str:
    """Classifica a categoria de um produto usando IA com contexto da conversa.

    Args:
        termo_busca: O termo de busca.
        contexto_conversa: Contexto da conversa para melhor classificação.
        usar_ia: Se deve usar IA para classificação.

    Returns:
        A categoria do produto.
    """
    if not termo_busca or not termo_busca.strip():
        return "outros"
    
    termo_busca = termo_busca.strip()
    
    # Para termos com contexto, não usa cache
    usar_cache = not contexto_conversa
    chave_cache = _normalizar_para_cache(termo_busca) if usar_cache else None
    
    if usar_cache:
        cache = _carregar_cache()
        if chave_cache in cache:
            resultado_cache = cache[chave_cache]
            logging.debug(f"Cache hit: '{termo_busca}' → '{resultado_cache}'")
            return resultado_cache
    
    categoria_final = "outros"
    if usar_ia:
        resultado_ia = _classificar_por_ia_com_contexto(termo_busca, contexto_conversa)
        if resultado_ia:
            categoria_final = resultado_ia
    
    # Salva no cache apenas se não usou contexto
    if usar_cache:
        cache = _carregar_cache()
        cache[chave_cache] = categoria_final
        _cache_categoria[chave_cache] = categoria_final
        
        if len(cache) % 5 == 0:
            _salvar_cache()
    
    logging.info(f"Classificado IA-CONTEXTO: '{termo_busca}' → '{categoria_final}'")
    return categoria_final

def classificar_categoria_produto(termo_busca: str, usar_ia: bool = True) -> str:
    """Classifica a categoria de um produto.

    Args:
        termo_busca: O termo de busca.
        usar_ia: Se deve usar IA para classificação.

    Returns:
        A categoria do produto.
    """
    if not termo_busca or not termo_busca.strip():
        return "outros"
    
    termo_busca = termo_busca.strip()
    chave_cache = _normalizar_para_cache(termo_busca)
    
    cache = _carregar_cache()
    if chave_cache in cache:
        resultado_cache = cache[chave_cache]
        logging.debug(f"Cache hit: '{termo_busca}' → '{resultado_cache}'")
        return resultado_cache
    
    categoria_final = "outros"
    if usar_ia:
        resultado_ia = _classificar_por_ia(termo_busca)
        if resultado_ia:
            categoria_final = resultado_ia
    
    cache[chave_cache] = categoria_final
    _cache_categoria[chave_cache] = categoria_final
    
    if len(cache) % 5 == 0:
        _salvar_cache()
    
    logging.info(f"Classificado IA-ONLY: '{termo_busca}' → '{categoria_final}'")
    return categoria_final

def obter_exemplos_categoria(categoria: str) -> List[str]:
    """Retorna exemplos de produtos de uma categoria.

    Args:
        categoria: A categoria.

    Returns:
        Uma lista de exemplos.
    """
    if categoria not in EXEMPLOS_CATEGORIA:
        return []
    
    exemplos = EXEMPLOS_CATEGORIA[categoria]
    return [ex.title() for ex in exemplos]

def obter_todas_categorias() -> List[str]:
    """Retorna todas as categorias disponíveis.

    Returns:
        Uma lista de todas as categorias.
    """
    return CATEGORIAS_PRINCIPAIS.copy()

def limpar_cache():
    """Limpa o cache de classificações."""
    global _cache_categoria, _cache_carregado
    _cache_categoria = {}
    _cache_carregado = False
    
    try:
        if ARQUIVO_CACHE.exists():
            ARQUIVO_CACHE.unlink()
        logging.info("Cache de categorias limpo")
    except Exception as e:
        logging.error(f"Erro ao limpar cache: {e}")

def obter_estatisticas_cache() -> Dict[str, int]:
    """Retorna estatísticas do cache.

    Returns:
        Um dicionário com as estatísticas.
    """
    cache = _carregar_cache()
    
    estatisticas = {"total": len(cache)}
    
    for categoria in CATEGORIAS_PRINCIPAIS:
        estatisticas[categoria] = sum(1 for cat in cache.values() if cat == categoria)
    
    return estatisticas

def testar_exemplos_classificacao():
    """Testa a classificação com exemplos conhecidos."""
    casos_teste = [
        ("cerveja skol", "bebidas"),
        ("sabão em pó", "limpeza"), 
        ("arroz branco", "alimentos"),
        ("shampoo", "higiene"),
        ("pão francês", "padaria"),
        ("carne bovina", "açougue"),
        ("chocolate", "doces"),
        ("salgadinho", "petiscos"),
        ("sorvete", "congelados"),
        ("produto desconhecido xyz", "outros")
    ]
    
    print("\n[TESTE] TESTE DE CLASSIFICACAO:")
    print("=" * 50)
    
    resultados = {"correto": 0, "errado": 0}
    
    for termo_busca, esperado in casos_teste:
        resultado = classificar_categoria_produto(termo_busca, usar_ia=False)
        status = "[OK]" if resultado == esperado else "[ERRO]"
        
        print(f"{status} '{termo_busca}' -> '{resultado}' (esperado: '{esperado}')")
        
        if resultado == esperado:
            resultados["correto"] += 1
        else:
            resultados["errado"] += 1
    
    print("=" * 50)
    print(f"[OK] Corretos: {resultados['correto']}")
    print(f"[ERRO] Errados: {resultados['errado']}")
    print(f"Taxa de acerto: {resultados['correto'] / len(casos_teste) * 100:.1f}%")
    
    return resultados

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("SISTEMA DE CLASSIFICACAO DE CATEGORIAS")
    print(f"Categorias disponiveis: {len(CATEGORIAS_PRINCIPAIS)}")
    print(f"IA disponivel: {'SIM' if OLLAMA_DISPONIVEL else 'NAO'}")
    
    testar_exemplos_classificacao()
    
    estatisticas = obter_estatisticas_cache()
    print(f"\nCache: {estatisticas['total']} entradas")
