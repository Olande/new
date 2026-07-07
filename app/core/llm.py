from functools import cache

from langchain.chat_models import init_chat_model

from app.config.settings import settings


@cache
def get_llm():
    nvidia_model = init_chat_model(
        "meta/llama-3.1-70b-instruct",
        model_provider="nvidia",
        api_key=settings.nvidia_api_key,
    )
    gemini_model = init_chat_model(
        "gemini-3.1-flash-lite",
        model_provider="google_genai",
        api_key=settings.google_api_key,
    )
    deepseek_flash = init_chat_model("deepseek_chat", api_key=settings.deepseek_api_key)
    deepseek_pro = init_chat_model(
        "deepseek_reasoner", api_key=settings.deepseek_api_key
    )

    return nvidia_model.with_fallbacks([gemini_model, deepseek_flash, deepseek_pro])
