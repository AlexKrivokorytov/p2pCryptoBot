#!/bin/bash
# P2P Bot Quality Check Script (GitHub-like)
set -e

echo "🚀 Running P2P Bot Quality Checks..."

echo -e "\n🔍 Running Ruff Lint..."
ruff check . --fix

echo -e "\n🎨 Checking Code Formatting..."
ruff format .

echo -e "\n🧪 Running Mypy Strict Check..."
mypy --strict bot/ services/ providers/ utils/ tasks/ db/

echo -e "\n✅ Running Tests..."
pytest tests/

echo -e "\n✨ ALL CHECKS PASSED! ✨"
