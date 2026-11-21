Write-Host ""
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host "  CowTribe Dashboard v2  -  Auto-Refresh Mode" -ForegroundColor Cyan
Write-Host " ================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host " [1/2] Starting background data updater (every 5 min)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'd:\company-dashboard-v2'; python scripts\data_updater.py" -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host " [2/2] Launching Streamlit dashboard..." -ForegroundColor Yellow
Write-Host "        http://localhost:8502" -ForegroundColor Green
Write-Host ""

python -m streamlit run d:\company-dashboard-v2\dashboard\app.py --server.port 8502
