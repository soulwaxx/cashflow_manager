# ── Stage 1: Build frontend ────────────────────────────────────────────────
FROM node:24-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install --global npm@11.19.0 \
    && npm ci
COPY frontend/ .
RUN npm run build

# ── Stage 2: Production image ──────────────────────────────────────────────
FROM python:3.14-alpine
WORKDIR /app

# System packages
RUN apk add --no-cache nginx supervisor

# Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Frontend static files
COPY --from=frontend-build /app/dist /usr/share/nginx/html

# Backend source + migrations
COPY backend/ .

# Process management configs
COPY nginx.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisord.conf
COPY start.sh /app/start.sh

# Make runtime-writable directories world-accessible so any UID supplied
# via docker-compose `user:` works without permission errors.
# All paths follow FHS: pid files in /run, nginx state in /var/lib/nginx.
RUN chmod +x /app/start.sh \
    && mkdir -p \
    /app/data \
    /run \
    /var/lib/nginx/client_temp \
    /var/lib/nginx/proxy_temp \
    /var/lib/nginx/fastcgi_temp \
    /var/lib/nginx/uwsgi_temp \
    /var/lib/nginx/scgi_temp \
    /var/lib/nginx/logs \
    /var/log/nginx \
    && chmod -R 777 /app/data /run /var/lib/nginx /var/log/nginx

# Default to a non-root UID for defense-in-depth.
# deploy/docker-compose.yml overrides this with `user: ${APP_UID}:${APP_GID}`,
# but anyone running `docker run` directly should not land as root.
USER 1000:1000

EXPOSE 8080
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
