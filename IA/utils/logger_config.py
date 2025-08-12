# file: IA/utils/logger_config.py
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
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path("logs")
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
DETAILED_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [%(funcName)s] %(message)s"

class ColoredFormatter(logging.Formatter):
    """Formatter com cores para console."""
    
    # Códigos de cor ANSI
    COLORS = {
        'DEBUG': '\033[36m',     # Ciano
        'INFO': '\033[32m',      # Verde
        'WARNING': '\033[33m',   # Amarelo
        'ERROR': '\033[31m',     # Vermelho
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        # Adiciona cor baseada no nível
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Formata mensagem original
        formatted = super().format(record)
        
        # Adiciona cores apenas se for terminal
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            return f"{color}{formatted}{reset}"
        
        return formatted

class JSONFormatter(logging.Formatter):
    """Formatter JSON para logs estruturados."""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }
        
        # Adiciona informações extras se disponíveis
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        
        if hasattr(record, 'session_id'):
            log_entry['session_id'] = record.session_id
        
        if hasattr(record, 'execution_time'):
            log_entry['execution_time'] = record.execution_time
        
        if hasattr(record, 'tool_name'):
            log_entry['tool_name'] = record.tool_name
        
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)

class PerformanceFilter(logging.Filter):
    """Filtro para logs de performance."""
    
    def filter(self, record):
        # Só passa logs que têm informação de performance
        return hasattr(record, 'execution_time')

class ModuleFilter(logging.Filter):
    """Filtro para logs de módulos específicos."""
    
    def __init__(self, modules: list):
        super().__init__()
        self.modules = modules
    
    def filter(self, record):
        return any(module in record.name for module in self.modules)

class SensitiveDataFilter(logging.Filter):
    """Filtro para remover dados sensíveis dos logs."""
    
    SENSITIVE_PATTERNS = [
        r'password["\s]*[:=]["\s]*([^"\s,}]+)',
        r'token["\s]*[:=]["\s]*([^"\s,}]+)',
        r'auth["\s]*[:=]["\s]*([^"\s,}]+)',
        r'cnpj["\s]*[:=]["\s]*([^"\s,}]+)',
        r'whatsapp:\+(\d+)',
    ]
    
    def filter(self, record):
        if hasattr(record, 'msg'):
            message = str(record.msg)
            for pattern in self.SENSITIVE_PATTERNS:
                import re
                message = re.sub(pattern, r'\1***', message, flags=re.IGNORECASE)
            record.msg = message
        
        return True

def setup_logger(
    name: str = None, 
    level: str = None, 
    log_to_file: bool = True,
    log_to_console: bool = True,
    use_json_format: bool = False,
    enable_performance: bool = False
) -> logging.Logger:
    """
    Configura logger personalizado.
    
    Args:
        name: Nome do logger (usa __name__ se None)
        level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Se deve logar em arquivo
        log_to_console: Se deve logar no console
        use_json_format: Se deve usar formato JSON
        enable_performance: Se deve habilitar logs de performance
    """
    
    # Determina nome do logger
    if name is None:
        name = __name__
    
    # Determina nível
    if level is None:
        level = DEFAULT_LOG_LEVEL
    
    # Cria logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove handlers existentes para evitar duplicação
    logger.handlers.clear()
    
    # Cria diretório de logs se necessário
    if log_to_file:
        LOG_DIR.mkdir(exist_ok=True)
    
    # Handler para console
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        if use_json_format:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(ColoredFormatter(LOG_FORMAT))
        
        # Adiciona filtro de dados sensíveis
        console_handler.addFilter(SensitiveDataFilter())
        
        logger.addHandler(console_handler)
    
    # Handler para arquivo principal
    if log_to_file:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "gav_app.log",
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        if use_json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        
        file_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(file_handler)
    
    # Handler para erros (arquivo separado)
    if log_to_file:
        error_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "gav_errors.log",
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        error_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(error_handler)
    
    # Handler para performance (se habilitado)
    if enable_performance and log_to_file:
        perf_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "gav_performance.log",
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        perf_handler.setLevel(logging.INFO)
        perf_handler.setFormatter(JSONFormatter())
        perf_handler.addFilter(PerformanceFilter())
        logger.addHandler(perf_handler)
    
    return logger

