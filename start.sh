#!/bin/bash

# Optimize memory allocation to prevent fragmentation in limited RAM
export MALLOC_ARENA_MAX=2

# Start the Celery worker with extreme memory constraints (--pool=solo executes tasks in main process)
echo "Starting Celery Worker (Memory Optimized)..."
celery -A celery_worker.celery worker --beat --pool=solo --loglevel=warning &

# Start the Flask web app with 1 worker and preloaded memory
echo "Starting Gunicorn server (Memory Optimized)..."
gunicorn run:app --workers 1 --threads 4 --preload
