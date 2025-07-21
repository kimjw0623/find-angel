# find-angel 프로젝트 가이드

## 프로젝트 개요

이 프로젝트는 **로스트아크 경매장 시장 분석 및 모니터링 시스템**입니다. 경매장의 고급 악세서리(목걸이, 귀걸이, 반지)와 팔찌의 가격을 자동으로 수집하고 분석하여, 수익성이 높은 매물을 찾아 디스코드로 알림을 보내는 시스템입니다.

## 주요 기능

### 1. 데이터 수집 및 분석
- **가격 수집**: 30분마다 경매장 데이터 수집 (`async_price_collector.py`)
- **실시간 모니터링**: 새로 올라온 매물 실시간 스캔 (`async_item_checker.py`)
- **가격 평가**: 캐시된 가격 데이터 기반 아이템 평가 (`item_evaluator.py`)
- **디스코드 알림**: 수익성 높은 매물 자동 알림 (`discord_manager.py`)

### 2. 웹 인터페이스
- **백엔드 API**: FastAPI 기반 REST API (`backend.py`)
- **프론트엔드**: React 기반 시각화 대시보드 (`frontend/`)
  - 악세서리 가격 추이 차트
  - 팔찌 가격 분석
  - 연마 시뮬레이터

### 3. 데이터베이스 구조
- **메인 DB**: 원시 가격 기록 저장 (`database.py`)
- **캐시 DB**: 가공된 가격 패턴 저장 (`cache_database.py`)

## 기술 스택

### Backend
- **Python 3.x**: 메인 언어
- **FastAPI**: 웹 API 프레임워크
- **aiohttp**: 비동기 HTTP 클라이언트
- **SQLite**: 데이터베이스 (WAL 모드)
- **asyncio**: 비동기 프로그래밍

### Frontend
- **React 18**: UI 라이브러리
- **Tailwind CSS**: 스타일링
- **Chakra UI**: 컴포넌트 라이브러리
- **Recharts**: 차트 라이브러리
- **axios**: HTTP 클라이언트

## 실행 방법

### 환경 설정
1. `.env` 파일 생성 및 API 토큰 설정:
   ```
   PRICE_TOKEN_1=your_token_here
   PRICE_TOKEN_2=your_token_here
   MONITOR_TOKEN_1=your_token_here
   MONITOR_TOKEN_2=your_token_here
   ```

### 백엔드 실행
```bash
# 가격 수집기 실행
./scripts/run_price_collector.sh
# 또는: python -m src.core.async_price_collector

# 실시간 모니터링 실행  
./scripts/run_item_checker.sh
# 또는: python -m src.core.async_item_checker

# 웹 API 서버 실행
./scripts/run_backend.sh  
# 또는: python -m src.api.backend

# API 테스트 도구 실행
./scripts/run_api_inspector.sh
# 또는: python tools/api_inspector.py
```

### 프론트엔드 실행
```bash
cd frontend
npm install
npm start
```

## 주요 커밋 히스토리 분석

### 최근 개발 동향
- **비동기 처리 도입**: `asyncio`, `aiohttp` 사용으로 성능 향상
- **프론트엔드 개발**: React 기반 시각화 대시보드 구현
- **데이터베이스 최적화**: 캐시 DB 분리, 검색 성능 개선
- **디스코드 통합**: 매물 추적 및 알림 시스템 구현

### 주요 개선사항
- JS에서 JSX로 변경으로 코드 가독성 향상
- 디스코드 에러 처리 개선
- 가격 비율 조정 알고리즘 개선 (0.5~0.75 범위)
- 팔찌 시각화 기능 추가

## 개발 패턴 및 컨벤션

### 코드 구조
- **모듈화**: 기능별 파일 분리
- **비동기 처리**: `async/await` 패턴 사용
- **에러 처리**: 안정적인 예외 처리
- **로깅**: 상세한 로그 기록

### 데이터 처리
- **캐싱**: 성능 최적화를 위한 다단계 캐싱
- **배치 처리**: API 호출 효율성 향상
- **동시성**: 안전한 멀티스레딩

### 프론트엔드 구조
- **컴포넌트 분리**: 재사용 가능한 컴포넌트 구조
- **페이지 기반 라우팅**: 기능별 대시보드 분리
- **반응형 디자인**: Tailwind CSS 활용