def setup_module_loggers():
    """Configura loggers específicos para cada módulo do G.A.V."""
    
    # Logger principal da aplicação
    app_logger = setup_logger("gav_app", "INFO")
    
    # Logger para base de dados
    db_logger = setup_logger("gav_database", "INFO")
    
    # Logger para IA/LLM
    ai_logger = setup_logger("gav_ai", "INFO")
    
    # Logger para comunicação (WhatsApp)
    comm_logger = setup_logger("gav_communication", "INFO")
    
    # Logger para sessões
    session_logger = setup_logger("gav_sessions", "DEBUG")
    
    # Logger para knowledge base
    kb_logger = setup_logger("gav_knowledge", "INFO")
    
    # Logger para performance
    perf_logger = setup_logger("gav_performance", "INFO", enable_performance=True)
    
    return {
        "app": app_logger,
        "database": db_logger,
        "ai": ai_logger,
        "communication": comm_logger,
        "sessions": session_logger,
        "knowledge": kb_logger,
        "performance": perf_logger
    }

class PerformanceLogger:
    """Logger especializado para métricas de performance."""
    
    def __init__(self):
        self.logger = setup_logger("gav_performance", enable_performance=True)
    
    def log_execution_time(self, function_name: str, execution_time: float, 
                          context: Dict = None):
        """Log tempo de execução de função."""
        extra = {
            'execution_time': execution_time,
            'function': function_name
        }
        
        if context:
            extra.update(context)
        
        self.logger.info(
            f"PERFORMANCE: {function_name} executed in {execution_time:.3f}s",
            extra=extra
        )
    
    def log_database_query(self, query_type: str, execution_time: float, 
                          rows_affected: int = None):
        """Log performance de query no banco."""
        extra = {
            'execution_time': execution_time,
            'query_type': query_type,
            'rows_affected': rows_affected
        }
        
        self.logger.info(
            f"DB_PERFORMANCE: {query_type} took {execution_time:.3f}s",
            extra=extra
        )
    
    def log_llm_request(self, model: str, execution_time: float, 
                       token_count: int = None):
        """Log performance de requisição LLM."""
        extra = {
            'execution_time': execution_time,
            'model': model,
            'token_count': token_count
        }
        
        self.logger.info(
            f"LLM_PERFORMANCE: {model} took {execution_time:.3f}s",
            extra=extra
        )

class AuditLogger:
    """Logger especializado para audit trail."""
    
    def __init__(self):
        self.logger = setup_logger("gav_audit", use_json_format=True)
    
    def log_user_action(self, user_id: str, action: str, details: Dict = None):
        """Log ação do usuário."""
        extra = {
            'user_id': user_id,
            'action': action,
            'details': details or {}
        }
        
        self.logger.info(f"USER_ACTION: {action}", extra=extra)
    
    def log_system_event(self, event_type: str, details: Dict = None):
        """Log evento do sistema."""
        extra = {
            'event_type': event_type,
            'details': details or {}
        }
        
        self.logger.info(f"SYSTEM_EVENT: {event_type}", extra=extra)
    
    def log_security_event(self, event_type: str, user_id: str = None, 
                          details: Dict = None):
        """Log evento de segurança."""
        extra = {
            'security_event': event_type,
            'user_id': user_id,
            'details': details or {}
        }
        
        self.logger.warning(f"SECURITY: {event_type}", extra=extra)

