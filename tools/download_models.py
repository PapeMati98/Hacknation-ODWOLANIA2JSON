"""Pobiera model GGUF (Apache-2.0) do katalogu models/ z przypiętą rewizją.

  python tools/download_models.py          # model domyślny (Qwen3.5-4B)
  python tools/download_models.py --all    # także mniejszy model 0.8B (tylko do porównań)
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

if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "models"
    for repo, revision, filename in MODELS + (EXTRA if "--all" in sys.argv else []):
        if (target / filename).is_file():
            print("jest już:", filename)
            continue
        print("pobieram", repo, filename)
        hf_hub_download(repo, filename, revision=revision, local_dir=target)
