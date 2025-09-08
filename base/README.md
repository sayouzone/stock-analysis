# Web & REST API & Ajax 아키텍처

웹 크롤러(Web Crawler)가 주기적으로 목표 웹사이트(Target Website)를 방문하여 HTML 정보를 가져옵니다. 
파서(Parser)는 이 HTML에서 필요한 데이터(뉴스 기사, 댓글 등)만 추출합니다. 
LLM(Large Language Model)으로 뉴스 기사, 댓글 등을 요약하거나 분석합니다. 
추출된 데이터는 Big Lake(BigQuery)에 저장되어 나중에 분석 및 조회를 위해 사용됩니다.

FastAPI로 제작한 웹페이지 기록

## 설정

## 배포

## 테스트

## 오류