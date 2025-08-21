# file: IA/core/gerenciador_sessao.py
"""
Gerenciador de Sessões do G.A.V.
"""

import os
import json
import logging
import pickle
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
import redis
import re
from IA.utils.classificador_intencao import detectar_intencao_usuario_com_ia


# Logger
logger = logging.getLogger(__name__)
# Configurações
REDIS_ATIVADO = os.getenv("REDIS_ENABLED", "false").lower() == "true"
HOST_REDIS = os.getenv("REDIS_HOST", "localhost")
PORTA_REDIS = int(os.getenv("REDIS_PORT", 6379))
DB_REDIS = int(os.getenv("REDIS_DB", 0))
TTL_SESSAO = int(os.getenv("SESSION_TTL", 86400))  # 24 horas em segundos

# Cliente Redis (opcional)
cliente_redis = None
if REDIS_ATIVADO:
    try:
        cliente_redis = redis.Redis(
            host=HOST_REDIS,
            port=PORTA_REDIS,
            db=DB_REDIS,
            decode_responses=False
        )
        cliente_redis.ping()
        logging.info(f"Redis conectado: {HOST_REDIS}:{PORTA_REDIS}")
    except Exception as e:
        logging.warning(f"Redis não disponível: {e}. Usando armazenamento em arquivo.")
        cliente_redis = None


def resumir_texto_semantico(texto: str, max_frases: int = 2) -> str:
    """Gera um resumo simples baseado em frequência de palavras.

    Args:
        texto: Texto a ser resumido.
        max_frases: Número máximo de frases no resumo.

    Returns:
        Texto resumido contendo as frases mais relevantes.
    """
    sentences = re.split(r"(?<=[.!?])\s+", texto)
    if len(sentences) <= max_frases:
        return texto.strip()

    palavras = re.findall(r"\w+", texto.lower(), flags=re.UNICODE)
    frequencias = Counter(p for p in palavras if len(p) > 3)

    pontuacoes = []
    for frase in sentences:
        score = sum(frequencias.get(palavra, 0) for palavra in re.findall(r"\w+", frase.lower(), flags=re.UNICODE))
        pontuacoes.append((score, frase))

    pontuacoes.sort(key=lambda x: x[0], reverse=True)
    melhores = [frase for _, frase in pontuacoes[:max_frases]]
    return " ".join(melhores).strip()


def _resumo_para_string(resumo: Union[str, List[Dict[str, str]]]) -> str:
    """Converte estrutura de resumo em string legível."""
    if not resumo:
        return ""
    if isinstance(resumo, str):
        return resumo

    linhas = []
    for item in resumo:
        role = "Cliente" if item.get("role") == "user" else "G.A.V."
        acao = item.get("action_type", "")
        info_acao = f" [{acao}]" if acao else ""
        linhas.append(f"{role}{info_acao}: {item.get('summary', '')}")

    return " | ".join(linhas)

def _obter_caminho_arquivo_sessao(id_sessao: str) -> str:
    """Retorna o caminho do arquivo de sessão.

    Args:
        id_sessao: O ID da sessão.

    Returns:
        O caminho do arquivo de sessão.
    """
    logging.debug(f"Obtendo caminho do arquivo de sessão para o ID: {id_sessao}")
    diretorio_sessoes = "data"
    if not os.path.exists(diretorio_sessoes):
        os.makedirs(diretorio_sessoes)
    
    id_seguro = id_sessao.replace(":", "_").replace("/", "_")
    caminho_arquivo = os.path.join(diretorio_sessoes, f"sessao_{id_seguro}.json")
    logging.debug(f"Caminho do arquivo de sessão: {caminho_arquivo}")
    return caminho_arquivo

