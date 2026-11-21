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
import http.client
import socket
import ssl
import threading
import time
import urllib.parse

HEADER_RE = re.compile(r"^#+\s*([\w\-]+)(?:\s+(\d+))?")


def guided_fill(session, sections: list[tuple[str, bool, list[str]]], max_value_tokens: int = 200, max_items: int = 8,
                signed: frozenset[str] = frozenset(), min_items: dict[str, int] | None = None) -> str:
    """Prowadzone wypełnianie formularza - wspólne dla modelu lokalnego i modelu po API.

    `session.force(tekst)` dopisuje tekst do kontekstu modelu (nagłówki sekcji i klucze podaje kod),
    `session.gen(limit, dash_shortcut)` generuje tekst do końca linii (model podaje same wartości).
    Zwraca tekst formularza (`## Sekcja`, linie `klucz: wartość`).
    """
    lines: list[str] = []
    bol = True              # czy kontekst jest na początku linii

    def force(text: str):
        nonlocal bol
        session.force(text)
        bol = text.endswith("\n")

    def newline():
        if not bol:
            force("\n")

    def ask(key: str) -> str:
        force(f"{key}:")
        value = session.gen(max_value_tokens, key not in signed)
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
            if index < (min_items or {}).get(name, 0):
                # Z tekstu wynika, że podmiotów jest więcej (reguła listy z YAML): kolejny element jest
                # wymuszony. Pusty albo powtórzony element i tak zostanie odrzucony wyżej.
                index += 1
                continue
            # Czy dokument zawiera kolejny podmiot tej sekcji? Model sam zaczyna następną linię.
            newline()
            line = session.gen(60, False)
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
    return "\n".join(lines)


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
        self._say_tokens: list[int] | None = None                 # tokeny ostatniego krótkiego pytania (wspólny początek)
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
        from llama_cpp._utils import suppress_stdout_stderr
        with suppress_stdout_stderr(disable=False):      # biblioteka obrazu wypisuje dziennik na stderr
            out = self._vision(llama=self.llm, temperature=0.0, max_tokens=max_tokens, messages=[
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": uri}}, {"type": "text", "text": prompt}]}])
        text = out["choices"][0]["message"]["content"] or ""
        text = re.sub(r"<think>.*?(</think>|\Z)", "", text, flags=re.DOTALL).strip()
        if out["choices"][0].get("finish_reason") == "length" and " " in text:
            text = text.rsplit(None, 1)[0]              # odczyt urwany limitem: ostatni wyraz jest niepełny
        return text

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

    def say(self, prompt: str, max_tokens: int = 48) -> str:
        """Krótka odpowiedź (jedna linia, zachłannie) na gotowy prompt - do końcowej walidacji wartości."""
        stats = self.last_stats
        tokens, kept = self._tok(prompt, bos=True), 0
        if self._say_tokens is not None:          # kolejne pytania mają wspólny początek - czytamy tylko różnicę
            for a, b in zip(self._say_tokens, tokens):
                if a != b:
                    break
                kept += 1
            kept = min(kept, len(tokens) - 1)
        if kept and self.llm._ctx.kv_cache_seq_rm(-1, kept, -1):
            self._n_past = kept
        else:
            kept = 0
            self._reset()
        self._feed(tokens[kept:])
        self._say_tokens = tokens
        self.last_stats = {"wygenerowane": 0}
        text, _ = self._line(max_tokens)
        self.last_stats = stats
        return text.strip().strip("«»")

    # ------------------------------------------------------------- prowadzone wypełnianie formularza
    def fill(self, system: str, static_user: str, doc_text: str, sections: list[tuple[str, bool, list[str]]],
             max_value_tokens: int = 200, max_items: int = 8, signed: frozenset[str] = frozenset(),
             min_items: dict[str, int] | None = None) -> str:
        """Wypełnia formularz: sections = [(nazwa sekcji, czy lista, [klucze])]. Zwraca tekst formularza.

        `signed` - klucze, których wartość może zaczynać się od minusa (kwoty): dla nich sam znak „-”
        na początku nie jest jeszcze pustą wartością.
        """
        t0 = time.perf_counter()
        self._say_tokens = None
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

        pending = ""            # tekst wymuszony, jeszcze niepodany modelowi
        backend = self

        class Session:
            def force(self, text: str) -> None:
                nonlocal pending
                pending += text

            def gen(self, max_tokens: int, dash_shortcut: bool) -> str:
                nonlocal pending
                if pending:
                    backend._feed(backend._tok(pending))
                    pending = ""
                value, deferred = backend._line(max_tokens, dash_shortcut=dash_shortcut)
                pending += deferred
                return value

        answer = guided_fill(Session(), sections, max_value_tokens, max_items, signed, min_items)
        self.last_stats["czas_s"] = round(time.perf_counter() - t0, 2)
        return answer

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
    """Model open source serwowany przez API zgodne z OpenAI (vLLM, llama.cpp server).

    Formularz jest wypełniany tak samo jak lokalnie: kod podaje nagłówki i klucze, a model dopisuje
    wartość do końca linii (`/completions` z surowym promptem). Serwer pamięta wspólny początek promptu,
    więc kolejne pytania o ten sam dokument kosztują tylko nowe tokeny.
    """
    DASHES = ("-", "\u2013", "\u2014")
    # Przerwy między próbami (razem ok. 2 min): restart serwera albo chwilowy brak sieci nie gubi dokumentu.
    RETRY_DELAYS = (0.5, 2, 4, 8, 15, 30, 30, 30)
    PING_DELAYS = (0.5, 2, 4, 8)        # sprawdzenie na starcie: krócej, żeby zły adres wyszedł od razu
    OUTAGE_LIMIT = 180                  # tyle sekund bez żadnej udanej odpowiedzi i kolejne zapytania już nie czekają

    def __init__(self, base_url: str, model: str, api_key: str | None = None, doc_chars: int = 24000):
        self.base = urllib.parse.urlsplit(base_url.rstrip("/"))
        self.model, self.api_key, self.doc_chars = model, api_key, doc_chars
        self.name = f"API {base_url} ({model})"
        self._local = threading.local()            # jedno trwałe połączenie i jedne statystyki na wątek
        self._lock = threading.Lock()
        self._down_since: float | None = None      # od kiedy serwer nie odpowiada (wspólne dla wątków)
        # Ile dokumentów naraz: serwer łączy zapytania w paczki, więc równoległość skraca czas całej partii.
        self.parallel = max(1, int(os.environ.get("O2J_API_PARALLEL", "8")))

    @property
    def last_stats(self) -> dict:
        if not hasattr(self._local, "stats"):
            self._local.stats = {}
        return self._local.stats

    @last_stats.setter
    def last_stats(self, value: dict) -> None:
        self._local.stats = value

    def ping(self) -> str | None:
        """Sprawdza, czy serwer odpowiada jednym krótkim zapytaniem; zwraca opis problemu albo None."""
        try:
            self._post("/completions", {"model": self.model, "max_tokens": 1, "temperature": 0,
                                        "prompt": "<|im_start|>user\nTest<|im_end|>\n<|im_start|>assistant\n"},
                       delays=self.PING_DELAYS)
        except RuntimeError as exc:
            return str(exc)
        return None

    @property
    def unavailable(self) -> bool:
        """Serwer nie odpowiada dłużej niż OUTAGE_LIMIT - ponawianie dokumentów nie ma sensu."""
        with self._lock:
            return self._down_since is not None and time.monotonic() - self._down_since > self.OUTAGE_LIMIT

    @staticmethod
    def _explain(error: Exception | None) -> str:
        """Przyczyna po ludzku; szczegół techniczny zostaje w nawiasie na końcu komunikatu."""
        text = str(error)
        if isinstance(error, ssl.SSLError):
            return "nie udało się nawiązać bezpiecznego połączenia - sprawdź adres w O2J_API_BASE"
        if isinstance(error, socket.gaierror):
            return "nie znaleziono serwera - sprawdź adres w O2J_API_BASE i połączenie z internetem"
        if isinstance(error, (TimeoutError, ConnectionError, OSError, http.client.HTTPException)):
            return "brak połączenia z serwerem - sprawdź internet; serwer może być chwilowo niedostępny"
        if text.startswith(("API 401", "API 403")):
            return "serwer odrzucił klucz - sprawdź O2J_API_KEY (plik api.env)"
        if text.startswith("API 404"):
            return "serwer nie zna tego adresu albo modelu - sprawdź O2J_API_BASE i O2J_API_MODEL"
        if text.startswith("API 429"):
            return "serwer odrzuca zapytania z powodu limitu - zmniejsz O2J_API_PARALLEL"
        if text.startswith("API 5"):
            return "serwer modelu jest chwilowo niedostępny"
        return "serwer zwrócił błąd"

    # ------------------------------------------------------------- HTTP
    def _post(self, path: str, body: dict, delays: tuple | None = None) -> dict:
        delays = self.RETRY_DELAYS if delays is None else delays
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        error: Exception | None = None
        for attempt in range(len(delays) + 1):
            conn = getattr(self._local, "conn", None)
            if conn is None:
                factory = http.client.HTTPSConnection if self.base.scheme == "https" else http.client.HTTPConnection
                conn = self._local.conn = factory(self.base.netloc, timeout=300)
            try:
                conn.request("POST", self.base.path + path, body=data, headers=headers)
                resp = conn.getresponse()
                payload = resp.read()
                if resp.status == 200:
                    with self._lock:
                        self._down_since = None
                    return json.loads(payload)
                error = RuntimeError(f"API {resp.status}: {payload[:300]!r}")
                if resp.status < 500 and resp.status != 429:
                    break
            except (OSError, http.client.HTTPException) as exc:
                error = exc
            conn.close()
            self._local.conn = None
            now = time.monotonic()
            with self._lock:
                if self._down_since is None:
                    self._down_since = now
                down = now - self._down_since
            if attempt == len(delays) or down > self.OUTAGE_LIMIT:
                break
            time.sleep(delays[attempt])
        raise RuntimeError(f"Model po API nie odpowiada ({self.name}): {self._explain(error)} [{error}]")

    def _line(self, prompt: str, max_tokens: int) -> str:
        out = self._post("/completions", {"model": self.model, "prompt": prompt, "max_tokens": max_tokens,
                                          "temperature": 0, "stop": ["\n", "<|im_end|>"]})
        self.last_stats["wygenerowane"] = self.last_stats.get("wygenerowane", 0) + out.get("usage", {}).get("completion_tokens", 0)
        self.last_stats["zapytania"] = self.last_stats.get("zapytania", 0) + 1
        return out["choices"][0]["text"]

    # ------------------------------------------------------------- prowadzone wypełnianie formularza
    def fill(self, system: str, static_user: str, doc_text: str, sections: list[tuple[str, bool, list[str]]],
             max_value_tokens: int = 200, max_items: int = 8, signed: frozenset[str] = frozenset(),
             min_items: dict[str, int] | None = None) -> str:
        t0 = time.perf_counter()
        self.last_stats = {"wygenerowane": 0, "zapytania": 0}
        prompt = (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{static_user}{doc_text[:self.doc_chars]}"
                  f"<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
        backend = self

        class Session:
            def force(self, text: str) -> None:
                nonlocal prompt
                prompt += text

            def gen(self, max_tokens: int, dash_shortcut: bool) -> str:
                nonlocal prompt
                text = backend._line(prompt, max_tokens)
                value = text.strip()
                if dash_shortcut and value.startswith(backend.DASHES):
                    text, value = " -", "-"          # pusta wartość - jak w trybie lokalnym
                prompt += text
                return value

        answer = guided_fill(Session(), sections, max_value_tokens, max_items, signed, min_items)
        self.last_stats["czas_s"] = round(time.perf_counter() - t0, 2)
        return answer

    def complete(self, system: str, user: str, prefill: str, max_tokens: int) -> str:
        out = self._post("/chat/completions", {
            "model": self.model, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "chat_template_kwargs": {"enable_thinking": False}})
        content = out["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def make_backend(model_path: str, n_threads: int):
    base = os.environ.get("O2J_API_BASE")
    if base:
        return OpenAIBackend(base, os.environ.get("O2J_API_MODEL", "default"), os.environ.get("O2J_API_KEY"))
    return LlamaCppBackend(model_path, n_threads)
