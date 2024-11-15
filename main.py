import os
import time
from datetime import datetime
from dotenv import load_dotenv
from database import init_database
from price_collector import PriceCollector
from item_checker import ItemChecker
from playsound import playsound

class LostArkMarketMonitor:
    def __init__(self):
        # 환경 변수 로드
        load_dotenv()
        
        # 데이터베이스 초기화
        self.db_manager = init_database()
        
        # 가격 수집기 초기화 (2시간 간격)
        self.price_collector = PriceCollector(
            db_manager=self.db_manager,
            interval=7200
        )
        
        # 아이템 체커 초기화
        self.item_checker = ItemChecker(
            db_manager=self.db_manager
        )
        
        # 알림음 파일 경로
        self.alert_sound_path = 'level-up-2-199574.mp3'

    def play_alert(self):
        """알림음 재생"""
        try:
            playsound(self.alert_sound_path)
        except Exception as e:
            print(f"알림음 재생 실패: {e}")

    def run(self):
        """메인 프로그램 실행"""
        print(f"로스트아크 시장 모니터링 시작 - {datetime.now()}")
        
        try:
            # 가격 수집 스레드 시작
            self.price_collector.start()
            print("가격 수집기 시작됨")

            # 메인 루프 (아이템 체커)
            while True:
                try:
                    # # 새로운 매물 체크
                    # found_notable_items = self.item_checker.check_new_items()
                    
                    # # 주목할 만한 매물이 있으면 알림음 재생
                    # if found_notable_items:
                    #     self.play_alert()
                    
                    # 잠시 대기
                    time.sleep(2)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"아이템 체크 중 오류 발생: {e}")
                    # 오류 발생시 잠시 대기 후 계속
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            print("\n프로그램 종료 중...")
        except Exception as e:
            print(f"심각한 오류 발생: {e}")
        finally:
            print("프로그램 종료됨")

def main():
    """프로그램 시작점"""
    try:
        monitor = LostArkMarketMonitor()
        monitor.run()
    except Exception as e:
        print(f"프로그램 초기화 실패: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())