## 개발 시 주의사항

### API 사용
- 로스트아크 공식 API 사용량 제한 준수
- 토큰 로테이션으로 효율적인 API 호출
- 에러 발생 시 적절한 백오프 전략 적용

### 데이터베이스
- SQLite WAL 모드 사용으로 동시성 보장
- 인덱스 최적화로 쿼리 성능 향상
- 정기적인 데이터 정리 필요

### 디스코드 통합
- 웹훅 URL 보안 관리
- 메시지 포맷 일관성 유지
- 스팸 방지를 위한 알림 주기 조절

### 설정 관리
- **config.py**: 모든 설정값은 config 객체를 통해 접근
- **하드코딩 금지**: 직접 숫자나 문자열 하드코딩 대신 설정값 사용
- **환경 변수**: 민감한 정보는 `.env` 파일로 관리
- **설정 분류**: 기능별로 논리적으로 그룹화된 설정 구조 유지

## 실행 명령어

### 개발 환경
```bash
# 백엔드 개발 서버 실행
./scripts/run_backend.sh

# 프론트엔드 개발 서버 실행
cd frontend && npm start

# API 테스트 도구 실행
./scripts/run_api_inspector.sh

# 개별 컴포넌트 테스트
python tools/item_test.py
python tools/manual_cache_update.py
```

### 배포 환경
```bash
# 프론트엔드 빌드
cd frontend && npm run build

# 백엔드 프로덕션 실행
python -m src.api.backend --host 0.0.0.0 --port 8000
```

## 최근 리팩토링 작업 (2025-07-12)

### 프로젝트 구조 대정리 
- **디렉토리 구조 재설계**: 기능별 모듈을 논리적 구조로 재배치
- **파일 분산 문제 해결**: 루트에 흩어진 파일들을 체계적으로 정리  
- **Import 경로 전면 업데이트**: 모든 모듈의 import 구문을 새 구조에 맞게 수정

### 코드 정리 및 구조 개선
- **old 폴더 정리**: 더 이상 사용하지 않는 동기 버전 코드들 제거
- **토큰 관리 통합**: `utils.py`의 사용하지 않는 `TokenManager` 클래스 제거
- **import 경로 수정**: `item_test.py`에서 `item_checker` → `item_evaluator`로 변경

### 데이터베이스 아키텍처 리팩토링
- **BaseDatabaseManager 도입**: 공통 데이터베이스 로직 추상화
- **중복 코드 제거**: ~115줄의 중복된 세션 관리 코드 제거
- **확장성 개선**: 새로운 데이터베이스 추가 시 간편한 확장 구조

### 설정 관리 시스템 구축
- **통합 Config 클래스**: 모든 설정값을 중앙 관리
- **환경 변수 자동 로드**: 토큰, 웹훅 URL 등 자동 매핑
- **하드코딩 제거**: 마법 숫자들을 의미 있는 설정값으로 대체
- **타입 안정성**: 설정값 접근 패턴 일관성 확보

### 개발 도구 개선
- **API 인스펙터 개발**: JSON 기반으로 API 요청/응답 테스트 가능
- **대화형 인터페이스**: 직관적인 명령어 시스템
- **실행 스크립트 추가**: 각 컴포넌트별 독립 실행 스크립트 제공

### 새로 추가된 파일
- `src/database/base_database.py`: 데이터베이스 매니저의 공통 기능 제공
- `tools/api_inspector.py`: JSON 파일 기반 API 테스트 도구
- `scripts/*.sh`: 컴포넌트별 실행 스크립트들

### 개선된 파일들
- `src/database/raw_database.py`: RawDatabaseManager 간소화 (60줄 → 6줄)
- `src/database/pattern_database.py`: PatternDatabaseManager 간소화 (55줄 → 6줄)
- `src/common/utils.py`: 불필요한 import 및 클래스 제거
- `src/common/config.py`: 통합 설정 관리 시스템 구축

## 프로젝트 구조 (2025-07-04 정리)

