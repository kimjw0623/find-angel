#!/bin/bash

case "$1" in
    start)
        sudo systemctl start lostark-pattern-generator
        sudo systemctl start lostark-price-collector
        sudo systemctl start lostark-item-checker
        echo "서비스들이 시작되었습니다."
        ;;
    stop)
        sudo systemctl stop lostark-price-collector
        sudo systemctl stop lostark-item-checker
        sudo systemctl stop lostark-pattern-generator
        echo "서비스들이 중지되었습니다."
        ;;
    restart)
        sudo systemctl restart lostark-pattern-generator
        sudo systemctl restart lostark-price-collector
        sudo systemctl restart lostark-item-checker
        echo "서비스들이 재시작되었습니다."
        ;;
    status)
        echo "=== Pattern Generator Status ==="
        sudo systemctl status lostark-pattern-generator --no-pager
        echo ""
        echo "=== Price Collector Status ==="
        sudo systemctl status lostark-price-collector --no-pager
        echo ""
        echo "=== Item Checker Status ==="
        sudo systemctl status lostark-item-checker --no-pager
        ;;
    logs)
        if [ -z "$2" ]; then
            echo "Usage: $0 logs [pattern-generator|price-collector|item-checker]"
            exit 1
        fi
        case "$2" in
            pattern-generator)
                sudo journalctl -u lostark-pattern-generator -f
                ;;
            price-collector)
                sudo journalctl -u lostark-price-collector -f
                ;;
            item-checker)
                sudo journalctl -u lostark-item-checker -f
                ;;
            *)
                echo "Invalid service name. Use 'pattern-generator', 'price-collector', or 'item-checker'"
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [service-name]}"
        echo "Examples:"
        echo "  $0 start                      # 모든 서비스 시작"
        echo "  $0 status                     # 모든 서비스 상태 확인"
        echo "  $0 logs pattern-generator     # pattern generator 로그 실시간 보기"
        echo "  $0 logs price-collector       # price collector 로그 실시간 보기"
        echo "  $0 logs item-checker          # item checker 로그 실시간 보기"
        exit 1
        ;;
esac