from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routers import news, market, fundamentals
import os

app = FastAPI()

# CORS 설정
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# 프로덕션 환경에서는 실제 도메인 추가
if os.getenv("ENVIRONMENT") == "production":
    origins.extend([
        "https://*.run.app",  # Cloud Run 도메인
        "https://*.googleusercontent.com",  # Cloud Run 기본 도메인
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.getenv("ENVIRONMENT") == "production" else origins,  # 프로덕션에서는 모든 origin 허용
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

# StaticFiles를 마지막에 마운트 (catch-all)
app.mount("/", StaticFiles(directory="frontend/build", html=True), name="static")
