# file: IA/utils/configuracao_logs.py
"""
Sistema de logging avançado para o G.A.V.

Recursos:
- Múltiplos handlers (arquivo, console, erro)
- Formatação estruturada
- Rotação automática de logs
- Filtros por módulo
- Níveis configuráveis por ambiente
- Logging de performance
- Logging de audit trail
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Set
import json
import hashlib
import time
from collections import defaultdict
import threading

# Configurações padrão
NIVEL_LOG_PADRAO = os.getenv("LOG_LEVEL", "DEBUG").upper()
DIRETORIO_LOGS = Path("logs")
TAMANHO_MAX_LOG = 5 * 1024 * 1024  # 5MB (reduzido)
QUANTIDADE_BACKUP = 3  # Reduzido para economizar espaço
FORMATO_LOG = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
FORMATO_DETALHADO = "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [%(funcName)s] %(message)s"
FORMATO_SUPER_DETALHADO = "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [%(funcName)s] %(message)s"

# Configurações de deduplicação
DEDUPLICACAO_HABILITADA = True
JANELA_DEDUPLICACAO = 300  # 5 minutos
MAX_MENSAGENS_IDENTICAS = 3
INTERVALO_LIMPEZA_CACHE = 3600  # 1 hora

class DeduplicadorLogs:
    """Sistema de deduplicação de logs para evitar spam."""
    
    def __init__(self):
        self._cache_mensagens = defaultdict(lambda: {'count': 0, 'first_time': 0, 'last_time': 0})
        self._lock = threading.Lock()
        self._ultima_limpeza = time.time()
    
    def deve_registrar(self, record: logging.LogRecord) -> tuple[bool, str]:
        """Determina se uma mensagem deve ser registrada."""
        if not DEDUPLICACAO_HABILITADA:
            return True, record.getMessage()
        
        # Nunca deduplica logs críticos de resposta
        mensagem = record.getMessage()
        if any(palavra in mensagem for palavra in [
            "RESPOSTA ENVIADA AO USUARIO", 
            "MENSAGEM RECEBIDA DO USUARIO",
            "INTENCAO DETECTADA", 
            "FERRAMENTA EXECUTADA"
        ]):
            return True, mensagem
        
        # Cria hash da mensagem para identificar duplicatas
        mensagem_base = f"{record.levelname}:{record.name}:{record.funcName}:{record.getMessage()}"
        hash_mensagem = hashlib.md5(mensagem_base.encode()).hexdigest()[:12]
        
        agora = time.time()
        
        with self._lock:
            # Limpeza periódica do cache
            if agora - self._ultima_limpeza > INTERVALO_LIMPEZA_CACHE:
                self._limpar_cache_antigo(agora)
                self._ultima_limpeza = agora
            
            entrada = self._cache_mensagens[hash_mensagem]
            
            # Primeira ocorrência
            if entrada['count'] == 0:
                entrada['first_time'] = agora
                entrada['last_time'] = agora
                entrada['count'] = 1
                return True, record.getMessage()
            
            # Verificar se ainda está dentro da janela de tempo
            if agora - entrada['first_time'] > JANELA_DEDUPLICACAO:
                # Nova janela - reset contador
                entrada['first_time'] = agora
                entrada['last_time'] = agora
                entrada['count'] = 1
                return True, record.getMessage()
            
            # Dentro da janela - incrementar contador
            entrada['count'] += 1
            entrada['last_time'] = agora
            
            # Permitir algumas repetições, depois suprimir
            if entrada['count'] <= MAX_MENSAGENS_IDENTICAS:
                return True, record.getMessage()
            elif entrada['count'] == MAX_MENSAGENS_IDENTICAS + 1:
                # Mensagem de supressão
                tempo_janela = int(JANELA_DEDUPLICACAO / 60)
                return True, f"[DEDUPLICADO] Mensagem anterior repetida {entrada['count']-1}x nos últimos {tempo_janela}min. Suprimindo repetições adicionais."
            else:
                # Suprimir mensagens adicionais
                return False, ""
    
    def _limpar_cache_antigo(self, agora: float):
        """Remove entradas antigas do cache."""
        chaves_antigas = [
            chave for chave, entrada in self._cache_mensagens.items()
            if agora - entrada['last_time'] > JANELA_DEDUPLICACAO * 2
        ]
        for chave in chaves_antigas:
            del self._cache_mensagens[chave]

# Instância global do deduplicador
_deduplicador_global = DeduplicadorLogs()

class FormatadorContextual(logging.Formatter):
    """Formatter que inclui contexto de usuário quando disponível."""
    
    def format(self, record):
        # Enriquece o record com contexto padrão se não existir
        if not hasattr(record, 'user_id'):
            record.user_id = 'N/A'
        if not hasattr(record, 'session_id'):
            record.session_id = 'N/A'
        
        # Verifica deduplicação
        deve_registrar, mensagem_processada = _deduplicador_global.deve_registrar(record)
        if not deve_registrar:
            return ""
        
        # Atualiza mensagem se foi processada pelo deduplicador
        if mensagem_processada != record.getMessage():
            record.msg = mensagem_processada
            record.args = ()
        
        # Monta formato base
        formatado = super().format(record)
        
        # Adiciona contexto se disponível e não for N/A
        if hasattr(record, 'user_id') and record.user_id != 'N/A':
            contexto = f"[U:{record.user_id}]"
            if hasattr(record, 'session_id') and record.session_id != 'N/A':
                contexto += f"[S:{record.session_id}]"
            formatado = formatado.replace(f"[{record.levelname}]", f"[{record.levelname}] {contexto}")
        
        # Adiciona informações extras importantes nos logs críticos
        mensagem = record.getMessage()
        extras_visiveis = []
        
        if "RESPOSTA ENVIADA" in mensagem:
            if hasattr(record, 'resposta_completa'):
                extras_visiveis.append(f"RESPOSTA='{record.resposta_completa}'")
            if hasattr(record, 'tamanho_resposta'):
                extras_visiveis.append(f"TAMANHO={record.tamanho_resposta}")
        
        elif "MENSAGEM RECEBIDA" in mensagem:
            if hasattr(record, 'mensagem_completa_recebida'):
                extras_visiveis.append(f"MSG='{record.mensagem_completa_recebida}'")
            if hasattr(record, 'tamanho_mensagem'):
                extras_visiveis.append(f"TAMANHO={record.tamanho_mensagem}")
        
        elif "INTENCAO DETECTADA" in mensagem:
            if hasattr(record, 'tool_name'):
                extras_visiveis.append(f"TOOL={record.tool_name}")
            if hasattr(record, 'parametros'):
                extras_visiveis.append(f"PARAMS={record.parametros}")
        
        if extras_visiveis:
            formatado += f" | {' | '.join(extras_visiveis)}"
        
        return formatado

class FormatadorColorido(FormatadorContextual):
    """Formatter com cores para console baseado no contextual."""
    
    # Códigos de cor ANSI
    CORES = {
        'DEBUG': '\033[36m',     # Ciano
        'INFO': '\033[32m',      # Verde
        'WARNING': '\033[33m',   # Amarelo
        'ERROR': '\033[31m',     # Vermelho
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        # Enriquece o record com contexto padrão se não existir
        if not hasattr(record, 'user_id'):
            record.user_id = 'N/A'
        if not hasattr(record, 'session_id'):
            record.session_id = 'N/A'
        
        # CONSOLE NUNCA USA DEDUPLICAÇÃO - queremos ver tudo!
        # Monta formato base
        formatado = logging.Formatter.format(self, record)
        
        # Adiciona contexto se disponível e não for N/A
        if hasattr(record, 'user_id') and record.user_id != 'N/A':
            contexto = f"[U:{record.user_id}]"
            if hasattr(record, 'session_id') and record.session_id != 'N/A':
                contexto += f"[S:{record.session_id}]"
            formatado = formatado.replace(f"[{record.levelname}]", f"[{record.levelname}] {contexto}")
        
        # Adiciona informações extras importantes nos logs críticos
        mensagem = record.getMessage()
        extras_visiveis = []
        
        if "RESPOSTA ENVIADA" in mensagem:
            if hasattr(record, 'resposta_completa'):
                extras_visiveis.append(f"RESPOSTA='{record.resposta_completa}'")
            if hasattr(record, 'tamanho_resposta'):
                extras_visiveis.append(f"TAMANHO={record.tamanho_resposta}")
        
        elif "MENSAGEM RECEBIDA" in mensagem:
            if hasattr(record, 'mensagem_completa_recebida'):
                extras_visiveis.append(f"MSG='{record.mensagem_completa_recebida}'")
            if hasattr(record, 'tamanho_mensagem'):
                extras_visiveis.append(f"TAMANHO={record.tamanho_mensagem}")
        
        elif "INTENCAO DETECTADA" in mensagem:
            if hasattr(record, 'tool_name'):
                extras_visiveis.append(f"TOOL={record.tool_name}")
            if hasattr(record, 'parametros'):
                extras_visiveis.append(f"PARAMS={record.parametros}")
        
        if extras_visiveis:
            formatado += f" | {' | '.join(extras_visiveis)}"
        
        # Adiciona cor baseada no nível
        cor = self.CORES.get(record.levelname, self.CORES['RESET'])
        reset = self.CORES['RESET']
        
        # Adiciona cores apenas se for terminal
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            return f"{cor}{formatado}{reset}"
        
        return formatado

class FormatadorJSON(logging.Formatter):
    """Formatter JSON para logs estruturados."""
    
    def format(self, record):
        # Enriquece o record com contexto padrão
        if not hasattr(record, 'user_id'):
            record.user_id = 'N/A'
        if not hasattr(record, 'session_id'):
            record.session_id = 'N/A'
        
        # Verifica deduplicação
        deve_registrar, mensagem_processada = _deduplicador_global.deve_registrar(record)
        if not deve_registrar:
            return ""
        
        entrada_log = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'nivel': record.levelname,
            'logger': record.name,
            'modulo': record.module,
            'funcao': record.funcName,
            'linha': record.lineno,
            'mensagem': mensagem_processada if mensagem_processada != record.getMessage() else record.getMessage(),
            'user_id': getattr(record, 'user_id', 'N/A'),
            'session_id': getattr(record, 'session_id', 'N/A')
        }
        
        # Adiciona todos os campos extras de forma organizada
        extras_importantes = {
            'mensagem_completa_recebida', 'resposta_completa', 'resposta_gerada',
            'intencao_completa', 'tool_name', 'parametros', 'categoria',
            'tamanho_mensagem', 'tamanho_resposta'
        }
        
        for campo in extras_importantes:
            if hasattr(record, campo):
                entrada_log[campo] = getattr(record, campo)
        
        # Adiciona informações extras se disponíveis
        if hasattr(record, 'id_usuario'):
            entrada_log['id_usuario'] = record.id_usuario
        
        if hasattr(record, 'id_sessao'):
            entrada_log['id_sessao'] = record.id_sessao
        
        if hasattr(record, 'tempo_execucao'):
            entrada_log['tempo_execucao'] = record.tempo_execucao
        
        if hasattr(record, 'nome_ferramenta'):
            entrada_log['nome_ferramenta'] = record.nome_ferramenta
        
        if hasattr(record, 'contexto_adicional'):
            entrada_log['contexto'] = record.contexto_adicional
        
        if record.exc_info:
            entrada_log['excecao'] = self.formatException(record.exc_info)
        
        return json.dumps(entrada_log, ensure_ascii=False)

class FiltroPerformance(logging.Filter):
    """Filtro para logs de performance."""
    
    def filter(self, record):
        # Só passa logs que têm informação de performance
        return hasattr(record, 'tempo_execucao')

class FiltroModulo(logging.Filter):
    """Filtro para logs de módulos específicos."""
    
    def __init__(self, modulos: list):
        super().__init__()
        self.modulos = modulos
    
    def filter(self, record):
        return any(modulo in record.name for modulo in self.modulos)

class FiltroDeduplicacao(logging.Filter):
    """Filtro que usa o deduplicador global."""
    
    def filter(self, record):
        deve_registrar, _ = _deduplicador_global.deve_registrar(record)
        return deve_registrar

def configurar_logs(
    nome: str = None, 
    nivel: str = None, 
    salvar_arquivo: bool = True,
    mostrar_console: bool = True,
    usar_formato_json: bool = False,
    habilitar_performance: bool = False,
    contexto_usuario: Dict = None
) -> logging.Logger:
    """
    Configura logger personalizado para o sistema G.A.V.    
    Args:
        nome (str, optional): Nome do logger. Se None, usa __name__.
        nivel (str, optional): Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        salvar_arquivo (bool): Se deve salvar logs em arquivo.
        mostrar_console (bool): Se deve mostrar logs no console.
        usar_formato_json (bool): Se deve usar formato JSON estruturado.
        habilitar_performance (bool): Se deve habilitar logs de performance.
    
    Returns:
        logging.Logger: Logger configurado e pronto para uso.        
    Example:
        >>> logger = configurar_logs("meu_modulo", "DEBUG")
        >>> logger.info("Sistema iniciado")
    """
    
    # Determina nome do logger
    if nome is None:
        nome = __name__
    
    # Determina nível
    if nivel is None:
        nivel = NIVEL_LOG_PADRAO
    
    # Cria logger
    logger = logging.getLogger(nome)
    logger.setLevel(getattr(logging, nivel.upper()))
    
    # Remove handlers existentes para evitar duplicação
    logger.handlers.clear()
    
    # Adiciona contexto padrão se fornecido
    if contexto_usuario:
        old_factory = logging.getLogRecordFactory()
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in contexto_usuario.items():
                setattr(record, key, value)
            return record
        logging.setLogRecordFactory(record_factory)
    
    # Cria diretório de logs se necessário
    if salvar_arquivo:
        DIRETORIO_LOGS.mkdir(exist_ok=True)
    
    # Handler para console - MOSTRA TUDO no terminal
    if mostrar_console:
        manipulador_console = logging.StreamHandler(sys.stdout)
        manipulador_console.setLevel(logging.DEBUG)  # TUDO no terminal
        
        if usar_formato_json:
            manipulador_console.setFormatter(FormatadorJSON())
        else:
            manipulador_console.setFormatter(FormatadorColorido(FORMATO_SUPER_DETALHADO))
        
        # Nunca deduplica no console para ver todo o fluxo
        logger.addHandler(manipulador_console)
    
    # Handler para arquivo principal com deduplicação
    if salvar_arquivo:
        manipulador_arquivo = logging.handlers.RotatingFileHandler(
            DIRETORIO_LOGS / "gav_app.log",
            maxBytes=TAMANHO_MAX_LOG,
            backupCount=QUANTIDADE_BACKUP,
            encoding='utf-8'
        )
        manipulador_arquivo.setLevel(logging.DEBUG)
        
        if usar_formato_json:
            manipulador_arquivo.setFormatter(FormatadorJSON())
        else:
            manipulador_arquivo.setFormatter(FormatadorContextual(FORMATO_SUPER_DETALHADO))
        
        # Adiciona filtro de deduplicação para arquivos
        if DEDUPLICACAO_HABILITADA:
            manipulador_arquivo.addFilter(FiltroDeduplicacao())
        
        logger.addHandler(manipulador_arquivo)
    
    # Handler para erros (arquivo separado) com deduplicação mais agressiva
    if salvar_arquivo:
        manipulador_erro = logging.handlers.RotatingFileHandler(
            DIRETORIO_LOGS / "gav_errors.log",
            maxBytes=TAMANHO_MAX_LOG,
            backupCount=QUANTIDADE_BACKUP,
            encoding='utf-8'
        )
        manipulador_erro.setLevel(logging.ERROR)
        manipulador_erro.setFormatter(FormatadorContextual(FORMATO_SUPER_DETALHADO))
        
        # Deduplicação especialmente importante para erros
        if DEDUPLICACAO_HABILITADA:
            manipulador_erro.addFilter(FiltroDeduplicacao())
        
        logger.addHandler(manipulador_erro)
    
    # Handler para performance (se habilitado)
    if habilitar_performance and salvar_arquivo:
        manipulador_perf = logging.handlers.RotatingFileHandler(
            DIRETORIO_LOGS / "gav_performance.log",
            maxBytes=TAMANHO_MAX_LOG,
            backupCount=QUANTIDADE_BACKUP,
            encoding='utf-8'
        )
        manipulador_perf.setLevel(logging.INFO)
        manipulador_perf.setFormatter(FormatadorJSON())
        manipulador_perf.addFilter(FiltroPerformance())
        logger.addHandler(manipulador_perf)
    
    return logger

def configurar_loggers_modulos():
    """Configura loggers específicos para cada módulo do G.A.V."""
    
    # Logger principal da aplicação
    logger_app = configurar_logs("gav_app", "DEBUG")
    
    # Logger para base de dados
    logger_db = configurar_logs("gav_database", "DEBUG")
    
    # Logger para IA/LLM
    logger_ai = configurar_logs("gav_ai", "DEBUG")
    
    # Logger para comunicação (WhatsApp)
    logger_comm = configurar_logs("gav_communication", "DEBUG")
    
    # Logger para sessões
    logger_session = configurar_logs("gav_sessions", "DEBUG")
    
    # Logger para knowledge base
    logger_kb = configurar_logs("gav_knowledge", "INFO")
    
    # Logger para performance
    logger_perf = configurar_logs("gav_performance", "INFO", habilitar_performance=True)
    
    return {
        "app": logger_app,
        "banco_dados": logger_db,
        "ia": logger_ai,
        "comunicacao": logger_comm,
        "sessoes": logger_session,
        "conhecimento": logger_kb,
        "performance": logger_perf
    }

class LoggerPerformance:
    """Logger especializado para métricas de performance."""
    
    def __init__(self):
        self.logger = configurar_logs("gav_performance", habilitar_performance=True)
    
    def registrar_tempo_execucao(self, nome_funcao: str, tempo_execucao: float, 
                          contexto: Dict = None):
        """
        Registra tempo de execução de função.        
        Args:
            nome_funcao (str): Nome da função executada.
            tempo_execucao (float): Tempo em segundos.
            contexto (Dict, optional): Contexto adicional para o log.
        """
        extra = {
            'tempo_execucao': tempo_execucao,
            'funcao': nome_funcao
        }
        
        if contexto:
            extra.update(contexto)
        
        self.logger.info(
            f"PERFORMANCE: {nome_funcao} executada em {tempo_execucao:.3f}s",
            extra=extra
        )
    
    def registrar_consulta_banco(self, tipo_consulta: str, tempo_execucao: float, 
                          linhas_afetadas: int = None):
        """
        Registra performance de consulta no banco.
        
        Args:
            tipo_consulta (str): Tipo da consulta (SELECT, INSERT, etc.).
            tempo_execucao (float): Tempo em segundos.
            linhas_afetadas (int, optional): Número de linhas afetadas.
        """
        extra = {
            'tempo_execucao': tempo_execucao,
            'tipo_consulta': tipo_consulta,
            'linhas_afetadas': linhas_afetadas
        }
        
        self.logger.info(
            f"DB_PERFORMANCE: {tipo_consulta} levou {tempo_execucao:.3f}s",
            extra=extra
        )
    
    def registrar_requisicao_llm(self, modelo: str, tempo_execucao: float, 
                       contagem_tokens: int = None):
        """
        Registra performance de requisição LLM.
        
        Args:
            modelo (str): Nome do modelo usado.
            tempo_execucao (float): Tempo em segundos.
            contagem_tokens (int, optional): Número de tokens processados.
        """
        extra = {
            'tempo_execucao': tempo_execucao,
            'modelo': modelo,
            'contagem_tokens': contagem_tokens
        }
        
        self.logger.info(
            f"LLM_PERFORMANCE: {modelo} levou {tempo_execucao:.3f}s",
            extra=extra
        )

class LoggerAuditoria:
    """Logger especializado para audit trail."""
    
    def __init__(self):
        self.logger = configurar_logs("gav_audit", usar_formato_json=True)
    
    def registrar_acao_usuario(self, id_usuario: str, acao: str, detalhes: Dict = None):
        """
        Registra ação do usuário.
        
        Args:
            id_usuario (str): ID do usuário.
            acao (str): Ação realizada.
            detalhes (Dict, optional): Detalhes adicionais da ação.
        """
        extra = {
            'id_usuario': id_usuario,
            'acao': acao,
            'detalhes': detalhes or {}
        }
        
        self.logger.info(f"ACAO_USUARIO: {acao}", extra=extra)
    
    def registrar_evento_sistema(self, tipo_evento: str, detalhes: Dict = None):
        """
        Registra evento do sistema.
        
        Args:
            tipo_evento (str): Tipo do evento.
            detalhes (Dict, optional): Detalhes do evento.
        """
        extra = {
            'tipo_evento': tipo_evento,
            'detalhes': detalhes or {}
        }
        
        self.logger.info(f"EVENTO_SISTEMA: {tipo_evento}", extra=extra)
    
    def registrar_evento_seguranca(self, tipo_evento: str, id_usuario: str = None, 
                          detalhes: Dict = None):
        """
        Registra evento de segurança.
        
        Args:
            tipo_evento (str): Tipo do evento de segurança.
            id_usuario (str, optional): ID do usuário relacionado.
            detalhes (Dict, optional): Detalhes do evento.
        """
        extra = {
            'evento_seguranca': tipo_evento,
            'id_usuario': id_usuario,
            'detalhes': detalhes or {}
        }
        
        self.logger.warning(f"SEGURANCA: {tipo_evento}", extra=extra)

def obter_estatisticas_logs() -> Dict:
    """
    Retorna estatísticas dos arquivos de log.
    
    Returns:
        Dict: Estatísticas de cada arquivo de log incluindo tamanho e data.
    """
    estatisticas = {}
    
    if DIRETORIO_LOGS.exists():
        for arquivo_log in DIRETORIO_LOGS.glob("*.log"):
            try:
                stats_arquivo = arquivo_log.stat()
                estatisticas[arquivo_log.name] = {
                    'tamanho_bytes': stats_arquivo.st_size,
                    'tamanho_mb': round(stats_arquivo.st_size / (1024 * 1024), 2),
                    'modificado': datetime.fromtimestamp(stats_arquivo.st_mtime).isoformat(),
                    'linhas': sum(1 for _ in arquivo_log.open('r', encoding='utf-8', errors='ignore'))
                }
            except Exception as e:
                estatisticas[arquivo_log.name] = {'erro': str(e)}
    
    return estatisticas

def limpar_logs_antigos(dias: int = 30):
    """
    Remove logs antigos.
    
    Args:
        dias (int): Número de dias para manter os logs.
    """
    if not DIRETORIO_LOGS.exists():
        return
    
    tempo_corte = datetime.now().timestamp() - (dias * 24 * 3600)
    contador_removidos = 0
    
    for arquivo_log in DIRETORIO_LOGS.glob("*.log.*"):
        try:
            if arquivo_log.stat().st_mtime < tempo_corte:
                arquivo_log.unlink()
                contador_removidos += 1
        except Exception as e:
            logging.error(f"Erro ao remover log antigo {arquivo_log}: {e}")
    
    logging.info(f"Removidos {contador_removidos} arquivos de log antigos")

# Decorator para logging automático de performance
def registrar_performance(nome_logger: str = "gav_performance"):
    """
    Decorator para log automático de performance.
    
    Args:
        nome_logger (str): Nome do logger a ser usado.
    """
    def decorator(func):
        import functools
        import time
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tempo_inicio = time.time()
            
            try:
                resultado = func(*args, **kwargs)
                tempo_execucao = time.time() - tempo_inicio
                
                logger_perf = LoggerPerformance()
                logger_perf.registrar_tempo_execucao(
                    func.__name__, 
                    tempo_execucao,
                    {'sucesso': True}
                )
                
                return resultado
                
            except Exception as e:
                tempo_execucao = time.time() - tempo_inicio
                
                logger_perf = LoggerPerformance()
                logger_perf.registrar_tempo_execucao(
                    func.__name__, 
                    tempo_execucao,
                    {'sucesso': False, 'erro': str(e)}
                )
                
                raise
        
        return wrapper
    return decorator

# Decorator para logging automático de auditoria
def registrar_auditoria(acao: str):
    """
    Decorator para log automático de auditoria.
    
    Args:
        acao (str): Ação sendo executada.
    """
    def decorator(func):
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Tenta extrair id_usuario dos argumentos
            id_usuario = None
            if args and hasattr(args[0], 'id_usuario'):
                id_usuario = args[0].id_usuario
            elif 'id_usuario' in kwargs:
                id_usuario = kwargs['id_usuario']
            elif 'id_sessao' in kwargs:
                id_usuario = kwargs['id_sessao']
            
            logger_audit = LoggerAuditoria()
            
            try:
                resultado = func(*args, **kwargs)
                
                logger_audit.registrar_acao_usuario(
                    id_usuario or 'desconhecido',
                    acao,
                    {'sucesso': True, 'funcao': func.__name__}
                )
                
                return resultado
                
            except Exception as e:
                logger_audit.registrar_acao_usuario(
                    id_usuario or 'desconhecido',
                    acao,
                    {'sucesso': False, 'erro': str(e), 'funcao': func.__name__}
                )
                
                raise
        
        return wrapper
    return decorator

def obter_estatisticas_deduplicacao() -> Dict:
    """Retorna estatísticas do sistema de deduplicação."""
    with _deduplicador_global._lock:
        return {
            'mensagens_em_cache': len(_deduplicador_global._cache_mensagens),
            'total_suprimidas': sum(
                max(0, entrada['count'] - MAX_MENSAGENS_IDENTICAS) 
                for entrada in _deduplicador_global._cache_mensagens.values()
            ),
            'configuracao': {
                'habilitada': DEDUPLICACAO_HABILITADA,
                'janela_segundos': JANELA_DEDUPLICACAO,
                'max_identicas': MAX_MENSAGENS_IDENTICAS
            }
        }

def limpar_cache_deduplicacao():
    """Força limpeza do cache de deduplicação."""
    with _deduplicador_global._lock:
        _deduplicador_global._cache_mensagens.clear()
        _deduplicador_global._ultima_limpeza = time.time()

# Configuração principal do sistema
def configurar_logging_principal():
    """Configura logging principal do sistema G.A.V."""
    
    # Cria diretório de logs
    DIRETORIO_LOGS.mkdir(exist_ok=True)
    
    # Configura logger raiz
    logger_raiz = logging.getLogger()
    logger_raiz.setLevel(logging.DEBUG)
    
    # Remove handlers padrão
    logger_raiz.handlers.clear()
    
    # Configura formatters
    formatador_contextual = FormatadorContextual(FORMATO_SUPER_DETALHADO)
    formatador_simples = logging.Formatter(FORMATO_LOG)
    formatador_json = FormatadorJSON()
    
    # Handler para console (DEBUG+) - MOSTRA TUDO no terminal
    manipulador_console = logging.StreamHandler(sys.stdout)
    manipulador_console.setLevel(logging.DEBUG)  # TUDO no console
    manipulador_console.setFormatter(FormatadorColorido(FORMATO_SUPER_DETALHADO))  # Formato completo
    logger_raiz.addHandler(manipulador_console)
    
    # Handler para arquivo principal (DEBUG+) com deduplicação
    manipulador_arquivo_principal = logging.handlers.RotatingFileHandler(
        DIRETORIO_LOGS / "gav_main.log",
        maxBytes=TAMANHO_MAX_LOG,
        backupCount=QUANTIDADE_BACKUP,
        encoding='utf-8'
    )
    manipulador_arquivo_principal.setLevel(logging.DEBUG)
    manipulador_arquivo_principal.setFormatter(formatador_contextual)
    if DEDUPLICACAO_HABILITADA:
        manipulador_arquivo_principal.addFilter(FiltroDeduplicacao())
    logger_raiz.addHandler(manipulador_arquivo_principal)
    
    # Handler para erros (ERROR+) com deduplicação agressiva
    manipulador_arquivo_erro = logging.handlers.RotatingFileHandler(
        DIRETORIO_LOGS / "gav_errors.log",
        maxBytes=TAMANHO_MAX_LOG,
        backupCount=QUANTIDADE_BACKUP,
        encoding='utf-8'
    )
    manipulador_arquivo_erro.setLevel(logging.ERROR)
    manipulador_arquivo_erro.setFormatter(formatador_contextual)
    if DEDUPLICACAO_HABILITADA:
        manipulador_arquivo_erro.addFilter(FiltroDeduplicacao())
    logger_raiz.addHandler(manipulador_arquivo_erro)
    
    # Handler para auditoria (JSON)
    manipulador_arquivo_audit = logging.handlers.RotatingFileHandler(
        DIRETORIO_LOGS / "gav_audit.log",
        maxBytes=TAMANHO_MAX_LOG,
        backupCount=QUANTIDADE_BACKUP,
        encoding='utf-8'
    )
    manipulador_arquivo_audit.setLevel(logging.INFO)
    manipulador_arquivo_audit.setFormatter(formatador_json)
    manipulador_arquivo_audit.addFilter(FiltroModulo(['gav_audit']))
    logger_raiz.addHandler(manipulador_arquivo_audit)
    
    # Handler separado para performance com JSON
    manipulador_performance = logging.handlers.RotatingFileHandler(
        DIRETORIO_LOGS / "gav_performance.log",
        maxBytes=TAMANHO_MAX_LOG,
        backupCount=QUANTIDADE_BACKUP,
        encoding='utf-8'
    )
    manipulador_performance.setLevel(logging.INFO)
    manipulador_performance.setFormatter(formatador_json)
    manipulador_performance.addFilter(FiltroPerformance())
    logger_raiz.addHandler(manipulador_performance)
    
    # Suprime logs verbosos de bibliotecas externas
    logging.getLogger('twilio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Flask
    
    # Log inicial
    logging.info("Sistema de logging G.A.V. inicializado com deduplicação")
    
    return logger_raiz

# Instâncias globais
logger_performance = LoggerPerformance()
logger_auditoria = LoggerAuditoria()

# Inicialização automática
if __name__ != "__main__":
    configurar_logging_principal()

# Exemplo de uso
if __name__ == "__main__":
    
    # Configura logging principal
    configurar_logging_principal()
    
    # Obtém loggers específicos
    loggers = configurar_loggers_modulos()
    
    # Exemplo de logs
    loggers['app'].debug("Mensagem de debug da aplicação")
    loggers['app'].info("Aplicação iniciada")
    loggers['app'].warning("Atenção: configuração X não encontrada")
    loggers['app'].error("Falha ao iniciar serviço Y")
    
    loggers['banco_dados'].info("Conectando ao banco de dados...")
    
    loggers['ia'].debug("Enviando prompt para LLM")
    
    # Exemplo de log de performance
    @registrar_performance()
    def funcao_demorada():
        time.sleep(0.5)
        return "Resultado"

    funcao_demorada()
    
    # Exemplo de log de auditoria
    @registrar_auditoria("LOGIN_USUARIO")
    def login(id_usuario, senha):
        if senha == "123":
            return True
        raise ValueError("Senha inválida")
    
    login(id_usuario="user123", senha="123")
    try:
        login(id_usuario="user123", senha="errada")
    except ValueError:
        pass
    
    # Exemplo de estatísticas
    print("\nEstatísticas de Logs:")
    print(json.dumps(obter_estatisticas_logs(), indent=2))
    
    # Limpeza de logs antigos
    limpar_logs_antigos(dias=0) # Limpa logs de exemplo
    
    print("\nLogs antigos removidos")
    print(json.dumps(obter_estatisticas_logs(), indent=2))