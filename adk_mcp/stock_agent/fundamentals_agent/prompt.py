import logging
import os
import sys

# utils 모듈을 import 할 수 있도록 프로젝트 루트를 python path에 추가한다.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from utils.gcpmanager import GCSManager

logger = logging.getLogger(__name__)

INLINE_FALLBACK = (
    "당신은 요청된 종목의 펀더멘털 데이터를 수집·정리하는 에이전트입니다. "
    "도구 호출은 최소화하되 반드시 근거를 남기세요. 한국 종목이라면 'fundamentals_mcp_tool' 호출은 최대 1회만 시도하고, "
    "정성 항목은 'tavily_search'를 주제별로 1회씩만 사용하세요. 실패하거나 근거를 찾지 못하면 해당 필드에 '근거 부족'이라고 명확히 남기십시오."
)


def fetch_fundamentals_data_instructions():
    """펀더멘털 분석 지침을 GCS에서 로드한다.

    - 환경 변수 `PROMPT_BLOB`에 참조 경로(디렉터리)를 지정한다.
    - GCS 버킷에서 `fetch_fundamentals_data.md`를 로드한다.
    - 실패하면 최소한의 기본 지침(INLINE_FALLBACK)을 반환한다.
    """

    blob_root = os.getenv("PROMPT_BLOB")
    if not blob_root:
        logger.error("PROMPT_BLOB 환경 변수가 설정되어 있지 않아 지침 파일을 찾을 수 없습니다. 기본 메시지를 사용합니다.")
        return INLINE_FALLBACK

    # 환경 변수 값에 포함될 수 있는 불필요한 공백이나 따옴표를 제거하여 경로 오류를 방지합니다.
    cleaned_blob_root = blob_root.strip().strip('"\'"')
    blob_path = os.path.join(cleaned_blob_root, "fetch_fundamentals_data.md")

    payload: str | None = None

    gcs_manager = GCSManager()
    if getattr(gcs_manager, "_storage_available", False):
        try:
            payload = gcs_manager.read_file(blob_path)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("GCS 지침 파일 로딩 중 오류 발생 (%s): %s", blob_path, exc)

    if payload and payload.strip():
        # stock_country 같은 누락 컨텍스트 변수로 인한 템플릿 오류 방지
        try:
            sanitized = (
                payload.replace("{{stock_country}}", "")
                .replace("{{ stock_country }}", "")
            )
        except Exception:
            sanitized = payload
        logger.info("펀더멘털 지침을 GCS에서 성공적으로 불러왔습니다: %s", blob_path)
        return sanitized

    logger.error("GCS에서 지침 파일을 찾을 수 없거나 비어있습니다: %s", blob_path)
    return INLINE_FALLBACK
