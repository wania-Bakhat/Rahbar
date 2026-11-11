FROM node:22.14.0-alpine AS assets
WORKDIR /src
COPY index.html ./index.html

FROM nginxinc/nginx-unprivileged:1.27.5-alpine AS runtime
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=assets /src/index.html /usr/share/nginx/html/index.html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
