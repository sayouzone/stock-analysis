from pathlib import Path

def fetch_fundamentals_prompt() -> str:
    fetch_fundamentals_prompt_path = Path(__file__).parent / "prompt" / "fetch_fundamentals.md"
    fetch_fundamentals_prompt_content = fetch_fundamentals_prompt_path.read_text(encoding='utf-8')

    return fetch_fundamentals_prompt_content