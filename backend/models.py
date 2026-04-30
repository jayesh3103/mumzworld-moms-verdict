"""Pydantic models for Moms Verdict structured output.

Every field is strictly typed and validated. The LLM output must conform to
these schemas or the pipeline will reject and retry. Empty strings and null
values in required fields are treated as validation failures, not silent passes.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SafetyFlag(BaseModel):
    """A safety concern extracted from reviews. Must cite actual review content."""
    issue_en: str = Field(..., min_length=5, description="Safety issue in English")
    issue_ar: str = Field(..., min_length=3, description="Safety issue in Arabic")
    severity: Severity = Field(..., description="Severity: low, medium, high")
    source_quote: str = Field(..., min_length=5, description="Direct quote from the review that raised this concern")

    @field_validator("issue_en", "issue_ar", "source_quote")
    @classmethod
    def no_empty_or_placeholder(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or stripped in ("N/A", "n/a", "-", "None", "null"):
            raise ValueError("Field must contain meaningful content, not placeholders")
        return stripped


class ReviewVerdict(BaseModel):
    """The structured verdict synthesized from product reviews."""
    product_id: str = Field(..., description="Product ID this verdict is for")
    product_name_en: str = Field(..., min_length=2)
    product_name_ar: str = Field(..., min_length=2)
    review_count: int = Field(..., ge=0, description="Number of reviews analyzed")
    overall_score: float = Field(..., ge=1.0, le=5.0, description="Overall score 1-5")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in verdict 0-1")
    confidence_reasoning: str = Field(..., min_length=10, description="Why confidence is at this level")

    summary_en: str = Field(..., min_length=20, description="Overall summary in English")
    summary_ar: str = Field(..., min_length=10, description="Overall summary in Arabic")

    pros_en: list[str] = Field(default_factory=list, description="Pros in English")
    pros_ar: list[str] = Field(default_factory=list, description="Pros in Arabic")
    cons_en: list[str] = Field(default_factory=list, description="Cons in English")
    cons_ar: list[str] = Field(default_factory=list, description="Cons in Arabic")

    verdict_en: str = Field(..., min_length=10, description="Final verdict in English")
    verdict_ar: str = Field(..., min_length=5, description="Final verdict in Arabic")

    value_for_money: Optional[float] = Field(None, ge=1.0, le=5.0, description="Value for money score")
    age_suitability_en: Optional[str] = Field(None, description="Age suitability notes in English")
    age_suitability_ar: Optional[str] = Field(None, description="Age suitability notes in Arabic")

    safety_flags: list[SafetyFlag] = Field(default_factory=list, description="Safety concerns found in reviews")

    @field_validator("summary_en", "verdict_en")
    @classmethod
    def english_not_placeholder(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or stripped in ("N/A", "-", "None"):
            raise ValueError("English content must be meaningful")
        return stripped

    @field_validator("summary_ar", "verdict_ar")
    @classmethod
    def arabic_not_placeholder(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or stripped in ("N/A", "-", "None"):
            raise ValueError("Arabic content must be meaningful")
        return stripped


class InsufficientDataVerdict(BaseModel):
    """Returned when there aren't enough reviews to form a reliable verdict."""
    product_id: str
    product_name_en: str
    product_name_ar: str
    review_count: int = Field(..., ge=0)
    reason_en: str = Field(..., min_length=10)
    reason_ar: str = Field(..., min_length=5)
    available_reviews: list[dict] = Field(default_factory=list, description="Raw reviews if any exist")


class VerdictRequest(BaseModel):
    """API request to generate a verdict."""
    product_id: str = Field(..., min_length=1)


class VerdictResponse(BaseModel):
    """API response wrapper."""
    success: bool
    verdict: Optional[ReviewVerdict] = None
    insufficient_data: Optional[InsufficientDataVerdict] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
    processing_time_ms: Optional[int] = None

# --- Multi-Agent Intermediate Schemas ---

class SafetyExtractionResult(BaseModel):
    """Step 1: Safety & Filter Agent output."""
    has_safety_concerns: bool
    safety_flags_en: list[dict] = Field(default_factory=list, description="List of safety concerns in English with 'issue' and 'source_quote' and 'severity'")
    valid_review_ids: list[str] = Field(..., description="List of review IDs that are on-topic and valid to analyze")
    excluded_review_ids: list[str] = Field(default_factory=list, description="List of review IDs excluded (spam, off-topic)")

class EnglishSynthesisResult(BaseModel):
    """Step 2: English Synthesis Agent output."""
    overall_score: float = Field(..., ge=1.0, le=5.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_reasoning: str = Field(..., min_length=10)
    summary_en: str = Field(..., min_length=20)
    pros_en: list[str] = Field(default_factory=list)
    cons_en: list[str] = Field(default_factory=list)
    verdict_en: str = Field(..., min_length=10)
    value_for_money: Optional[float] = None
    age_suitability_en: Optional[str] = None

class ArabicLocalizationResult(BaseModel):
    """Step 3: Arabic Localization Agent output."""
    summary_ar: str = Field(..., min_length=10)
    pros_ar: list[str] = Field(default_factory=list)
    cons_ar: list[str] = Field(default_factory=list)
    verdict_ar: str = Field(..., min_length=5)
    age_suitability_ar: Optional[str] = None
    safety_flags_ar: list[dict] = Field(default_factory=list, description="List of dictionaries with 'issue_ar' matching the English safety flags")

class EvaluationResult(BaseModel):
    """Step 4: Evaluator Agent output."""
    passed: bool = Field(..., description="True if the synthesis is 100% grounded and safe")
    reason: str = Field(..., description="Explanation of why it passed or failed")
