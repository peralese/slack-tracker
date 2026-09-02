"""
llm_client.py — Configurable LLM provider abstraction.

Exposes two functions:
    score_relevance(text, config) -> tuple[float, str]
    summarize_document(text, config) -> str

Supported providers (set via config.yaml llm.provider):
    openai   — OpenAI-compatible REST API (also works with compatible endpoints)
    watsonx  — IBM watsonx.ai REST API
    ollama   — Local Ollama server (no API key required)
"""

from __future__ import annotations

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """You are a relevance scoring assistant.
The user is an {user_profile}.
Your job is to evaluate how relevant a given Slack message is to their professional interests.

Score GENEROUSLY — err on the side of inclusion. Use these guidelines:
- Score 8-10: Directly about AI, LLMs, agents, data, cloud, or IBM tools the user works with
- Score 6-8: Training sessions, workshops, or events about AI tools, IBM technology, or productivity for consultants — these are ALWAYS relevant even if not explicitly about the user's core topics
- Score 4-6: Announcements, case studies, or tools that could tangentially apply to the user's work
- Score 1-3: Loosely related or general IBM news
- Score 0: Completely unrelated (HR-only, social events, facilities, etc.)

IBM Consulting Advantage (ICA), Watson, watsonx, and any IBM AI tools are directly relevant to this user.
Any training or session about building AI agents, prompting, or AI workflows scores at least 7.

Respond ONLY with a JSON object in this exact format (no markdown, no extra text):
{{"score": <float 0.0-10.0>, "explanation": "<one sentence explaining why>"}}"""

_USER_PROMPT_TEMPLATE = """Rate the relevance of this Slack message to the user described above:

\"\"\"
{text}
\"\"\"

Respond with only the JSON object."""

_SUMMARY_SYSTEM_PROMPT_TEMPLATE = """You are a professional document summarizer assisting an {user_profile}.
Produce a concise 3-5 sentence summary of the document provided.
Focus on the key points most relevant to the user's role.
Respond with plain text only — no bullet points, no markdown, no headers."""

_SUMMARY_USER_PROMPT_TEMPLATE = """Please summarize the following document:

{text}"""

_SUMMARY_FALLBACK = "Summary unavailable — document attached but could not be processed."


def score_relevance(text: str, cfg: dict) -> tuple[float, str]:
    """Call the configured LLM provider and return (score, explanation).

    Falls back to (0.0, "LLM unavailable") on any error so ranking never
    blocks ingestion.
    """
    llm_cfg = cfg.get("llm", {})
    ranking_cfg = cfg.get("ranking", {})
    provider = llm_cfg.get("provider", "ollama").lower()
    model = llm_cfg.get("model", "llama3.2")
    base_url = llm_cfg.get("base_url", "").rstrip("/")
    user_profile = ranking_cfg.get("user_profile", "technical professional")
    api_key = os.environ.get("LLM_API_KEY", "")

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(user_profile=user_profile)
    user_prompt = _USER_PROMPT_TEMPLATE.format(text=text[:2000])  # cap input length

    try:
        if provider == "openai":
            return _call_openai(system_prompt, user_prompt, model, base_url, api_key)
        elif provider == "watsonx":
            return _call_watsonx(system_prompt, user_prompt, model, base_url, api_key)
        elif provider == "ollama":
            return _call_ollama(system_prompt, user_prompt, model, base_url)
        else:
            logger.error("Unknown LLM provider: %s", provider)
            return 0.0, "Unknown LLM provider"
    except Exception as exc:
        logger.error("LLM scoring failed (%s): %s", provider, exc)
        return 0.0, "LLM unavailable"


# ---------------------------------------------------------------------------
# Document summarization
# ---------------------------------------------------------------------------

