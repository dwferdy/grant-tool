#!/bin/bash
# Jalankan semua test. Membuat .venv dan install library otomatis kalau belum ada.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Membuat virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

.venv/bin/python -m pytest -q "$@"
