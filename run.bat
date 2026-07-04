@echo off
echo Starting NodeView Platform...
echo ==========================================

REM Install dependencies automatically
echo [1/3] Resolving Python dependencies...
python -m pip install --upgrade pip
pip install -r server/requirements.txt
pip install -r agent/requirements.txt

REM Start FastAPI Server in a separate console window
echo [2/3] Starting Central C2 Server on http://localhost:8000 ...
start "NodeView C2 Server" cmd /k "cd server && python main.py"

REM Give server time to bind the port
timeout /t 3 /nobreak > NUL

REM Start Simulated Agent 1
echo [3/3] Launching Simulated Agent (East-Segment)...
start "Agent East Segment" cmd /k "cd agent && python agent.py --name Agent-East --mock"

REM Start Simulated Agent 2
echo Launching Simulated Agent (West-Segment)...
start "Agent West Segment" cmd /k "cd agent && python agent.py --name Agent-West --mock"

echo ==========================================
echo NodeView successfully launched!
echo Open your browser and navigate to: http://localhost:8000
echo ==========================================
pause
