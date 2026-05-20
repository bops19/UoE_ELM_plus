DEFAULTS = {
    "useCase": "general",
    "tier": "standard",
    "thinking": "medium",
}

USE_CASES = [
    {"label": "Chat & reasoning", "key": "general", "promptSetup": True},
    {"label": "Pure reasoning", "key": "reasoning", "promptSetup": True},
    {"label": "Coding", "key": "coding", "promptSetup": True},
    {"label": "Search", "key": "search"},
    {"label": "Deep research", "key": "deep", "promptSetup": True},
    {"label": "Computer agents", "key": "computer"},
    {"label": "Voice & audio", "key": "voice", "promptSetup": True},
    {"label": "Audio chat", "key": "audio", "promptSetup": True},
    {"label": "Transcription", "key": "transcription"},
    {"label": "Text-to-speech", "key": "tts"},
    {"label": "Image generation", "key": "image"},
    {"label": "Video generation", "key": "video"},
    {"label": "Embeddings", "key": "embeddings"},
]

TIERS = [
    {"label": " Premium", "key": "premium"},
    {"label": " Standard", "key": "standard"},
    {"label": " Budget", "key": "budget"},
    {"label": " Cheapest", "key": "cheapest"},
]

MODEL_MAP = {
    "general": {
        "premium": ["gpt-5.5-pro", "gpt-5.4-pro", "gpt-5.2-pro", "gpt-5-pro"],
        "standard": ["gpt-5.5", "gpt-5.4", "gpt-5.2", "gpt-5.1", "gpt-5"],
        "budget": ["gpt-5.4-mini", "gpt-5-mini"],
        "cheapest": ["gpt-5.4-nano", "gpt-5-nano", "gpt-4.1-nano", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "reasoning": {
        "premium": ["o3-pro", "gpt-5.5-pro", "gpt-5.4-pro", "gpt-5.2-pro", "gpt-5-pro"],
        "standard": ["o3", "gpt-5.5", "gpt-5.4", "gpt-5.3-chat-latest", "gpt-5.2", "gpt-5.1", "gpt-5"],
        "budget": ["o4-mini", "o3-mini", "gpt-5.4-mini", "gpt-5-mini"],
        "cheapest": ["gpt-5.4-nano", "gpt-5-nano", "gpt-4.1-nano", "gpt-4-turbo", "gpt-3.5-turbo", "o3-mini", "o4-mini"],
    },
    "coding": {
        "premium": ["gpt-5.1-codex-max"],
        "standard": ["gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.1-codex", "gpt-5-codex"],
        "budget": ["gpt-5.1-codex-mini"],
        "cheapest": ["gpt-4.1-nano", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-5.1-codex-mini"],
    },
    "search": {
        "premium": ["gpt-5-search-api"],
        "standard": ["gpt-4o-search-preview"],
        "budget": ["gpt-4o-mini-search-preview"],
        "cheapest": ["gpt-4o-mini-search-preview"],
    },
    "deep": {
        "premium": ["o3-deep-research"],
        "standard": ["o3-deep-research"],
        "budget": ["o4-mini-deep-research"],
        "cheapest": ["o4-mini-deep-research"],
    },
    "computer": {
        "premium": ["gpt-5.5-pro", "gpt-5.4-pro", "computer-use-preview"],
        "standard": ["gpt-5.5", "gpt-5.4", "gpt-5.3-chat-latest", "gpt-5.2", "gpt-5.1", "gpt-5", "computer-use-preview"],
        "budget": ["gpt-5.4-mini", "gpt-5-mini"],
        "cheapest": ["gpt-5.4-nano", "gpt-5-nano", "gpt-4.1-nano", "gpt-4-turbo"],
    },
    "voice": {
        "premium": ["gpt-realtime"],
        "standard": ["gpt-realtime-1.5"],
        "budget": ["gpt-realtime-mini"],
        "cheapest": ["gpt-realtime-mini"],
    },
    "audio": {
        "premium": ["gpt-audio"],
        "standard": ["gpt-audio-1.5"],
        "budget": ["gpt-audio-mini"],
        "cheapest": ["gpt-audio-mini"],
    },
    "transcription": {
        "premium": ["gpt-4o-transcribe"],
        "standard": ["gpt-4o-transcribe"],
        "budget": ["gpt-4o-mini-transcribe"],
        "cheapest": ["whisper-1"],
    },
    "tts": {
        "premium": ["tts-1-hd"],
        "standard": ["tts-1"],
        "budget": ["gpt-4o-mini-tts"],
        "cheapest": ["gpt-4o-mini-tts"],
    },
    "image": {
        "premium": ["gpt-image-2"],
        "standard": ["gpt-image-1.5", "gpt-image-1"],
        "budget": ["gpt-image-1-mini"],
        "cheapest": ["gpt-image-1-mini"],
    },
    "video": {
        "premium": ["sora-2-pro"],
        "standard": ["sora-2"],
        "budget": ["sora-2"],
        "cheapest": ["sora-2"],
    },
    "embeddings": {
        "premium": ["text-embedding-3-large"],
        "standard": ["text-embedding-3-large"],
        "budget": ["text-embedding-3-small"],
        "cheapest": ["text-embedding-ada-002"],
    },
}

LEGACY_TTS_VOICES = [
    "alloy",
    "ash",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
]

MODERN_TTS_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
]

REALTIME_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
]

AUDIO_OUTPUT_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "marin",
    "cedar",
]

