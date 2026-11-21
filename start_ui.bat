@echo off
rem Odwolania2json Web UI: upload PDF, podglad JSON, sladu ekstrakcji i klas YAML (CPU, bez GPU).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tworzenie srodowiska Python 3.13...
    py -3.13 -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

rem Model po API (zmienna O2J_API_BASE albo plik api.env): lokalnego modelu nie trzeba instalowac ani pobierac.
if defined O2J_API_BASE goto :run
if exist "api.env" goto :run
".venv\Scripts\python.exe" -c "import llama_cpp" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Instalacja biblioteki modelu lokalnego ^(llama.cpp^)...
    ".venv\Scripts\python.exe" -m pip install -r requirements-local.txt || goto :error
)
if not exist "models\Qwen3.5-4B-Q4_K_M.gguf" (
    echo [2/3] Pobieranie modelu Qwen3.5-4B GGUF ^(Apache-2.0^)...
    ".venv\Scripts\python.exe" tools\download_models.py || goto :error
)

:run

echo [3/3] Uruchamianie Web UI pod adresem http://127.0.0.1:8080 ...
".venv\Scripts\python.exe" -m odwolania2json.web %*
exit /b %errorlevel%

:error
echo Blad - szczegoly powyzej.
exit /b 1
