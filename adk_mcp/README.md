# ADK & MCP 아키텍처

개발자는 ADK를 사용하여 특정 기능(예: 뉴스 분석, 주가 예측)을 수행하는 개별 에이전트(Agent)들을 개발합니다. 개발된 에이전트들은 MCP 플랫폼에 배포되어 관리됩니다. MCP는 이 에이전트들이 안정적으로 작동하고 서로 통신할 수 있는 환경을 제공합니다.

추후 LangGraph, CrewAI 등 적용 모델이 추가될 예정입니다.

```tree
├── frontend                # 프론트엔드             
├── backend                 # 백엔드
│   ├── utils               # 유틸리티(크롤링)
│   ├── routers             # fastapi 라우터
│   ├── mcp_server          # ADK 에이전트의 유틸 호출을 위한 MCP 서버
│   └── stock_agent         # ADK 에이전트
│       ├── fundamentals_agent # 펀더멘탈 분석(재무제표 정성적 분석) 에이전트
│       ├── market_agent    # 주가 데이터 분석 에이전트
│       └── data_agent      # 데이터 처리 에이전트(임시)
├── old                     # 레거시 파일
├── docs                    # 관련 문서
├── prompt                  # 프롬프트 모음
├── main.py
└── README.md               # 설명 - 다양한 설명 (Repository overview)
```

## 설정

빌드 명령어
```
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_VITE_API_URL="https://stocks-analysis-1037372895180.us-central1.run.app"
```
gemini api에 mcp 서버를 연결시킬 경우에는 mcp client를 따로 구성해야 한다는 결론에 도달했다.
google adk는 따로 client를 구성할 필요 없이 MCPToolset이 따로 있어 클라이언트를 구성할 필요가 없기에 테스트를 고려중이다.
fnguide 데이터를 저장하기 위해 Cloud Storage - BigQuery 구성하는 과정에서 원문 데이터를 가공하고 업로드 방식을 수정했다.
BigQuery 데이터 적재를 위해 Cloud Storage에 로우 데이터를 저장하는 로직을 수정했다.

Backend 응답:
```json
{
    "result": {
        # 재무제표 데이터
        "balance_sheet": {...},
        "income_statement": {...},
        "cash_flow": {...}
    }
}
```
## 배포

## 로컬 테스트

#### ADK 테스트

```bash
source .venv/bin/activate
```

```bash
pip install pandas fastmcp lxml playwright beautifulsoup4 yfinance uv
```

```bash
cd adk_mcp/backend/stock_agent
```

mcp server stdio 테스트

```bash
fastmcp run backend/mcp_server/server.py:mcp --project ../../adk_mcp
```

정상 동작 화면

```bash

                                                                 ╭──────────────────────────────────────────────────────────────────────────────╮
                                                                 │                                                                              │
                                                                 │                         ▄▀▀ ▄▀█ █▀▀ ▀█▀ █▀▄▀█ █▀▀ █▀█                        │
                                                                 │                         █▀  █▀█ ▄▄█  █  █ ▀ █ █▄▄ █▀▀                        │
                                                                 │                                                                              │
                                                                 │                               FastMCP 2.13.0.2                               │
                                                                 │                                                                              │
                                                                 │                                                                              │
                                                                 │                   🖥  Server name: StockFundamentalsServer                   │
                                                                 │                                                                              │
                                                                 │                   📦 Transport:   STDIO                                      │
                                                                 │                                                                              │
                                                                 │                   📚 Docs:        https://gofastmcp.com                      │
                                                                 │                   🚀 Hosting:     https://fastmcp.cloud                      │
                                                                 │                                                                              │
                                                                 ╰──────────────────────────────────────────────────────────────────────────────╯


[10/29/25 18:02:48] INFO     Starting MCP server 'StockFundamentalsServer' with transport 'stdio'  
```

```bash
export GOOGLE_API_KEY=[API_KEY]
adk web
```

정상 동작 화면

```bash
/Users/seongjungkim/Development/sayouzone/.venv/lib/python3.11/site-packages/google/adk/cli/fast_api.py:130: UserWarning: [EXPERIMENTAL] InMemoryCredentialService: This feature is experimental and may change or be removed in future versions without notice. It may introduce breaking changes at any time.
  credential_service = InMemoryCredentialService()
/Users/seongjungkim/Development/sayouzone/.venv/lib/python3.11/site-packages/google/adk/auth/credential_service/in_memory_credential_service.py:33: UserWarning: [EXPERIMENTAL] BaseCredentialService: This feature is experimental and may change or be removed in future versions without notice. It may introduce breaking changes at any time.
  super().__init__()
INFO:     Started server process [26390]
INFO:     Waiting for application startup.

+-----------------------------------------------------------------------------+
| ADK Web Server started                                                      |
|                                                                             |

| For local testing, access at http://127.0.0.1:8000.                         |
+-----------------------------------------------------------------------------+

INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

## 오류

```
ValueError: No root_agent found for 'stock_agent'. Searched in 'stock_agent.agent.root_agent', 'stock_agent.root_agent' and 'stock_agent/root_agent.yaml'. Ensure '/Users/kimchan-woo/Desktop/sayouzone/stock-analysis/stock-analysis/adk_mcp/stock_agent' is structured correctly, an .env file can be loaded if present, and a root_agent is exposed.
```
ADK WebUI에서 테스트 하던 도중 발생한 오류이다. stock_agent 패키지에서 root_agent 심볼을 찾지 못해 발생한 에러이다.
기존 커스텀 에이전트를 root_agent로 지정하였다.

```
KeyError: 'Context variable not found: `fundamentals_data`.'
```
stock_agent/agent.py:297에서 "CountryFinder" 단계에서 self.country_finder이 아닌 self.analyst.run_async(ctx)를 호출하여 생긴 오류이다.
```
AttributeError: 'InvocationContext' object has no attribute 'session_state'. Did you mean: 'session_service'?
```
ctx.session.state를 ctx.session_state로 적어 발생한 오류이다.

```
ValueError: AnyOf is not supported in function declaration schema for Google AI
```
Google AI에서는 여러 타입을 동시에 허용하는 정의를 지원하지 않아서 발생한 오류이다.
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for AnalysisResult
  Invalid JSON: expected value at line 1 column 1 [type=json_invalid, input_value='**Constructing the Samsu...ve industry trends."\n}', input_type=str]
    For further information visit https://errors.pydantic.dev/2.11/v/json_invalid
```
analyst 프롬프트에 json 형식으로 출력하는 요구가 없어서 발생한 오류이다.

```
ImportError: attempted relative import beyond top-level package
```
원인:
ADK의 agent_loader가 fundamentals_agent를 최상위 모듈로 직접 로드합니다
이 때 Python은 backend/stock_agent/를 sys.path에 추가합니다
상대 경로 import (..tools, ...utils)는 최상위 패키지 밖으로 나갈 수 없어서 에러가 발생합니다
해결 방법: agent.py:23-34에서 런타임에 backend/ 디렉토리를 sys.path에 추가했습니다:
```
# 현재 파일 위치: backend/stock_agent/fundamentals_agent/agent.py
_backend_dir = Path(__file__).resolve().parent.parent.parent
# parent → fundamentals_agent/
# parent.parent → stock_agent/
# parent.parent.parent → backend/

sys.path.insert(0, str(_backend_dir))  # backend/를 sys.path에 추가
```