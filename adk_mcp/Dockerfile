# Stage 1: Frontend 빌드
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy package.json first for better caching
COPY frontend/package.json ./
RUN npm install

# Copy the rest of the frontend code
COPY frontend/ .

# Manually run svelte-kit sync to generate necessary files
RUN npx svelte-kit sync

# 💡 1. --build-arg "VITE_API_URL=..." 로 전달된 값을 받기 위해 ARG 선언
ARG VITE_API_URL

# 💡 2. 받은 ARG 값을 ENV로 설정하여 'npm run build' 프로세스가 사용하도록 함
ENV VITE_API_URL=${VITE_API_URL}

# Build with production environment
RUN npm run build

# Stage 2: Python 백엔드 + 프론트엔드 통합
FROM python:3.11-slim AS backend

# Install system dependencies
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# fastmcp가 사용하는 uv 설치
RUN pip install uv

# Copy backend source code
COPY main.py .
COPY mcp_server/ ./mcp_server/
COPY routers/ ./routers/
COPY utils/ ./utils/
COPY stock_agent/ ./stock_agent/

# Copy frontend build from previous stage
COPY --from=frontend-builder /app/frontend/build ./frontend/build/

# Set runtime environment variables
ENV HOST=0.0.0.0
ENV PORT=8080
# ENVIRONMENT, GCP_PROJECT_ID 등은 Cloud Run 서비스에서 직접 설정합니다.

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]