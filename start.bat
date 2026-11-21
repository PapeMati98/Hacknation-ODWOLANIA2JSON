@echo off
rem Odwolania2json: przetwarza input\<sprawa>\*.pdf -> output\<sprawa>\<nazwa>.json (CPU, bez GPU).
rem Model jezykowy: po API (plik api.env albo zmienne O2J_API_*) albo lokalny plik GGUF.
rem Pierwsze uruchomienie pobiera biblioteki i modele OCR (ok. 2 min); w trybie lokalnym takze model jezykowy 2,7 GB.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tworzenie srodowiska Python...
    set "PY="
    py -3.13 -c "print(1)" >nul 2>&1 && set "PY=py -3.13"
    if not defined PY py -3.14 -c "print(1)" >nul 2>&1 && set "PY=py -3.14"
    if not defined PY py -3.12 -c "print(1)" >nul 2>&1 && set "PY=py -3.12"
    if not defined PY python -c "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>&1 && set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
    if not defined PY (
        echo Nie znaleziono Pythona 3.12-3.14. Zainstaluj Python 3.13 z https://www.python.org/downloads/ ^(z opcja "py launcher"^) i uruchom ponownie.
        exit /b 1
    )
    %PY% -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
    rem Modele OCR pobieramy od razu, zeby samo przetwarzanie nie wymagalo juz internetu.
    ".venv\Scripts\python.exe" tools\download_models.py --ocr-only || goto :error
)

rem Model po API (zmienna O2J_API_BASE albo plik api.env): lokalnego modelu nie trzeba pobierac.
if defined O2J_API_BASE goto :run
if exist "api.env" goto :run
rem Tryb lokalny: biblioteka llama.cpp z gotowego kola (bez kompilacji) i plik modelu.
".venv\Scripts\python.exe" -c "import llama_cpp" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Instalacja biblioteki modelu lokalnego ^(llama.cpp^)...
    ".venv\Scripts\python.exe" -m pip install -r requirements-local.txt || goto :error
)
if not exist "models\Qwen3.5-4B-Q4_K_M.gguf" (
    echo [2/3] Pobieranie modelu Qwen3.5-4B GGUF ^(Apache-2.0, 2,7 GB^)...
    echo       Bez internetu: skopiuj plik Qwen3.5-4B-Q4_K_M.gguf do folderu models i uruchom ponownie.
    ".venv\Scripts\python.exe" tools\download_models.py || goto :error
)

:run
echo [3/3] Przetwarzanie dokumentow...
".venv\Scripts\python.exe" -m odwolania2json %*
exit /b %errorlevel%

:error
echo Blad - szczegoly powyzej.
exit /b 1
