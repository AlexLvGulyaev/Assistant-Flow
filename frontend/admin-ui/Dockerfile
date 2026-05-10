# Production-style static bundle for portfolio compose (Vite build + nginx).
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Browser on host calls published Admin API port (see docker-compose.portfolio.yml).
ARG VITE_ADMIN_API_BASE_URL=http://localhost:8600
ENV VITE_ADMIN_API_BASE_URL=$VITE_ADMIN_API_BASE_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
