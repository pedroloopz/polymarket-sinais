#!/usr/bin/env bash
# Avisa no Telegram que um workflow falhou (com o link do log).
# Uso: avisar_falha.sh "Nome do workflow"
set -uo pipefail
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  echo "Telegram não configurado; sem aviso."
  exit 0
fi
log="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
curl -s -o /dev/null -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  --data-urlencode text="⚠️ Falhou: $1. Enquanto isso, o painel pode ficar desatualizado. Log: ${log}"
