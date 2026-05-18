@echo off
cd /d "%~dp0"

echo Starting Bid Price AI MVP...
echo Folder: %cd%
echo.

if not exist ".streamlit" mkdir ".streamlit"
if not exist ".streamlit\config.toml" (
    echo [browser] > ".streamlit\config.toml"
    echo gatherUsageStats = false >> ".streamlit\config.toml"
)

python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo Installing required Python packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Package installation failed.
        pause
        exit /b 1
    )
)

echo Restarting local app server...
powershell -NoProfile -Command "$ports=@(8502); foreach($p in $ports){ $lines=netstat -ano | Select-String (':' + $p); foreach($line in $lines){ $parts=($line.ToString() -split '\s+') | Where-Object { $_ }; if($parts.Count -ge 5){ $pid=[int]$parts[-1]; Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } } }"
ping 127.0.0.1 -n 2 >nul
start "Bid AI Streamlit Server" cmd /k "cd /d ""%~dp0"" && python -m streamlit run app.py --server.port 8502 --server.headless true --browser.gatherUsageStats false"
ping 127.0.0.1 -n 5 >nul

start "" "http://localhost:8502"
echo Opened: http://localhost:8502
echo You can close this window.
ping 127.0.0.1 -n 3 >nul
