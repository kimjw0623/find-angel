#!/bin/bash

# 알림 허브 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🔔 Starting Find Angel Notification Hub..."
echo "📍 Working directory: $(pwd)"

# 환경 변수 로드
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env"
    export $(cat .env | xargs)
fi

# 가상환경 활성화 (있다면)
if [ -d "venv" ]; then
    echo "🐍 Activating virtual environment"
    source venv/bin/activate
fi

# Python 경로 설정
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "🚀 Starting notification hub..."
python -m src.notifications.notification_hub