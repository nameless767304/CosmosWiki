# backend/app/config.py
import os
import logging
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))

# Prefer .env; fall back to .env.local (some setups only create the latter)
for env_filename in (".env", ".env.local"):
    candidate_path = os.path.join(current_dir, "../../", env_filename)
    if os.path.exists(candidate_path):
        load_dotenv(candidate_path)
        break

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Local SQLite database file path (default: backend/data/cosmos.db)
default_db_path = os.path.join(current_dir, "../data/cosmos.db")
LOCAL_DB_PATH = os.environ.get("LOCAL_DB_PATH", "").strip() or os.path.normpath(default_db_path)

# Project root (CosmosWiki/) and default local code directory to scan/sync
PROJECT_ROOT = os.path.normpath(os.path.join(current_dir, "../../"))
DEFAULT_WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "").strip() or os.path.join(PROJECT_ROOT, "workspace")

# Directory names to skip while walking the local code tree
IGNORED_DIR_NAMES = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".idea", ".vscode"}

# File extensions eligible for scanning/indexing
SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rs", ".json", ".md", ".yml",
    ".yaml", ".txt", ".sql", ".sh"
}

# Skip files larger than this to avoid loading huge blobs into SQLite
MAX_SYNC_FILE_BYTES = 500_000

# Chat history window size
WINDOW_SIZE = 20

# Minimum similarity threshold for node links
SIMILARITY_THRESHOLD = 0.60

# Maximum outgoing relations per node
TOP_K_RELATIONS = 5

# Context budget for project mode (characters)
PROJECT_BUDGET_LIMIT = 16000

# Context budget for general mode (characters)
COSMOS_BUDGET_LIMIT = 8000

# Max length for source code input
L1_MAX_LIMIT = 11500


def verify_env_integrity():
    """Verify environment variables."""
    logger = logging.getLogger("cosmos_wiki")
    logger.info("--- Environment Status ---")
    logger.info(f"Gemini API Key: {len(GEMINI_API_KEY) > 0} ({len(GEMINI_API_KEY)} chars)")
    logger.info(f"Local DB Path: {LOCAL_DB_PATH}")
    logger.info("--------------------------")