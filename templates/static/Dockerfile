# Site statique servi par Nginx sans privilèges root (port 8080).
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/security-headers.conf /etc/nginx/security-headers.conf
COPY . /usr/share/nginx/html

# Les fichiers de build copiés avec le site ne doivent pas être servis.
USER root
RUN rm -rf /usr/share/nginx/html/docker /usr/share/nginx/html/Dockerfile
USER 101

EXPOSE 8080
