# 재무제표 스키마 통합 리팩토링

## 개요
FnGuide와 Yahoo Finance의 재무제표 데이터를 **동일한 스키마**로 통합하고, rating 기능을 제거하여 코드를 간소화했습니다.

---

## 🎯 목표

1. **스키마 통일**: FnGuide와 Yahoo Finance 모두 동일한 데이터 구조 반환
2. **코드 간소화**: 복잡한 분석/평가 로직 제거
3. **재무제표 집중**: 3종 재무제표만 수집 (balance_sheet, income_statement, cash_flow)
4. **LLM 친화적**: 표준화된 구조로 에이전트가 쉽게 처리

---

## 📋 통합 스키마

### Before (FnGuide)
```python
{
    "market_conditions": [...],
    "earning_issue": [...],
    "holdings_status": [...],
    "포괄손익계산서": [...],
    "재무상태표": [...],
    "현금흐름표": [...],
    "session_state": {...}
}
```

### Before (Yahoo Finance)
```python
{
    "result": {
        "market_conditions": [...],
        "industry_comparison": [...],
        ...
    },
    "analysis": "텍스트 분석...",
    "rating": {"score": 70, "rate": "good"},
    "session_state": {...}
}
```

### After (통합 스키마) ✅
```python
{
    "ticker": "005930" | "AAPL",
    "country": "KR" | "US",
    "balance_sheet": "{...JSON...}" | None,
    "income_statement": "{...JSON...}" | None,
    "cash_flow": "{...JSON...}" | None
}
```

---

## 🔄 변경 사항

### 1. FnGuide 크롤러 (`backend/utils/crawler/fnguide.py`)

#### 변경 내용
- ✅ 재무제표 3종만 반환 (yfinance 스키마 준수)
- ✅ 한글 키명 → 영문 키명 매핑
  - `포괄손익계산서` → `income_statement`
  - `재무상태표` → `balance_sheet`
  - `현금흐름표` → `cash_flow`
- ✅ 정적 테이블은 GCS에만 저장 (기존 호환성 유지)
- ✅ `country` 필드 항상 `"KR"` 반환

#### 코드 예시
```python
# FnGuide 한글 키명 → 영문 키명 매핑
result = {
    "ticker": self.stock,
    "country": "KR",
    "balance_sheet": None,
    "income_statement": None,
    "cash_flow": None
}

if "포괄손익계산서" in dynamic_data:
    result["income_statement"] = json.dumps(
        dynamic_data["포괄손익계산서"],
        ensure_ascii=False
    )
```

---

### 2. Yahoo Finance 유틸리티 (`backend/utils/yahoofinance.py`)

#### 변경 내용
- ✅ **코드 49% 감소** (273줄 → 139줄)
- ❌ 복잡한 분석 로직 제거 (market_conditions, industry_comparison 등)
- ❌ 자동 평가 시스템 제거 (rating 계산)
- ❌ 포맷팅 함수 제거 (fmt_signed, fmt_percent 등)
- ✅ GCS 캐싱 유지
- ✅ 재무제표 3종만 수집

#### 코드 예시
```python
class Fundamentals:
    def fundamentals(self, query: str, use_cache: bool = True):
        # 국가 정보 추론
        country = info.get("country") or "Unknown"
        if ".KS" in ticker_symbol or ".KQ" in ticker_symbol:
            country = "KR"

        # 재무제표 3종 수집
        result = {
            "ticker": ticker_symbol,
            "country": country,
            "balance_sheet": ticker.balance_sheet.to_json(...),
            "income_statement": ticker.income_stmt.to_json(...),
            "cash_flow": ticker.cashflow.to_json(...)
        }
        return result
```

---

### 3. MCP 도구 (`backend/mcp_server/fundamentals.py`)

#### 변경 내용
- ✅ `find_fnguide_data` - yfinance와 동일한 스키마 반환
- ✅ `get_yahoofinance_fundamentals` - 캐싱 지원 추가
- ✅ 중복 코드 91줄 → 1줄로 축소

#### Before
```python
@mcp.tool(name="get_yahoofinance_fundamentals")
def get_yahoofinance_fundamentals(query: str):
    # 91줄의 중복 코드...
    ticker = yf.Ticker(ticker_symbol)
    result = {...}
    # 재무제표 수집...
    return result
```

#### After
```python
@mcp.tool(name="get_yahoofinance_fundamentals")
def get_yahoofinance_fundamentals(query: str, use_cache: bool = True):
    return YahooFundamentals().fundamentals(query=query, use_cache=use_cache)
```

---

### 4. LLM 에이전트 (`backend/stock_agent/fundamentals_agent/agent.py`)

#### 변경 내용
- ❌ `RatingResult` 모델 제거
- ❌ rating 계산 로직 제거
- ❌ rating 업로드 로직 제거
- ✅ 반환값 간소화: `(response, state, rating)` → `(response, state)`

