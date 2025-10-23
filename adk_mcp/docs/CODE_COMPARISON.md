# Yahoo Finance 코드 비교 분석

## 개요
`backend/mcp_server/fundamentals.py`와 `backend/utils/yahoofinance.py`의 yfinance 활용 코드 비교

---

## 비교표

| 항목 | MCP 도구 (`fundamentals.py`) | 유틸리티 (`yahoofinance.py`) |
|------|---------------------------|---------------------------|
| **코드 길이** | 70줄 | 300줄+ |
| **캐싱** | ❌ 없음 | ✅ GCS 캐싱 |
| **날짜 파라미터** | ❌ 없음 | ❌ 없음 (둘 다) |
| **단일 책임** | ✅ 재무제표만 수집 | ❌ 수집+분석+포맷팅 혼재 |
| **반환 형식 일관성** | ✅ 항상 동일한 dict | ⚠️ 상황에 따라 다름 |
| **에러 처리** | ✅ try-except 개별 처리 | ✅ try-except + logging |
| **확장성** | ⚠️ 제한적 | ✅ 매우 유연함 |
| **테스트 용이성** | ✅ 단순함 | ❌ 복잡함 |
| **문서화** | ✅ 명확한 docstring | ⚠️ 일부 누락 |
| **로깅** | ❌ print만 사용 | ✅ logging 모듈 |
| **성능** | ⚠️ 매번 API 호출 | ✅ 캐시로 최적화 |

---

## 상세 분석

### 1. MCP 도구 버전 (`fundamentals.py:70-149`)

```python
def get_yahoofinance_fundamentals(query: str):
    # 장점:
    # - 명확한 단일 목적 (재무제표 3종만 수집)
    # - 간결한 70줄 코드
    # - 항상 동일한 dict 구조 반환

    # 단점:
    # - 캐싱 없음 → 매번 API 호출
    # - 날짜 파라미터 없음
    # - 기본 정보만 제공 (PER, 배당 등 없음)

    return {
        "ticker": str,
        "country": str,
        "balance_sheet": str | None,
        "income_statement": str | None,
        "cash_flow": str | None
    }
```

**사용 사례:**
- LLM 에이전트의 MCP 도구로 사용
- 빠른 재무제표 조회
- 표준화된 데이터 파이프라인

---

### 2. 유틸리티 버전 (`yahoofinance.py:312-585`)

```python
def fundamentals(
    stock: str | None = None,
    query: str | None = None,
    *,
    use_cache: bool = True,
    overwrite: bool = False,
    attribute_name_str: str | None = None
) -> dict[str, object]:
    # 장점:
    # - GCS 캐싱으로 반복 호출 최적화
    # - 유연한 API (전체 요약 or 특정 attribute)
    # - 풍부한 메타데이터 (PER, 배당, 환율 등)
    # - 자동 평가 시스템 (rating)
    # - 프로덕션 품질 로깅

    # 단점:
    # - 300줄 이상의 복잡한 구조
    # - 단일 책임 원칙 위반
    # - 테스트 어려움

    return {
        'result': {...},
        'analysis': str,
        'rating': {...},
        'session_state': {...},
        'agent_final_response': None
    }
```

**사용 사례:**
- 프론트엔드 API 응답
- 상세한 재무 분석이 필요한 경우
- 캐싱이 중요한 프로덕션 환경

---

## 권장 사항

### ✅ MCP 도구 버전을 선택해야 하는 경우
1. LLM 에이전트가 재무제표만 필요할 때
2. 빠른 응답이 중요할 때
3. 표준화된 데이터 형식이 필요할 때
4. 테스트가 중요한 경우

### ✅ 유틸리티 버전을 선택해야 하는 경우
1. 캐싱으로 API 호출 비용을 줄여야 할 때
2. 추가 메타데이터(PER, 배당 등)가 필요할 때
3. 프론트엔드에 바로 표시할 데이터가 필요할 때
4. 환율 변환이 필요한 경우

---

## 개선 제안

### MCP 도구 버전 개선안
```python
@mcp.tool(name="get_yahoofinance_fundamentals")
def get_yahoofinance_fundamentals(
    query: str,
    period: Literal["annual", "quarterly"] = "annual",  # ← 추가
    use_cache: bool = True  # ← 추가
):
    # GCS 캐싱 추가
    # logging 모듈 사용
    # 날짜 파라미터 지원
    pass
```

### 유틸리티 버전 개선안
```python
class Fundamentals:
    def fetch_data(self, ticker: str):
        """데이터 수집만 담당"""
        pass

    def format_data(self, raw_data: dict):
        """포맷팅만 담당"""
        pass

    def calculate_rating(self, data: dict):
        """평가만 담당"""
        pass

    def fundamentals(self, query: str):
        """오케스트레이터 역할만"""
        data = self.fetch_data(query)
        formatted = self.format_data(data)
        rating = self.calculate_rating(formatted)
        return {**formatted, 'rating': rating}
```

---

## 결론

| 기준 | 승자 |
|------|------|
| **코드 품질** | MCP 도구 (간결성, 단일 책임) |
| **기능성** | 유틸리티 (캐싱, 메타데이터) |
| **유지보수성** | MCP 도구 (테스트 용이) |
| **프로덕션 적합성** | 유틸리티 (캐싱, 로깅) |
| **LLM 에이전트 적합성** | MCP 도구 (표준화된 출력) |

### 최종 판단
- **MCP 도구가 "더 잘 짜여진" 코드** (SOLID 원칙 준수)
- **유틸리티가 "더 기능이 많은" 코드** (프로덕션 환경에 적합)

**추천**:
- MCP 도구 버전에 **캐싱 기능을 추가**하고
- 유틸리티 버전을 **여러 함수로 분리**하여
- 두 버전을 **목적에 맞게 사용**하는 것이 최선
