#!/usr/bin/env bash
# Salva ./dados no branch `dados` como um ÚNICO commit (sem histórico).
# Motivo: o SQLite é binário; guardar um commit por hora incharia o repositório
# em gigabytes. O backup diário fica como artefato das Actions (7 dias).
set -euo pipefail
cd dados
if [ ! -f bot.sqlite ]; then
  echo "Nada para salvar (dados/bot.sqlite não existe)."
  exit 0
fi
cat > LEIAME.md <<'EOF'
# Branch de dados
Gerado automaticamente pelas GitHub Actions. Não edite.
- `bot.sqlite`: histórico (séries, mercados, diário de sinais).
- Este branch guarda só o último estado (um commit, sobrescrito a cada execução).
EOF
git add -A
arvore=$(git write-tree)
commit=$(echo "dados: $(date -u +%Y-%m-%dT%H:%MZ)" | git commit-tree "$arvore")
for tentativa in 1 2 3 4; do
  if git push -q -f origin "$commit:refs/heads/dados"; then
    echo "Dados salvos no branch dados."
    exit 0
  fi
  sleep $((2 ** tentativa))
done
echo "::error::Não consegui salvar o branch dados."
exit 1
