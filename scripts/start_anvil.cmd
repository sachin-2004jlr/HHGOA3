@echo off
REM Start a local Anvil dev chain with persistent state (survives restarts).
set ROOT=%~dp0..
if not exist "%ROOT%\.anvil" mkdir "%ROOT%\.anvil"
set ANVIL=%ROOT%\tools\foundry\anvil.exe
if not exist "%ANVIL%" (
  where anvil >nul 2>nul && set ANVIL=anvil
)
if not exist "%ANVIL%" if not "%ANVIL%"=="anvil" (
  echo anvil.exe not found. Run:  python scripts\get_anvil.py
  exit /b 1
)
echo Starting Anvil (chain id 31337) at http://127.0.0.1:8545  -- state file: %ROOT%\.anvil\state.json
"%ANVIL%" --state "%ROOT%\.anvil\state.json" --state-interval 5 %*
