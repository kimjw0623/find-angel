#!/bin/bash

# 시스템 서비스 디렉토리로 복사
sudo cp lostark-price-collector.service /etc/systemd/system/
# sudo cp lostark-item-checker.service /etc/systemd/system/

# systemd 데몬 리로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅시 자동 시작)
sudo systemctl enable lostark-price-collector.service
# sudo systemctl enable lostark-item-checker.service

echo "서비스가 성공적으로 설치되었습니다."
echo "서비스 시작: sudo systemctl start lostark-price-collector"
# echo "서비스 시작: sudo systemctl start lostark-item-checker"
echo "상태 확인: sudo systemctl status lostark-price-collector"
echo "로그 확인: sudo journalctl -u lostark-price-collector -f"