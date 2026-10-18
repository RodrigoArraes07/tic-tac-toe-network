#!/usr/bin/env bash
# Emite o primeiro certificado do Let's Encrypt e sobe a stack de produção.
# Rodar uma vez, na raiz do repositório, com o .env de produção pronto:
#   ./infra/deploy/primeiro-certificado.sh            # certificado real
#   ./infra/deploy/primeiro-certificado.sh --staging  # teste, sem gastar o limite
set -euo pipefail

COMPOSE=(docker compose -f compose.yaml -f compose.prod.yaml)
WEBROOT=/var/www/certbot

extra_args=()
if [[ "${1:-}" == "--staging" ]]; then
    extra_args+=(--staging)
fi

read_env() {
    grep -E "^$1=" .env | tail -n 1 | cut -d= -f2-
}

domain="$(read_env DOMAIN || true)"
email="$(read_env LETSENCRYPT_EMAIL || true)"
if [[ -z "$domain" || -z "$email" ]]; then
    echo "Defina DOMAIN e LETSENCRYPT_EMAIL no .env antes de continuar." >&2
    exit 1
fi

# O Nginx não sobe sem certificado. Por isso o primeiro sai no modo standalone,
# com o próprio certbot ocupando a porta 80 enquanto o Nginx ainda está parado.
echo "Emitindo o certificado de $domain..."
"${COMPOSE[@]}" run --rm --no-deps -p 80:80 --entrypoint certbot certbot \
    certonly --standalone --non-interactive --agree-tos \
    --email "$email" -d "$domain" "${extra_args[@]}"

echo "Subindo a stack..."
"${COMPOSE[@]}" up -d --build --wait

# Daqui em diante a renovação passa pelo Nginx (webroot); o reconfigure grava
# isso na configuração do certificado e faz um teste de renovação.
echo "Configurando a renovação por webroot..."
"${COMPOSE[@]}" run --rm --no-deps --entrypoint certbot certbot \
    reconfigure --cert-name "$domain" --webroot -w "$WEBROOT"

echo "Pronto: https://$domain"