def get_log_statistics() -> Dict:
    """Retorna estatísticas dos arquivos de log."""
    stats = {}
    
    if LOG_DIR.exists():
        for log_file in LOG_DIR.glob("*.log"):
            try:
                file_stats = log_file.stat()
                stats[log_file.name] = {
                    'size_bytes': file_stats.st_size,
                    'size_mb': round(file_stats.st_size / (1024 * 1024), 2),
                    'modified': datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                    'lines': sum(1 for _ in log_file.open('r', encoding='utf-8', errors='ignore'))
                }
            except Exception as e:
                stats[log_file.name] = {'error': str(e)}
    
    return stats

def cleanup_old_logs(days: int = 30):
    """Remove logs antigos."""
    if not LOG_DIR.exists():
        return
    
    cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
    removed_count = 0
    
    for log_file in LOG_DIR.glob("*.log.*"):  # Arquivos rotacionados
        try:
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()
                removed_count += 1
        except Exception as e:
            logging.error(f"Erro ao remover log antigo {log_file}: {e}")
    
    logging.info(f"Removidos {removed_count} arquivos de log antigos")

# Decorator para logging automático de performance
def log_performance(logger_name: str = "gav_performance"):
    """Decorator para log automático de performance."""
    def decorator(func):
        import functools
        import time
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                perf_logger = PerformanceLogger()
                perf_logger.log_execution_time(
                    func.__name__, 
                    execution_time,
                    {'success': True}
                )
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                perf_logger = PerformanceLogger()
                perf_logger.log_execution_time(
                    func.__name__, 
                    execution_time,
                    {'success': False, 'error': str(e)}
                )
                
                raise
        
        return wrapper
    return decorator

# Decorator para logging automático de audit
def log_audit(action: str):
    """Decorator para log automático de audit."""
    def decorator(func):
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Tenta extrair user_id dos argumentos
            user_id = None
            if args and hasattr(args[0], 'user_id'):
                user_id = args[0].user_id
            elif 'user_id' in kwargs:
                user_id = kwargs['user_id']
            elif 'session_id' in kwargs:
                user_id = kwargs['session_id']
            
            audit_logger = AuditLogger()
            
            try:
                result = func(*args, **kwargs)
                
                audit_logger.log_user_action(
                    user_id or 'unknown',
                    action,
                    {'success': True, 'function': func.__name__}
                )
                
                return result
                
            except Exception as e:
                audit_logger.log_user_action(
                    user_id or 'unknown',
                    action,
                    {'success': False, 'error': str(e), 'function': func.__name__}
                )
                
                raise
        
        return wrapper
    return decorator

# Configuração principal do sistema
def setup_main_logging():
    """Configura logging principal do sistema G.A.V."""
    
    # Cria diretório de logs
    LOG_DIR.mkdir(exist_ok=True)
    
    # Configura logger raiz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove handlers padrão
    root_logger.handlers.clear()
    
    # Configura formatters
    detailed_formatter = logging.Formatter(DETAILED_FORMAT)
    simple_formatter = logging.Formatter(LOG_FORMAT)
    json_formatter = JSONFormatter()
    
    # Handler para console (INFO+)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter(LOG_FORMAT))
    console_handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(console_handler)
    
    # Handler para arquivo principal (DEBUG+)
    main_file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "gav_main.log",
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    main_file_handler.setLevel(logging.DEBUG)
    main_file_handler.setFormatter(detailed_formatter)
    main_file_handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(main_file_handler)
    
    # Handler para erros (ERROR+)
    error_file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "gav_errors.log",
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_file_handler)
    
    # Handler para audit (JSON)
    audit_file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "gav_audit.log",
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    audit_file_handler.setLevel(logging.INFO)
    audit_file_handler.setFormatter(json_formatter)
    audit_file_handler.addFilter(ModuleFilter(['gav_audit']))
    root_logger.addHandler(audit_file_handler)
    
    # Suprime logs verbosos de bibliotecas externas
    logging.getLogger('twilio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # Log inicial
    logging.info("🚀 Sistema de logging G.A.V. inicializado")
    
    return root_logger

# Instâncias globais
performance_logger = PerformanceLogger()
audit_logger = AuditLogger()

# Inicialização automática
if __name__ != "__main__":
    setup_main_logging()