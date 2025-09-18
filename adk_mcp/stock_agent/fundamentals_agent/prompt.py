import logging
import os
from pathlib import Path
import sys

# utils 모듈을 import 할 수 있도록 프로젝트 루트를 python path에 추가한다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from utils.gcpmanager import GCSManager

logger = logging.getLogger(__name__)

INLINE_FALLBACK = (
    "당신은 요청된 종목의 펀더멘털 데이터를 수집·정리하는 에이전트입니다. "
    "도구 호출은 최소화하되 반드시 근거를 남기세요. 한국 종목이라면 'fundamentals_mcp_tool' 호출은 최대 1회만 시도하고, "
    "정성 항목은 'tavily_search'를 주제별로 1회씩만 사용하세요. 실패하거나 근거를 찾지 못하면 해당 필드에 '근거 부족'이라고 명확히 남기십시오."
)


def fetch_fundamentals_data_instructions():
    """GCS에서 펀더멘털 분석 지침을 로드한다.

    - 환경 변수 `PROMPT_BLOB`에 GCS 경로(디렉터리)를 지정해야 한다.
    - 파일은 해당 경로 하위의 `fetch_fundamentals_data.md`로 고정된다.
    - 로컬 파일은 더 이상 읽지 않으며, 실패 시 최소한의 한국어 기본 지침을 반환한다.
    """

    blob_root = os.getenv("PROMPT_BLOB")
    if not blob_root:
        logger.error("PROMPT_BLOB 환경 변수가 설정되어 있지 않아 GCS 지침을 불러올 수 없습니다.")
        return INLINE_FALLBACK

    gcs_path = Path(blob_root) / "fetch_fundamentals_data.md"

    try:
        payload = GCSManager().read_file(str(gcs_path))
    except Exception as exc:
        logger.error("GCS 지침 파일 로딩 중 오류 발생 (%s): %s", gcs_path, exc)
        return INLINE_FALLBACK

    if not payload:
        logger.error("GCS 지침 파일이 비어있거나 존재하지 않습니다: %s", gcs_path)
        return INLINE_FALLBACK

    logger.info("펀더멘털 지침을 GCS에서 성공적으로 불러왔습니다: %s", gcs_path)
    return payload
