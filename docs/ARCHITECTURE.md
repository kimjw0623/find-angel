# Find Angel 시스템 아키텍처

## 전체 시스템 구조

```
┌─────────────────────┐    ┌─────────────────────┐
│   Price Collector   │    │   Item Checker      │
│  (30분 주기 수집)    │    │  (실시간 모니터링)   │
└─────────────────────┘    └─────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────┐
│  Pattern Analyzer   │    │  Item Evaluator     │
│   (패턴 생성)        │    │   (가치 평가)       │
└─────────────────────┘    └─────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────┐
│   Pattern DB        │    │ Discord Manager     │
│  (패턴 저장)        │    │   (알림 발송)       │
└─────────────────────┘    └─────────────────────┘
```

## 프로세스 상세

### 1. Price Collector Process
**목적**: 시장 가격 데이터 수집 및 패턴 생성

**주기**: 30분마다

**작업 흐름**:
1. 로스트아크 공식 API에서 경매장 데이터 수집
2. 수집된 데이터를 Raw DB에 저장
3. 패턴 분석기 호출하여 가격 패턴 생성
4. 생성된 패턴을 Pattern DB에 저장

**특징**:
- CPU 집약적 작업 (패턴 분석)
- 대량 데이터 처리
- 수행 시간: 5-15분

### 2. Item Checker Process  
**목적**: 실시간 매물 모니터링 및 알림

**주기**: 1-5분마다

**작업 흐름**:
1. 최신 경매장 매물 수집
2. Pattern DB에서 가격 패턴 로드
3. 각 아이템의 실제 가치 평가
4. 수익성 높은 매물 발견 시 Discord 알림

**특징**:
- I/O 집약적 작업 (API 호출, 알림)
- 실시간성 중요
- 수행 시간: 30초-2분

## 아키텍처 옵션

### Option A: 현재 방식 (동기 처리)
```python
async def price_collector():
    # 데이터 수집
    data = await collect_market_data()
    
    # 패턴 생성 (블로킹)
    analyzer.update_pattern(data)  # 5-15분 소요
    
    print("수집 완료")

async def item_checker():
    # 매물 체크
    items = await get_latest_items()
    
    # 평가 및 알림 (블로킹)
    for item in items:
        if is_profitable(item):
            discord_manager.send_alert(item)
```

**장점**:
- 구현 단순
- 디버깅 용이
- 상태 공유 쉬움

**단점**:
- 패턴 생성 중 collector 블로킹
- 확장성 제한

### Option B: 비동기 큐 방식 (추천)
```python
pattern_queue = asyncio.Queue()
notification_queue = asyncio.Queue()

async def price_collector():
    # 데이터 수집
    data = await collect_market_data()
    
    # 패턴 생성 작업을 큐에 추가 (비블로킹)
    await pattern_queue.put(data)
    
    print("수집 완료 - 패턴 생성은 백그라운드에서 진행")

async def pattern_worker():
    """패턴 생성 전용 워커"""
    while True:
        data = await pattern_queue.get()
        # 패턴 생성 (다른 작업 차단 안 함)
        await asyncio.to_thread(analyzer.update_pattern, data)
        pattern_queue.task_done()

async def item_checker():
    items = await get_latest_items()
    
    for item in items:
        if is_profitable(item):
            # 알림 작업을 큐에 추가
            await notification_queue.put(item)

async def notification_worker():
    """알림 전용 워커"""
    while True:
        item = await notification_queue.get()
        await discord_manager.send_alert_async(item)
        notification_queue.task_done()

async def main():
    # 모든 작업을 동시에 실행
    await asyncio.gather(
        price_collector_scheduler(),
        item_checker_scheduler(), 
        pattern_worker(),
        notification_worker()
    )
```

**장점**:
- 비블로킹 처리
- 확장 용이
- 작업 큐 모니터링 가능
- 리소스 사용 최적화

**단점**:
- 약간의 복잡성 증가

### Option C: Multiprocessing 방식
```python
from multiprocessing import Process, Queue

def pattern_worker_process(queue):
    """별도 프로세스에서 패턴 생성"""
    while True:
        data = queue.get()
        analyzer.update_pattern(data)

def main():
    pattern_queue = Queue()
    
    # 패턴 생성 전용 프로세스
    pattern_process = Process(target=pattern_worker_process, args=(pattern_queue,))
    pattern_process.start()
    
    # 메인 프로세스에서 수집 작업
    asyncio.run(price_collector(pattern_queue))
```

**장점**:
- 진정한 병렬 처리
- 메모리 격리
- 프로세스 크래시 격리

**단점**:
- 구현 복잡성
- 프로세스 간 통신 오버헤드
- 메모리 사용량 증가
- 디버깅 어려움

## 권장사항

### 현재 단계: Option B (비동기 큐)
1. **구현 복잡도**: 적당함
2. **성능 향상**: 확실함  
3. **유지보수**: 양호함
4. **확장성**: 우수함

### 미래 확장시: Option C (Multiprocessing)
- 사용자 수 대폭 증가
- 패턴 생성 시간이 30분 이상
- 메모리 사용량 문제 발생

## 모니터링 포인트

1. **큐 크기**: 작업 적체 감지
2. **처리 시간**: 성능 병목 지점 파악  
3. **메모리 사용량**: 리소스 모니터링
4. **에러율**: 안정성 체크

## 구현 단계

1. **Phase 1**: 현재 구조 유지하며 안정화
2. **Phase 2**: 비동기 큐 도입
3. **Phase 3**: 필요시 multiprocessing 검토