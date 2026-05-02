#!/bin/bash
set -e

cd /app
export PYTHONUNBUFFERED=1

exec python main.py
