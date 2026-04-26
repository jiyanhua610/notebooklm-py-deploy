@echo off
cd /d C:\notebooklm-py\app

:: Basic environment settings
set PYTHONPATH=src
set PYTHONUTF8=1

:: Run the service using the JSON configuration file (service_config.json)
:: The config file contains Token, Storage Path, and 30-day retention settings.
.venv\Scripts\python.exe -m uvicorn notebooklm.service.app:create_app --factory --host 0.0.0.0 --port 8000
