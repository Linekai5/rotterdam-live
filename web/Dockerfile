# Multi-Stage Dockerfile for Rotterdam Live Frontend (Svelte + Vite)
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency definitions
COPY package*.json ./

# Install clean dependencies
RUN npm ci

# Copy source code and assets
COPY . .

# Build production bundle to dist/
RUN npm run build

# Production static serving runtime
FROM nginx:stable-alpine AS runner

# Copy built application assets to nginx root
COPY --from=builder /app/dist /usr/share/nginx/html

# Hardened minimal nginx configuration for the internal web container
RUN cat <<'EOF' > /etc/nginx/conf.d/default.conf
server {
    listen 80;
    listen [::]:80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Same-origin API access works in the local Docker preview as well as
    # behind the production gateway. Preserve the original request path.
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Static asset caching headers
    location ~* \.(?:css|js|jpg|jpeg|gif|png|ico|cur|gz|svg|svgz|mp4|ogg|ogv|webm|htc|woff|woff2|ttf)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
}
EOF

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