def carregar_sessao(id_sessao: str) -> Dict:
    """Carrega os dados da sessão do armazenamento.

    Args:
        id_sessao: O ID da sessão.

    Returns:
        Um dicionário com os dados da sessão.
    """
    logging.debug(f"Carregando sessão para o ID: {id_sessao}")
    sessao_padrao = {
        "contexto_cliente": None,
        "carrinho_compras": [],
        "historico_conversa": [],
        "resumo_conversa": [],
        "ultimo_tipo_busca": None,
        "ultimos_parametros_busca": {},
        "offset_atual": 0,
        "ultimos_produtos_mostrados": [],
        "ultima_acao_bot": None,
        "acao_pendente": None,
        "selecao_produto_pendente": None,
        "quantidade_pendente": None,
        "ultimo_termo_busca_kb": None,
        "ultimos_resultados_busca": [],
        "ultima_analise_busca": {},
        "ultimas_sugestoes_busca": [],
        "criado_em": datetime.now().isoformat(),
        "ultima_atividade": datetime.now().isoformat()
    }
    
    if cliente_redis:
        try:
            dados = cliente_redis.get(f"sessao:{id_sessao}")
            if dados:
                sessao = pickle.loads(dados)
                logging.debug(f"[SESSAO] Sessão carregada do Redis: {id_sessao}")
                return sessao
        except Exception as e:
            logging.warning(f"Erro ao carregar sessão do Redis: {e}")
    
    caminho_arquivo = _obter_caminho_arquivo_sessao(id_sessao)
    
    if os.path.exists(caminho_arquivo):
        try:
            with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                sessao = json.load(f)
                logging.debug(f"[SESSAO] Sessão carregada do arquivo: {caminho_arquivo}")
                
                for chave, valor in sessao_padrao.items():
                    if chave not in sessao:
                        sessao[chave] = valor
                
                return sessao
        except Exception as e:
            logging.error(f"Erro ao carregar sessão do arquivo: {e}")
    
    logging.info(f"[SESSAO] Nova sessão criada: {id_sessao}")
    return sessao_padrao

def salvar_sessao(id_sessao: str, dados_sessao: Dict):
    """Salva os dados da sessão no armazenamento.

    Args:
        id_sessao: O ID da sessão.
        dados_sessao: Os dados da sessão.
    """
    logging.debug(f"Salvando sessão para o ID: {id_sessao}")
    dados_sessao["ultima_atividade"] = datetime.now().isoformat()
    _resumir_mensagens_antigas(dados_sessao)
    
    if cliente_redis:
        try:
            cliente_redis.setex(
                f"sessao:{id_sessao}",
                TTL_SESSAO,
                pickle.dumps(dados_sessao)
            )
            logging.debug(f"[SESSAO] Sessão salva no Redis: {id_sessao}")
            return
        except Exception as e:
            logging.warning(f"Erro ao salvar sessão no Redis: {e}")
    
    caminho_arquivo = _obter_caminho_arquivo_sessao(id_sessao)
    
    try:
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados_sessao, f, ensure_ascii=False, indent=2)
        logging.debug(f"[SESSAO] Sessão salva no arquivo: {caminho_arquivo}")
    except Exception as e:
        logging.error(f"Erro ao salvar sessão no arquivo: {e}")

def limpar_sessao(id_sessao: str):
    """Limpa os dados da sessão.

    Args:
        id_sessao: O ID da sessão.
    """
    logging.debug(f"Limpando sessão para o ID: {id_sessao}")
    if cliente_redis:
        try:
            cliente_redis.delete(f"sessao:{id_sessao}")
            logging.debug(f"[SESSAO] Sessão removida do Redis: {id_sessao}")
        except Exception as e:
            logging.warning(f"Erro ao remover sessão do Redis: {e}")
    
    try:
        caminho_arquivo = _obter_caminho_arquivo_sessao(id_sessao)
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
            logging.debug(f"[SESSAO] Arquivo de sessão removido: {caminho_arquivo}")
    except Exception as e:
        logging.error(f"[SESSAO] Erro ao remover arquivo de sessão: {e}")
    
def limpar_sessoes_antigas():
    """Remove sessões antigas (mais de 7 dias)."""
    logging.debug("Limpando sessões antigas.")
    if cliente_redis:
        try:
            logging.info("Redis gerencia expiração automaticamente")
        except Exception as e:
            logging.warning(f"Erro ao limpar sessões Redis: {e}")
    
    diretorio_sessoes = "data"
    if os.path.exists(diretorio_sessoes):
        data_corte = datetime.now() - timedelta(days=7)
        
        for nome_arquivo in os.listdir(diretorio_sessoes):
            if nome_arquivo.startswith("sessao_"):
                caminho_arquivo = os.path.join(diretorio_sessoes, nome_arquivo)
                
                try:
                    tempo_arquivo = datetime.fromtimestamp(os.path.getmtime(caminho_arquivo))
                    if tempo_arquivo < data_corte:
                        os.remove(caminho_arquivo)
                        logging.info(f"Sessão antiga removida: {nome_arquivo}")
                except Exception as e:
                    logging.warning(f"Erro ao processar {nome_arquivo}: {e}")

