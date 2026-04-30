"""Multi-step AI pipeline for generating product review verdicts.

Pipeline steps:
1. Load & preprocess reviews for the requested product
2. Check if sufficient data exists (≥3 reviews)
3. Agent 1: Safety & Filter - identify spam and extract safety flags
4. Agent 2: Synthesis - Chain-of-Thought reasoning to build English verdict
5. Agent 3: Localization - Natively translate to Arabic
6. Agent 4: Evaluator - Check for hallucinations (retry Agent 2 if fails)
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
import re
from typing import Optional

import httpx

from backend.config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    PRIMARY_MODEL, FALLBACK_MODEL,
    MAX_RETRIES, MIN_REVIEWS_FOR_VERDICT,
    TEMPERATURE, MAX_TOKENS,
)
from backend.models import (
    ReviewVerdict, InsufficientDataVerdict,
    VerdictResponse, SafetyExtractionResult,
    EnglishSynthesisResult, ArabicLocalizationResult,
    EvaluationResult, SafetyFlag
)
from backend.prompts import (
    SYSTEM_PROMPT, 
    AGENT_1_SAFETY_FILTER_PROMPT,
    AGENT_2_SYNTHESIS_PROMPT,
    AGENT_3_LOCALIZATION_PROMPT,
    AGENT_4_EVALUATOR_PROMPT,
    INSUFFICIENT_DATA_TEMPLATE,
)

logger = logging.getLogger(__name__)


def load_data() -> tuple[list[dict], list[dict]]:
    import pathlib
    data_dir = pathlib.Path(__file__).parent.parent / "data"
    with open(data_dir / "products.json", "r", encoding="utf-8") as f:
        products = json.load(f)
    with open(data_dir / "reviews.json", "r", encoding="utf-8") as f:
        reviews = json.load(f)
    return products, reviews


def get_product(product_id: str, products: list[dict]) -> Optional[dict]:
    for p in products:
        if p["id"] == product_id:
            return p
    return None


def get_reviews_for_product(product_id: str, reviews: list[dict]) -> list[dict]:
    return [r for r in reviews if r["product_id"] == product_id]


def format_reviews_for_llm(reviews: list[dict]) -> str:
    if not reviews:
        return "(No reviews available)"
    lines = []
    for i, r in enumerate(reviews, 1):
        lang_tag = f"[{r.get('language', 'en').upper()}]"
        stars = "★" * r.get("rating", 0) + "☆" * (5 - r.get("rating", 0))
        lines.append(f"Review {r['id']} {lang_tag} {stars} ({r.get('rating', '?')}/5):")
        lines.append(f"  \"{r['text']}\"")
        lines.append("")
    return "\n".join(lines)


def extract_json_from_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:200]}...")


async def call_openrouter(prompt: str, model: str = PRIMARY_MODEL, temperature: float = TEMPERATURE) -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/jayesh3103/mumzworld-moms-verdict",
        "X-Title": "Moms Verdict ML",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": MAX_TOKENS,
    }

    max_api_retries = 3
    async with httpx.AsyncClient(timeout=90.0) as client:
        for api_attempt in range(max_api_retries):
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            elif response.status_code in (429, 502, 503) and api_attempt < max_api_retries - 1:
                wait_time = (api_attempt + 1) * 10  # 10s, 20s backoff
                logger.warning(f"API returned {response.status_code}, retrying in {wait_time}s (attempt {api_attempt + 1}/{max_api_retries})...")
                await asyncio.sleep(wait_time)
            else:
                raise httpx.HTTPStatusError(
                    f"OpenRouter returned {response.status_code}: {response.text}",
                    request=response.request,
                    response=response,
                )


async def generate_verdict(product_id: str) -> VerdictResponse:
    start_time = time.time()
    products, reviews = load_data()
    product = get_product(product_id, products)
    if not product:
        return VerdictResponse(success=False, error=f"Product '{product_id}' not found")

    product_reviews = get_reviews_for_product(product_id, reviews)
    if len(product_reviews) < MIN_REVIEWS_FOR_VERDICT:
        return await _handle_insufficient_data(product, product_reviews, start_time)

    model_used = PRIMARY_MODEL
    last_error = None

    try:
        # AGENT 1: Safety & Filter
        logger.info("Running Agent 1: Safety & Filter")
        all_reviews_text = format_reviews_for_llm(product_reviews)
        safety_prompt = AGENT_1_SAFETY_FILTER_PROMPT.format(
            product_name=product["name_en"],
            reviews_text=all_reviews_text
        )
        safety_response = await call_openrouter(safety_prompt, temperature=0.1)
        safety_data = extract_json_from_response(safety_response)
        safety_result = SafetyExtractionResult(**safety_data)

        # Filter reviews for next agent
        valid_reviews = [r for r in product_reviews if r["id"] in safety_result.valid_review_ids]
        if len(valid_reviews) < MIN_REVIEWS_FOR_VERDICT:
            return await _handle_insufficient_data(product, valid_reviews, start_time)

        valid_reviews_text = format_reviews_for_llm(valid_reviews)

        # Self-Correction Loop for Synthesis
        english_result = None
        evaluator_feedback_text = ""  # No feedback on first attempt
        for attempt in range(MAX_RETRIES + 1):
            try:
                # AGENT 2: Synthesis
                logger.info(f"Running Agent 2: Synthesis (Attempt {attempt+1})")
                synthesis_prompt = AGENT_2_SYNTHESIS_PROMPT.format(
                    product_name=product["name_en"],
                    price_aed=product["price_aed"],
                    age_range=product["age_range"],
                    valid_reviews_text=valid_reviews_text,
                    evaluator_feedback=evaluator_feedback_text
                )
                synthesis_response = await call_openrouter(synthesis_prompt, temperature=0.3)
                synthesis_data = extract_json_from_response(synthesis_response)
                temp_english = EnglishSynthesisResult(**synthesis_data)

                # AGENT 4: Evaluator
                logger.info("Running Agent 4: Evaluator")
                evaluator_prompt = AGENT_4_EVALUATOR_PROMPT.format(
                    reviews_text=valid_reviews_text,
                    synthesis_json=json.dumps(synthesis_data, indent=2)
                )
                eval_response = await call_openrouter(evaluator_prompt, temperature=0.1)
                eval_data = extract_json_from_response(eval_response)
                eval_result = EvaluationResult(**eval_data)

                if eval_result.passed:
                    english_result = temp_english
                    break
                else:
                    logger.warning(f"Evaluator rejected synthesis: {eval_result.reason}")
                    last_error = f"Evaluator rejection: {eval_result.reason}"
                    # Feed rejection reason back to synthesis for self-correction
                    evaluator_feedback_text = (
                        f"⚠️ PREVIOUS ATTEMPT WAS REJECTED BY THE EVALUATOR.\n"
                        f"Rejection reason: {eval_result.reason}\n"
                        f"You MUST fix the issues identified above in this attempt. "
                        f"Do NOT repeat the same mistakes."
                    )
            except Exception as e:
                logger.warning(f"Synthesis step failed: {e}")
                last_error = str(e)

        if not english_result:
            raise ValueError(f"Failed to generate valid synthesis after retries. Last error: {last_error}")

        # AGENT 3: Localization
        logger.info("Running Agent 3: Localization")
        localization_prompt = AGENT_3_LOCALIZATION_PROMPT.format(
            english_json=english_result.model_dump_json(indent=2),
            safety_flags_en_json=json.dumps(safety_result.safety_flags_en, indent=2)
        )
        loc_response = await call_openrouter(localization_prompt, temperature=0.3)
        loc_data = extract_json_from_response(loc_response)
        arabic_result = ArabicLocalizationResult(**loc_data)

        # Assemble Final Verdict
        safety_flags = []
        for i, flag_en in enumerate(safety_result.safety_flags_en):
            issue_ar = flag_en["issue"]
            if i < len(arabic_result.safety_flags_ar):
                issue_ar = arabic_result.safety_flags_ar[i].get("issue_ar", flag_en["issue"])
            
            safety_flags.append(SafetyFlag(
                issue_en=flag_en["issue"],
                issue_ar=issue_ar,
                severity=flag_en["severity"],
                source_quote=flag_en["source_quote"]
            ))

        verdict = ReviewVerdict(
            product_id=product["id"],
            product_name_en=product["name_en"],
            product_name_ar=product["name_ar"],
            review_count=len(valid_reviews),
            overall_score=english_result.overall_score,
            confidence=english_result.confidence,
            confidence_reasoning=english_result.confidence_reasoning,
            summary_en=english_result.summary_en,
            summary_ar=arabic_result.summary_ar,
            pros_en=english_result.pros_en,
            pros_ar=arabic_result.pros_ar,
            cons_en=english_result.cons_en,
            cons_ar=arabic_result.cons_ar,
            verdict_en=english_result.verdict_en,
            verdict_ar=arabic_result.verdict_ar,
            value_for_money=english_result.value_for_money,
            age_suitability_en=english_result.age_suitability_en,
            age_suitability_ar=arabic_result.age_suitability_ar,
            safety_flags=safety_flags
        )

        elapsed_ms = int((time.time() - start_time) * 1000)
        return VerdictResponse(
            success=True,
            verdict=verdict,
            model_used="Multi-Agent Pipeline",
            processing_time_ms=elapsed_ms,
        )

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return VerdictResponse(
            success=False,
            error=str(e),
            model_used=model_used,
            processing_time_ms=elapsed_ms,
        )


async def _handle_insufficient_data(
    product: dict,
    reviews: list[dict],
    start_time: float,
) -> VerdictResponse:
    review_count = len(reviews)
    if review_count == 0:
        insufficient = InsufficientDataVerdict(
            product_id=product["id"],
            product_name_en=product["name_en"],
            product_name_ar=product["name_ar"],
            review_count=0,
            reason_en=f"No customer reviews are available for {product['name_en']}.",
            reason_ar=f"لا توجد تقييمات من العملاء لمنتج {product['name_ar']}.",
            available_reviews=[],
        )
        elapsed_ms = int((time.time() - start_time) * 1000)
        return VerdictResponse(success=True, insufficient_data=insufficient, processing_time_ms=elapsed_ms)

    reviews_text = format_reviews_for_llm(reviews)
    reviews_json = json.dumps(reviews, ensure_ascii=False)
    prompt = INSUFFICIENT_DATA_TEMPLATE.format(
        product_name_en=product["name_en"],
        product_name_ar=product["name_ar"],
        product_id=product["id"],
        review_count=review_count,
        reviews_text=reviews_text,
        reviews_json=reviews_json,
    )

    try:
        raw_response = await call_openrouter(prompt)
        parsed = extract_json_from_response(raw_response)
        insufficient = InsufficientDataVerdict(**parsed)
    except Exception:
        insufficient = InsufficientDataVerdict(
            product_id=product["id"],
            product_name_en=product["name_en"],
            product_name_ar=product["name_ar"],
            review_count=review_count,
            reason_en=f"Only {review_count} review(s) available.",
            reason_ar=f"يوجد فقط {review_count} تقييم(ات).",
            available_reviews=reviews,
        )

    elapsed_ms = int((time.time() - start_time) * 1000)
    return VerdictResponse(
        success=True,
        insufficient_data=insufficient,
        model_used=PRIMARY_MODEL,
        processing_time_ms=elapsed_ms,
    )
