@echo off
rem Odwolania2json: przetwarza input\<sprawa>\*.pdf -> output\<sprawa>\<nazwa>.json (CPU, bez GPU).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tworzenie srodowiska Python 3.13...
    py -3.13 -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu || goto :error
)

if not exist "models\Qwen3.5-4B-Q4_K_M.gguf" (
    echo [2/3] Pobieranie modelu Qwen3.5-4B GGUF (Apache-2.0)...
    ".venv\Scripts\python.exe" tools\download_models.py || goto :error
)

echo [3/3] Przetwarzanie dokumentow...
".venv\Scripts\python.exe" -m odwolania2json %*
exit /b %errorlevel%

:error
echo Blad - szczegoly powyzej.
exit /b 1
