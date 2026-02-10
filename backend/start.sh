#!/bin/bash
# Startup script for Railway deployment

# Set the Python path to include the current directory
export PYTHONPATH=/app:$PYTHONPATH

# Start uvicorn
exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
