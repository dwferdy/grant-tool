#!/bin/bash
# OFFLINE version: free keyword checker, no API calls, no cost. Opens http://localhost:8501
cd "$(dirname "$0")"
AI_MODE=offline exec ./run_app.sh "$@"
