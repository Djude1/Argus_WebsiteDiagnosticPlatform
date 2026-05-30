# Build stage：用 Node 編譯 React + Vite 產物
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Vite envDir 指向 ..（專案根的 .env），但 docker build context 是 ./frontend，
# 拿不到根目錄的 .env。改用 docker-compose build args 把 GOOGLE_OAUTH_CLIENT_ID
# 寫進 envDir 對應的位置（/app/.. = /），讓 vite build 階段讀得到。
ARG GOOGLE_OAUTH_CLIENT_ID=""
RUN echo "GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}" > /.env

RUN npm run build

# Serve stage：以 nginx 提供靜態檔，並反向代理 /api、/admin、/media 至後端
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
