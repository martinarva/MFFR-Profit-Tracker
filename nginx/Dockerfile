FROM nginx:alpine

RUN apk add --no-cache openssl

# Working inside /app (optional but fine)
WORKDIR /app

# ✅ Copy files from local context (already in ./nginx/)
COPY default.conf /etc/nginx/conf.d/default.conf
COPY nginx-entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]