MODEL_METADATA = {
    "gpt-audio": {
        "contextWindow": 128_000,
        "inputPricePerMtok": 2.5,
        "outputPricePerMtok": 10.0,
        "audioInputPricePerMtok": 32.0,
        "audioOutputPricePerMtok": 64.0,
        "assistantVoices": AUDIO_OUTPUT_VOICES,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-audio",
    },
    "gpt-audio-1.5": {
        "contextWindow": 128_000,
        "inputPricePerMtok": 2.5,
        "outputPricePerMtok": 10.0,
        "audioInputPricePerMtok": 32.0,
        "audioOutputPricePerMtok": 64.0,
        "assistantVoices": AUDIO_OUTPUT_VOICES,
        "canonicalModelId": "gpt-audio",
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-audio-1.5",
    },
    "gpt-audio-mini": {
        "contextWindow": 128_000,
        "inputPricePerMtok": 0.6,
        "outputPricePerMtok": 2.4,
        "audioInputPricePerMtok": 10.0,
        "audioOutputPricePerMtok": 20.0,
        "assistantVoices": AUDIO_OUTPUT_VOICES,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-audio-mini",
    },
    "gpt-realtime": {
        "contextWindow": 32_000,
        "inputPricePerMtok": 4.0,
        "cachedInputPricePerMtok": 0.4,
        "outputPricePerMtok": 16.0,
        "audioInputPricePerMtok": 32.0,
        "audioCachedInputPricePerMtok": 0.4,
        "audioOutputPricePerMtok": 64.0,
        "imageInputPricePerMtok": 5.0,
        "imageCachedInputPricePerMtok": 0.5,
        "assistantVoices": REALTIME_VOICES,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-realtime",
    },
    "gpt-realtime-1.5": {
        "contextWindow": 32_000,
        "inputPricePerMtok": 4.0,
        "cachedInputPricePerMtok": 0.4,
        "outputPricePerMtok": 16.0,
        "audioInputPricePerMtok": 32.0,
        "audioCachedInputPricePerMtok": 0.4,
        "audioOutputPricePerMtok": 64.0,
        "imageInputPricePerMtok": 5.0,
        "imageCachedInputPricePerMtok": 0.5,
        "assistantVoices": REALTIME_VOICES,
        "canonicalModelId": "gpt-realtime",
        "sourceUrl": "https://openai.com/api/pricing/",
    },
    "gpt-realtime-mini": {
        "contextWindow": 32_000,
        "inputPricePerMtok": 0.6,
        "cachedInputPricePerMtok": 0.06,
        "outputPricePerMtok": 2.4,
        "audioInputPricePerMtok": 10.0,
        "audioCachedInputPricePerMtok": 0.3,
        "audioOutputPricePerMtok": 20.0,
        "imageInputPricePerMtok": 0.8,
        "imageCachedInputPricePerMtok": 0.08,
        "assistantVoices": REALTIME_VOICES,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-realtime-mini",
    },
    "gpt-4o-transcribe": {
        "contextWindow": 16_000,
        "inputPricePerMtok": 2.5,
        "outputPricePerMtok": 10.0,
        "audioInputPricePerMtok": 6.0,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4o-transcribe",
    },
    "gpt-4o-mini-transcribe": {
        "contextWindow": 16_000,
        "inputPricePerMtok": 1.25,
        "outputPricePerMtok": 5.0,
        "audioInputPricePerMtok": 3.0,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4o-mini-transcribe",
    },
    "whisper-1": {
        "contextWindow": 0,
        "inputPricePerMtok": 0.006,
        "outputPricePerMtok": 0.0,
        "audioInputPricePerMtok": 0.006,
        "sourceUrl": "https://developers.openai.com/api/docs/models/whisper-1",
    },
    "tts-1": {
        "contextWindow": 0,
        "inputPricePerMtok": 0.0,
        "outputPricePerMtok": 0.0,
        "speechGenerationPricePerMchar": 15.0,
        "ttsVoices": LEGACY_TTS_VOICES,
        "sourceUrl": "https://platform.openai.com/docs/models/tts-1",
    },
    "tts-1-hd": {
        "contextWindow": 0,
        "inputPricePerMtok": 0.0,
        "outputPricePerMtok": 0.0,
        "speechGenerationPricePerMchar": 30.0,
        "ttsVoices": LEGACY_TTS_VOICES,
        "sourceUrl": "https://platform.openai.com/docs/models/tts-1-hd",
    },
    "gpt-4o-mini-tts": {
        "contextWindow": 2_000,
        "inputPricePerMtok": 0.6,
        "outputPricePerMtok": 0.0,
        "audioOutputPricePerMtok": 12.0,
        "ttsVoices": MODERN_TTS_VOICES,
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4o-mini-tts",
    },
    "gpt-5.5-pro": {"contextWindow": 1_050_000, "inputPricePerMtok": 30.0, "cachedInputPricePerMtok": 3.0, "outputPricePerMtok": 180.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.5-pro"},
    "gpt-5.5": {"contextWindow": 1_000_000, "inputPricePerMtok": 5.0, "cachedInputPricePerMtok": 0.5, "outputPricePerMtok": 30.0, "sourceUrl": "https://developers.openai.com/api/docs/models"},
    "gpt-5.4-pro": {"contextWindow": 1_050_000, "inputPricePerMtok": 30.0, "cachedInputPricePerMtok": 3.0, "outputPricePerMtok": 180.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.4-pro"},
    "gpt-5.4": {"contextWindow": 1_050_000, "inputPricePerMtok": 2.5, "cachedInputPricePerMtok": 0.25, "outputPricePerMtok": 15.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.4"},
    "gpt-5.4-mini": {"contextWindow": 400_000, "inputPricePerMtok": 0.75, "cachedInputPricePerMtok": 0.075, "outputPricePerMtok": 4.5, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.4-mini"},
    "gpt-5.4-nano": {"contextWindow": 400_000, "inputPricePerMtok": 0.2, "cachedInputPricePerMtok": 0.02, "outputPricePerMtok": 1.25, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.4-nano"},
    "gpt-5": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "cachedInputPricePerMtok": 0.125, "outputPricePerMtok": 10.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5-pro": {"contextWindow": 400_000, "inputPricePerMtok": 15.0, "cachedInputPricePerMtok": 1.5, "outputPricePerMtok": 120.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5-pro"},
    "gpt-5-mini": {"contextWindow": 400_000, "inputPricePerMtok": 0.25, "cachedInputPricePerMtok": 0.025, "outputPricePerMtok": 2.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5-mini"},
    "gpt-5-nano": {"contextWindow": 400_000, "inputPricePerMtok": 0.05, "cachedInputPricePerMtok": 0.005, "outputPricePerMtok": 0.4, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5-nano"},
    "gpt-5-chat-latest": {"contextWindow": 128_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5.1": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5.1-chat-latest": {"contextWindow": 128_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5.2": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5.2-pro": {"contextWindow": 400_000, "inputPricePerMtok": 15.0, "outputPricePerMtok": 120.0, "canonicalModelId": "gpt-5-pro", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5-pro"},
    "gpt-5.2-chat-latest": {"contextWindow": 128_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5.3-chat-latest": {"contextWindow": 128_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-5.3-codex": {"contextWindow": 400_000, "inputPricePerMtok": 1.75, "outputPricePerMtok": 14.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.3-codex"},
    "gpt-5.2-codex": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5.1-codex", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.1-codex"},
    "gpt-5-codex": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5.1-codex", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.1-codex"},
    "gpt-5.1-codex-max": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.1-codex-max"},
    "gpt-5.1-codex": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.1-codex"},
    "gpt-5.1-codex-mini": {"contextWindow": 400_000, "inputPricePerMtok": 0.25, "outputPricePerMtok": 2.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.1-codex-mini"},
    "gpt-5-search-api": {"contextWindow": 400_000, "inputPricePerMtok": 1.25, "outputPricePerMtok": 10.0, "canonicalModelId": "gpt-5", "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5"},
    "gpt-4o-search-preview": {"contextWindow": 128_000, "inputPricePerMtok": 2.5, "outputPricePerMtok": 10.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4o-search-preview"},
    "gpt-4o-mini-search-preview": {"contextWindow": 128_000, "inputPricePerMtok": 0.15, "outputPricePerMtok": 0.6, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4o-mini-search-preview"},
    "gpt-4-turbo": {"contextWindow": 128_000, "inputPricePerMtok": 10.0, "outputPricePerMtok": 30.0, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4-turbo"},
    "gpt-3.5-turbo": {"contextWindow": 16_385, "inputPricePerMtok": 0.5, "outputPricePerMtok": 1.5, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-3-5-turbo"},
    "gpt-4.1-nano": {"contextWindow": 128_000, "inputPricePerMtok": 0.1, "outputPricePerMtok": 0.4, "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-4.1-nano"},
    "o3-pro": {"contextWindow": 200_000, "inputPricePerMtok": 20.0, "outputPricePerMtok": 80.0, "sourceUrl": "https://developers.openai.com/api/docs/models/o3-pro"},
    "o3": {"contextWindow": 200_000, "inputPricePerMtok": 2.0, "outputPricePerMtok": 8.0, "sourceUrl": "https://developers.openai.com/api/docs/models/o3"},
    "o4-mini": {"contextWindow": 200_000, "inputPricePerMtok": 1.1, "outputPricePerMtok": 4.4, "sourceUrl": "https://developers.openai.com/api/docs/models/o4-mini"},
    "o3-mini": {"contextWindow": 200_000, "inputPricePerMtok": 1.1, "outputPricePerMtok": 4.4, "sourceUrl": "https://developers.openai.com/api/docs/models/o3-mini"},
    "o3-deep-research": {"contextWindow": 200_000, "inputPricePerMtok": 10.0, "outputPricePerMtok": 40.0, "sourceUrl": "https://developers.openai.com/api/docs/models/o3-deep-research"},
    "o4-mini-deep-research": {"contextWindow": 200_000, "inputPricePerMtok": 2.0, "outputPricePerMtok": 8.0, "sourceUrl": "https://developers.openai.com/api/docs/models/o4-mini-deep-research"},
    "computer-use-preview": {"contextWindow": 8_192, "inputPricePerMtok": 3.0, "outputPricePerMtok": 12.0, "sourceUrl": "https://developers.openai.com/api/docs/models/computer-use-preview"},
    "text-embedding-3-large": {"contextWindow": 8_192, "inputPricePerMtok": 0.13, "outputPricePerMtok": 0.0, "sourceUrl": "https://developers.openai.com/api/docs/models/text-embedding-3-large"},
    "text-embedding-3-small": {"contextWindow": 8_192, "inputPricePerMtok": 0.02, "outputPricePerMtok": 0.0, "sourceUrl": "https://developers.openai.com/api/docs/models/text-embedding-3-small"},
    "text-embedding-ada-002": {"contextWindow": 8_192, "inputPricePerMtok": 0.1, "outputPricePerMtok": 0.0, "sourceUrl": "https://developers.openai.com/api/docs/models/text-embedding-ada-002"},
}

# Developer label fragments (xor+base64 encoded, assembled server-side)
DEV_NAME_FRAGMENT_BETA = "WUgJ"
DEV_NAME_KEY_BETA = 41

THINKING_POLICY = {
    "enabledUseCases": ["general", "reasoning"],
    "defaultLevels": [
        {"key": "none", "label": "None"},
        {"key": "low", "label": "Low"},
        {"key": "medium", "label": "Medium"},
        {"key": "high", "label": "High"},
    ],
    "overridesByModelPrefix": {
        "gpt-5.5": [
            {"key": "medium", "label": "Medium"},
            {"key": "high", "label": "High"},
            {"key": "xhigh", "label": "Extra High"},
        ],
    },
}

REASONING_EFFORT_MODEL_PREFIXES = ["o1", "o3", "o3-mini", "o4-mini"]
RESPONSES_API_MODEL_PREFIXES = ["gpt-5", "o3-pro", "o3-deep-research", "o4-mini-deep-research"]

# Source: OpenAI API pricing docs (developers.openai.com/api/docs/pricing), captured 2026-05-08.
SERVICE_TIER_TEXT_PRICING = {
    "gpt-5.5": {
        "standard": {"inputPricePerMtok": 5.0, "cachedInputPricePerMtok": 0.5, "outputPricePerMtok": 30.0},
        "flex": {"inputPricePerMtok": 2.5, "cachedInputPricePerMtok": 0.25, "outputPricePerMtok": 15.0},
        "priority": {"inputPricePerMtok": 12.5, "cachedInputPricePerMtok": 1.25, "outputPricePerMtok": 75.0},
    },
    "gpt-5.5-pro": {
        "standard": {"inputPricePerMtok": 30.0, "cachedInputPricePerMtok": 3.0, "outputPricePerMtok": 180.0},
        "flex": {"inputPricePerMtok": 15.0, "cachedInputPricePerMtok": 1.5, "outputPricePerMtok": 90.0},
    },
    "gpt-5.4": {
        "standard": {"inputPricePerMtok": 2.5, "cachedInputPricePerMtok": 0.25, "outputPricePerMtok": 15.0},
        "flex": {"inputPricePerMtok": 1.25, "cachedInputPricePerMtok": 0.13, "outputPricePerMtok": 7.5},
        "priority": {"inputPricePerMtok": 5.0, "cachedInputPricePerMtok": 0.5, "outputPricePerMtok": 30.0},
    },
    "gpt-5.4-mini": {
        "standard": {"inputPricePerMtok": 0.75, "cachedInputPricePerMtok": 0.075, "outputPricePerMtok": 4.5},
        "flex": {"inputPricePerMtok": 0.375, "cachedInputPricePerMtok": 0.0375, "outputPricePerMtok": 2.25},
        "priority": {"inputPricePerMtok": 1.5, "cachedInputPricePerMtok": 0.15, "outputPricePerMtok": 9.0},
    },
    "gpt-5.4-nano": {
        "standard": {"inputPricePerMtok": 0.2, "cachedInputPricePerMtok": 0.02, "outputPricePerMtok": 1.25},
        "flex": {"inputPricePerMtok": 0.1, "cachedInputPricePerMtok": 0.01, "outputPricePerMtok": 0.625},
    },
    "gpt-5.4-pro": {
        "standard": {"inputPricePerMtok": 30.0, "cachedInputPricePerMtok": 3.0, "outputPricePerMtok": 180.0},
        "flex": {"inputPricePerMtok": 15.0, "cachedInputPricePerMtok": 1.5, "outputPricePerMtok": 90.0},
    },
}

SUPPORTED_SERVICE_TIERS = {"default", "flex", "priority"}


def _model_metadata_for_service_tier(service_tier: str | None = None) -> dict:
    tier = normalize_service_tier(service_tier)
    if tier == "default":
        return MODEL_METADATA

    adjusted: dict[str, dict] = {}
    for model_id, meta in MODEL_METADATA.items():
        merged = dict(meta)
        tier_pricing = pricing_for_model(model_id, service_tier=tier)
        if tier_pricing:
            merged["inputPricePerMtok"] = float(tier_pricing.get("input") or 0.0)
            merged["cachedInputPricePerMtok"] = float(tier_pricing.get("cached_input") or 0.0)
            merged["outputPricePerMtok"] = float(tier_pricing.get("output") or 0.0)
            merged["audioInputPricePerMtok"] = float(tier_pricing.get("audio_input") or 0.0)
            merged["audioCachedInputPricePerMtok"] = float(tier_pricing.get("audio_cached_input") or 0.0)
            merged["audioOutputPricePerMtok"] = float(tier_pricing.get("audio_output") or 0.0)
            merged["imageInputPricePerMtok"] = float(tier_pricing.get("image_input") or 0.0)
            merged["imageCachedInputPricePerMtok"] = float(tier_pricing.get("image_cached_input") or 0.0)
        adjusted[model_id] = merged
    return adjusted


def get_model_catalog_payload(service_tier: str | None = None) -> dict:
    normalized_tier = normalize_service_tier(service_tier)
    return {
        "useCases": USE_CASES,
        "tiers": TIERS,
        "modelMap": MODEL_MAP,
        "modelMetadata": _model_metadata_for_service_tier(normalized_tier),
        "serviceTierTextPricing": SERVICE_TIER_TEXT_PRICING,
        "defaults": DEFAULTS,
        "thinkingPolicy": THINKING_POLICY,
        "effectiveServiceTier": normalized_tier,
    }


def use_case_keys() -> set[str]:
    return {str(item.get("key") or "").strip() for item in USE_CASES if str(item.get("key") or "").strip()}


def normalize_service_tier(service_tier: str | None) -> str:
    normalized = str(service_tier or "").strip().lower()
    if normalized in SUPPORTED_SERVICE_TIERS:
        return normalized
    return "default"


def _resolve_model_meta(model: str | None) -> dict | None:
    model_value = str(model or "").strip()
    if not model_value:
        return None
    direct = MODEL_METADATA.get(model_value)
    if direct:
        canonical = direct.get("canonicalModelId")
        if isinstance(canonical, str) and canonical in MODEL_METADATA:
            return MODEL_METADATA[canonical]
        return direct
    for key, meta in MODEL_METADATA.items():
        if model_value.startswith(key):
            canonical = meta.get("canonicalModelId")
            if isinstance(canonical, str) and canonical in MODEL_METADATA:
                return MODEL_METADATA[canonical]
            return meta
    return None


def _resolve_service_tier_pricing(model: str | None) -> dict | None:
    model_value = str(model or "").strip()
    if not model_value:
        return None
    direct = SERVICE_TIER_TEXT_PRICING.get(model_value)
    if direct:
        return direct
    meta = MODEL_METADATA.get(model_value)
    canonical = str(meta.get("canonicalModelId") or "").strip() if isinstance(meta, dict) else ""
    if canonical and canonical in SERVICE_TIER_TEXT_PRICING:
        return SERVICE_TIER_TEXT_PRICING[canonical]
    for key, tiers in SERVICE_TIER_TEXT_PRICING.items():
        if model_value.startswith(key):
            return tiers
    return None


def model_supports_priority_service_tier(model: str | None) -> bool:
    tiers = _resolve_service_tier_pricing(model)
    return isinstance(tiers, dict) and isinstance(tiers.get("priority"), dict)


def model_supports_flex_service_tier(model: str | None) -> bool:
    tiers = _resolve_service_tier_pricing(model)
    return isinstance(tiers, dict) and isinstance(tiers.get("flex"), dict)


def pricing_for_model(model: str, service_tier: str | None = None) -> dict[str, float | str] | None:
    meta = _resolve_model_meta(model)
    if not meta:
        return None
    tier = normalize_service_tier(service_tier)
    tier_pricing = _resolve_service_tier_pricing(model)
    override = None
    if isinstance(tier_pricing, dict):
        if tier == "priority":
            override = tier_pricing.get("priority") or tier_pricing.get("standard")
        elif tier == "flex":
            override = tier_pricing.get("flex") or tier_pricing.get("standard")
        else:
            override = tier_pricing.get("standard")
    pricing_meta = dict(meta)
    if isinstance(override, dict):
        pricing_meta.update(override)
    return {
        "input": float(pricing_meta.get("inputPricePerMtok") or 0.0),
        "cached_input": float(pricing_meta.get("cachedInputPricePerMtok") or 0.0),
        "output": float(pricing_meta.get("outputPricePerMtok") or 0.0),
        "audio_input": float(pricing_meta.get("audioInputPricePerMtok") or 0.0),
        "audio_cached_input": float(pricing_meta.get("audioCachedInputPricePerMtok") or 0.0),
        "audio_output": float(pricing_meta.get("audioOutputPricePerMtok") or 0.0),
        "image_input": float(pricing_meta.get("imageInputPricePerMtok") or 0.0),
        "image_cached_input": float(pricing_meta.get("imageCachedInputPricePerMtok") or 0.0),
    }


def context_window_for_model(model: str) -> int | None:
    if not model:
        return None
    if model in MODEL_METADATA:
        return int(MODEL_METADATA[model].get("contextWindow") or 0) or None
    for key, meta in MODEL_METADATA.items():
        if model.startswith(key):
            return int(meta.get("contextWindow") or 0) or None
    return None


def model_supports_reasoning_effort(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in REASONING_EFFORT_MODEL_PREFIXES)


def model_uses_responses_api(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in RESPONSES_API_MODEL_PREFIXES)
