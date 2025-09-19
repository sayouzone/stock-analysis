# ADK & MCP 아키텍처

개발자는 ADK를 사용하여 특정 기능(예: 뉴스 분석, 주가 예측)을 수행하는 개별 에이전트(Agent)들을 개발합니다. 개발된 에이전트들은 MCP 플랫폼에 배포되어 관리됩니다. MCP는 이 에이전트들이 안정적으로 작동하고 서로 통신할 수 있는 환경을 제공합니다.

추후 LangGraph, CrewAI 등 적용 모델이 추가될 예정입니다.

## 설정
gemini api에 mcp 서버를 연결시킬 경우에는 mcp client를 따로 구성해야 한다는 결론에 도달했다.
google adk는 따로 client를 구성할 필요 없이 MCPToolset이 따로 있어 클라이언트를 구성할 필요가 없기에 테스트를 고려중이다.
fnguide 데이터를 저장하기 위해 Cloud Storage - BigQuery 구성하는 과정에서 원문 데이터를 가공하고 업로드 방식을 수정했다.
BigQuery 데이터 적재를 위해 Cloud Storage에 로우 데이터를 저장하는 로직을 수정했다.
## 배포

## 테스트

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