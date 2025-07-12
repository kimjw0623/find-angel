#!/bin/bash
# 로스트아크 실시간 매물 체커 실행 스크립트

cd "$(dirname "$0")/.."
python -m src.core.async_item_checker