def formatar_lista_produtos_para_exibicao(produtos: List[Dict], titulo: str, tem_mais: bool, offset: int = 0) -> str:
    """Formata uma lista de produtos para exibição no WhatsApp.

    Args:
        produtos: A lista de produtos.
        titulo: O título da lista.
        tem_mais: Um booleano indicando se há mais produtos.
        offset: O offset da paginação.

    Returns:
        A lista de produtos formatada.
    """
    logging.debug(f"Formatando lista de produtos para exibição. Título: {titulo}, Quantidade: {len(produtos)}, Tem mais: {tem_mais}, Offset: {offset}")
    if not produtos:
        return f"❌ {titulo}\nNão achei esse item. Posso sugerir similares?"
    
    contagem_real = len(produtos)
    produtos_limitados = produtos[:min(contagem_real, 10)]
    contagem_exibicao = len(produtos_limitados)

    resposta = f"📦 *{titulo}:*\n\n"

    for i, p in enumerate(produtos_limitados, start=offset + 1):
        preco = p.get('pvenda') or p.get('preco_varejo', 0.0)
        preco_str = f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        nome_produto = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')
        
        resposta += f"*{i}.* {nome_produto}\n"
        resposta += f"    💰 {preco_str}\n\n"
    
    if contagem_exibicao == 1:
        resposta += f"Digite *{offset + 1}* para selecionar este produto."
    elif contagem_exibicao == 2:
        resposta += (
            f"Qual você quer? Digite *{offset + 1}* ou *{offset + 2}*."
        )
    elif contagem_exibicao <= 5:
        numeros = [str(offset + i + 1) for i in range(contagem_exibicao)]
        resposta += f"Qual você quer? Digite {', '.join(numeros[:-1])} ou *{numeros[-1]}*."
    else:
        primeiro_num = offset + 1
        ultimo_num = offset + contagem_exibicao
        resposta += f"Qual você quer? Digite o número de *{primeiro_num}* a *{ultimo_num}*."
    
    if tem_mais:
        resposta += "\n📝 Digite *mais* para ver outros produtos!"
    
    logging.debug(f"Lista de produtos formatada: {resposta}")
    return resposta

