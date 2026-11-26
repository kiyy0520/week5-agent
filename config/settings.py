# config/settings.py
import os

MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "8"))
RUN_DEADLINE_SECONDS = float(os.getenv("AGENT_RUN_DEADLINE_SECONDS", "60"))
TOOL_TIMEOUT_SECONDS = float(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "10"))
READ_RETRY_MAX = int(os.getenv("AGENT_READ_RETRY_MAX", "2"))
TOTAL_RETRY_BUDGET = int(os.getenv("AGENT_TOTAL_RETRY_BUDGET", "4"))
APPROVAL_REQUIRED = os.getenv("AGENT_APPROVAL_REQUIRED", "0") == "1"