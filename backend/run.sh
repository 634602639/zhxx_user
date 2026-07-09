#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
[ ! -d venv ] && python -m venv venv
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate
pip install -q -r requirements.txt
echo "[info] starting on http://localhost:5000"
python app.py
