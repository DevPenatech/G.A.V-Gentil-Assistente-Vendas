# Dockerfile

# --- Estágio 1: Imagem Base ---
# Começamos com uma imagem oficial do Python. A versão 'slim' é menor e ideal para produção.
# Use a mesma versão do Python que você tem localmente para evitar problemas (ex: 3.9, 3.10, etc.)
FROM python:3.9-slim

# --- Estágio 2: Configuração do Ambiente ---
# Define o diretório de trabalho dentro do contêiner.
WORKDIR /app

# Define variáveis de ambiente para o Python.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- Estágio 3: Instalação das Dependências ---
# <<< MUDANÇA AQUI: Copia o requirements.txt de dentro da pasta /IA >>>
COPY requirements.txt .

# Instala as bibliotecas Python listadas.
RUN pip install --no-cache-dir -r requirements.txt

# --- Estágio 4: Copiar o Código da Aplicação ---
# <<< MUDANÇA AQUI: Copia todo o conteúdo da pasta /IA para o diretório de trabalho /app >>>
COPY IA/ .

# --- Estágio 5: Comando de Execução ---
# Expõe a porta que a aplicação usará.
EXPOSE 8080

# O comando para iniciar o servidor Flask.
# Como copiamos o conteúdo de /IA para /app, o app.py estará na raiz do WORKDIR.
CMD ["python", "app.py"]
