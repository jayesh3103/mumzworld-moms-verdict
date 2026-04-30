"""Configuration for OpenRouter API and model selection."""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API settings
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Primary: GPT-OSS 120B has better uptime currently
PRIMARY_MODEL = "openai/gpt-oss-120b:free"
# Fallback: openrouter/free automatically routes to available high-quality free models
FALLBACK_MODEL = "openrouter/free"

# Pipeline settings
MAX_RETRIES = 2  # Retry on schema validation failure
MIN_REVIEWS_FOR_VERDICT = 3  # Below this, return InsufficientDataVerdict
TEMPERATURE = 0.3  # Low temp for consistent structured output
MAX_TOKENS = 4096

# Confidence thresholds
CONFIDENCE_HIGH = 0.8   # 10+ reviews with good agreement
CONFIDENCE_MEDIUM = 0.5  # 5-9 reviews or mixed sentiment
CONFIDENCE_LOW = 0.3    # 3-4 reviews or very conflicting

# Server settings
HOST = "0.0.0.0"
PORT = 8000
CORS_ORIGINS = ["*"]
