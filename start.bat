@echo off
title CowTribe Dashboard Launcher
echo.
echo  ================================================
echo   CowTribe Dashboard  -  Auto-Refresh Mode
echo  ================================================
echo.
echo  [1/2] Starting background data updater (every 5 min)...
start "CowTribe Data Updater" cmd /k "cd /d d:\company-dashboard && python scripts\data_updater.py"

timeout /t 2 /nobreak > nul

echo  [2/2] Launching Streamlit dashboard...
echo         http://localhost:8501
echo.
python -m streamlit run d:\company-dashboard\dashboard\app.py
