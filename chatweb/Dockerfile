# file: chatweb/Dockerfile

FROM node:18-alpine AS development
WORKDIR /app

# Copia os arquivos de definição de dependências PRIMEIRO para otimizar o cache
COPY package.json ./
COPY package-lock.json ./

# Instala as dependências
RUN npm install

# Copia o resto do código-fonte
COPY . .

# Expõe a porta do servidor de desenvolvimento
EXPOSE 3000

# Comando para iniciar o servidor de desenvolvimento
CMD ["npm", "start"]