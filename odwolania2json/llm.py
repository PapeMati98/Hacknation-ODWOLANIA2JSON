"""Dostęp do modelu językowego: lokalnie na CPU (llama.cpp) albo przez API zgodne z OpenAI.

Wybór przez zmienne środowiskowe:
  O2J_API_BASE   np. http://127.0.0.1:8000/v1  -> tryb API (model open source serwowany osobno)
  O2J_API_MODEL  nazwa modelu w API
  O2J_API_KEY    klucz (opcjonalnie)
Bez O2J_API_BASE używany jest lokalny plik GGUF (O2J_MODEL lub parametr --model).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request


class LlamaCppBackend:
    name = "llama.cpp (CPU)"

    def __init__(self, model_path: str, n_threads: int, n_ctx: int = 8192):
        from llama_cpp import Llama
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads, n_threads_batch=n_threads,
                         verbose=False)
        self.n_ctx = n_ctx

    def complete(self, system: str, user: str, prefill: str, max_tokens: int) -> str:
        # ChatML z pustym blokiem rozumowania: model od razu wypełnia formularz.
        prompt = (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
                  f"<|im_start|>assistant\n<think>\n\n</think>\n\n{prefill}")
        budget = self.n_ctx - max_tokens - 16
        tokens = self.llm.tokenize(prompt.encode("utf-8"), special=True)
        if len(tokens) > budget:   # za długi dokument: przycinamy środek tekstu, zostaje początek i koniec promptu
            keep_tail = 64
            tokens = tokens[: budget - keep_tail] + tokens[-keep_tail:]
            prompt = self.llm.detokenize(tokens, special=True).decode("utf-8", errors="ignore")
        out = self.llm.create_completion(prompt, max_tokens=max_tokens, temperature=0.0, stop=["<|im_end|>"])
        return prefill + out["choices"][0]["text"]


class OpenAIBackend:
    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.api_key = model, api_key
        self.name = f"API {base_url} ({model})"

    def complete(self, system: str, user: str, prefill: str, max_tokens: int) -> str:
        body = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "chat_template_kwargs": {"enable_thinking": False}}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=600) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def make_backend(model_path: str, n_threads: int):
    base = os.environ.get("O2J_API_BASE")
    if base:
        return OpenAIBackend(base, os.environ.get("O2J_API_MODEL", "default"), os.environ.get("O2J_API_KEY"))
    return LlamaCppBackend(model_path, n_threads)
