@echo off
echo Starting Hashcat Server...
cd %~dp0
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
