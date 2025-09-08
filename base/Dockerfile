# Stage 1: Frontend 빌드
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy package.json first for better caching
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./

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

# Copy backend source code
COPY main.py .
COPY routers/ ./routers/
COPY utils/ ./utils/

# Copy frontend build from previous stage
COPY --from=frontend-builder /app/frontend/build ./frontend/build/

# 💡 3. --build-arg "FRONTEND_URL=..." 로 전달된 값을 받기 위해 ARG 선언
ARG FRONTEND_URL

# 💡 4. 받은 ARG 값을 ENV로 설정하여 FastAPI 런타임이 사용하도록 함
ENV FRONTEND_URL=${FRONTEND_URL}
ENV HOST=0.0.0.0
ENV PORT=8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]