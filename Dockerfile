# Odwołania2json - obraz CPU (bez GPU). Budowanie: docker compose build
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Narzędzia kompilacji są potrzebne tylko wtedy, gdy dla danej platformy nie ma gotowego koła llama-cpp-python.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# Modele OCR (PP-OCR ONNX) pobierane podczas budowania - kontener nie potrzebuje ich potem z sieci.
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"

COPY odwolania2json ./odwolania2json
COPY configs ./configs
COPY tools ./tools

# Model językowy (2,5 GB) leży w podmontowanym katalogu models/; brakujący jest pobierany przy starcie.
CMD ["sh", "-c", "python tools/download_models.py && python -m odwolania2json"]
