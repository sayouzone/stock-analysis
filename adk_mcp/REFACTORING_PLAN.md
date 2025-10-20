# 플랜: Tag-based LLM 자동 판단 방식으로 리팩토링

## 목표
- `companydict` 하드코딩 의존성 제거
- Backend를 `/{ticker}` 구조로 단순화 (캐시 우선 → Agent 호출)
- Frontend는 Agent에게 티커 기반 자동 판단 위임
- MCP Tools에 명확한 description + tags 추가하여 LLM이 티커 형식으로 자동 선택

---

## 1. MCP Server Tools 강화 (`mcp_server/fundamentals.py`)

**작업 내용**:
- `find_fnguide_data` tool에 명확한 description 추가
  - 사용 대상: 6자리 숫자, .KS/.KQ 접미사, 한국 기업명
  - tags: `["korea", "fnguide", "fundamentals"]`

- `get_yahoofinance_fundamentals` tool에 명확한 description 추가
  - 사용 대상: 알파벳 1-5자 티커, 해외 기업명
  - tags: `["global", "yahoo", "fundamentals"]`

**변경 사항**:
```python
@mcp.tool(
    name="find_fnguide_data",
    description="""FnGuide에서 한국 주식 재무제표 수집.

사용 대상:
- 6자리 숫자 티커: 005930, 000660
- .KS/.KQ 접미사: 005930.KS, 035720.KQ
- 한국 기업명: 삼성전자, SK하이닉스

반환: 재무상태표, 포괄손익계산서, 현금흐름표 (연간 데이터)
""",
    tags=["korea", "fnguide", "fundamentals"]
)

@mcp.tool(
    name="get_yahoofinance_fundamentals",
    description="""Yahoo Finance에서 해외 주식 재무제표 수집.

사용 대상:
- 알파벳 티커 (1-5자): AAPL, TSLA, GOOGL
- 해외 기업명: Apple, Tesla, Microsoft

반환: balance_sheet, income_statement, cash_flow (연간 데이터)
""",
    tags=["global", "yahoo", "fundamentals"]
)
```

---

## 2. Agent Prompt 업데이트 (`stock_agent/fundamentals_agent/agent.py`)

**작업 내용**:
- `FUNDAMENTALS_FETCHER_GUIDANCE` 프롬프트 수정
- 티커 형식 기반 Tool 선택 가이드라인 명시
- 한국 주식 vs 해외 주식 구분 기준 명확화

**변경 사항**:
```python
FUNDAMENTALS_FETCHER_GUIDANCE = """
# 재무제표 데이터 수집 가이드

## 티커 형식 기반 Tool 선택

**한국 주식** → `find_fnguide_data`:
- 6자리 숫자: 005930, 000660, 035720
- .KS/.KQ 접미사: 005930.KS, 035720.KQ
- 한국 기업명: 삼성전자, SK하이닉스

**해외 주식** → `get_yahoofinance_fundamentals`:
- 알파벳 티커: AAPL, TSLA, GOOGL
- 해외 기업명: Apple, Tesla, Microsoft

## 사용 예시

# 한국 주식
find_fnguide_data(stock="005930")
find_fnguide_data(stock="삼성전자")

# 해외 주식
get_yahoofinance_fundamentals(query="AAPL")
get_yahoofinance_fundamentals(query="Apple")

## 데이터 키 매핑

FnGuide:
- "재무상태표" → balance_sheet
- "포괄손익계산서" → income_statement
- "현금흐름표" → cash_flow

Yahoo Finance:
- 이미 올바른 키 이름 사용 (변환 불필요)
"""
```

---

## 3. Backend API 리팩토링 (`routers/fundamentals.py`)

**작업 내용**:

### 3-1. 삭제할 코드
- `_detect_stock_info()` 함수 (companydict 의존성 제거)
- `/analyze` endpoint (auto-detection 로직 제거)
- `from utils.stock_identifier import find` import 제거
- `asyncio` import 제거 (더 이상 필요 없음)

### 3-2. 새로운 `/{ticker}` endpoint 구현

**로직**:
1. 캐시에서 데이터 조회 (GCS 또는 기존 캐시 시스템 활용)
2. 캐시 있으면 → 즉시 반환
3. 캐시 없으면 → Agent 함수 호출하여 분석 결과 생성 → 캐시 저장 → 반환

**코드 구조**:
```python
@router.get("/{ticker}", summary="티커 기반 재무제표 조회")
async def get_fundamentals(ticker: str, nocache: bool = False):
    """
    1. 캐시 조회 우선
    2. 캐시 없으면 Agent 호출하여 데이터 수집
    3. Agent가 MCP tool 자동 선택 (티커 형식 기반)
    """

    # 1. 캐시 조회
    if not nocache:
        cached_data = await _check_cache(ticker)
        if cached_data:
            return cached_data

    # 2. Agent 호출
    from stock_agent.fundamentals_agent.agent import analyze_fundamentals
    agent_result = await analyze_fundamentals(ticker)

    # 3. 캐시 저장 및 반환
    await _save_to_cache(ticker, agent_result)
    return agent_result
```

