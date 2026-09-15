import os
from typing import Any, Type, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from app.core.config import settings

class LLMFactory:
    @staticmethod
    def get_chat_model(temperature: float = 0.1) -> Optional[BaseChatModel]:
        """
        Returns an initialized chat model based on environment configuration.
        """
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-"):
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=settings.OPENAI_MODEL,
                    api_key=settings.OPENAI_API_KEY,
                    temperature=temperature
                )
            except Exception as e:
                print(f"[LLMFactory] Warning: Failed to initialize ChatOpenAI: {e}")

        if settings.GEMINI_API_KEY:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=settings.GEMINI_MODEL,
                    google_api_key=settings.GEMINI_API_KEY,
                    temperature=temperature
                )
            except Exception as e:
                print(f"[LLMFactory] Warning: Failed to initialize ChatGoogleGenerativeAI: {e}")

        return None
