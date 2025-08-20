# file: IA/utils/gav_logger.py
"""
Sistema de logging centralizado e otimizado para o G.A.V.
"""

import logging
from typing import Dict, Optional, Any
import functools
import time
import inspect
from configuracao_logs import configurar_logging_principal, obter_estatisticas_deduplicacao

# Logger global configurado
_logger_principal = None

def inicializar_logging():
    """Inicializa o sistema de logging do G.A.V."""
    global _logger_principal
    if _logger_principal is None:
        _logger_principal = configurar_logging_principal()
    return _logger_principal

def obter_logger(nome_modulo: str = None) -> logging.Logger:
    """Obtém um logger para o módulo especificado."""
    if _logger_principal is None:
        inicializar_logging()
    
    if nome_modulo is None:
        # Tenta detectar o nome do módulo automaticamente
        frame = inspect.currentframe().f_back
        nome_modulo = frame.f_globals.get('__name__', 'desconhecido')
    
    return logging.getLogger(f"gav.{nome_modulo}")

class ContextoLog:
    """Gerenciador de contexto para logs com informações de usuário/sessão."""
    
    def __init__(self, user_id: str = None, session_id: str = None, **kwargs):
        self.contexto = {
            'user_id': user_id or 'N/A',
            'session_id': session_id or 'N/A',
            **kwargs
        }
        self.factory_anterior = None
    
    def __enter__(self):
        # Salva factory anterior
        self.factory_anterior = logging.getLogRecordFactory()
        
        # Cria nova factory que adiciona contexto
        def factory_com_contexto(*args, **kwargs):
            record = self.factory_anterior(*args, **kwargs)
            for chave, valor in self.contexto.items():
                setattr(record, chave, valor)
            return record
        
        logging.setLogRecordFactory(factory_com_contexto)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restaura factory anterior
        if self.factory_anterior:
            logging.setLogRecordFactory(self.factory_anterior)

def log_com_contexto(user_id: str = None, session_id: str = None, **kwargs):
    """Decorator para adicionar contexto a logs automaticamente."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **func_kwargs):
            contexto = {
                'user_id': user_id or func_kwargs.get('user_id', 'N/A'),
                'session_id': session_id or func_kwargs.get('session_id', 'N/A'),
                **kwargs
            }
            
            with ContextoLog(**contexto):
                return func(*args, **func_kwargs)
        return wrapper
    return decorator

def log_performance(func):
    """Decorator para logging automático de performance."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = obter_logger(func.__module__)
        inicio = time.time()
        nome_funcao = f"{func.__module__}.{func.__name__}"
        
        try:
            resultado = func(*args, **kwargs)
            tempo_execucao = time.time() - inicio
            
            logger.info(
                f"PERFORMANCE: {nome_funcao} executada em {tempo_execucao:.3f}s",
                extra={
                    'tempo_execucao': tempo_execucao,
                    'funcao': nome_funcao,
                    'sucesso': True
                }
            )
            
            return resultado
            
        except Exception as e:
            tempo_execucao = time.time() - inicio
            logger.error(
                f"ERRO_PERFORMANCE: {nome_funcao} falhou em {tempo_execucao:.3f}s: {str(e)}",
                extra={
                    'tempo_execucao': tempo_execucao,
                    'funcao': nome_funcao,
                    'sucesso': False,
                    'erro': str(e)
                }
            )
            raise
    
    return wrapper

