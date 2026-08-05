$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required and must already be available on PATH."
}

uv sync --extra dev
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe scripts\validate_documents.py
.venv\Scripts\python.exe scripts\initialize_databases.py
.venv\Scripts\python.exe scripts\seed_demo_data.py
.venv\Scripts\python.exe scripts\validate_platform_registry.py
.venv\Scripts\python.exe scripts\build_text_rag_index.py

Write-Output "Local setup and validation completed. No model download was requested."