def formatar_lista_produtos_inteligente(produtos_normais: List[Dict], produtos_promo: List[Dict], titulo: str) -> str:
    """Formata uma lista combinada de produtos normais e promocionais.

    Args:
        produtos_normais: A lista de produtos normais.
        produtos_promo: A lista de produtos em promoção.
        titulo: O título da lista.

    Returns:
        A lista de produtos formatada.
    """
    logging.debug(f"Formatando lista de produtos inteligente. Título: {titulo}, Produtos normais: {len(produtos_normais)}, Produtos em promoção: {len(produtos_promo)}")
    if not produtos_normais and not produtos_promo:
        return f"😕 {titulo}\nNão encontrei produtos para esta categoria."

    # Separar produtos com e sem desconto real
    produtos_com_desconto = []
    produtos_sem_desconto_extra = []
    
    logger.debug("🎯 [PROMO_DEBUG] Analisando %d produtos promocionais", len(produtos_promo))
    
    for p in produtos_promo:
        preco_antigo = p.get('pvenda') or p.get('preco_varejo', 0.0) or 0.0
        preco_promo = p.get('preco_promocional') or p.get('preco_atual') or preco_antigo
        desconto = p.get('desconto_percentual', 0.0) or 0.0
        
        # Garantir que não são None
        if preco_antigo is None:
            preco_antigo = 0.0
        if preco_promo is None:
            preco_promo = preco_antigo
        if desconto is None:
            desconto = 0.0
        
        # Calcular desconto se não informado
        if desconto == 0.0 and preco_antigo > 0 and preco_promo > 0 and preco_promo < preco_antigo:
            desconto = ((preco_antigo - preco_promo) / preco_antigo) * 100
        
        p['_preco_antigo'] = preco_antigo
        p['_preco_promo'] = preco_promo
        p['_desconto'] = desconto
        
        # Se tem desconto real (>1%), é promoção; senão é produto normal
        nome_produto = p.get('descricao', 'Produto sem nome')
        logger.debug(
            "🎯 [PROMO_ANALISE] %s: preço_antigo=%s, preço_promo=%s, desconto=%.1f%%",
            nome_produto,
            preco_antigo,
            preco_promo,
            desconto,
        )
        
        if desconto > 1.0:
            produtos_com_desconto.append(p)
            logger.debug("🎯 [PROMO_VALIDA] ✅ %s é uma promoção válida (%.1f%% OFF)", nome_produto, desconto)
        else:
            produtos_sem_desconto_extra.append(p)
            logger.debug("🎯 [PROMO_NORMAL] ❌ %s não tem desconto suficiente (%.1f%%)", nome_produto, desconto)
    
    # Unir todos os produtos normais
    todos_produtos_normais = produtos_normais + produtos_sem_desconto_extra
    
    resposta = f"*{titulo}*\n\n"
    contador = 1

    # Mostrar produtos normais
    if todos_produtos_normais:
        for p in todos_produtos_normais:
            preco = p.get('_preco_promo') or p.get('preco_atual') or p.get('pvenda') or p.get('preco_varejo', 0.0)
            preco_str = f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            nome_produto = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')
            resposta += f"*{contador}.* {nome_produto}\n"
            resposta += f"    💰 {preco_str}\n\n"
            contador += 1

    # Mostrar produtos com desconto real como promoções
    logger.info("🎯 [PROMO_RESULTADO] Encontradas %d promoções válidas", len(produtos_com_desconto))
    if produtos_com_desconto:
        logger.info("🎯 [PROMO_EXIBE] ✅ Exibindo seção de promoções")
        resposta += "🔥 *PROMOÇÕES ESPECIAIS* 🔥\n"
        resposta += "━━━━━━━━━━━━━━━━━━━━\n"
        
        for p in produtos_com_desconto:
            preco_antigo_str = f"R$ {p['_preco_antigo']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            preco_promo_str = f"R$ {p['_preco_promo']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            nome_produto = p.get('descricao') or p.get('canonical_name', 'Produto sem nome')

            resposta += f"*{contador}.* {nome_produto}\n"
            resposta += f"    ~{preco_antigo_str}~ → *{preco_promo_str}* ({int(p['_desconto'])}% OFF)\n\n"
            contador += 1

    total_produtos = len(todos_produtos_normais) + len(produtos_com_desconto)
    
    # Instruções de seleção
    if total_produtos == 1:
        resposta += "Digite *1* para selecionar este produto."
    else:
        resposta += f"Qual você quer? Digite o número de *1* a *{total_produtos}*."
    
    # Opção de ver mais produtos (sempre disponível para dar mais opções ao usuário)
    resposta += f"\n📝 Digite *mais* para ver outros produtos desta categoria!"

    logging.debug(f"Lista de produtos inteligente formatada: {resposta}")
    return resposta

def formatar_carrinho_para_exibicao(carrinho: List[Dict]) -> str:
    """🆕 VERSÃO COMPLETA: Formata carrinho com todas informações necessárias.

    Args:
        carrinho: A lista de itens no carrinho.

    Returns:
        O carrinho formatado com quantidade, descrição, preço unitário e total.
    """
    logging.debug(f"Formatando carrinho para exibição. Itens no carrinho: {len(carrinho)}")
    if not carrinho:
        return "🛒 Carrinho vazio"
    
    total = 0.0
    itens = []
    
    for i, item in enumerate(carrinho, 1):
        # 🎯 PEGA O PREÇO (promocional tem prioridade)
        preco_unitario = item.get('_preco_promo') or item.get('preco_promocional') or item.get('preco_atual') or item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        subtotal = preco_unitario * qt
        total += subtotal
        
        # Nome do produto
        descricao = item.get('descricao', 'Produto')
        
        # Formatação de quantidade
        if isinstance(qt, float) and qt.is_integer():
            display_qt = f"{int(qt)}"
        else:
            display_qt = str(qt)
        
        # Formatação de preços (padrão brasileiro)
        preco_str = f"R$ {preco_unitario:.2f}".replace(".", ",")
        subtotal_str = f"R$ {subtotal:.2f}".replace(".", ",")
        
        # Linha do item: Quantidade x Produto - Preço unitário = Total
        itens.append(f"{display_qt}x {descricao}\n   {preco_str} cada = {subtotal_str}")
    
    # Total formatado
    total_str = f"R$ {total:.2f}".replace(".", ",")
    
    # Formato final
    resposta = "🛒 *Carrinho:*" + "\n\n".join(itens) + f"\n\n💰 *Total Geral: {total_str}*"
    
    logging.debug(f"Carrinho formatado: {resposta}")
    return resposta

def _resumir_mensagens_antigas(dados_sessao: Dict, max_historico: int = 40, manter_recentes: int = 20):
    """Resume mensagens antigas para evitar crescimento infinito do histórico.

    Args:
        dados_sessao: Os dados da sessão.
        max_historico: O número máximo de mensagens no histórico.
        manter_recentes: O número de mensagens recentes a serem mantidas.
    """
    logging.debug("Resumindo mensagens antigas do histórico.")
    historico = dados_sessao.get("historico_conversa", [])
    if len(historico) <= max_historico:
        return

    mensagens_antigas = historico[:-manter_recentes] if manter_recentes > 0 else historico[:]

    resumo_existente = dados_sessao.get("resumo_conversa", [])
    if isinstance(resumo_existente, str):
        resumo_existente = [{"role": "system", "action_type": "", "summary": resumo_existente}]

    for msg in mensagens_antigas:
        conteudo = msg.get("message", "")
        resumo_msg = resumir_texto_semantico(conteudo)
        resumo_existente.append({
            "role": msg.get("role"),
            "action_type": msg.get("action_type", ""),
            "summary": resumo_msg,
        })

    # Limita o tamanho total do resumo a 1000 caracteres
    while len(_resumo_para_string(resumo_existente)) > 1000 and resumo_existente:
        resumo_existente.pop(0)

    dados_sessao["resumo_conversa"] = resumo_existente
    dados_sessao["historico_conversa"] = historico[-manter_recentes:]
    logging.debug("Mensagens antigas do histórico resumidas com sucesso.")

def adicionar_mensagem_historico(dados_sessao: Dict, role: str, mensagem: str, tipo_acao: str = ""):
    """Adiciona uma mensagem ao histórico da conversa.

    Args:
        dados_sessao: Os dados da sessão.
        role: O papel do autor da mensagem (user ou assistant).
        mensagem: A mensagem a ser adicionada.
        tipo_acao: O tipo de ação associado à mensagem.
    """
    logging.debug(f"Adicionando mensagem ao histórico. Role: {role}, Tipo de Ação: {tipo_acao}, Mensagem: {mensagem[:100]}...")
    if "historico_conversa" not in dados_sessao:
        dados_sessao["historico_conversa"] = []
    
    dados_sessao["historico_conversa"].append({
        "role": role,
        "message": mensagem[:500],
        "timestamp": datetime.now().isoformat(),
        "action_type": tipo_acao
    })

    _resumir_mensagens_antigas(dados_sessao)

def obter_contexto_conversa(dados_sessao: Dict, max_mensagens: int = 14) -> str:
    """Retorna o contexto da conversa.

    Args:
        dados_sessao: Os dados da sessão.
        max_mensagens: O número máximo de mensagens a serem retornadas.

    Returns:
        O contexto da conversa.
    """
    logging.debug(f"Obtendo contexto da conversa com no máximo {max_mensagens} mensagens.")
    historico = dados_sessao.get("historico_conversa", [])
    resumo_dados = dados_sessao.get("resumo_conversa")
    resumo_texto = _resumo_para_string(resumo_dados)

    if not historico and not resumo_texto:
        return "Primeira interação com o cliente."

    partes = []
    if resumo_texto:
        partes.append(f"RESUMO ANTERIOR:\n{resumo_texto}")

    if historico:
        historico_recente = historico[-max_mensagens:]
        contexto = "HISTÓRICO RECENTE DA CONVERSA:\n"
        for i, msg in enumerate(historico_recente, 1):
            role = "Usuário" if msg['role'] == 'user' else "G.A.V"
            mensagem_completa = msg['message'] if len(msg['message']) <= 200 else msg['message'][:200] + "..."
            tipo_acao = msg.get('action_type', '')
            info_acao = f" [{tipo_acao}]" if tipo_acao else ""
            contexto += f"{i}. {role}{info_acao}: {mensagem_completa}\n"
        partes.append(contexto)

    contexto_final = "\n\n".join(partes)
    logging.debug(f"Contexto da conversa obtido: {contexto_final[:200]}...")
    return contexto_final

def obter_contexto_conversa_resumido(dados_sessao: Dict, max_mensagens: int = 20) -> Dict[str, Union[str, List[str]]]:
    """Retorna um contexto estruturado com resumo e mensagens recentes.

    Args:
        dados_sessao: Os dados da sessão.
        max_mensagens: Quantidade máxima de mensagens recentes a incluir.

    Returns:
        Dict com chaves:
            - resumo: resumo combinado das mensagens anteriores (limitado).
            - mensagens_recentes: lista de strings das mensagens recentes.
    """
    historico = dados_sessao.get("historico_conversa", [])
    resumo_dados = dados_sessao.get("resumo_conversa", []) or []

    resumo_texto = _resumo_para_string(resumo_dados)
    resumo_limitado = resumo_texto[-1000:]

    mensagens_formatadas: List[str] = []
    if historico:
        for msg in historico[-max_mensagens:]:
            role = "Cliente" if msg.get("role") == "user" else "G.A.V."
            conteudo = msg.get("message", "").replace("\n", " ")
            if len(conteudo) > 200:
                conteudo = conteudo[:200] + "..."
            mensagens_formatadas.append(f"{role}: {conteudo}")

    return {"resumo": resumo_limitado, "mensagens_recentes": mensagens_formatadas}

def detectar_comandos_limpar_carrinho(mensagem: str) -> bool:
    """Detecta comandos de limpeza de carrinho.

    Args:
        mensagem: A mensagem do usuário.

    Returns:
        True se um comando de limpeza for detectado, False caso contrário.
    """
    logging.debug(f"Detectando comandos de limpar carrinho na mensagem: '{mensagem}'")
    mensagem_minuscula = mensagem.lower().strip()
    
    comandos_limpar = [
        'esvaziar carrinho', 'limpar carrinho', 'zerar carrinho',
        'resetar carrinho', 'apagar carrinho', 'deletar carrinho',
        'esvaziar tudo', 'limpar tudo', 'zerar tudo',
        'apagar tudo', 'deletar tudo', 'remover tudo',
        'começar de novo', 'recomeçar', 'reiniciar',
        'do zero', 'novo pedido', 'nova compra',
        'limpa carrinho', 'esvazia carrinho', 'zera carrinho'
    ]

    if mensagem_minuscula in comandos_limpar:
        logging.debug("Comando de limpar carrinho detectado.")
        return True

    verbos_limpeza = [
        'esvaziar', 'esvazia', 'limpar', 'limpa', 'zerar', 'zera',
        'apagar', 'apaga', 'deletar', 'deleta', 'remover', 'remove',
        'resetar', 'reseta'
    ]
    termos_carrinho = [
        'carrinho', 'tudo', 'todos', 'cesta', 'compra', 'compras', 'pedido'
    ]

    if any(v in mensagem_minuscula for v in verbos_limpeza) and \
       any(t in mensagem_minuscula for t in termos_carrinho):
        logging.debug("Verbo de limpeza com termo relacionado a carrinho detectado.")
        return True

    padroes_limpar = [
        r'\b(carrinho|tudo)\s+(vazio|limpo|zerado)\b',
        r'\bcomeca\w*\s+de\s+novo\b',
        r'\brecome\w*\b',
        r'\breinicia\w*\s+(carrinho|tudo|compra)\b',
        r'\bdo\s+zero\b'
    ]

    for padrao in padroes_limpar:
        if re.search(padrao, mensagem_minuscula):
            logging.debug("Padrão de limpar carrinho detectado.")
            return True
    
    logging.debug("Nenhum comando de limpar carrinho detectado.")
    return False

def detectar_tipo_intencao_usuario(mensagem: str, dados_sessao: Dict) -> str:
    """Detecta o tipo de intenção do usuário utilizando classificador de IA.

    Args:
        mensagem: A mensagem do usuário.
        dados_sessao: Os dados da sessão que podem conter o histórico de conversa.

    Returns:
        O tipo de intenção detectado em formato padronizado.
    """
    logging.debug(
        f"Detectando tipo de intenção do usuário para a mensagem: '{mensagem}'"
    )

    historico = dados_sessao.get("historico_conversa", [])
    contexto = "\n".join(
        f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in historico
    )

    try:
        resultado = detectar_intencao_usuario_com_ia(mensagem, contexto)
        nome_ferramenta = resultado.get("nome_ferramenta", "").lower()
    except Exception as e:
        logging.warning(f"[INTENCAO] Falha ao classificar com IA: {e}")
        nome_ferramenta = ""

    mapa_intencoes = {
        "limpar_carrinho": "CLEAR_CART",
        "adicionar_item_ao_carrinho": "NUMERIC_SELECTION",
        "visualizar_carrinho": "VIEW_CART",
        "checkout": "CHECKOUT",
        "busca_inteligente_com_promocoes": "SEARCH_PRODUCT",
        "obter_produtos_mais_vendidos_por_nome": "SEARCH_PRODUCT",
        "handle_chitchat": "GREETING",
        "atualizacao_inteligente_carrinho": "UPDATE_CART",
        "show_more_products": "SHOW_MORE_PRODUCTS",
        "lidar_conversa": "GENERAL",
    }

    return mapa_intencoes.get(nome_ferramenta, "GENERAL")

def obter_estatisticas_sessao(dados_sessao: Dict) -> Dict:
    """Retorna estatísticas da sessão atual.

    Args:
        dados_sessao: Os dados da sessão.

    Returns:
        Um dicionário com as estatísticas da sessão.
    """
    logging.debug("Obtendo estatísticas da sessão.")
    estatisticas = {
        "itens_carrinho": len(dados_sessao.get("carrinho_compras", [])),
        "tamanho_conversa": len(dados_sessao.get("historico_conversa", [])),
        "cliente_identificado": bool(dados_sessao.get("customer_context")),
        "ultima_acao": dados_sessao.get("last_bot_action", "NONE"),
        "tem_selecao_pendente": bool(dados_sessao.get("last_shown_products")),
        "tem_quantidade_pendente": bool(dados_sessao.get("pending_product_selection"))
    }

    carrinho = dados_sessao.get("carrinho_compras", [])
    valor_total = 0.0
    for item in carrinho:
        # 🎯 PRIORIZA PREÇO PROMOCIONAL se disponível
        preco = item.get('_preco_promo') or item.get('preco_promocional') or item.get('preco_atual') or item.get('pvenda', 0.0) or item.get('preco_varejo', 0.0)
        qt = item.get('qt', 0)
        valor_total += preco * qt
    
    estatisticas["valor_total_carrinho"] = valor_total
    
    logging.debug(f"Estatísticas da sessão: {estatisticas}")
    return estatisticas

def formatar_acoes_rapidas(tem_carrinho: bool = False, tem_produtos: bool = False) -> str:
    """Gera um menu de ações rápidas para o WhatsApp.

    Args:
        tem_carrinho: Booleano indicando se há itens no carrinho.
        tem_produtos: Booleano indicando se há produtos na lista.

    Returns:
        O menu de ações rápidas formatado.
    """
    logging.debug(f"Formatando ações rápidas. Tem carrinho: {tem_carrinho}, Tem produtos: {tem_produtos}")
    acoes = []
    
    if tem_produtos:
        return "Digite o número (1, 2 ou 3) do produto desejado"
    
    if tem_carrinho:
        acoes = [
            "*1* - 🔍 Buscar produtos",
            "*2* - 🛒 Ver carrinho",
            "*3* - ✅ Finalizar pedido"
        ]
    else:
        acoes = [
            "🔍 Digite o nome do produto",
            "📦 Digite *produtos* para ver os mais vendidos",
            "❓ Digite *ajuda* para mais opções"
        ]
    
    resposta = "\n".join(acoes)
    logging.debug(f"Ações rápidas formatadas: {resposta}")
    return resposta

def atualizar_contexto_sessao(dados_sessao: Dict, novo_contexto: Dict):
    """Atualiza os dados da sessão.

    Args:
        dados_sessao: Os dados da sessão.
        novo_contexto: O novo contexto a ser adicionado.
    """
    logging.debug(f"Atualizando contexto da sessão com: {novo_contexto}")
    dados_sessao.update(novo_contexto)

    dados_sessao["ultima_atividade"] = datetime.now().isoformat()

    dados_sessao["estatisticas_sessao"] = obter_estatisticas_sessao(dados_sessao)
    logging.debug("Contexto da sessão atualizado com sucesso.")