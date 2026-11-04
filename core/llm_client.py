"""Unified LLM Provider abstraction for Gemini, Groq, and Mock/Dry-Run.

Allows seamless switching between free-tier LLM providers without altering agent logic.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.llm")


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate raw text response."""
        ...

    @abstractmethod
    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured JSON response."""
        ...


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider (Free Tier)."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash", temperature: float = 0.7):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config={"temperature": self.temperature}
                )
            except ImportError:
                logger.warning("google-generativeai package not installed or configuration failed.")
                raise
        return self._client

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        client = self._get_client()
        response = client.generate_content(full_prompt)
        return response.text if response and hasattr(response, "text") else ""

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        json_instruction = (
            "\n\nIMPORTANT: Return ONLY a valid JSON object. No Markdown code fences, "
            "no backticks (```json), no conversational filler."
        )
        raw_text = await self.generate_text(prompt + json_instruction, system_prompt)
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        return json.loads(cleaned)


class GroqProvider(BaseLLMProvider):
    """Groq Cloud API Provider (Free Tier compatible)."""

    def __init__(self, api_key: str, model_name: str = "llama-3.3-70b-versatile", temperature: float = 0.7):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature
        }
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        text = await self.generate_text(prompt, system_prompt)
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())


class MockLLMProvider(BaseLLMProvider):
    """Fallback / Mock LLM provider for Dry-Run mode, tests, and CI/CD without API keys."""

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return "यह एक सुरक्षित और स्वचालित हिंदी टेस्ट स्क्रिप्ट है।"

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        return {
            "title": "आज की बड़ी खबरें - 60 सेकंड में",
            "hook": "क्या आपको पता है आज देश में क्या बड़ा फैसला हुआ?",
            "scenes": [
                {
                    "scene_number": 1,
                    "narration": "भारत सरकार ने आज एक बड़ा आर्थिक और तकनीकी निर्णय लिया है।",
                    "visual_instructions": "Fast cut of cabinet briefing and modern digital infrastructure",
                    "duration": 15.0,
                    "transition": "slide_left",
                    "sources": ["https://pib.gov.in"]
                },
                {
                    "scene_number": 2,
                    "narration": "इस परियोजना से लाखों युवाओं को रोजगार और नई तकनीक का लाभ मिलेगा।",
                    "visual_instructions": "Visuals of youth working in tech hub and manufacturing unit",
                    "duration": 20.0,
                    "transition": "zoom_in",
                    "sources": ["https://ddnews.gov.in"]
                },
                {
                    "scene_number": 3,
                    "narration": "विशेषज्ञों का मानना है कि यह कदम भारतीय अर्थव्यवस्था को नई गति देगा।",
                    "visual_instructions": "Economic growth charts and global trade animation",
                    "duration": 18.0,
                    "transition": "fade",
                    "sources": ["https://pib.gov.in"]
                }
            ],
            "total_duration": 53.0,
            "language": "hi",
            "sources": ["https://pib.gov.in", "https://ddnews.gov.in"]
        }


def get_llm_client(provider: str, api_key: str = "", model_name: Optional[str] = None, temperature: float = 0.7) -> BaseLLMProvider:
    """Factory function to acquire configured LLM provider instance."""
    provider_clean = (provider or "").lower().strip()
    if provider_clean == "gemini" and api_key:
        return GeminiProvider(api_key=api_key, model_name=model_name or "gemini-2.0-flash", temperature=temperature)
    elif provider_clean == "groq" and api_key:
        return GroqProvider(api_key=api_key, model_name=model_name or "llama-3.3-70b-versatile", temperature=temperature)
    else:
        logger.info("Using Mock/Offline LLM Provider (no live API key provided or dry-run requested)")
        return MockLLMProvider()