**필요한 헬퍼 함수**:
- `_check_cache(ticker: str)`: GCS 또는 기존 캐시 시스템에서 데이터 조회
- `_save_to_cache(ticker: str, data: dict)`: 캐시에 데이터 저장

---

## 4. Frontend 수정 (`frontend/src/routes/fundamentals/+page.svelte`)

**작업 내용**:
- `site` 선택 로직 제거
- `/{ticker}` endpoint 호출로 단순화

**변경 전**:
```svelte
function requestFundamentals() {
    const code = currentTicker.code.trim();
    const site = /^[0-9]{5,6}$/.test(code) ? 'fnguide' : 'yahoofinance';
    fundamentalsState.load(site, code);
}
```

**변경 후**:
```svelte
function requestFundamentals() {
    const ticker = currentTicker.code.trim();
    fundamentalsState.load(ticker); // site 파라미터 제거
}
```

---

## 5. Frontend Store 수정 (`frontend/src/lib/stores/fundamentals.ts`)

**작업 내용**:
- `load()` 함수 시그니처 변경: `load(site, ticker)` → `load(ticker)`
- API 호출 경로 변경: `/fundamentals/{site}/{ticker}` → `/fundamentals/{ticker}`

**변경 전**:
```typescript
async load(site: string, ticker: string) {
    const payload = await fetchJson(`/fundamentals/${site}/${ticker}`);
    ...
}
```

**변경 후**:
```typescript
async load(ticker: string, nocache: boolean = false) {
    const url = nocache
        ? `/fundamentals/${ticker}?nocache=true`
        : `/fundamentals/${ticker}`;
    const payload = await fetchJson(url);
    ...
}
```

---

## 6. Agent 함수 확인 및 수정 (필요시)

**작업 내용**:
- `stock_agent/fundamentals_agent/agent.py`에 router에서 호출 가능한 함수 존재 여부 확인
- 없으면 새로 생성: `async def analyze_fundamentals(ticker: str) -> dict`
- Agent가 MCP tool을 호출하여 데이터 수집하도록 구현

**예상 코드**:
```python
async def analyze_fundamentals(ticker: str) -> dict:
    """
    Router에서 호출하는 Agent 진입점.
    MCP tools를 사용하여 티커 기반 재무제표 데이터 수집.
    """
    # Agent 실행 (MCP tool 자동 선택)
    result = await agent.run(f"티커 {ticker}의 재무제표를 수집해주세요")
    return result
```

---

## 구현 순서

1. **MCP Server Tools 강화** (`mcp_server/fundamentals.py`)
   - Description + tags 추가

2. **Agent Prompt 업데이트** (`stock_agent/fundamentals_agent/agent.py`)
   - 티커 형식 기반 선택 가이드 추가

3. **Agent 함수 확인/생성** (`stock_agent/fundamentals_agent/agent.py`)
   - Router에서 호출 가능한 `analyze_fundamentals()` 함수

4. **Backend API 리팩토링** (`routers/fundamentals.py`)
   - `/analyze` 제거
   - `_detect_stock_info()` 제거
   - `/{ticker}` endpoint 구현 (캐시 우선 → Agent 호출)

5. **Frontend Store 수정** (`frontend/src/lib/stores/fundamentals.ts`)
   - `load(ticker)` 시그니처 변경

6. **Frontend UI 수정** (`frontend/src/routes/fundamentals/+page.svelte`)
   - Site 선택 로직 제거

---

## 예상 효과

✅ **하드코딩 제거**: `companydict` 의존성 완전 제거
✅ **확장성**: 나중에 `?country=KR` 등 쿼리 파라미터 추가 용이
✅ **단순화**: Backend auto-detection 로직 제거, LLM에게 위임
✅ **DB 전환 대비**: Tool description만 유지하면 되므로 DB 전환 시 영향 최소화
✅ **성능**: 캐시 우선 조회로 불필요한 Agent 호출 최소화

---

## 주의사항

⚠️ **Agent 함수 구조 확인 필요**: 현재 `stock_agent/fundamentals_agent/agent.py`의 실제 구현 구조를 확인해야 정확한 호출 방법 결정 가능
⚠️ **캐시 시스템**: 기존 GCS 캐시 시스템을 그대로 활용할 수 있는지 확인 필요
⚠️ **LLM 판단 테스트**: 티커 형식 기반 자동 선택이 실제로 잘 작동하는지 테스트 필요
