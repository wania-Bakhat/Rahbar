FROM nginxinc/nginx-unprivileged:1.27.5-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
