FROM nginx:1.25-alpine

# Replace the entire main config (gives us worker_processes, events{}, http{} control)
COPY nginx.conf /etc/nginx/nginx.conf
COPY proxy_params.conf /etc/nginx/proxy_params.conf
