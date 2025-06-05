#!/bin/sh

CERT_DIR="/etc/nginx/certs"
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/cert.pem" ] || [ ! -f "$CERT_DIR/key.pem" ]; then
  echo "🔐 Generating self-signed certificate..."
  openssl req -x509 -nodes -days 365 \
    -subj "/C=EE/ST=Harjumaa/L=Tallinn/O=Local/CN=localhost" \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem"
fi

echo "🚀 Starting Nginx..."
nginx -g 'daemon off;'