#!/bin/bash
# 로스트아크 실시간 매물 체커 실행 스크립트

cd "$(dirname "$0")/.."

# 가상 환경 활성화
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# PYTHONPATH 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

python -m src.core.async_item_checker