from datetime import datetime, timedelta
from collections import deque
import time
import requests
from typing import List, Dict

class TokenManager:
    def __init__(self, tokens: List[str], requests_per_minute: int = 100):
        self.tokens = tokens
        self.current_index = 0
        self.requests_per_minute = requests_per_minute
        # 각 토큰별로 요청 시간을 저장하는 큐
        self.token_usage = {token: deque() for token in tokens}

    def do_search(self, url: str, post_body: dict, timeout: int = 10, max_retries: int = 6, delay: int = 10) -> requests.Response:
        """여러 토큰을 사용하여 API 검색 수행"""
        current_token = self._get_available_token()

        headers = {
            'accept': 'application/json',
            'authorization': f"bearer {current_token}",
            'content-Type': 'application/json'
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=post_body, timeout=timeout)
                response.raise_for_status()
                
                # 성공한 요청 시간 기록
                self.token_usage[current_token].append(datetime.now())
                return response

            except (requests.exceptions.ConnectionError, 
                   requests.exceptions.HTTPError, 
                   requests.exceptions.ReadTimeout) as e:
                if attempt + 1 == max_retries:
                    raise
                time.sleep(delay)

    def _get_available_token(self) -> str:
        """사용 가능한 토큰 반환"""
        current_time = datetime.now()
        one_minute_ago = current_time - timedelta(minutes=1)
        
        # 모든 토큰을 순회하면서 사용 가능한 토큰 찾기
        for _ in range(len(self.tokens)):
            token = self.tokens[self.current_index]
            request_times = self.token_usage[token]
            
            # 1분이 지난 요청들 제거
            while request_times and request_times[0] < one_minute_ago:
                request_times.popleft()

            # 최근 1분간 요청 수가 한도 미만이면 사용
            if len(request_times) < self.requests_per_minute:
                return token

            # 다음 토큰으로 이동
            self.current_index = (self.current_index + 1) % len(self.tokens)

        # 모든 토큰이 한도에 도달했으면 가장 빨리 사용 가능해지는 토큰 찾기
        earliest_available = None
        min_wait_time = float('inf')
        
        for token in self.tokens:
            if self.token_usage[token]:
                wait_time = (self.token_usage[token][0] + timedelta(minutes=1) - current_time).total_seconds()
                if wait_time < min_wait_time:
                    min_wait_time = wait_time
                    earliest_available = token

        # 대기 후 토큰 반환
        if earliest_available and min_wait_time > 0:
            time.sleep(min_wait_time)
            return earliest_available

        # 안전장치: 1초 대기 후 재시도
        time.sleep(1)
        return self._get_available_token()