FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/tsconfig*.json frontend/vite.config.ts ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN npm run build

FROM caddy:2-alpine

COPY --from=build /app/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
