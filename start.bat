@echo off
title CowTribe Dashboard v2 Launcher
echo.
echo  ================================================
echo   CowTribe Dashboard v2  -  Auto-Refresh Mode
echo  ================================================
echo.
echo  [1/2] Starting background data updater (every 5 min)...
start "CowTribe Data Updater v2" cmd /k "cd /d d:\company-dashboard-v2 && python scripts\data_updater.py"

timeout /t 2 /nobreak > nul

echo  [2/2] Launching Streamlit dashboard...
echo         http://localhost:8502
echo.
python -m streamlit run d:\company-dashboard-v2\dashboard\app.py --server.port 8502
