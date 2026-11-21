"""Pobiera model GGUF (Apache-2.0) do katalogu models/ z przypiętą rewizją.

  python tools/download_models.py          # model domyślny (Qwen3.5-4B)
  python tools/download_models.py --all    # także mniejszy model 0.8B (tylko do porównań)
  python tools/download_models.py --vision # także projektor obrazu (672 MB) dla opcji --visual-reader on
  python tools/download_models.py --ocr-only   # same modele OCR (kilkanaście MB), bez modelu językowego
"""
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

MODELS = [
    ("unsloth/Qwen3.5-4B-GGUF", "e87f176479d0", "Qwen3.5-4B-Q4_K_M.gguf"),
]
EXTRA = [
    ("unsloth/Qwen3.5-0.8B-GGUF", "6ab461498e20", "Qwen3.5-0.8B-Q4_K_M.gguf"),
]

VISION = [
    ("unsloth/Qwen3.5-4B-GGUF", "e87f176479d0", "mmproj-F16.gguf"),
]

if __name__ == "__main__":
    # Modele OCR (PP-OCR ONNX) biblioteka pobiera przy pierwszym użyciu - robimy to tutaj, żeby samo
    # przetwarzanie dokumentów nie wymagało już internetu.
    from rapidocr import RapidOCR
    RapidOCR()
    print("modele OCR: gotowe")
    if "--ocr-only" in sys.argv:
        raise SystemExit(0)
    target = Path(__file__).resolve().parent.parent / "models"
    wanted = MODELS + (EXTRA if "--all" in sys.argv else []) + (VISION if "--vision" in sys.argv else [])
    for repo, revision, filename in wanted:
        if (target / filename).is_file():
            print("jest już:", filename)
            continue
        print("pobieram", repo, filename)
        hf_hub_download(repo, filename, revision=revision, local_dir=target)
