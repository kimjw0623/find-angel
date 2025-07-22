#!/bin/bash

echo "Installing Lost Ark services..."

# 시스템 서비스 디렉토리로 복사
sudo cp lostark-pattern-generator.service /etc/systemd/system/
sudo cp lostark-price-collector.service /etc/systemd/system/
sudo cp lostark-item-checker.service /etc/systemd/system/

# systemd 데몬 리로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅시 자동 시작)
sudo systemctl enable lostark-pattern-generator.service
sudo systemctl enable lostark-price-collector.service
sudo systemctl enable lostark-item-checker.service

# logrotate 설정 설치
echo "Installing logrotate configuration..."
sudo cp lostark-logrotate.conf /etc/logrotate.d/lostark

# logs 디렉토리 생성
mkdir -p /home/ahrrri/find-angel/logs

echo "✅ 서비스가 성공적으로 설치되었습니다."
echo ""
echo "🚀 서비스 시작:"
echo "  ./manage-services.sh start"
echo ""
echo "📊 상태 확인:"
echo "  ./manage-services.sh status"
echo ""
echo "📋 로그 확인:"
echo "  ./manage-services.sh logs pattern-generator"
echo "  ./manage-services.sh logs price-collector" 
echo "  ./manage-services.sh logs item-checker"
echo ""
echo "📂 로그 파일 위치: /home/ahrrri/find-angel/logs/"
echo "🔄 로그 로테이션: 매일, 7일 보관"