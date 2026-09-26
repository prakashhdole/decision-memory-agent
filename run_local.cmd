@echo off
REM Start the app so ONLY this laptop can open it: http://localhost:8501
cd /d "%~dp0"
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m streamlit run app.py --server.address localhost
