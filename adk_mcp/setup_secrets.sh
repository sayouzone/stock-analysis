#!/bin/bash

# 사용법: ./setup_secrets.sh [GCP_PROJECT_ID]
# 예: ./setup_secrets.sh my-gcp-project

# GCP 프로젝트 ID가 인자로 제공되었는지 확인
if [ -z "$1" ]; then
  echo "오류: GCP 프로젝트 ID를 인자로 제공해야 합니다."
  echo "사용법: $0 [GCP_PROJECT_ID]"
  exit 1
fi

PROJECT_ID=$1
ENV_FILE=".env"

# .env 파일이 존재하는지 확인
if [ ! -f "$ENV_FILE" ]; then
  echo "오류: '.env' 파일이 현재 디렉토리에 없습니다."
  exit 1
fi

# gcloud auth 및 project 설정 확인
ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
if [ -z "$ACCOUNT" ]; then
  echo "gcloud에 로그인되어 있지 않습니다. 'gcloud auth login'을 실행해주세요."
  exit 1
fi

echo "현재 활성 계정: $ACCOUNT"
gcloud config set project $PROJECT_ID
echo "GCP 프로젝트가 '$PROJECT_ID'로 설정되었습니다."

# Secret Manager API 활성화
echo "Secret Manager API를 활성화합니다..."
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

# .env 파일을 한 줄씩 읽어서 Secret Manager에 시크릿 생성
while IFS='=' read -r key value || [ -n "$key" ]; do
  # 주석이나 빈 줄은 건너뛰기
  if [[ "$key" =~ ^# ]] || [ -z "$key" ]; then
    continue
  fi

  echo "시크릿 '$key' 처리 중..."

  # 시크릿이 이미 존재하는지 확인
  if gcloud secrets describe "$key" --project="$PROJECT_ID" &>/dev/null; then
    echo "시크릿 '$key'가 이미 존재합니다. 새 버전을 추가합니다."
    # 기존 시크릿에 새 버전 추가
    printf "%s" "$value" | gcloud secrets versions add "$key" --data-file=- --project="$PROJECT_ID"
  else
    echo "시크릿 '$key'를 새로 생성합니다."
    # 시크릿 신규 생성
    printf "%s" "$value" | gcloud secrets create "$key" --data-file=- --replication-policy="automatic" --project="$PROJECT_ID"
  fi

done < "$ENV_FILE"

echo "모든 시크릿 처리가 완료되었습니다."
