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
from typing import Dict
import json

# Configurações padrão
NIVEL_LOG_PADRAO = os.getenv("LOG_LEVEL", "INFO").upper()
DIRETORIO_LOGS = Path("logs")
TAMANHO_MAX_LOG = 10 * 1024 * 1024  # 10MB
QUANTIDADE_BACKUP = 5
FORMATO_LOG = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
FORMATO_DETALHADO = "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [%(funcName)s] %(message)s"

class FormatadorColorido(logging.Formatter):
    """Formatter com cores para console."""
    
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
        # Adiciona cor baseada no nível
        cor = self.CORES.get(record.levelname, self.CORES['RESET'])
        reset = self.CORES['RESET']
        
        # Formata mensagem original
        formatado = super().format(record)
        
        # Adiciona cores apenas se for terminal
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            return f"{cor}{formatado}{reset}"
        
        return formatado

class FormatadorJSON(logging.Formatter):
    """Formatter JSON para logs estruturados."""
    
    def format(self, record):
        entrada_log = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'nivel': record.levelname,
            'logger': record.name,
            'modulo': record.module,
            'funcao': record.funcName,
            'linha': record.lineno,
            'mensagem': record.getMessage(),
        }
        
        # Adiciona informações extras se disponíveis
        if hasattr(record, 'id_usuario'):
            entrada_log['id_usuario'] = record.id_usuario
        
        if hasattr(record, 'id_sessao'):
            entrada_log['id_sessao'] = record.id_sessao
        
        if hasattr(record, 'tempo_execucao'):
            entrada_log['tempo_execucao'] = record.tempo_execucao
        
        if hasattr(record, 'nome_ferramenta'):
            entrada_log['nome_ferramenta'] = record.nome_ferramenta
        
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

class FiltroDadosSensiveis(logging.Filter):
    """Filtro para remover dados sensíveis dos logs."""
    
    PADROES_SENSIVEIS = [
        r'password["\s]*[:=]["\s]*([^"\s,}]+)',
        r'token["\s]*[:=]["\s]*([^"\s,}]+)',
        r'auth["\s]*[:=]["\s]*([^"\s,}]+)',
        r'cnpj["\s]*[:=]["\s]*([^"\s,}]+)',
        r'whatsapp:\+(\d+)',
    ]
    
    def filter(self, record):
        if hasattr(record, 'msg'):
            mensagem = str(record.msg)
            for padrao in self.PADROES_SENSIVEIS:
                import re
                mensagem = re.sub(padrao, r'\1***', mensagem, flags=re.IGNORECASE)
            record.msg = mensagem
        
        return True

def configurar_logs(
    nome: str = None, 
    nivel: str = None, 
    salvar_arquivo: bool = True,
    mostrar_console: bool = True,
    usar_formato_json: bool = False,
    habilitar_performance: bool = False
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
    
    # Cria diretório de logs se necessário
    if salvar_arquivo:
        DIRETORIO_LOGS.mkdir(exist_ok=True)
    
    # Handler para console
    if mostrar_console:
        manipulador_console = logging.StreamHandler(sys.stdout)
        manipulador_console.setLevel(logging.INFO)
        
        if usar_formato_json:
            manipulador_console.setFormatter(FormatadorJSON())
        else:
            manipulador_console.setFormatter(FormatadorColorido(FORMATO_LOG))
        
        # Adiciona filtro de dados sensíveis
        manipulador_console.addFilter(FiltroDadosSensiveis())
        
        logger.addHandler(manipulador_console)
    
    # Handler para arquivo principal
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
            manipulador_arquivo.setFormatter(logging.Formatter(FORMATO_DETALHADO))
        
        manipulador_arquivo.addFilter(FiltroDadosSensiveis())
        logger.addHandler(manipulador_arquivo)
    
    # Handler para erros (arquivo separado)
    if salvar_arquivo:
        manipulador_erro = logging.handlers.RotatingFileHandler(
            DIRETORIO_LOGS / "gav_errors.log",
            maxBytes=TAMANHO_MAX_LOG,
            backupCount=QUANTIDADE_BACKUP,
            encoding='utf-8'
        )
        manipulador_erro.setLevel(logging.ERROR)
        manipulador_erro.setFormatter(logging.Formatter(FORMATO_DETALHADO))
        manipulador_erro.addFilter(FiltroDadosSensiveis())
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
    
    for arquivo_log in DIRETORIO_LOGS.glob("*.log.*"):  # Arquivos rotacionados
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
    formatador_detalhado = logging.Formatter(FORMATO_DETALHADO)
    formatador_simples = logging.Formatter(FORMATO_LOG)
    formatador_json = FormatadorJSON()
    
    # Handler para console (INFO+)
    manipulador_console = logging.StreamHandler(sys.stdout)
    manipulador_console.setLevel(logging.INFO)
    manipulador_console.setFormatter(FormatadorColorido(FORMATO_LOG))
    manipulador_console.addFilter(FiltroDadosSensiveis())
    logger_raiz.addHandler(manipulador_console)
    
    # Handler para arquivo principal (DEBUG+)
    manipulador_arquivo_principal = logging.handlers.RotatingFileHandler(
        DIRETORIO_LOGS / "gav_main.log",
        maxBytes=TAMANHO_MAX_LOG,
        backupCount=QUANTIDADE_BACKUP,
        encoding='utf-8'
    )
    manipulador_arquivo_principal.setLevel(logging.DEBUG)
    manipulador_arquivo_principal.setFormatter(formatador_detalhado)
    manipulador_arquivo_principal.addFilter(FiltroDadosSensiveis())
    logger_raiz.addHandler(manipulador_arquivo_principal)
    
    # Handler para erros (ERROR+)
    manipulador_arquivo_erro = logging.handlers.RotatingFileHandler(
        DIRETORIO_LOGS / "gav_errors.log",
        maxBytes=TAMANHO_MAX_LOG,
        backupCount=QUANTIDADE_BACKUP,
        encoding='utf-8'
    )
    manipulador_arquivo_erro.setLevel(logging.ERROR)
    manipulador_arquivo_erro.setFormatter(formatador_detalhado)
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
    
    # Suprime logs verbosos de bibliotecas externas
    logging.getLogger('twilio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # Log inicial
    logging.info("Sistema de logging G.A.V. inicializado")
    
    return logger_raiz

# Instâncias globais
logger_performance = LoggerPerformance()
logger_auditoria = LoggerAuditoria()

# Inicialização automática
if __name__ != "__main__":
    configurar_logging_principal()