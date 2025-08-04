#!/usr/bin/env bash
set -euo pipefail

# 1) Python

# 1.0) Install Python tools (if needed)
# python -m pip install --upgrade pip
# pip install -r requirements.txt

# 1.1) PEP8 style fix
autopep8 . --recursive --in-place --aggressive --aggressive --exclude .venv,.git,__pycache__,*/migrations/*

# 1.2) lint check
flake8 . --max-line-length=79 --exclude .venv,.git,__pycache__,*/migrations/*

# 1.3) type check
mypy . --exclude '(\.venv/|\.git/|__pycache__/|.*/migrations/.*)'

# 2) JavaScript

# 2.0) Install JavaScript tools (if needed)
# Ensure Node.js and npm are installed.
# npm install standard --global

# 2.1) JavaScript Standard Style fix
if find . -path './.venv' -prune -o -path './.git' -prune -o \
   -type f \( -name "*.js" -o -name "*.mjs" -o -name "*.cjs" -o -name "*.jsx" \) \
   -print -quit 2>/dev/null | grep -q .; then
  npx standard --fix
fi
