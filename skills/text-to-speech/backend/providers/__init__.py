"""Provider contracts and registry for the Text to Speech skill."""

from .base import (
    AudioArtifact,
    ProviderCapabilities,
    ProviderConfigField,
    SafeErrorCode,
    SpeechGenerationError,
    SpeechProvider,
    SpeechRequest,
    SpeechResult,
)
from .google import GoogleGeminiSpeechProvider
from .mock import DeterministicMockSpeechProvider
from .openai import OpenAISpeechProvider
from .openrouter import OpenRouterSpeechProvider
from .registry import SpeechProviderRegistry, provider_registry

__all__ = [
    "AudioArtifact",
    "DeterministicMockSpeechProvider",
    "GoogleGeminiSpeechProvider",
    "OpenAISpeechProvider",
    "OpenRouterSpeechProvider",
    "ProviderCapabilities",
    "ProviderConfigField",
    "SafeErrorCode",
    "SpeechGenerationError",
    "SpeechProvider",
    "SpeechProviderRegistry",
    "SpeechRequest",
    "SpeechResult",
    "provider_registry",
]
