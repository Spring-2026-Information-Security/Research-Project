#!/usr/bin/env bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
echo "Created .venv. To activate: source .venv/bin/activate"