import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

try:
    from google.adk.models import Message
    print("Found Message in google.adk.models")
except ImportError:
    print("Not in google.adk.models")

try:
    from google.adk.models.lite_llm import Message
    print("Found Message in google.adk.models.lite_llm")
except ImportError:
    print("Not in google.adk.models.lite_llm")

# Check where Event comes from
try:
    from google.adk.events import Message
    print("Found Message in google.adk.events")
except ImportError:
    print("Not in google.adk.events")

# Inspect google.adk.agents.llm_agent to see what it uses
try:
    from google.adk.agents.llm_agent import Message
    print("Found Message in google.adk.agents.llm_agent")
except ImportError:
    print("Not in google.adk.agents.llm_agent")

import google.adk
print(f"ADK Path: {google.adk.__file__}")
