#!/bin/bash
# API 인스펙터 도구 실행 스크립트

cd "$(dirname "$0")/.."

# 가상 환경 활성화
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# PYTHONPATH 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

python tools/api_inspector.py