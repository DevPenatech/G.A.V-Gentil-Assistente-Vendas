# Dockerfile

# --- Estágio 1: Imagem Base ---
# Começamos com uma imagem oficial do Python. A versão 'slim' é menor e ideal para produção.
# Use a mesma versão do Python que você tem localmente para evitar problemas (ex: 3.9, 3.10, etc.)
FROM python:3.9-slim as base

# Instala dependências do sistema necessárias
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Variáveis de ambiente globais
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=America/Sao_Paulo

# --- Estágio 2: Configuração do Ambiente ---

FROM base as python-deps
# Atualiza pip e instala wheel
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Define diretório de trabalho
WORKDIR /app

FROM base as production
# --- Estágio 4: Copiar o Código da Aplicação ---
# <<< MUDANÇA AQUI: Copia todo o conteúdo da pasta /IA para o diretório de trabalho /app >>>
COPY IA/ .

# CORRIGIDO: Cria diretórios necessários
RUN mkdir -p /app/logs /app/data

# Copia dependências Python do estágio anterior
COPY --from=python-deps /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

#RUN python knowledge/knowledge.py

# --- Estágio 5: Comando de Execução ---
# Expõe a porta que a aplicação usará.
EXPOSE 8080

# O comando para iniciar o servidor Flask.
# Como copiamos o conteúdo de /IA para /app, o app.py estará na raiz do WORKDIR.
CMD ["python", "app.py"]
