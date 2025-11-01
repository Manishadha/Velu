# velu-console/Dockerfile

FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# write a SPA-friendly nginx conf; single-quoted heredoc prevents $ expansion
RUN cat > /etc/nginx/conf.d/default.conf <<'NGINX'
server {
  listen 80;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  # Single-page app fallback
  location / {
    try_files $uri $uri/ /index.html;
  }
}
NGINX
