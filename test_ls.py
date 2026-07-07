from app.observability.langsmith_setup import setup_langsmith
import os

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_API_KEY"] = "fake"
os.environ["LANGSMITH_PROJECT"] = "careerpilot"
setup_langsmith()
print("Success")
