# The web app: built once, served by nginx, which also forwards /api to the API so the browser
# sees one origin (session and CSRF cookies work exactly as in development).
FROM node:22-slim AS build
RUN corepack enable
WORKDIR /web
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Telemetry from the browser is off in production unless a collector is set up behind /otlp.
ENV VITE_OTEL_ENABLED=0
RUN pnpm exec vite build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