def _truncate_to_words(text: str, max_words: int = 3000) -> str:
    """Truncate text to at most max_words words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def summarize_document(text: str, cfg: dict) -> str:
    """Send extracted document text to the configured LLM and return a summary string.

    Truncates input to 3,000 words. Returns _SUMMARY_FALLBACK on any error.
    """
    llm_cfg = cfg.get("llm", {})
    ranking_cfg = cfg.get("ranking", {})
    provider = llm_cfg.get("provider", "ollama").lower()
    model = llm_cfg.get("model", "llama3.2")
    base_url = llm_cfg.get("base_url", "").rstrip("/")
    user_profile = ranking_cfg.get("user_profile", "technical professional")
    api_key = os.environ.get("LLM_API_KEY", "")

    truncated = _truncate_to_words(text)
    system_prompt = _SUMMARY_SYSTEM_PROMPT_TEMPLATE.format(user_profile=user_profile)
    user_prompt = _SUMMARY_USER_PROMPT_TEMPLATE.format(text=truncated)

    try:
        if provider == "openai":
            return _call_openai_summary(system_prompt, user_prompt, model, base_url, api_key)
        elif provider == "watsonx":
            return _call_watsonx_summary(system_prompt, user_prompt, model, base_url, api_key)
        elif provider == "ollama":
            return _call_ollama_summary(system_prompt, user_prompt, model, base_url)
        else:
            logger.error("Unknown LLM provider: %s", provider)
            return _SUMMARY_FALLBACK
    except Exception as exc:
        logger.error("Document summarization failed (%s): %s", provider, exc)
        return _SUMMARY_FALLBACK


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _parse_response(content: str) -> tuple[float, str]:
    """Extract score and explanation from the LLM's JSON response."""
    # Strip markdown code fences if present
    content = re.sub(r"```(?:json)?", "", content).strip("`").strip()
    try:
        data = json.loads(content)
        score = float(data["score"])
        score = max(0.0, min(10.0, score))  # clamp to [0, 10]
        explanation = str(data.get("explanation", "")).strip()
        return score, explanation
    except (json.JSONDecodeError, KeyError, ValueError):
        # Try a regex fallback for score extraction
        match = re.search(r'"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)', content)
        if match:
            score = max(0.0, min(10.0, float(match.group(1))))
            return score, content[:200]
        logger.warning("Could not parse LLM response: %s", content[:200])
        return 0.0, "Could not parse LLM response"


def _call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
    api_key: str,
) -> tuple[float, str]:
    url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 150,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_response(content)


def _call_watsonx(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
    api_key: str,
) -> tuple[float, str]:
    base = base_url or "https://us-south.ml.cloud.ibm.com"
    # watsonx.ai uses IAM bearer tokens; api_key is the IAM API key
    iam_token = _get_watsonx_iam_token(api_key)
    project_id = os.environ.get("WATSONX_PROJECT_ID", "")

    url = f"{base}/ml/v1/text/generation?version=2024-05-31"
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }
    # Combine system + user into a single prompt for watsonx text generation
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"
    payload = {
        "model_id": model,
        "input": combined_prompt,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 150,
            "temperature": 0.0,
        },
        "project_id": project_id,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    content = resp.json()["results"][0]["generated_text"]
    return _parse_response(content)


def _get_watsonx_iam_token(api_key: str) -> str:
    """Exchange an IBM Cloud IAM API key for a bearer token."""
    resp = httpx.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _call_ollama(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
) -> tuple[float, str]:
    url = (base_url or "http://localhost:11434") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _parse_response(content)


# ---------------------------------------------------------------------------
# Summary provider implementations
# ---------------------------------------------------------------------------

def _call_openai_summary(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
    api_key: str,
) -> str:
    url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 400,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_watsonx_summary(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
    api_key: str,
) -> str:
    base = base_url or "https://us-south.ml.cloud.ibm.com"
    iam_token = _get_watsonx_iam_token(api_key)
    project_id = os.environ.get("WATSONX_PROJECT_ID", "")
    url = f"{base}/ml/v1/text/generation?version=2024-05-31"
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"
    payload = {
        "model_id": model,
        "input": combined_prompt,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 400,
            "temperature": 0.3,
        },
        "project_id": project_id,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    return resp.json()["results"][0]["generated_text"].strip()


def _call_ollama_summary(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
) -> str:
    url = (base_url or "http://localhost:11434") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    with httpx.Client(timeout=300) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
    return resp.json()["message"]["content"].strip()
