# file: IA/utils/limited_cache.py
"""
Cache inteligente com limite de tamanho e TTL para o G.A.V.
Resolve problema de cache crescendo indefinidamente em fuzzy_search.py e outros.
"""

import time
import threading
from collections import OrderedDict
from typing import Any, Optional, Dict

class LimitedCache:
    """
    Cache com limite de tamanho e TTL (Time To Live).
    Thread-safe e otimizado para performance.
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Inicializa cache limitado.
        
        Args:
            max_size: Número máximo de itens no cache
            ttl_seconds: Tempo de vida dos itens em segundos
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = OrderedDict()
        self.timestamps = {}
        self.access_counts = {}
        self._lock = threading.RLock()  # Thread-safe
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtém valor do cache, verificando TTL.
        
        Args:
            key: Chave do item
            
        Returns:
            Valor armazenado ou None se não existe/expirado
        """
        with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            # Verifica TTL
            if time.time() - self.timestamps[key] > self.ttl_seconds:
                self._remove_unsafe(key)
                self.misses += 1
                return None
            
            # Move para final (LRU) e incrementa contador
            self.cache.move_to_end(key)
            self.access_counts[key] = self.access_counts.get(key, 0) + 1
            self.hits += 1
            
            return self.cache[key]
    
    def set(self, key: str, value: Any) -> None:
        """
        Armazena valor no cache.
        
        Args:
            key: Chave do item
            value: Valor a ser armazenado
        """
        with self._lock:
            current_time = time.time()
            
            # Remove se já existe
            if key in self.cache:
                self._remove_unsafe(key)
            
            # Remove itens expirados primeiro
            self._cleanup_expired_unsafe()
            
            # Remove item mais antigo se necessário (LRU)
            while len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                self._remove_unsafe(oldest_key)
            
            # Adiciona novo valor
            self.cache[key] = value
            self.timestamps[key] = current_time
            self.access_counts[key] = 1
    
    def _remove_unsafe(self, key: str) -> None:
        """Remove item do cache (versão não thread-safe)."""
        self.cache.pop(key, None)
        self.timestamps.pop(key, None)
        self.access_counts.pop(key, None)
    
    def _cleanup_expired_unsafe(self) -> None:
        """Remove itens expirados (versão não thread-safe)."""
        current_time = time.time()
        expired_keys = []
        
        for key, timestamp in self.timestamps.items():
            if current_time - timestamp > self.ttl_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            self._remove_unsafe(key)
    
    def remove(self, key: str) -> bool:
        """
        Remove item específico do cache.
        
        Args:
            key: Chave do item a ser removido
            
        Returns:
            bool: True se item foi removido, False se não existia
        """
        with self._lock:
            if key in self.cache:
                self._remove_unsafe(key)
                return True
            return False
    
    def clear(self) -> None:
        """Limpa todo o cache."""
        with self._lock:
            self.cache.clear()
            self.timestamps.clear()
            self.access_counts.clear()
            self.hits = 0
            self.misses = 0
    
    def size(self) -> int:
        """Retorna tamanho atual do cache."""
        with self._lock:
            return len(self.cache)
    
    def cleanup(self) -> int:
        """
        Remove itens expirados e retorna quantidade removida.
        
        Returns:
            int: Número de itens removidos
        """
        with self._lock:
            initial_size = len(self.cache)
            self._cleanup_expired_unsafe()
            return initial_size - len(self.cache)
    
    def get_stats(self) -> Dict:
        """
        Retorna estatísticas do cache.
        
        Returns:
            Dict: Estatísticas de uso
        """
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 2),
                "ttl_seconds": self.ttl_seconds,
                "most_accessed": self._get_most_accessed_unsafe()
            }
    
    def _get_most_accessed_unsafe(self) -> Optional[str]:
        """Retorna chave mais acessada (versão não thread-safe)."""
        if not self.access_counts:
            return None
        
        return max(self.access_counts.items(), key=lambda x: x[1])[0]
    
    def contains(self, key: str) -> bool:
        """
        Verifica se chave existe no cache (sem afetar LRU).
        
        Args:
            key: Chave a ser verificada
            
        Returns:
            bool: True se existe e não expirou
        """
        with self._lock:
            if key not in self.cache:
                return False
            
            # Verifica TTL sem afetar ordem LRU
            return time.time() - self.timestamps[key] <= self.ttl_seconds
    
    def keys(self) -> list:
        """
        Retorna lista de chaves válidas (não expiradas).
        
        Returns:
            list: Lista de chaves
        """
        with self._lock:
            valid_keys = []
            current_time = time.time()
            
            for key, timestamp in self.timestamps.items():
                if current_time - timestamp <= self.ttl_seconds:
                    valid_keys.append(key)
            
            return valid_keys
    
    def update_ttl(self, key: str) -> bool:
        """
        Atualiza TTL de um item específico.
        
        Args:
            key: Chave do item
            
        Returns:
            bool: True se item existe e foi atualizado
        """
        with self._lock:
            if key in self.cache:
                self.timestamps[key] = time.time()
                return True
            return False
    
    def set_if_absent(self, key: str, value: Any) -> bool:
        """
        Armazena valor apenas se chave não existe.
        
        Args:
            key: Chave do item
            value: Valor a ser armazenado
            
        Returns:
            bool: True se valor foi armazenado, False se já existia
        """
        with self._lock:
            if self.contains(key):
                return False
            
            self.set(key, value)
            return True
    
    def get_or_set(self, key: str, value_factory) -> Any:
        """
        Obtém valor ou armazena resultado de factory se não existe.
        
        Args:
            key: Chave do item
            value_factory: Função que retorna valor a ser armazenado
            
        Returns:
            Valor do cache ou resultado da factory
        """
        # Primeiro tenta obter do cache
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value
        
        # Se não existe, gera novo valor e armazena
        with self._lock:
            # Double-check locking
            cached_value = self.get(key)
            if cached_value is not None:
                return cached_value
            
            # Gera novo valor
            if callable(value_factory):
                new_value = value_factory()
            else:
                new_value = value_factory
            
            self.set(key, new_value)
            return new_value

class TTLDict(dict):
    """
    Dicionário simples com TTL para casos mais básicos.
    Alternativa mais leve ao LimitedCache.
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        super().__init__()
        self.ttl_seconds = ttl_seconds
        self._timestamps = {}
    
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._timestamps[key] = time.time()
    
    def __getitem__(self, key):
        if self._is_expired(key):
            self._remove_expired(key)
            raise KeyError(key)
        return super().__getitem__(key)
    
    def __contains__(self, key):
        if self._is_expired(key):
            self._remove_expired(key)
            return False
        return super().__contains__(key)
    
    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default
    
    def _is_expired(self, key):
        if key not in self._timestamps:
            return True
        return time.time() - self._timestamps[key] > self.ttl_seconds
    
    def _remove_expired(self, key):
        super().pop(key, None)
        self._timestamps.pop(key, None)
    
    def cleanup(self):
        """Remove todos os itens expirados."""
        expired_keys = [
            key for key in self._timestamps
            if self._is_expired(key)
        ]
        
        for key in expired_keys:
            self._remove_expired(key)
        
        return len(expired_keys)

# Instâncias globais para uso comum
similarity_cache = LimitedCache(max_size=10000, ttl_seconds=3600)  # 1 hora
correction_cache = LimitedCache(max_size=1000, ttl_seconds=1800)   # 30 minutos
prompt_cache = LimitedCache(max_size=10, ttl_seconds=300)          # 5 minutos