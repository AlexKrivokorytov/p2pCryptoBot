#!/bin/bash
echo "===================================================================="
echo "🚀 Starting P2P Bot Test Suite Verification..."
echo "===================================================================="
echo ""
echo "Installing testing dependencies in the container and running pytest..."
echo "Please wait..."
echo ""

docker compose run --rm -v "$(pwd):/app" bot bash -c "pip install -q pytest pytest-asyncio pytest-cov pytest-sugar aiohttp && python -m pytest"
EXIT_CODE=$?

echo ""
echo "===================================================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ SUCCESS: All tests passed flawlessly! Great job!"
else
    echo "❌ FAILED: Some tests encountered issues. See the report above for details."
fi
echo "===================================================================="

exit $EXIT_CODE