```
find-angel/
├── src/                        # 메인 소스 코드
│   ├── core/                   # 핵심 기능
│   │   ├── async_price_collector.py    # 가격 수집기
│   │   ├── async_item_checker.py       # 실시간 매물 모니터
│   │   ├── item_evaluator.py           # 아이템 평가 엔진
│   │   └── market_price_cache.py       # 시장 가격 캐시 관리
│   │
│   ├── api/                    # API 관련
│   │   ├── async_api_client.py         # 비동기 API 클라이언트
│   │   └── backend.py                  # FastAPI 백엔드
│   │
│   ├── database/               # 데이터베이스
│   │   ├── base_database.py            # 데이터베이스 기본 클래스
│   │   ├── database.py                 # 메인 DB (원시 데이터)
│   │   └── cache_database.py           # 캐시 DB (가공 데이터)
│   │
│   ├── notifications/          # 알림 시스템
│   │   └── discord_manager.py          # Discord 웹훅 관리
│   │
│   └── common/                 # 공통 유틸리티
│       ├── config.py                   # 통합 설정 관리
│       └── utils.py                    # 유틸리티 함수
│
├── tools/                      # 도구 및 유틸리티
│   ├── api_inspector.py                # API 테스트 도구
│   ├── item_test.py                    # 아이템 평가 테스트
│   ├── manual_cache_update.py          # 수동 캐시 업데이트
│   ├── enhancement_simulator.py        # 연마 시뮬레이터
│   ├── enhancement_sim_with_auction.py # 경매 연동 시뮬레이터
│   └── abidos_search.py                # 아비도스 검색
│
├── frontend/                   # React 프론트엔드
│   ├── src/
│   │   ├── components/                 # UI 컴포넌트
│   │   ├── pages/                      # 페이지 컴포넌트
│   │   └── services/                   # API 서비스
│   └── ...
│
├── data/                       # 데이터 파일
│   ├── test_accessory_search.json
│   ├── post_auctions_items_request.json
│   └── get_auctions_options_response.json
│
├── docs/                       # 문서
│   ├── README.md
│   └── CLAUDE.md (이 파일)
│
├── scripts/                    # 실행 스크립트
├── tests/                      # 테스트 코드
├── .env                        # 환경 변수
├── .gitignore
└── requirements.txt

## 시스템 아키텍처 (2025-07-18 정리)

### 핵심 프로세스 구조
프로젝트는 **두 개의 독립적인 주요 프로세스**로 구성됩니다:

#### 1. Price Collector (가격 수집 + 패턴 생성)
- **역할**: 30분마다 전체 경매장 데이터 수집 및 가격 패턴 생성
- **프로세스**: `async_price_collector.py`
- **후속 작업**: `price_pattern_analyzer.update_pattern()` 호출
- **특징**: CPU 집약적, 장시간 소요 (5-15분)

#### 2. Item Checker (실시간 모니터링 + 알림)  
- **역할**: 1-5분마다 최신 매물 모니터링 및 수익성 판단
- **프로세스**: `async_item_checker.py`
- **후속 작업**: `discord_manager` 알림 발송
- **특징**: I/O 집약적, 실시간성 중요

### 아키텍처 개선 방향
현재는 **동기 처리 방식** (단순하지만 블로킹 발생)

**권장 개선안**: **비동기 큐 방식**
```python
# 패턴 생성과 알림을 별도 워커로 분리
pattern_queue = asyncio.Queue()
notification_queue = asyncio.Queue()

# 메인 프로세스는 블로킹되지 않음
# 백그라운드 워커가 큐 작업 처리
```

**장점**:
- 패턴 생성 중에도 매물 모니터링 지속
- 작업 큐 모니터링으로 성능 최적화
- 확장성 및 안정성 향상

### 상세 설계 문서
전체 아키텍처 상세 정보는 `docs/ARCHITECTURE.md` 참조

## 향후 개발 계획

### 단기 목표
- 비동기 큐 아키텍처 도입
- 딜증 계산 기능 추가
- 수동 검색 기능 구현
- 대형 메서드 분해 (collect_prices, update_cache 등)

### 중기 목표
- 데이터베이스 용량 최적화
- 시각화 기능 확장
- 모바일 반응형 개선
- 타입 힌트 추가

### 장기 목표
- 머신러닝 기반 가격 예측
- 실시간 알림 시스템 고도화
- 사용자 맞춤형 필터링 기능