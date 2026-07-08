import os

from app.core.observability.langsmith_setup import setup_langsmith

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "fake"
os.environ["LANGSMITH_PROJECT"] = "careerpilot"
setup_langsmith()
print("Success")
