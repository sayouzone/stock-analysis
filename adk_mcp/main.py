import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (로컬 개발 환경용)
# 프로덕션 환경에서는 Cloud Run에 설정된 환경변수나 Secret Manager를 사용
if os.getenv("ENVIRONMENT") != "production":
    load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routers import news, market, fundamentals
from utils.gcpmanager import SecretManager

# 프로덕션 환경일 경우 Secret Manager에서 환경변수 로드
if os.getenv("ENVIRONMENT") == "production":
    # 로드할 시크릿 목록
    secrets_to_load = ["FRONTEND_URL", "DART_API_KEY", "GEMINI_API_KEY"]
    
    secret_manager = SecretManager()
    secret_manager.load_secrets_into_env(secrets_to_load)

app = FastAPI()

# CORS 설정
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 프로덕션 환경에서는 Secret Manager에서 로드한 FRONTEND_URL 사용
if os.getenv("ENVIRONMENT") == "production":
    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        origins.append(frontend_url)
    
    # Cloud Run 기본 도메인도 추가
    origins.extend([
        "https://*.run.app",
        "https://*.googleusercontent.com",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터를 먼저 등록 (우선순위)
app.include_router(market.router)
app.include_router(news.router)
app.include_router(fundamentals.router)

# 루트 경로에서 헬스체크 엔드포인트 추가
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

_frontend_build = Path(__file__).resolve().parent / "frontend" / "build"
if _frontend_build.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_build), html=True), name="static")
else:
    logging.warning("Frontend build directory not found at %s; static hosting disabled.", _frontend_build)