def log_audit(acao: str, categoria: str = "GERAL"):
    """Decorator para logging de auditoria."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            audit_logger = logging.getLogger("gav_audit")
            nome_funcao = f"{func.__module__}.{func.__name__}"
            
            # Tenta extrair user_id dos argumentos
            user_id = 'N/A'
            if kwargs.get('user_id'):
                user_id = kwargs['user_id']
            elif kwargs.get('session_id'):
                user_id = kwargs['session_id']
            elif hasattr(args[0] if args else None, 'user_id'):
                user_id = getattr(args[0], 'user_id', 'N/A')
            
            try:
                resultado = func(*args, **kwargs)
                
                audit_logger.info(
                    f"AUDIT: {acao} - {categoria}",
                    extra={
                        'acao': acao,
                        'categoria': categoria,
                        'funcao': nome_funcao,
                        'user_id': user_id,
                        'sucesso': True
                    }
                )
                
                return resultado
                
            except Exception as e:
                audit_logger.warning(
                    f"AUDIT_FALHA: {acao} - {categoria} - {str(e)}",
                    extra={
                        'acao': acao,
                        'categoria': categoria,
                        'funcao': nome_funcao,
                        'user_id': user_id,
                        'sucesso': False,
                        'erro': str(e)
                    }
                )
                raise
        
        return wrapper
    return decorator

# Funções de conveniência para logging comum
def _preparar_contexto_seguro(user_id: str = None, session_id: str = None, **extras):
    """Prepara contexto de logging de forma segura, evitando sobrescrever campos existentes."""
    import logging
    
    extra_dict = {}
    
    # Verifica se o logger atual tem factory personalizado que adiciona user_id/session_id
    current_factory = logging.getLogRecordFactory()
    factory_original = logging.LogRecord
    
    # Se há factory personalizado, não adiciona user_id/session_id no extra
    if current_factory != factory_original:
        # Factory personalizado já adiciona contexto, só adiciona extras seguros
        pass
    else:
        # Sem factory personalizado, adiciona contexto via extra
        extra_dict['user_id'] = user_id or 'N/A'
        extra_dict['session_id'] = session_id or 'N/A'
    
    # Adiciona extras, evitando campos do LogRecord padrão e conflitos conhecidos
    reserved_fields = {
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
        'filename', 'module', 'lineno', 'funcName', 'created', 
        'msecs', 'relativeCreated', 'thread', 'threadName',
        'processName', 'process', 'message', 'exc_info', 'exc_text',
        'stack_info', 'user_id', 'session_id'  # Adicionados para evitar conflito
    }
    
    for key, value in extras.items():
        if key not in reserved_fields:
            extra_dict[key] = value
    
    return extra_dict

def log_debug(message: str, user_id: str = None, session_id: str = None, **extras):
    """Log de debug com contexto seguro."""
    logger = obter_logger()
    extra_dict = _preparar_contexto_seguro(user_id, session_id, **extras)
    logger.debug(message, extra=extra_dict)

def log_info(message: str, user_id: str = None, session_id: str = None, **extras):
    """Log de informação com contexto seguro."""
    logger = obter_logger()
    extra_dict = _preparar_contexto_seguro(user_id, session_id, **extras)
    logger.info(message, extra=extra_dict)

def log_warning(message: str, user_id: str = None, session_id: str = None, **extras):
    """Log de aviso com contexto seguro."""
    logger = obter_logger()
    extra_dict = _preparar_contexto_seguro(user_id, session_id, **extras)
    logger.warning(message, extra=extra_dict)

def log_error(message: str, user_id: str = None, session_id: str = None, exception: Exception = None, **extras):
    """Log de erro com contexto seguro."""
    logger = obter_logger()
    extra_dict = _preparar_contexto_seguro(user_id, session_id, **extras)
    
    if exception:
        logger.error(message, exc_info=exception, extra=extra_dict)
    else:
        logger.error(message, extra=extra_dict)

def log_critical(message: str, user_id: str = None, session_id: str = None, exception: Exception = None, **extras):
    """Log crítico com contexto seguro."""
    logger = obter_logger()
    extra_dict = _preparar_contexto_seguro(user_id, session_id, **extras)
    
    if exception:
        logger.critical(message, exc_info=exception, extra=extra_dict)
    else:
        logger.critical(message, extra=extra_dict)

def log_whatsapp_error(message: str, error_code: str = None, user_id: str = None, **extras):
    """Log específico para erros do WhatsApp."""
    logger = obter_logger("whatsapp")
    extra_dict = {
        'user_id': user_id or 'N/A',
        'error_code': error_code,
        'categoria': 'WHATSAPP_ERROR',
        **extras
    }
    logger.error(f"WHATSAPP_ERROR: {message}", extra=extra_dict)

def log_database_query(query_type: str, execution_time: float, rows_affected: int = None, user_id: str = None, **extras):
    """Log específico para consultas de banco de dados."""
    logger = obter_logger("database")
    extra_dict = {
        'query_type': query_type,
        'execution_time': execution_time,
        'rows_affected': rows_affected,
        'user_id': user_id or 'N/A',
        'categoria': 'DATABASE_PERFORMANCE',
        **extras
    }
    logger.info(f"DB_QUERY: {query_type} - {execution_time:.3f}s", extra=extra_dict)

def log_llm_request(model: str, execution_time: float, token_count: int = None, user_id: str = None, **extras):
    """Log específico para requisições LLM."""
    logger = obter_logger("llm")
    extra_dict = {
        'model': model,
        'execution_time': execution_time,
        'token_count': token_count,
        'user_id': user_id or 'N/A',
        'categoria': 'LLM_PERFORMANCE',
        **extras
    }
    logger.info(f"LLM_REQUEST: {model} - {execution_time:.3f}s", extra=extra_dict)

def obter_status_logs():
    """Retorna status detalhado do sistema de logging."""
    from configuracao_logs import obter_estatisticas_logs
    
    return {
        'deduplicacao': obter_estatisticas_deduplicacao(),
        'arquivos': obter_estatisticas_logs(),
        'logger_principal_ativo': _logger_principal is not None,
        'nivel_root': logging.getLogger().level
    }

# Inicialização automática
inicializar_logging()