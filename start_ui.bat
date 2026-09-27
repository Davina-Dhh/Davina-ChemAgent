@echo off
cd /d "%~dp0"
echo ChemCrow Lab UI: http://localhost:8502
".venv\Scripts\streamlit.exe" run app.py --server.headless true --server.port 8502
pause
