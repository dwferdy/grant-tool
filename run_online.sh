#!/bin/bash
# ONLINE version: Claude reviews applications (uses API credits). Opens http://localhost:8501
# No API key yet? The app shows a step-by-step "Connect Claude" screen under AI mode.
cd "$(dirname "$0")"
AI_MODE=claude exec ./run_app.sh "$@"
