"""
llm_client.py - LLM Backend Abstraction
========================================

This module provides a unified interface to Large Language Models (LLMs).
Currently supports Ollama (local, open-source models) with extensibility
for other backends (local HuggingFace, remote APIs, etc.).

Features:
- Configurable Backend: Ollama, local stub, or custom implementations
- Retry Logic: Exponential backoff for transient failures
- Timeouts: Prevents hanging on unresponsive LLM services
- Response Parsing: Tolerant parsing handles multiple Ollama response shapes
- Model Listing: Queries available models for frontend selector
- Error Handling: Graceful fallback messages instead of stack traces

Configuration (Environment Variables):
    LLM_BACKEND     : "ollama" (default) or "local"
    OLLAMA_URL      : Base URL for Ollama server (default "http://localhost:11434")
    OLLAMA_MODEL    : Default model name if not specified in request
                      (default "llama3.1")

Example:
    from llm_client import llm
    response = llm.chat("What is 2+2?", model="mistral")
    models = llm.list_models()
"""

import os
import time
import logging
from typing import Any

import requests
import json

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configuration from environment
LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")


class LLMClient:
    """
    Unified client for querying Language Models.
    
    Abstracts multiple backends (Ollama, local, etc.) behind a consistent interface.
    Provides automatic retries, timeouts, and error handling.
    """

    def __init__(self, retries: int = 3, backoff: float = 1.0, timeout: int = 30):
        """
        Initialize the LLM client.
        
        Args:
            retries (int): Number of retry attempts for transient failures
            backoff (float): Initial backoff duration (seconds) for exponential backoff
                            Actual backoff = backoff * (2 ** attempt)
            timeout (int): HTTP request timeout (seconds)
            
        Notes:
            - Backend is determined by LLM_BACKEND environment variable
            - Configuration is applied at initialization time
        """
        self.backend = LLM_BACKEND
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout

    def chat(self, prompt: str, model: str | None = None) -> str:
        """
        Send a prompt to the LLM and get a response.
        
        This is the main entry point. It dispatches to the appropriate backend
        implementation (Ollama, local, etc.).
        
        Args:
            prompt (str): The input prompt for the LLM
            model (str | None): Specific model to use (if supported by backend)
                               If None, uses the default (OLLAMA_MODEL env var)
                               
        Returns:
            str: The LLM's text response. On errors, returns a user-friendly
                 message like "[LLM error: connection refused]" instead of
                 raising an exception (keeps downstream code simpler)
                 
        Notes:
            - If backend == "ollama", calls _ollama_chat()
            - If backend == "local", calls _local_stub() (placeholder)
            - For other backends, also calls _local_stub()
            - All errors are caught and returned as strings (no exceptions)
        """
        if self.backend == "ollama":
            return self._ollama_chat(prompt, model=model)
        elif self.backend == "local":
            return self._local_stub(prompt)
        else:
            return self._local_stub(prompt)

    def _ollama_chat(self, prompt: str, model: str | None = None) -> str:
        """
        Query the Ollama LLM backend.
        
        Implementation Details:
        1. Constructs the request URL with model name
        2. Sends a chat message to Ollama's /chat endpoint
        3. Handles retries with exponential backoff on network errors
        4. Parses the JSON response (tolerates multiple response shapes)
        5. Returns user-friendly error messages on failure
        
        Args:
            prompt (str): The prompt text to send to the LLM
            model (str | None): Model name (e.g., "llama3.1", "mistral")
                               If None, uses OLLAMA_MODEL environment variable
                               
        Returns:
            str: LLM's text response, or error message like "[LLM timeout after 3 attempts]"
            
        Error Handling:
            - Timeouts: retries with exponential backoff, returns friendly message
            - Connection errors: retries as above
            - HTTP errors (4xx, 5xx): returns immediately with error message (no retry)
            - JSON parsing errors: returns raw response text or JSON error
            
        Response Parsing (Tolerant):
            Handles multiple Ollama response shapes:
            - {"message": {"content": "..."}}  (common)
            - {"choices": [{"message": {"content": "..."}}]}  (some versions)
            - {"response": "..."}  (other versions)
            - {"output": "..."}  (fallback)
            - Returns full JSON as string if no recognized structure
            
        Notes:
            - Ollama runs locally by default (OLLAMA_URL)
            - HTTP timeout prevents indefinite hangs
            - Retry logic helps with transient network issues
            - Backend availability is not checked (failures occur on first request)
        """
        used_model = model or OLLAMA_MODEL
        url = f"{OLLAMA_URL}/chat?model={used_model}"
        payload = {"messages": [{"role": "user", "content": prompt}]}

        attempt = 0
        while attempt < self.retries:
            try:
                LOG.debug("Calling Ollama (%s), attempt %d", url, attempt + 1)
                r = requests.post(url, json=payload, timeout=self.timeout)
                try:
                    r.raise_for_status()
                except requests.exceptions.HTTPError as he:
                    LOG.warning("Ollama HTTP error (status %s): %s", getattr(r, "status_code", "?"), he)
                    # For HTTP errors, do not retry many times — return informative message
                    return f"[LLM HTTP error: {he}]"

                # Parse JSON response if possible
                try:
                    data = r.json()
                except ValueError:
                    LOG.warning("Ollama returned non-JSON response")
                    return r.text or "[LLM returned non-JSON response]"

                # Try multiple response shapes in a tolerant way
                if isinstance(data, dict):
                    # Common: {"message": {"content": "..."}}
                    content = data.get("message", {}).get("content") if isinstance(data.get("message"), dict) else None

                    # Some versions: {"choices": [{"message": {"content": "..."}}]}
                    if not content and isinstance(data.get("choices"), list) and data.get("choices"):
                        first = data["choices"][0]
                        if isinstance(first, dict):
                            content = (first.get("message", {}) or {}).get("content") or first.get("content") or first.get("text")

                    # Other shapes
                    if not content and "response" in data:
                        content = data.get("response")
                    if not content and "output" in data:
                        content = data.get("output")

                    if content is not None:
                        return content

                # Fallback: return full JSON as string
                return json.dumps(data)

            except requests.exceptions.Timeout as e:
                attempt += 1
                LOG.warning("Ollama request timed out (attempt %d/%d): %s", attempt, self.retries, e)
                if attempt >= self.retries:
                    LOG.error("Ollama timed out after %d attempts", attempt)
                    return f"[LLM timeout after {attempt} attempts]"
                # Exponential backoff: 1s, 2s, 4s, ...
                sleep_for = self.backoff * (2 ** (attempt - 1))
                time.sleep(sleep_for)

            except requests.exceptions.RequestException as e:
                attempt += 1
                LOG.warning("Ollama request failed (attempt %d/%d): %s", attempt, self.retries, e)
                if attempt >= self.retries:
                    LOG.error("Ollama unavailable after %d attempts", attempt)
                    return f"[LLM error: {e}]"
                # Exponential backoff
                sleep_for = self.backoff * (2 ** (attempt - 1))
                time.sleep(sleep_for)

        return "[LLM error: unknown]"

    def list_models(self) -> list:
        """
        List available LLM models from the configured backend.
        
        For Ollama, queries the /models endpoint and returns a list of model names.
        This enables the frontend to populate a model selector dropdown.
        
        Returns:
            list: Model names (e.g., ["llama3.1", "mistral", "neural-chat"])
                  Empty list on errors or if not supported by backend
                  
        Error Handling:
            - Non-Ollama backends: logs and returns empty list
            - Network errors: retries with exponential backoff, then returns empty list
            - JSON parsing errors: returns empty list
            - Malformed responses: attempts multiple parsing strategies
            
        Response Parsing (Tolerant):
            Handles multiple Ollama /models endpoint response shapes:
            - [{"name": "llama3.1"}, ...]  (list of dicts with "name")
            - ["llama3.1", "mistral", ...]  (list of strings)
            - {"models": [...]}  (dict with "models" key)
            - {model_name: model_info, ...}  (dict keyed by model name)
            
        Notes:
            - Returns unique model names in order
            - Used by Chat component to populate dropdown
            - If Ollama is unavailable, returns empty list (no error shown to user)
            - This is called once on Chat component mount
        """
        if self.backend != "ollama":
            LOG.info("Model listing not supported for backend=%s", self.backend)
            return []

        url = f"{OLLAMA_URL}/models"
        attempt = 0
        while attempt < self.retries:
            try:
                LOG.debug("Listing Ollama models from %s (attempt %d)", url, attempt + 1)
                r = requests.get(url, timeout=self.timeout)
                r.raise_for_status()
                try:
                    data = r.json()
                except ValueError:
                    LOG.warning("Ollama returned non-JSON for models list")
                    return []

                # Tolerant parsing: if list, map to names; if dict with 'models', extract
                models = []
                if isinstance(data, list):
                    # items may be strings or dicts with "name" field
                    for it in data:
                        if isinstance(it, str):
                            models.append(it)
                        elif isinstance(it, dict) and it.get("name"):
                            models.append(it.get("name"))
                elif isinstance(data, dict):
                    if "models" in data and isinstance(data["models"], list):
                        # Format: {"models": [{"name": "..."}, ...]}
                        for it in data["models"]:
                            if isinstance(it, str):
                                models.append(it)
                            elif isinstance(it, dict) and it.get("name"):
                                models.append(it.get("name"))
                    else:
                        # Format: {model_name: model_info, ...}
                        for k in data.keys():
                            models.append(k)

                # Remove duplicates while preserving order
                seen = set()
                out = []
                for m in models:
                    if m and m not in seen:
                        seen.add(m)
                        out.append(m)
                return out

            except requests.exceptions.RequestException as e:
                attempt += 1
                LOG.warning("Failed to list models (attempt %d/%d): %s", attempt, self.retries, e)
                if attempt >= self.retries:
                    LOG.error("Model listing failed after %d attempts", attempt)
                    return []
                # Exponential backoff
                time.sleep(self.backoff * (2 ** (attempt - 1)))

        return []

    def _local_stub(self, prompt: str) -> str:
        """
        Placeholder for local LLM backend.
        
        This is a stub implementation for a future local LLM backend
        (e.g., using transformers, llama.cpp, or other local inference engines).
        
        For now, returns a message indicating the backend is not configured.
        
        Args:
            prompt (str): The prompt (not used by stub)
            
        Returns:
            str: Error message indicating feature is not implemented
            
        Future Enhancement:
            To implement a local backend:
            1. Load a model (e.g., from HuggingFace or ONNX)
            2. Tokenize the prompt
            3. Run inference
            4. Return generated text
            
        Example:
            from transformers import pipeline
            generator = pipeline("text-generation", model="gpt2")
            response = generator(prompt, max_length=100)[0]["generated_text"]
        """
        LOG.info("Local LLM backend requested but not configured")
        return "[Local LLM backend not configured]"


# Global LLM client instance (singleton pattern)
# All code should use this instance rather than creating new LLMClient objects
llm = LLMClient()