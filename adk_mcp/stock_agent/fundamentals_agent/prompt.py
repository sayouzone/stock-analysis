import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.gcpmanager import GCSManager

def fetch_fundamentals_data_instructions():
    """Dynamically loads agent instructions and few-shot examples."""
    try:
        # Load prompt
        blob_path = os.getenv("PROMPT_BLOB")
        file_path = blob_path + "fetch_fundamentals_data.md"
        full_instruction = GCSManager().read_file(file_path)
        print("Successfully loaded instructions.")
        return full_instruction

    except Exception as e:
        print(f"FATAL: Could not load agent instructions: {e}")
        # Fallback to guidance that still directs the LLM to the fundamentals MCP tool
        return (
            "You are an agent that compiles fundamental data for the requested stock. "
            "Use the MCP tool 'find_fnguide_data' to retrieve FnGuide fundamentals when the ticker is Korean. "
            "If the tool cannot be used or returns nothing, explain the limitation clearly."
        )
