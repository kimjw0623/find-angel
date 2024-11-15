# find-angel


## 1. 시세 추적
 반지 하나에 대해서만 하면 나머지는 빠르게 할 수 있음(목, 귀는 동일)
 어떤 물품의 시세를 볼 거냐?
 반지라고 치면
 노연마는 살 일이 없긴 함
 1연마(치피와 치적에 대해 각각 하/중/상, 품질은 70/80/90)
 2연마(치피와 치적 한 줄에 대해 각각 하/중/상)
 3연마(치피와 치적 한 줄에 대해 각각 하/중/상, 두 개 다 붙은 거 하하/중하/상하/중중)

## 2. 최근 올라온 매물만 빠르게 찾기
1분당 API키당 100개 그럼 적어도 10개의 api key를 10개는 얻을 거 아니야

얘는 그럼 조건을 걸면 안되나

## 3. 고대 1연마, 유물 3연마 깡통값만 한 번씩 업데이트

1과 2를 가지고 angel을 찾고(찾으면 알람) + 직작이 이득인 구간이 있는지 판별

### 수동으로 원하는 거 검색할 수 있게


# Todo
이 작업의 최종 목적 중 하나는 가루를 어디에 소모하는 게 제일 효율적인지 알기 위한 것.

재료들 값도 체크해야함(떡작 추가)

지금 문제가 품질을 가격 책정에 고려하긴 하는데 시세 검색에서 딜 증가량으로 고려를 안 하는게 문제인 것 같다...
그래서 품질 높은 것들이 조금 과하게 찍히는 듯.

evaluate function 업데이트를 lowest_price_log에서 하게 하고 싶은데,
그러면 얘는 쓰기 담당이고 find_honey 쪽에서 읽기를 담당해야 해서
괜히 충돌날까봐 지금 두렵다.
일단 lock 파일을 만드는 걸로 관리를 해보자.

1. 일단 utils.py에 최대한 모으기
2. evaluate function 로딩 로직 개선하기

# Todo(241114)
- DB 써보기
- 우선 lowest_price_log.py를 업데이트하는 걸로 해보고 팔찌나 돌 등도 추가해보자.
- 꿀매물 찾기는 어차피 API limit 증가도 기다려야 하니까...