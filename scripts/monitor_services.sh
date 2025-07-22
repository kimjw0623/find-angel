#!/bin/bash

# Lost Ark 서비스들의 리소스 사용량 모니터링 스크립트

echo "=== Lost Ark Services Resource Monitor ==="
echo "Timestamp: $(date)"
echo ""

# 서비스 상태 확인
echo "📊 Service Status:"
for service in lostark-price-collector lostark-pattern-generator lostark-item-checker; do
    status=$(systemctl is-active $service 2>/dev/null || echo "inactive")
    echo "  $service: $status"
done
echo ""

# 프로세스별 리소스 사용량
echo "💻 Process Resource Usage:"
echo "  PID    %CPU %MEM   VSZ   RSS NICE  COMMAND"
echo "  ----------------------------------------"

# Lost Ark 관련 프로세스 찾기
ps aux | grep -E "(price_collector|pattern_generator|item_checker)" | grep -v grep | while read line; do
    echo "  $line"
done
echo ""

# 메모리 사용량 요약
echo "🧠 Memory Usage Summary:"
total_mem=$(free -m | awk 'NR==2{printf "%.0f", $2}')
used_mem=$(free -m | awk 'NR==2{printf "%.0f", $3}')
free_mem=$(free -m | awk 'NR==2{printf "%.0f", $4}')
echo "  Total: ${total_mem}MB | Used: ${used_mem}MB | Free: ${free_mem}MB"
echo ""

# 디스크 I/O 통계 (iotop 대체)
echo "💾 Disk Usage:"
df -h . | tail -1 | awk '{print "  Disk Usage: " $3 "/" $2 " (" $5 ")"}'
echo ""

# 로그 파일 크기 확인
echo "📋 Log File Sizes:"
log_dir="/home/ahrrri/find-angel/logs"
if [ -d "$log_dir" ]; then
    for log_file in "$log_dir"/*.log; do
        if [ -f "$log_file" ]; then
            size=$(du -h "$log_file" | cut -f1)
            echo "  $(basename "$log_file"): $size"
        fi
    done
else
    echo "  Log directory not found"
fi
echo ""

# 개별 서비스 PID와 우선순위 정보
echo "🎯 Service Priority Info:"
for service in lostark-price-collector lostark-pattern-generator lostark-item-checker; do
    pid=$(systemctl show $service --property=MainPID --value 2>/dev/null)
    if [ "$pid" != "0" ] && [ -n "$pid" ]; then
        nice_val=$(ps -o ni= -p $pid 2>/dev/null | tr -d ' ')
        echo "  $service (PID: $pid, Nice: $nice_val)"
    fi
done
echo ""

echo "=== Monitor Complete ==="