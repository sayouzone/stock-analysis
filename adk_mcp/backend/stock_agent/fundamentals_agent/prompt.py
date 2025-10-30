from pathlib import Path

def fetch_fundamentals_prompt() -> str:
    """
    Navigate to project root and find prompt file
    Current file: backend/stock_agent/fundamentals_agent/prompt.py
    Target file: prompt/fetch_fundamentals.md (from project root)
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    fetch_fundamentals_prompt_path = project_root / "prompt" / "fetch_fundamentals.md"
    fetch_fundamentals_prompt_content = fetch_fundamentals_prompt_path.read_text(encoding='utf-8')

    return fetch_fundamentals_prompt_content