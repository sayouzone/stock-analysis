import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.gcpmanager import GCSManager

def fetch_fundamentals_data_instructions():
    """Load agent instructions from GCS if configured, otherwise fall back to local file.

    Order of precedence:
    1) GCS (when PROMPT_BLOB is set and readable)
    2) Local file at project root: fetch_fundamentals_data.md
    3) Minimal inline fallback guidance
    """
    # 1) Try GCS when PROMPT_BLOB is set
    blob_path = os.getenv("PROMPT_BLOB")
    if blob_path:
        try:
            file_path = blob_path.rstrip("/") + "/fetch_fundamentals_data.md"
            full_instruction = GCSManager().read_file(file_path)
            if full_instruction:
                print("Successfully loaded instructions from GCS.")
                return full_instruction
            else:
                print("GCS returned empty content; falling back to local file.")
        except Exception as e:
            print(f"Warning: GCS load failed: {e}. Falling back to local file.")

    # 2) Try local file next
    try:
        project_root = Path(__file__).resolve().parents[2]
        local_path = project_root / "fetch_fundamentals_data.md"
        if local_path.exists():
            content = local_path.read_text(encoding="utf-8")
            print("Successfully loaded instructions from local file.")
            return content
        else:
            print(f"Local instruction file not found at: {local_path}")
    except Exception as e:
        print(f"Warning: Local file load failed: {e}")

    # 3) Minimal inline fallback
    print("FATAL: Could not load agent instructions; using inline fallback guidance.")
    return (
        "You are an agent that compiles fundamental data for the requested stock. "
        "Minimize tool calls: call 'find_fnguide_data' at most once for Korean tickers; "
        "use 'tavily_search' once per qualitative field and batch 'tavily_extract' calls. "
        "If a tool fails or returns nothing, leave the structured field null or write '근거 부족' for qualitative notes."
    )
