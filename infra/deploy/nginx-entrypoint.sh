#!/bin/sh
# Sobe o Nginx pelo entrypoint oficial (que renderiza o template) e o recarrega
# quando o certbot marca uma renovação, sem dar ao certbot acesso ao Docker.
set -eu

RENEWED_FLAG=/etc/letsencrypt/renewed
RELOADED_FLAG=/tmp/nginx-reloaded
CHECK_INTERVAL_S=300

watch_renewals() {
    touch "$RELOADED_FLAG"
    while :; do
        sleep "$CHECK_INTERVAL_S"
        if [ "$RENEWED_FLAG" -nt "$RELOADED_FLAG" ]; then
            nginx -s reload && touch "$RELOADED_FLAG"
        fi
    done
}

watch_renewals &
exec /docker-entrypoint.sh nginx -g 'daemon off;'
