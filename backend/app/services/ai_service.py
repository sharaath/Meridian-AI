"""Provider-independent AI service layer with Gemini, Anthropic, and OpenAI adapters."""

from __future__ import annotations

import base64
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import get_settings


class AIProviderError(Exception):
    """Base error raised by AI providers."""


class AIProviderNotConfiguredError(AIProviderError):
    """Raised when the requested model's provider has no configured API key."""


@dataclass(frozen=True)
class AIModelInfo:
    id: str
    name: str
    provider: str
    description: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool = True
    supports_streaming: bool = True
    supports_audio: bool = False
    required_env_var: str = "GEMINI_API_KEY"
    configured: bool = False


@dataclass
class AIAttachment:
    filename: str
    mime_type: str
    data: bytes
    extracted_text: str = ""
    pages: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ChatMessageInput:
    role: str  # "user" | "assistant" | "system"
    content: str
    attachments: List[AIAttachment] = field(default_factory=list)


@dataclass
class AIGenerationConfig:
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.95
    system_instruction: str = ""


@dataclass
class AIStreamChunk:
    delta: str = ""
    done: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error: str = ""


MODE_SYSTEM_PROMPTS: Dict[str, str] = {
    "general": (
        "You are Meridian, a thoughtful, accurate, and clear AI assistant. "
        "Provide well-structured answers using Markdown where helpful. "
        "When citing uploaded documents, include the document filename and page number. "
        "When web search results are provided, distinguish searched facts with inline citations [1], [2]."
    ),
    "coding": (
        "You are Meridian in Coding Assistant mode. Write clean, idiomatic, production-ready code, "
        "explain complex logic clearly line by line when asked, identify root causes when debugging, "
        "and wrap all code in fenced Markdown blocks with explicit language tags."
    ),
    "writing": (
        "You are Meridian in Writing Assistant mode. Craft clear, engaging, well-paced prose tailored "
        "to the user's audience and tone, offering concise improvements without losing the user's voice."
    ),
    "email": (
        "You are Meridian in Email Drafting mode. Produce polished, concise emails with clear subject lines, "
        "appropriate tone, and actionable structure."
    ),
    "translation": (
        "You are Meridian in Translation mode. Provide accurate, natural-sounding translations preserving "
        "nuance, idioms, and formatting, and briefly note cultural or phrasing nuances if relevant."
    ),
    "tutor": (
        "You are Meridian in Learning & Tutoring mode. Teach step by step, verify understanding, "
        "give intuitive analogies and worked examples, and encourage active problem-solving."
    ),
    "math": (
        "You are Meridian in Mathematical Problem Solving mode. Show rigorous step-by-step derivations, "
        "verify edge cases and units, and clearly box or highlight the final answer."
    ),
}


