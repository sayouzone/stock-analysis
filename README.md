# LLM을 활용하여 Stock Market 분석

[주식 시장 분석 서비스](https://stocks.sayouzone.com)

주식 투자에 대해 정보 수집 및 분석하는 서비스를 구축하는 방법에 대해 알아보겠습니다. FastAPI, yfinance, 웹 크롤링, LLM 분석, MCP 서버 구축 및 Agentic AI 아키텍처를 활용한 종합적인 접근 방식을 다룹니다. LLM은 기본적으로 Gemini Pro 2.5를 사용하며 상황에 따라 GPT-5를 활용하고 있습니다. 추후 Claude 및 Llama 4.0, Mistral, DeepSeek도 활용할 예정입니다.

폴더 구성은 아래와 같습니다.

```tree
├── adk_mcp                     # ADK 기반 Agent + MCP 모델
│   ├── frontend                # 프론트엔드             
│   ├── backend                 # 백엔드
│   │   ├── utils               # 유틸리티(크롤링)
│   │   ├── routers             # fastapi 라우터
│   │   ├── mcp_server          # ADK 에이전트의 유틸 호출을 위한 MCP 서버
│   │   └── stock_agent         # ADK 에이전트
│   │       ├── fundamentals_agent # 펀더멘탈 분석(재무제표 정성적 분석) 에이전트
│   │       ├── market_agent    # 주가 데이터 분석 에이전트
│   │       └── data_agent      # 데이터 처리 에이전트(임시)
│   ├── old                     # 레거시 파일
│   ├── docs                    # 관련 문서
│   ├── prompt                  # 프롬프트 모음
│   ├── main.py
│   └── README.md               # 설명 - 다양한 설명 (Repository overview)
├── base                        # Web & REST API & Ajax 아키텍처
│   ├── frontend                # 프론트엔드             
│   ├── jupyter                 # Jupyter Notebook 파일
│   ├── old                     # 레거시 파일
│   ├── routers                 # Fastapi 라우터
│   ├── utils                   # 유틸리티(크롤링)
│   ├── docs                    # 관련 문서
│   ├── Dockerfile
│   ├── cloudbuild.yaml         # Google Cloud Build 설정
│   ├── main.py
│   ├── requirements.txt
│   └── README.md               # 설명 - 다양한 설명 (Repository overview)
├── multi-agents                # Multi-Agents 모델 (추후 개발 예정)
│   └── README.md               # 설명 - 다양한 설명 (Repository overview)
├── LICENSE                     # 라이선스 정책
└── README.md                   # 설명 - 전체 서비스 구조 설명 (Repository overview)
```

**Web & REST API & Ajax 아키텍처**

![기본 구조](https://www.sayouzone.com/resource/images/blog/stock_analysis_basis.png)

**ADK & MCP 아키텍처**

![ADK & MCP](https://www.sayouzone.com/resource/images/blog/stock_analysis_agents.png)

**Agentic AI (A2A, ADK & MCP) 아키텍처**

![Agentic AI](https://www.sayouzone.com/resource/images/blog/stock_analysis_agentic_ai.png)

## 기본 모델 (Web & REST API & Ajax 아키텍처)

웹 크롤러(Web Crawler)가 주기적으로 목표 웹사이트(Target Website)를 방문하여 HTML 정보를 가져옵니다.<br>
파서(Parser)는 이 HTML에서 필요한 데이터(뉴스 기사, 댓글 등)만 추출합니다.<br>
LLM(Large Language Model)으로 뉴스 기사, 댓글 등을 요약하거나 분석합니다.

[기본 모델](https://github.com/sayouzone/stock-analysis/tree/main/base)

## Agent 모델 (ADK & MCP 아키텍처)

개발자는 ADK를 사용하여 특정 기능(예: 뉴스 분석, 주가 예측)을 수행하는 개별 에이전트(Agent)들을 개발합니다.<br>
개발된 에이전트들은 MCP 플랫폼에 배포되어 관리됩니다.<br>
MCP는 이 에이전트들이 안정적으로 작동하고 서로 통신할 수 있는 환경을 제공합니다.

[Agent 모델](https://github.com/sayouzone/stock-analysis/tree/main/adk_mcp)

## Multi-Agents 모델 (Agentic AI (A2A, ADK & MCP) 아키텍처)

이 프로젝트의 핵심은 Agentic AI 아키텍처에 있습니다. 이는 복잡한 작업을 자율적으로 수행하는 여러 AI 에이전트들의 협력 시스템을 의미합니다.<br>
예를 들어, '시장 뉴스 분석 에이전트'는 매일 새로운 뉴스를 크롤링하고, LLM을 이용해 "이 뉴스가 A 기업에 긍정적인가, 부정적인가?"를 판단하여 그 결과를 '투자 전략 에이전트'에게 전달합니다.<br>
'투자 전략 에이전트'는 이 정보를 종합하여 최종 투자 의견을 생성합니다.

[Multi-Agents 모델](https://github.com/sayouzone/stock-analysis/tree/main/multi-agents)

## 참고

- [주식 투자에 대한 서비스 구축](https://www.sayouzone.com/blog/item/stocks_investment_service_development)
- [LLM을 활용하여 주식 시장 분석](https://www.sayouzone.com/blog/item/stocks_overview)