# Etape 1 : construction de l'interface.
FROM node:22-alpine AS construction
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Etape 2 : service des fichiers statiques.
FROM nginx:1.27-alpine
COPY --from=construction /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
