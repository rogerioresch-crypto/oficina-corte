#!/bin/bash
# ─── Analytics Pro — Iniciar Backend ───────────────────────
set -e

cd "$(dirname "$0")/backend"

# Copia .env.example se .env não existe
if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  Arquivo .env criado. Preencha suas credenciais em backend/.env antes de continuar."
  exit 1
fi

echo "🚀 Iniciando Analytics Pro API em http://localhost:8000"
echo "📊 Abra o frontend em http://localhost:8000"
echo ""

python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
