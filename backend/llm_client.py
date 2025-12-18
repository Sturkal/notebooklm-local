"""
llm_client.py - LLM Backend Abstraction (clean rebuild)
======================================================

This file provides a compact, robust client for Ollama (local) with
fallback behaviors for legacy vs OpenAI-compatible endpoints. It exposes
`llm.chat(prompt, model=None)` and `llm.list_models()` and returns
friendly error strings on failure.
"""

import os
import time
import logging
from typing import List

import requests
import json

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configuration from environment
LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama2:latest")


class LLMClient:
    def __init__(self, retries: int = 3, backoff: float = 1.0, timeout: int = 30):
        self.backend = LLM_BACKEND
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout

    def chat(self, prompt: str, model: str | None = None) -> str:
        if self.backend != "ollama":
            return self._local_stub(prompt)
        return self._ollama_chat(prompt, model=model)

    def _ollama_chat(self, prompt: str, model: str | None = None) -> str:
        used_model = model or OLLAMA_MODEL
        legacy_url = f"{OLLAMA_URL}/chat?model={used_model}"
        responses_url = f"{OLLAMA_URL}/v1/responses"
        legacy_payload = {"messages": [{"role": "user", "content": prompt}]}
        responses_payload = {"model": used_model, "input": prompt}

        attempt = 0
        while attempt < self.retries:
            try:
                LOG.debug(
                    "Calling Ollama legacy chat (%s), attempt %d",
                    legacy_url,
                    attempt + 1,
                )
                r = requests.post(legacy_url, json=legacy_payload, timeout=self.timeout)
                # If legacy not found, try v1 API
                if r.status_code == 404:
                    LOG.debug("Legacy /chat returned 404; trying /v1/responses")
                    r = requests.post(
                        responses_url, json=responses_payload, timeout=self.timeout
                    )

                try:
                    r.raise_for_status()
                except requests.exceptions.HTTPError as he:
                    LOG.warning(
                        "Ollama HTTP error (status %s): %s",
                        getattr(r, "status_code", "?"),
                        he,
                    )
                    return f"[LLM HTTP error: {he}]"

                try:
                    data = r.json()
                except ValueError:
                    LOG.warning(
                        "Ollama returned non-JSON response; raw=%s", r.text[:1000]
                    )
                    return r.text or "[LLM returned non-JSON response]"

                # Parse common shapes
                # Legacy: {"message": {"content": "..."}}
                if isinstance(data, dict):
                    # legacy message
                    if isinstance(data.get("message"), dict) and data["message"].get(
                        "content"
                    ):
                        return data["message"]["content"]

                    # choices style
                    if isinstance(data.get("choices"), list) and data["choices"]:
                        first = data["choices"][0]
                        if isinstance(first, dict):
                            return (
                                (first.get("message", {}) or {}).get("content")
                                or first.get("content")
                                or first.get("text")
                                or json.dumps(first)
                            )

                    # v1/responses: contains output -> content -> output_text
                    if isinstance(data.get("output"), list) and data.get("output"):
                        out0 = data.get("output")[0]
                        if isinstance(out0, dict) and isinstance(
                            out0.get("content"), list
                        ):
                            for c in out0.get("content"):
                                if (
                                    isinstance(c, dict)
                                    and c.get("type") == "output_text"
                                    and c.get("text")
                                ):
                                    return c.get("text")

                    # response or output keys
                    if "response" in data and isinstance(data["response"], str):
                        return data["response"]

                # Fallback
                return json.dumps(data)

            except requests.exceptions.Timeout as e:
                attempt += 1
                LOG.warning(
                    "Ollama request timed out (attempt %d/%d): %s",
                    attempt,
                    self.retries,
                    e,
                )
                if attempt >= self.retries:
                    return f"[LLM timeout after {attempt} attempts]"
                time.sleep(self.backoff * (2 ** (attempt - 1)))

            except requests.exceptions.RequestException as e:
                attempt += 1
                LOG.warning(
                    "Ollama request failed (attempt %d/%d): %s",
                    attempt,
                    self.retries,
                    e,
                )
                if attempt >= self.retries:
                    return f"[LLM error: {e}]"
                time.sleep(self.backoff * (2 ** (attempt - 1)))

        return "[LLM error: unknown]"

    def list_models(self) -> List[str]:
        if self.backend != "ollama":
            LOG.info("Model listing not supported for backend=%s", self.backend)
            return []

        urls = [f"{OLLAMA_URL}/v1/models", f"{OLLAMA_URL}/models"]
        attempt = 0
        while attempt < self.retries:
            for url in urls:
                try:
                    LOG.debug("Listing Ollama models from %s", url)
                    r = requests.get(url, timeout=self.timeout)
                    if r.status_code == 404:
                        LOG.debug("%s returned 404", url)
                        continue
                    r.raise_for_status()
                    try:
                        data = r.json()
                    except ValueError:
                        LOG.warning(
                            "Ollama returned non-JSON for models list; raw=%s",
                            r.text[:1000],
                        )
                        return []

                    LOG.debug(
                        "Raw models response status=%s text=%s",
                        r.status_code,
                        (r.text[:1000] if r.text else ""),
                    )

                    models = []
                    if (
                        isinstance(data, dict)
                        and data.get("object") == "list"
                        and isinstance(data.get("data"), list)
                    ):
                        for it in data.get("data", []):
                            if isinstance(it, dict) and it.get("id"):
                                models.append(it.get("id"))
                    elif isinstance(data, list):
                        for it in data:
                            if isinstance(it, str):
                                models.append(it)
                            elif isinstance(it, dict) and it.get("name"):
                                models.append(it.get("name"))
                    elif isinstance(data, dict):
                        if "models" in data and isinstance(data["models"], list):
                            for it in data["models"]:
                                if isinstance(it, str):
                                    models.append(it)
                                elif isinstance(it, dict) and it.get("name"):
                                    models.append(it.get("name"))
                        else:
                            for k in data.keys():
                                models.append(k)

                    # Deduplicate while preserving order
                    seen = set()
                    out = []
                    for m in models:
                        if m and m not in seen:
                            seen.add(m)
                            out.append(m)
                    return out

                except requests.exceptions.RequestException as e:
                    LOG.warning("Failed to list models from %s: %s", url, e)
                    continue

            attempt += 1
            time.sleep(self.backoff * (2 ** (attempt - 1)))

        LOG.error("Model listing failed after %d attempts", self.retries)
        return []

    def _local_stub(self, prompt: str) -> str:
        LOG.info("Local LLM backend requested but not configured")
        return "[Local LLM backend not configured]"


# Global instance
llm = LLMClient()
