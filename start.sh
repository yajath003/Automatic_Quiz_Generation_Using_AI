#!/bin/bash

# Start the Celery worker centrally in the background
echo "Starting Celery Worker..."
celery -A celery_worker.celery worker --beat --loglevel=info &

# Start the Flask web application in the foreground
echo "Starting Gunicorn server..."
gunicorn run:app
