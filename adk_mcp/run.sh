#!/bin/bash
# 스크립트의 어떤 명령이라도 실패하면 즉시 중단
set -e

# Uvicorn 웹 서버를 백그라운드에서 실행
echo "Starting Uvicorn server..."
uvicorn main:app --host 0.0.0.0 --port 8080 &

# FastMCP 서버를 포그라운드에서 실행
echo "Starting FastMCP server..."
python mcp_server/server.py

