#!/bin/bash
# Buka UI officer di browser (http://localhost:8501). Membuat .venv otomatis kalau belum ada.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Membuat virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

.venv/bin/streamlit run app.py "$@"
