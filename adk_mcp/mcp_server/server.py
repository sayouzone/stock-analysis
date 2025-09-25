from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from mcp_server.fundamentals import mcp

if __name__ == "__main__":
    mcp.run()