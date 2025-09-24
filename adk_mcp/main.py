import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (로컬 개발 환경용)
# 프로덕션 환경에서는 Cloud Run에 설정된 환경변수나 Secret Manager를 사용
if os.getenv("ENVIRONMENT") != "production":
    load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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
        "https://stocks.sayouzone.com"
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 루트 경로에서 헬스체크 엔드포인트 추가
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(market.router)
app.include_router(news.router)
app.include_router(fundamentals.router)

_frontend_build = Path(__file__).resolve().parent / "frontend" / "build"
if _frontend_build.exists() and (_frontend_build / "index.html").exists():
    
    @app.exception_handler(404)
    async def not_found_exception_handler(request: Request, exc: HTTPException):
        return FileResponse(str(_frontend_build / "index.html"))

    app.mount("/", StaticFiles(directory=str(_frontend_build)), name="static")
    
else:
    logging.warning("Frontend build directory not found at %s; static hosting disabled.", _frontend_build)
