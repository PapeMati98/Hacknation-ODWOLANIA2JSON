"""Odwołania2json: PDF sprawy odwoławczej KIO -> JSON według schematu UZP."""
from __future__ import annotations

import os
from pathlib import Path


def load_api_env(path: Path | None = None) -> list[str]:
    """Wczytuje ustawienia modelu po API z pliku `api.env` leżącego obok programu (linie NAZWA=wartość,
    `#` zaczyna komentarz). Zmienna ustawiona już w środowisku ma pierwszeństwo. Zwraca nazwy ustawione z pliku."""
    path = path or Path(__file__).resolve().parent.parent / "api.env"
    loaded = []
    if not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, sep, value = line.strip().partition("=")
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if sep and name.startswith("O2J_") and value and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded


load_api_env()