#### 제거된 코드
```python
# 제거됨
class RatingResult(BaseModel):
    score: int
    rate: str
    justification: Optional[str]

# 제거됨
raw_rating = final_state.get("rating")
final_rating = raw_rating.model_dump()

# 제거됨
analysis_payload = {
    "rating": final_rating,  # 제거됨
    ...
}
```

---

## 📊 영향 받는 API

### 1. FnGuide 크롤러
```python
# Before
from utils.crawler.fnguide import FnGuideCrawler
data = FnGuideCrawler("005930").fundamentals()
# Returns: {"market_conditions": [...], "포괄손익계산서": [...], ...}

# After
data = FnGuideCrawler("005930").fundamentals()
# Returns: {"ticker": "005930", "country": "KR", "balance_sheet": "...", ...}
```

### 2. Yahoo Finance
```python
# Before
from utils.yahoofinance import Fundamentals
data = Fundamentals().fundamentals(query="AAPL")
# Returns: {"result": {...}, "analysis": "...", "rating": {...}, ...}

# After
data = Fundamentals().fundamentals(query="AAPL")
# Returns: {"ticker": "AAPL", "country": "US", "balance_sheet": "...", ...}
```

### 3. MCP 도구
```python
# Before
find_fnguide_data(stock="005930")
# Returns: {"포괄손익계산서": [...], "재무상태표": [...], ...}

# After
find_fnguide_data(stock="005930")
# Returns: {"ticker": "005930", "country": "KR", "income_statement": "...", ...}
```

---

## ✅ 장점

### 1. 단순화
- 코드 길이 49% 감소 (273줄 → 139줄)
- 복잡한 분석/평가 로직 제거
- 테스트 용이성 향상

### 2. 표준화
- FnGuide와 Yahoo Finance 동일한 스키마
- LLM 에이전트가 티커 종류에 관계없이 동일한 방식으로 처리

### 3. 성능
- GCS 캐싱 유지 (API 호출 비용 절감)
- 불필요한 데이터 제거 (네트워크/저장소 최적화)

### 4. 유지보수성
- 단일 책임 원칙 준수 (재무제표 수집만)
- 명확한 데이터 구조
- 문서화 개선

---

## ⚠️ Breaking Changes

### 제거된 필드
다음 필드를 사용하던 코드는 수정이 필요합니다:

#### FnGuide
- ❌ `market_conditions`
- ❌ `earning_issue`
- ❌ `holdings_status`
- ❌ `governance`
- ❌ `shareholders`
- ❌ `bond_rating`
- ❌ `analysis`
- ❌ `industry_comparison`
- ❌ `session_state`

#### Yahoo Finance
- ❌ `result.market_conditions`
- ❌ `result.industry_comparison`
- ❌ `analysis` (텍스트 분석)
- ❌ `rating` (평가 점수)
- ❌ `session_state`

### 마이그레이션 가이드
```python
# Before
data = Fundamentals().fundamentals(query="AAPL")
score = data["rating"]["score"]  # ❌ 더 이상 존재하지 않음
analysis = data["analysis"]       # ❌ 더 이상 존재하지 않음

# After
data = Fundamentals().fundamentals(query="AAPL")
income_statement = json.loads(data["income_statement"])  # ✅ 재무제표 직접 사용
# 분석/평가는 별도 에이전트에서 수행
```

---

## 🔍 테스트 확인 사항

### FnGuide
```python
data = FnGuideCrawler("005930").fundamentals()
assert data["ticker"] == "005930"
assert data["country"] == "KR"
assert "balance_sheet" in data
assert "income_statement" in data
assert "cash_flow" in data
```

### Yahoo Finance
```python
data = Fundamentals().fundamentals(query="AAPL")
assert data["ticker"] == "AAPL"
assert data["country"] != "Unknown"
assert "balance_sheet" in data
assert "income_statement" in data
assert "cash_flow" in data
```

### MCP 도구
```python
# 한국 주식
kr_data = find_fnguide_data(stock="005930")
us_data = get_yahoofinance_fundamentals(query="AAPL")

# 동일한 스키마 확인
assert set(kr_data.keys()) == set(us_data.keys())
assert kr_data["country"] == "KR"
assert us_data["country"] == "US"
```

---

## 📝 다음 단계

1. ✅ FnGuide 스키마 통합 완료
2. ✅ Yahoo Finance 리팩토링 완료
3. ✅ MCP 도구 업데이트 완료
4. ✅ Rating 로직 제거 완료
5. ⏳ 프론트엔드 API 응답 검증
6. ⏳ 통합 테스트 작성
7. ⏳ 문서 업데이트

---

## 📚 참고 문서

- [CODE_COMPARISON.md](CODE_COMPARISON.md) - Yahoo Finance 코드 비교 분석
- [REFACTORING_PLAN.md](REFACTORING_PLAN.md) - 전체 리팩토링 계획
