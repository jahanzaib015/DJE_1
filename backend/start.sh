#!/bin/bash
# Startup script for Render deployment
# This ensures the app binds to the port immediately

# Don't exit on error - we want to see what's happening
set +e

echo "=== Starting OCRD Extractor Backend ==="
echo "PORT: ${PORT:-8000}"
echo "HOST: ${HOST:-0.0.0.0}"
echo "Working directory: $(pwd)"
echo "Python version: $(python --version 2>&1)"
echo ""

# Ensure we're in the backend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || {
    echo "ERROR: Could not change to script directory: $SCRIPT_DIR"
    exit 1
}

# Set PYTHONPATH to ensure imports work
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
echo "PYTHONPATH: ${PYTHONPATH}"

# Get port from environment (Render sets this)
PORT=${PORT:-8000}
HOST=${HOST:-0.0.0.0}

# Validate PORT is a number
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: PORT must be a number, got: $PORT"
    exit 1
fi

echo "Starting uvicorn on ${HOST}:${PORT}..."
echo "Command: python -m uvicorn app.main:app --host ${HOST} --port ${PORT}"
echo ""

# Test import first
echo "Testing app import..."
python -c "from app.main import app; print('✅ App imported successfully')" || {
    echo "ERROR: Failed to import app"
    exit 1
}

echo ""
echo "Starting server..."
echo ""

# Start uvicorn with explicit error handling
exec python -m uvicorn app.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --log-level info \
    --timeout-keep-alive 30 \
    --no-server-header

