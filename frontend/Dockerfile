# Base images overridable for regions where Docker Hub is unreachable (e.g.
# mainland China): compose passes BUN_IMAGE/NGINX_IMAGE prefixed with a registry
# mirror (docker.1ms.run/oven/bun:1, docker.1ms.run/library/nginx:1).
# ARGs used by FROM must be declared at the very top for the classic builder.
ARG BUN_IMAGE=oven/bun:1
ARG NGINX_IMAGE=nginx:1

FROM ${BUN_IMAGE} AS build-stage

WORKDIR /app

COPY package.json bun.lock /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

# Optional registry mirror for restricted networks (e.g. https://registry.npmmirror.com).
ARG NPM_REGISTRY
RUN bun install ${NPM_REGISTRY:+--registry "$NPM_REGISTRY"}

COPY ./frontend /app/frontend
ARG VITE_API_URL

RUN bun run build


FROM ${NGINX_IMAGE}

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf
