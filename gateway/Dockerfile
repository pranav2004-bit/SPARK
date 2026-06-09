FROM nginx:1.25-alpine

# Bake config into image — avoids Windows bind-mount I/O issues
# and enables clean `nginx -s reload` from within the container.
COPY nginx.conf /etc/nginx/conf.d/default.conf