class BaseAIProvider(ABC):
    """Abstract interface that every AI provider adapter implements."""

    provider_id: str
    required_env_var: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True only when real credentials are present."""

    @abstractmethod
    def list_models(self) -> List[AIModelInfo]:
        """Return catalog of models for this provider with configured status."""

    @abstractmethod
    async def stream_chat(
        self,
        model_id: str,
        messages: List[ChatMessageInput],
        config: AIGenerationConfig,
    ) -> AsyncIterator[AIStreamChunk]:
        """Yield incremental AIStreamChunk tokens from the provider."""

    async def transcribe_audio(self, model_id: str, audio_bytes: bytes, mime_type: str) -> str:
        """Optional audio transcription capability."""
        raise AIProviderError(f"Audio transcription is not supported by provider '{self.provider_id}'.")


class GeminiProvider(BaseAIProvider):
    """Google Gemini API provider powered by google-genai SDK."""

    provider_id = "gemini"
    required_env_var = "GEMINI_API_KEY"

    MODELS = [
        AIModelInfo(
            id="gemini-2.5-flash",
            name="Gemini 2.5 Flash",
            provider="gemini",
            description="Fast, multimodal flagship model for chat, documents, code, and images.",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
            supports_audio=True,
            required_env_var="GEMINI_API_KEY",
        ),
        AIModelInfo(
            id="gemini-2.5-pro",
            name="Gemini 2.5 Pro",
            provider="gemini",
            description="High-reasoning model for complex coding, math, and deep document synthesis.",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
            supports_audio=True,
            required_env_var="GEMINI_API_KEY",
        ),
        AIModelInfo(
            id="gemini-2.0-flash",
            name="Gemini 2.0 Flash",
            provider="gemini",
            description="Low-latency general-purpose multimodal model.",
            context_window=1048576,
            max_output_tokens=8192,
            supports_vision=True,
            supports_audio=True,
            required_env_var="GEMINI_API_KEY",
        ),
    ]

    def is_configured(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def list_models(self) -> List[AIModelInfo]:
        configured = self.is_configured()
        return [
            AIModelInfo(
                id=m.id,
                name=m.name,
                provider=m.provider,
                description=m.description,
                context_window=m.context_window,
                max_output_tokens=m.max_output_tokens,
                supports_vision=m.supports_vision,
                supports_streaming=m.supports_streaming,
                supports_audio=m.supports_audio,
                required_env_var=m.required_env_var,
                configured=configured,
            )
            for m in self.MODELS
        ]

    def _build_contents(self, messages: List[ChatMessageInput]):
        from google.genai import types

        contents = []
        for msg in messages:
            if msg.role == "system":
                continue
            role = "model" if msg.role == "assistant" else "user"
            parts = []
            if msg.content:
                parts.append(types.Part.from_text(text=msg.content))
            for att in msg.attachments:
                if att.mime_type.startswith("image/") and att.data:
                    parts.append(types.Part.from_bytes(data=att.data, mime_type=att.mime_type))
                elif att.extracted_text:
                    doc_block = f"\n[Attached Document: {att.filename}]\n{att.extracted_text[:24000]}\n"
                    parts.append(types.Part.from_text(text=doc_block))
            if parts:
                contents.append(types.Content(role=role, parts=parts))
        return contents

    async def stream_chat(
        self,
        model_id: str,
        messages: List[ChatMessageInput],
        config: AIGenerationConfig,
    ) -> AsyncIterator[AIStreamChunk]:
        api_key = get_settings().gemini_api_key
        if not api_key:
            raise AIProviderNotConfiguredError(
                "Gemini API is not configured. Set GEMINI_API_KEY in backend/.env to enable Gemini models."
            )

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        contents = self._build_contents(messages)
        gen_config = types.GenerateContentConfig(
            system_instruction=config.system_instruction or None,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            top_p=config.top_p,
        )

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        try:
            stream = await client.aio.models.generate_content_stream(
                model=model_id,
                contents=contents,
                config=gen_config,
            )
            async for chunk in stream:
                text = getattr(chunk, "text", None) or ""
                usage = getattr(chunk, "usage_metadata", None)
                if usage:
                    prompt_tokens = getattr(usage, "prompt_token_count", prompt_tokens) or prompt_tokens
                    completion_tokens = getattr(usage, "candidates_token_count", completion_tokens) or completion_tokens
                    total_tokens = getattr(usage, "total_token_count", total_tokens) or total_tokens
                if text:
                    yield AIStreamChunk(delta=text)

            yield AIStreamChunk(
                done=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens or (prompt_tokens + completion_tokens),
            )
        except Exception as exc:
            raise AIProviderError(f"Gemini API error: {exc}") from exc

    async def transcribe_audio(self, model_id: str, audio_bytes: bytes, mime_type: str) -> str:
        api_key = get_settings().gemini_api_key
        if not api_key:
            raise AIProviderNotConfiguredError(
                "Gemini API is not configured. Set GEMINI_API_KEY in backend/.env to transcribe audio."
            )
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        response = await client.aio.models.generate_content(
            model=model_id or "gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="Transcribe this audio recording verbatim. Output only the spoken transcript."
                        ),
                        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    ],
                )
            ],
        )
        return (getattr(response, "text", None) or "").strip()


class AnthropicProvider(BaseAIProvider):
    """Anthropic Claude API adapter (active only when ANTHROPIC_API_KEY is configured)."""

    provider_id = "anthropic"
    required_env_var = "ANTHROPIC_API_KEY"

    MODELS = [
        AIModelInfo(
            id="claude-sonnet-4-20250514",
            name="Claude Sonnet 4",
            provider="anthropic",
            description="Anthropic Claude Sonnet 4 for nuanced writing, analysis, and coding.",
            context_window=200000,
            max_output_tokens=8192,
            supports_vision=True,
            required_env_var="ANTHROPIC_API_KEY",
        ),
    ]

    def is_configured(self) -> bool:
        return bool(get_settings().anthropic_api_key)

    def list_models(self) -> List[AIModelInfo]:
        configured = self.is_configured()
        return [
            AIModelInfo(**{**m.__dict__, "configured": configured})
            for m in self.MODELS
        ]

    async def stream_chat(
        self,
        model_id: str,
        messages: List[ChatMessageInput],
        config: AIGenerationConfig,
    ) -> AsyncIterator[AIStreamChunk]:
        api_key = get_settings().anthropic_api_key
        if not api_key:
            raise AIProviderNotConfiguredError(
                "Anthropic API is not configured. Set ANTHROPIC_API_KEY in backend/.env."
            )

        formatted_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            content_blocks: List[Dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for att in msg.attachments:
                if att.mime_type.startswith("image/") and att.data:
                    content_blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": att.mime_type,
                                "data": base64.b64encode(att.data).decode("ascii"),
                            },
                        }
                    )
                elif att.extracted_text:
                    content_blocks.append(
                        {"type": "text", "text": f"[Attached Document: {att.filename}]\n{att.extracted_text[:24000]}"}
                    )
            formatted_messages.append({"role": msg.role, "content": content_blocks})

        payload: Dict[str, Any] = {
            "model": model_id,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": formatted_messages,
            "stream": True,
        }
        if config.system_instruction:
            payload["system"] = config.system_instruction

        prompt_tokens = 0
        completion_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise AIProviderError(f"Anthropic API error ({resp.status_code}): {body.decode(errors='ignore')}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    evt = json.loads(raw)
                    evt_type = evt.get("type")
                    if evt_type == "message_start":
                        usage = (evt.get("message") or {}).get("usage") or {}
                        prompt_tokens = usage.get("input_tokens", prompt_tokens)
                    elif evt_type == "content_block_delta":
                        delta = (evt.get("delta") or {}).get("text", "")
                        if delta:
                            yield AIStreamChunk(delta=delta)
                    elif evt_type == "message_delta":
                        usage = evt.get("usage") or {}
                        completion_tokens = usage.get("output_tokens", completion_tokens)

        yield AIStreamChunk(
            done=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


class OpenAIProvider(BaseAIProvider):
    """OpenAI API adapter (active only when OPENAI_API_KEY is configured)."""

    provider_id = "openai"
    required_env_var = "OPENAI_API_KEY"

    MODELS = [
        AIModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            provider="openai",
            description="OpenAI fast multimodal model.",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
            required_env_var="OPENAI_API_KEY",
        ),
    ]

    def is_configured(self) -> bool:
        return bool(get_settings().openai_api_key)

    def list_models(self) -> List[AIModelInfo]:
        configured = self.is_configured()
        return [
            AIModelInfo(**{**m.__dict__, "configured": configured})
            for m in self.MODELS
        ]

    async def stream_chat(
        self,
        model_id: str,
        messages: List[ChatMessageInput],
        config: AIGenerationConfig,
    ) -> AsyncIterator[AIStreamChunk]:
        api_key = get_settings().openai_api_key
        if not api_key:
            raise AIProviderNotConfiguredError(
                "OpenAI API is not configured. Set OPENAI_API_KEY in backend/.env."
            )

        formatted: List[Dict[str, Any]] = []
        if config.system_instruction:
            formatted.append({"role": "system", "content": config.system_instruction})

        for msg in messages:
            if msg.role == "system":
                continue
            parts: List[Dict[str, Any]] = []
            if msg.content:
                parts.append({"type": "text", "text": msg.content})
            for att in msg.attachments:
                if att.mime_type.startswith("image/") and att.data:
                    b64 = base64.b64encode(att.data).decode("ascii")
                    parts.append(
                        {"type": "image_url", "image_url": {"url": f"data:{att.mime_type};base64,{b64}"}}
                    )
                elif att.extracted_text:
                    parts.append(
                        {"type": "text", "text": f"[Attached Document: {att.filename}]\n{att.extracted_text[:24000]}"}
                    )
            formatted.append({"role": msg.role, "content": parts or msg.content})

        payload = {
            "model": model_id,
            "messages": formatted,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise AIProviderError(f"OpenAI API error ({resp.status_code}): {body.decode(errors='ignore')}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    evt = json.loads(raw)
                    usage = evt.get("usage")
                    if usage:
                        prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                        completion_tokens = usage.get("completion_tokens", completion_tokens)
                        total_tokens = usage.get("total_tokens", total_tokens)
                    choices = evt.get("choices") or []
                    if choices:
                        delta = (choices[0].get("delta") or {}).get("content") or ""
                        if delta:
                            yield AIStreamChunk(delta=delta)

        yield AIStreamChunk(
            done=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
        )


class AIServiceRegistry:
    """Registry managing available AI providers and model routing."""

    def __init__(self) -> None:
        self.providers: List[BaseAIProvider] = [
            GeminiProvider(),
            AnthropicProvider(),
            OpenAIProvider(),
        ]

    def list_models(self, include_unconfigured: bool = False) -> List[AIModelInfo]:
        models: List[AIModelInfo] = []
        for provider in self.providers:
            for model in provider.list_models():
                if include_unconfigured or model.configured:
                    models.append(model)
        return models

    def get_default_model_id(self) -> Optional[str]:
        configured = self.list_models(include_unconfigured=False)
        return configured[0].id if configured else None

    def resolve_provider(self, model_id: Optional[str]) -> tuple[BaseAIProvider, AIModelInfo]:
        all_models = self.list_models(include_unconfigured=True)
        target_id = model_id or self.get_default_model_id()

        if not target_id:
            raise AIProviderNotConfiguredError(
                "No AI provider is configured. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY / OPENAI_API_KEY) in backend/.env."
            )

        for provider in self.providers:
            for model in provider.list_models():
                if model.id == target_id:
                    if not provider.is_configured():
                        raise AIProviderNotConfiguredError(
                            f"Model '{model.name}' requires {provider.required_env_var} to be configured on the server."
                        )
                    return provider, model

        valid_ids = ", ".join(m.id for m in all_models)
        raise AIProviderError(f"Unknown model '{target_id}'. Supported models: {valid_ids}")

    def provider_status_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "provider": p.provider_id,
                "configured": p.is_configured(),
                "required_env_var": p.required_env_var,
                "models": [m.id for m in p.list_models()],
            }
            for p in self.providers
        ]


ai_registry = AIServiceRegistry()

