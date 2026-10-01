#!/bin/bash
set -e
cd "$(dirname "$0")/.."
pip install -r docs/requirements.txt
python docs/generate_pdf.py
echo "✅ الدليل جاهز: docs/USER_MANUAL.pdf"
