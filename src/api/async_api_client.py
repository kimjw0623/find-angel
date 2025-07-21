from typing import List, Dict, Any, Tuple
import aiohttp
import asyncio
import time
from datetime import datetime

class TokenBatchRequester:
    def __init__(self, tokens: List[str]):
        self.tokens = tokens
        self.MAX_REQUESTS_PER_MINUTE = 100
        self.session = None
        self.token_info = {
            token: {
                'index': index,
                'remaining': self.MAX_REQUESTS_PER_MINUTE,
                'reset_time': None,
                'last_use': 0
            } for index, token in enumerate(tokens)
        }

    def _token_info_str(self): 
        return {
            f"token {index}": self.token_info[token] for index, token in enumerate(self.token_info.keys())            
        }

    async def initialize(self):
        if self.session is None:
            # TCP 커넥션 풀 설정
            conn = aiohttp.TCPConnector(
                limit=100,  # 동시 연결 수 제한
                limit_per_host=50,  # 호스트당 최대 연결 수
                enable_cleanup_closed=True,  # 닫힌 연결 정리
                force_close=False,  # 연결 재사용 허용
                ttl_dns_cache=300,  # DNS 캐시 시간 (초)
            )
            
            # 타임아웃 설정
            timeout = aiohttp.ClientTimeout(
                total=30,  # 전체 작업 타임아웃
                connect=10,  # 연결 타임아웃
                sock_connect=10,  # 소켓 연결 타임아웃
                sock_read=30  # 소켓 읽기 타임아웃
            )
            
            self.session = aiohttp.ClientSession(
                connector=conn,
                timeout=timeout
            )

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    def _update_token_info(self, token: str, success_headers_list: List[Dict[str, str]], rate_limited_headers_list: List[Dict[str, str]]):
        """여러 응답 헤더에서 가장 보수적인 rate limit 정보로 업데이트. 그런데 이렇게 잡아도 rate_limited가 발견되는 경우가 있는데, 왜인지 모르겠음"""
        try:
            # 현재 시간 기록
            current_time = time.time()
            self.token_info[token]['last_use'] = current_time

            if rate_limited_headers_list:
                # rate_limited가 발견되었으면 x-ratelimit-remaining이 남아 있어도 그냥 Retry-After 시간 이후에 다시 시작
                self.token_info[token]['remaining'] = 0

                retry_afters = [
                    int(headers.get('Retry-After', 60))
                    for headers in rate_limited_headers_list
                ]

                self.token_info[token]['reset_time'] = current_time + (max(retry_afters) if retry_afters else 60) + 1 # 안전하게 1초 추가

            else:
                # 모든 응답의 remaining 값 중 최소값 사용
                remaining_values = [
                    int(headers.get('x-ratelimit-remaining', 0))
                    for headers in success_headers_list
                ]
                self.token_info[token]['remaining'] = min(remaining_values) if remaining_values else 0
                
                # 모든 응답의 reset 시간 중 최대값 사용
                reset_values = [
                    int(headers.get('x-ratelimit-reset', 0))
                    for headers in success_headers_list
                    if headers.get('x-ratelimit-reset')
                ]
                if reset_values:
                    self.token_info[token]['reset_time'] = max(reset_values)

        except (ValueError, TypeError) as e:
            print(f"Error parsing rate limit headers: {e}")
            # 헤더 파싱 실패시 보수적으로 remaining을 0으로 설정
            self.token_info[token]['remaining'] = 0

    def _get_available_tokens(self) -> List[Tuple[str, int]]:
        """사용 가능한 토큰들을 더 지능적으로 선택"""
        current_time = time.time()
        available_tokens = []
        soon_available = []  # 곧 사용 가능해질 토큰들
        next_reset_times = []  # 모든 토큰의 리셋 시간 추적
        
        for token in self.tokens:
            info = self.token_info[token]
            remaining = info['remaining']
            reset_time = info['reset_time']
            
            if reset_time:
                next_reset_times.append(reset_time)
            
            # 리셋 시간이 지났으면 remaining을 MAX로 설정
            if reset_time and current_time >= reset_time:
                remaining = self.MAX_REQUESTS_PER_MINUTE
                self.token_info[token].update({
                    'remaining': remaining,
                    'reset_time': None
                })
                
            # 리셋 시간이 얼마 안 남은 경우 특별 처리
            if reset_time and reset_time - current_time < 5:  # 5초 이내 리셋
                # 리셋 시간이 매우 가까우면서 거의 소진된 경우
                if remaining < 10:
                    soon_available.append((token, self.MAX_REQUESTS_PER_MINUTE, reset_time))
                    continue
                
            if remaining > 0:
                available_tokens.append((token, remaining))
        
        # 현재 사용 가능한 토큰이 있는 경우
        if available_tokens:
            # remaining이 많은 순서로, 같으면 마지막 사용 시간이 오래된 순서로 정렬
            return sorted(available_tokens, key=lambda x: (-x[1], self.token_info[x[0]]['last_use']))
        
        # 곧 리셋될 토큰이 있는 경우
        if soon_available:
            soon_available.sort(key=lambda x: x[2])  # 가장 빨리 리셋될 토큰 순
            next_reset = soon_available[0][2]
            wait_time = max(0, next_reset - current_time)
            if wait_time < 5:  # 5초 이내로 기다려도 되는 경우
                time.sleep(wait_time + 0.1)  # 여유 있게 0.1초 추가
                return [(soon_available[0][0], soon_available[0][1])]
        
        # 모든 토큰이 소진된 경우, 가장 빠른 리셋 시간까지 대기
        if next_reset_times:
            next_reset = min(next_reset_times)
            wait_time = max(0, next_reset - current_time)
            print(f"All tokens exhausted. Waiting {wait_time:.1f} seconds for next reset")
            # print(f"Current token status: {self._token_info_str()}")
            time.sleep(wait_time + 0.1)
            return self._get_available_tokens()
            
        # 모든 토큰의 리셋 시간 정보가 없는 경우
        print("No token reset information available. Waiting 60 seconds as fallback")
        time.sleep(60)
        return self._get_available_tokens()

    async def process_requests(self, requests: List[Dict]) -> List[Dict]:
        """요청들을 토큰별 여유 용량에 따라 분배하여 처리"""
        await self.initialize()
        results = [None] * len(requests)
        pending_indices = list(range(len(requests)))

        while pending_indices:
            # print(f"\nBefore using tokens...{self._token_info_str()}")
            available_tokens = self._get_available_tokens()
            if not available_tokens:
                continue

            processing_tasks = []
            remaining_indices = []

            for token, remaining in available_tokens:
                if not pending_indices:
                    break
                    
                batch_indices = pending_indices[:remaining]
                pending_indices = pending_indices[remaining:]
                
                batch_requests = [requests[i] for i in batch_indices]
                task = self._process_batch_with_indices(
                    batch_requests, batch_indices, token, results)
                processing_tasks.append(task)
                # print(f"token {self.token_info[token]['index']}번이 {len(batch_requests)}개 사용")

            if processing_tasks:
                batch_results = await asyncio.gather(
                    *processing_tasks, return_exceptions=True)
                
                for batch_result in batch_results:
                    if isinstance(batch_result, Exception):
                        print(f"Batch processing error: {batch_result}")
                        continue
                    if batch_result and batch_result.get('retry_indices'):
                        remaining_indices.extend(batch_result['retry_indices'])
            
            if remaining_indices:
                pending_indices.extend(remaining_indices)

            # if pending_indices:
            #     print(f"Pending_indices: {pending_indices}")

            # print(f"After using tokens: {self._token_info_str()}\n")
        return results

    async def _process_batch_with_indices(self, batch_requests: List[Dict], 
                                        batch_indices: List[int], 
                                        token: str, 
                                        results: List[Dict]) -> Dict:
        """배치 처리 및 결과 저장"""
        try:
            batch_results = await self._process_single_batch(batch_requests, token)
            retry_indices = []
            
            for idx, (index, result) in enumerate(zip(batch_indices, batch_results)):
                try:
                    # 성공적인 응답만 results에 저장, 나머지는 모두 재시도
                    if isinstance(result, dict) and result.get('status') == 200:
                        results[index] = result.get('data')
                    else:
                        # 에러 상황별 로깅
                        if isinstance(result, dict):
                            if result.get('rate_limited'):
                                pass
                                # print(f"Rate limit hit at index {index}")
                            elif result.get('status'):
                                print(f"HTTP {result['status']} error at index {index}")
                            else:
                                print(f"Unknown error format at index {index}: {result}")
                        else:
                            print(f"Invalid response at index {index}: {result}")
                        
                        retry_indices.append(index)
                        
                except Exception as e:
                    print(f"Error processing result at index {index}: {str(e)}")
                    retry_indices.append(index)

            return {'retry_indices': retry_indices} if retry_indices else None

        except Exception as e:
            print(f"Batch processing error with token {token}: {str(e)}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            return {'retry_indices': batch_indices}

    async def _process_single_batch(self, batch: List[Dict], token: str) -> List[Dict]:
        """단일 토큰으로 배치 처리"""
        headers = {
            'accept': 'application/json',
            'authorization': f"bearer {token}",
            'content-Type': 'application/json'
        }

        tasks = []
        for request_data in batch:
            task = self._make_single_request(headers, request_data)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 성공한 요청들의 헤더 수집
        success_headers = [
            result['headers'] for result in results 
            if isinstance(result, dict) and result.get('status') == 200
        ]
        
        rate_limited_headers = [
            result['headers'] for result in results 
            if isinstance(result, dict) and result.get('status') == 429
        ]

        # 수집된 헤더로 토큰 정보 업데이트
        if success_headers or rate_limited_headers:
            self._update_token_info(token, success_headers, rate_limited_headers)

        return results

    async def _make_single_request(self, headers: Dict, request_data: Dict) -> Dict:
        """단일 요청 처리"""
        try:
            search_timestamp = datetime.now()
            # timeout을 더 길게 설정
            async with self.session.post( # type: ignore
                "https://developer-lostark.game.onstove.com/auctions/items",
                headers=headers,
                json=request_data,
                timeout=30  # 30초로 증가
            ) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        data['search_timestamp'] = search_timestamp
                        return {
                            'status': 200,
                            'data': data,
                            'headers': dict(response.headers)
                        }
                    except BaseException as e:
                        print(f"Error parsing response: {str(e)}")
                        return {
                            'status': 'error',
                            'error': f"JSON parse error: {str(e)}",
                            'error_type': type(e).__name__
                        }
                elif response.status == 429:
                    return {
                        'status': 429,
                        'rate_limited': True,
                        'headers': dict(response.headers)
                    }
                else:
                    print(f"Request failed with status {response.status}")
                    return {
                        'status': response.status,
                        'headers': dict(response.headers)
                    }

        except asyncio.CancelledError:
            # 취소된 경우 다시 raise하여 상위에서 처리
            raise

        except BaseException as e:
            print(f"Request error: {str(e)} ({type(e).__name__})")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }