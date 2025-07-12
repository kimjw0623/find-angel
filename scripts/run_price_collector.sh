#!/bin/bash
# 로스트아크 가격 수집기 실행 스크립트

cd "$(dirname "$0")/.."
python -m src.core.async_price_collector