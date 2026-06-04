#!/bin/bash
echo "Stopping Gunicorn..."
pkill gunicorn

echo "Activating virtual environment..."
source ~/myapi-env/bin/activate

echo "Starting Gunicorn..."
gunicorn --bind 127.0.0.1:5000 app:app --daemon

echo "API restarted successfully!"
