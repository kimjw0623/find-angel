#!/usr/bin/env python3
"""
로스트아크 API 인스펙터 - JSON 기반 API 테스트 도구

사용법:
  python api_inspector.py
  
JSON 파일을 준비해서 API 요청을 테스트할 수 있습니다.
"""

import json
import aiohttp
import asyncio
import os
from datetime import datetime
from typing import Dict, Any, Optional
from src.common.config import config

class APIInspector:
    def __init__(self):
        self.config = config
        self.api_base = config.api_base_url
        self.auction_endpoint = config.api_auction_endpoint
        # 첫 번째 토큰을 테스트용으로 사용
        self.test_token = config.price_tokens[0] if config.price_tokens else None
        
    def print_json(self, data: Any, title: str = ""):
        """JSON 데이터를 보기 좋게 출력"""
        if title:
            print(f"\n📋 {title}")
            print("=" * 60)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        
    def list_json_files(self) -> list:
        """현재 디렉토리의 JSON 파일 목록 반환"""
        return [f for f in os.listdir('.') if f.endswith('.json')]
    
    async def send_single_request(self, url: str, data: Dict) -> Dict:
        """단일 API 요청 전송"""
        headers = {
            'accept': 'application/json',
            'authorization': f"bearer {self.test_token}",
            'content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=data, headers=headers) as response:
                    response_data = await response.json()
                    
                    return {
                        'status': response.status,
                        'data': response_data,
                        'headers': dict(response.headers)
                    }
            except aiohttp.ClientError as e:
                return {
                    'status': 0,
                    'error': str(e)
                }
    
    async def send_request_from_json(self, json_file: str, endpoint: Optional[str] = None):
        """JSON 파일을 읽어서 API 요청 전송"""
        try:
            # JSON 파일 읽기
            with open(json_file, 'r', encoding='utf-8') as f:
                request_data = json.load(f)
            
            print(f"\n📄 {json_file} 파일을 읽었습니다.")
            self.print_json(request_data, "요청 데이터")
            
            # 엔드포인트 설정
            if endpoint is None:
                endpoint = self.auction_endpoint
            
            full_url = self.api_base + endpoint
            print(f"\n🌐 URL: {full_url}")
            
            # 토큰 확인
            if not self.test_token:
                print("❌ API 토큰이 설정되지 않았습니다. .env 파일을 확인하세요.")
                return
            
            # 요청 전송
            print("\n🚀 API 요청을 전송합니다...")
            start_time = datetime.now()
            result = await self.send_single_request(full_url, request_data)
            end_time = datetime.now()
            
            print(f"⏱️  응답 시간: {(end_time - start_time).total_seconds():.2f}초")
            print(f"📊 응답 상태: {result['status']}")
            
            # 응답 처리
            if result['status'] == 200:
                print("\n✅ 요청 성공!")
                self.print_json(result['data'], "응답 데이터")
                
                # 응답 구조 분석
                self.analyze_response(result['data'])
                
                # 응답 저장 옵션
                save = input("\n💾 응답을 파일로 저장하시겠습니까? (y/n): ").strip().lower()
                if save == 'y':
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_file = f"response_{timestamp}.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(result['data'], f, ensure_ascii=False, indent=2)
                    print(f"✅ 응답이 {output_file}에 저장되었습니다.")
                    
            elif result['status'] == 0:
                print(f"\n❌ 연결 에러: {result.get('error', 'Unknown error')}")
            else:
                print(f"\n❌ HTTP {result['status']} 에러")
                if 'data' in result:
                    self.print_json(result['data'], "에러 응답")
                
        except FileNotFoundError:
            print(f"❌ 파일을 찾을 수 없습니다: {json_file}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 에러: {e}")
        except Exception as e:
            print(f"❌ 예상치 못한 에러: {e}")
            import traceback
            traceback.print_exc()
    
    def analyze_response(self, response: Dict):
        """응답 구조 분석"""
        print(f"\n📊 응답 구조 분석:")
        print(f"• 최상위 키들: {list(response.keys())}")
        
        # Items 분석
        if 'Items' in response:
            items = response['Items']
            print(f"• 아이템 개수: {len(items)}")
            
            if items:
                first_item = items[0]
                print(f"• 첫 번째 아이템 키들: {list(first_item.keys())}")
                
                # 옵션 분석
                if 'Options' in first_item:
                    options = first_item['Options']
                    print(f"• 옵션 개수: {len(options)}")
                    if options:
                        print(f"• 첫 번째 옵션: {options[0]}")
                
                # 경매 정보 분석
                if 'AuctionInfo' in first_item:
                    auction_info = first_item['AuctionInfo']
                    print(f"• 경매 정보 키들: {list(auction_info.keys())}")
        
        # 페이지 정보 분석
        if 'PageNo' in response:
            print(f"• 현재 페이지: {response.get('PageNo', 0)}")
            print(f"• 전체 아이템 수: {response.get('TotalCount', 0)}")
            print(f"• 페이지당 아이템 수: {response.get('PageSize', 0)}")
    
    async def interactive_mode(self):
        """대화형 모드"""
        print("🎮 로스트아크 API 인스펙터 (JSON 파일 기반)")
        print("=" * 60)
        print("사용법:")
        print("1. JSON 파일을 현재 디렉토리에 준비하세요")
        print("2. 'list' - JSON 파일 목록 보기")
        print("3. 'send <파일명>' - JSON 파일로 요청 보내기")
        print("4. 'send <파일명> <엔드포인트>' - 특정 엔드포인트로 요청")
        print("5. 'help' - 도움말")
        print("6. 'exit' - 종료")
        print("=" * 60)
        
        while True:
            try:
                command = input("\n명령을 입력하세요 > ").strip()
                
                if command.lower() in ['exit', 'q']:
                    print("👋 종료합니다.")
                    break
                    
                elif command.lower() == 'list':
                    json_files = self.list_json_files()
                    if json_files:
                        print("\n📁 JSON 파일 목록:")
                        for i, file in enumerate(json_files, 1):
                            print(f"  {i}. {file}")
                    else:
                        print("❌ JSON 파일이 없습니다.")
                        
                elif command.lower().startswith('send '):
                    parts = command.split(maxsplit=2)
                    if len(parts) >= 2:
                        json_file = parts[1]
                        endpoint = parts[2] if len(parts) > 2 else None
                        await self.send_request_from_json(json_file, endpoint)
                    else:
                        print("❌ 파일명을 입력해주세요. 예: send request.json")
                        
                elif command.lower() == 'help':
                    print("\n📖 도움말:")
                    print("• list: 현재 디렉토리의 JSON 파일 목록 표시")
                    print("• send <파일명>: JSON 파일을 읽어서 기본 경매장 API로 요청")
                    print("• send <파일명> <엔드포인트>: 특정 엔드포인트로 요청")
                    print("\n예시:")
                    print("  send post_auctions_items_request.json")
                    print("  send my_request.json /auctions/options")
                    print("\n지원 엔드포인트:")
                    print("  /auctions/items (기본)")
                    print("  /auctions/options")
                    print("  /markets/items/{itemId}")
                    print("  /markets/options")
                    
                else:
                    print("❌ 알 수 없는 명령어입니다. 'help'를 입력해 도움말을 확인하세요.")
                    
            except KeyboardInterrupt:
                print("\n\n👋 종료합니다.")
                break
            except Exception as e:
                print(f"❌ 에러 발생: {e}")

async def main():
    inspector = APIInspector()
    await inspector.interactive_mode()

if __name__ == "__main__":
    asyncio.run(main())