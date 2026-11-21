"""Dostęp do modelu językowego: lokalnie na CPU (llama.cpp) albo przez API zgodne z OpenAI.

Wybór przez zmienne środowiskowe:
  O2J_API_BASE   np. http://127.0.0.1:8000/v1  -> tryb API (model open source serwowany osobno)
  O2J_API_MODEL  nazwa modelu w API
  O2J_API_KEY    klucz (opcjonalnie)
Bez O2J_API_BASE używany jest lokalny plik GGUF (O2J_MODEL lub parametr --model).

Tryb lokalny wypełnia formularz w sposób prowadzony (metoda `fill`):
  - klucze formularza są podawane modelowi jako wejście (szybkie przetwarzanie wsadowe),
    a model generuje wyłącznie wartości - około połowy mniej generowanych tokenów,
  - stan modelu po stałej części promptu (instrukcja + opis pól danej klasy) jest zapamiętywany
    i odtwarzany dla kolejnych dokumentów tej samej klasy, więc czytany jest tylko tekst dokumentu.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import time
import urllib.request

HEADER_RE = re.compile(r"^#+\s*([\w\-]+)(?:\s+(\d+))?")


class LlamaCppBackend:
    name = "llama.cpp (CPU)"

    def __init__(self, model_path: str, n_threads: int, n_ctx: int = 8192):
        import llama_cpp
        import numpy as np
        self._lib, self._np = llama_cpp, np
        self.llm = llama_cpp.Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads,
                                   n_threads_batch=n_threads, verbose=False)
        self.n_ctx = n_ctx
        self._n_past = 0
        self._cache: tuple[str, object, int, int] | None = None   # (stała część, bufor stanu, rozmiar, n_past)
        self._stop = {self.llm.token_eos()} | set(self._tok("<|im_end|>")) | set(self._tok("<|endoftext|>"))
        self.last_stats: dict = {}

    # ------------------------------------------------------------- odczyt obrazu (czytelnik wizualny)
    def enable_vision(self, mmproj_path: str) -> None:
        """Podłącza projektor obrazu (plik mmproj z tego samego repozytorium co model)."""
        from llama_cpp.llama_chat_format import MTMDChatHandler
        self._vision = MTMDChatHandler(clip_model_path=mmproj_path, verbose=False, use_gpu=False)

    def read_image(self, image, prompt: str, max_tokens: int = 48) -> str:
        """Przepisuje tekst z wycinka (obraz PIL). Zmienia kontekst modelu - `fill` i tak odtwarza swój stan."""
        import base64
        import io
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        out = self._vision(llama=self.llm, temperature=0.0, max_tokens=max_tokens, messages=[
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": uri}}, {"type": "text", "text": prompt}]}])
        text = out["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?(</think>|\Z)", "", text, flags=re.DOTALL).strip()

    # ------------------------------------------------------------- niskopoziomowe operacje na kontekście
    def _tok(self, text: str, bos: bool = False) -> list[int]:
        return self.llm.tokenize(text.encode("utf-8"), add_bos=bos, special=True)

    def _reset(self) -> None:
        self.llm._ctx.kv_cache_clear()
        self._n_past = 0

    def _feed(self, tokens: list[int]) -> None:
        for i in range(0, len(tokens), self.llm.n_batch):
            chunk = tokens[i: i + self.llm.n_batch]
            self.llm._batch.set_batch(batch=chunk, n_past=self._n_past, logits_all=False)
            self.llm._ctx.decode(self.llm._batch)
            self._n_past += len(chunk)

    def _next(self) -> int:
        logits = self._np.ctypeslib.as_array(self.llm._ctx.get_logits(), shape=(self.llm._n_vocab,))
        return int(self._np.argmax(logits))

    def _save(self, key: str) -> None:
        ctx = self.llm._ctx.ctx
        size = int(self._lib.llama_state_get_size(ctx))
        buf = (ctypes.c_uint8 * size)()
        written = int(self._lib.llama_state_get_data(ctx, buf, size))
        self._cache = (key, buf, written, self._n_past)

    def _load(self) -> None:
        _, buf, size, n_past = self._cache
        if int(self._lib.llama_state_set_data(self.llm._ctx.ctx, buf, size)) != size:
            raise RuntimeError("Nie udało się odtworzyć stanu modelu")
        self._n_past = n_past

    def _line(self, max_tokens: int, dash_shortcut: bool = False) -> tuple[str, str]:
        """Generuje tekst do końca linii. Zwraca (tekst, tekst_do_dopisania_bez_ewaluacji)."""
        buf = b""
        for i in range(max_tokens):
            token = self._next()
            if token in self._stop:
                break
            piece = self.llm.detokenize([token], special=False)
            if b"\n" in piece:
                buf += piece.split(b"\n")[0]
                break
            if dash_shortcut and i == 0 and piece.strip() in (b"-", b"\xe2\x80\x93", b"\xe2\x80\x94"):
                return "-", " -"       # pusta wartość: nie warto robić osobnego przebiegu modelu
            buf += piece
            self._feed([token])
            self.last_stats["wygenerowane"] += 1
        return buf.decode("utf-8", errors="ignore").strip(), ""

    # ------------------------------------------------------------- prowadzone wypełnianie formularza
    def fill(self, system: str, static_user: str, doc_text: str, sections: list[tuple[str, bool, list[str]]],
             max_value_tokens: int = 200, max_items: int = 8) -> str:
        """Wypełnia formularz: sections = [(nazwa sekcji, czy lista, [klucze])]. Zwraca tekst formularza."""
        t0 = time.perf_counter()
        self.last_stats = {"wygenerowane": 0, "stan_z_pamieci": False}
        static = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{static_user}"
        tail = self._tok("<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
        if self._cache and self._cache[0] == static:
            self._load()
            self.last_stats["stan_z_pamieci"] = True
        else:
            self._reset()
            self._feed(self._tok(static, bos=True))
            self._save(static)
        doc = self._tok(doc_text)
        reserve = 900                                   # miejsce na klucze i wartości formularza
        room = self.n_ctx - self._n_past - len(tail) - reserve
        if len(doc) > room:                             # za długi dokument: zostaje początek
            doc = doc[:max(room, 0)]
        self._feed(doc + tail)
        self.last_stats.update(prompt_tokeny=self._n_past, czas_czytania_s=round(time.perf_counter() - t0, 2))

        lines: list[str] = []
        pending = ""            # tekst wymuszony, jeszcze niepodany modelowi
        bol = True              # czy kontekst (razem z pending) jest na początku linii

        def flush():
            nonlocal pending
            if pending:
                self._feed(self._tok(pending))
                pending = ""

        def force(text: str):
            nonlocal pending, bol
            pending += text
            bol = text.endswith("\n")

        def newline():
            if not bol:
                force("\n")

        def ask(key: str) -> str:
            nonlocal pending, bol
            force(f"{key}:")
            flush()
            value, deferred = self._line(max_value_tokens, dash_shortcut=True)
            pending += deferred
            lines.append(f"{key}: {value}")
            return value

        header_in_context = False
        stray = None            # nagłówek, który model sam zaczął po zakończeniu listy
        for name, is_list, keys in sections:
            index = 1
            header_in_context = stray == name.casefold()
            stray = None
            skip_first: str | None = None
            items: list[dict[str, str]] = []           # wypełnione już elementy listy
            while True:
                header = f"## {name} {index}" if is_list else f"## {name}"
                if not header_in_context:
                    newline()
                    force(header + "\n")
                header_in_context = False
                start = len(lines)
                lines.append(header)
                current: dict[str, str] = {}
                repeated = False
                for key in keys:
                    if skip_first is not None and key == keys[0]:
                        value, skip_first = skip_first, None      # wartość już wygenerowana w linii decyzyjnej
                        lines.append(f"{key}: {value}")
                    else:
                        newline()
                        value = ask(key)
                    known = not any(v not in ("", "-") for v in current.values())
                    current[key] = value
                    # Pierwsza niepusta wartość elementu identyfikuje podmiot. Jeśli taki podmiot już jest
                    # na liście, model zaczął się powtarzać - kończymy listę i odrzucamy powtórzenie.
                    if known and value not in ("", "-") and any(
                            p.get(key, "").casefold() == value.casefold() for p in items):
                        repeated = True
                        break
                if is_list and items and (repeated or all(v in ("", "-") for v in current.values())):
                    del lines[start:]
                    break
                items.append(current)
                if not is_list or index >= max_items:
                    break
                # Czy dokument zawiera kolejny podmiot tej sekcji? Model sam zaczyna następną linię.
                newline()
                flush()
                line, _ = self._line(60)
                bol = not line
                m = HEADER_RE.match(line)
                first = re.match(rf"^{re.escape(keys[0])}\s*:\s*(.*)$", line)
                if m and m.group(1).casefold() == name.casefold():
                    index += 1
                    header_in_context = True          # nagłówek kolejnego elementu jest już w kontekście
                elif first and first.group(1).strip() not in ("", "-"):
                    index += 1                        # model pominął nagłówek i od razu podał pierwsze pole
                    header_in_context = True
                    skip_first = first.group(1).strip()
                else:
                    stray = m.group(1).casefold() if m else None
                    break
        self.last_stats["czas_s"] = round(time.perf_counter() - t0, 2)
        return "\n".join(lines)

    # ------------------------------------------------------------- swobodna generacja (zapas)
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
        self._cache = None
        self.llm.reset()
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
