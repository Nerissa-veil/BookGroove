@echo off
cd /d "%~dp0"
echo Starting BookGroove...
python -m streamlit run app.py
if errorlevel 1 pause
