@echo off
REM Quick Setup: Online Video Streaming dengan Ngrok
REM Jalankan script ini untuk expose CV stream ke internet

echo ========================================
echo   EPSIGHT CV - Online Stream Setup
echo ========================================
echo.

REM Check if ngrok installed
where ngrok >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Ngrok tidak ditemukan!
    echo.
    echo Download ngrok dari: https://ngrok.com/download
    echo Atau install via Chocolatey: choco install ngrok
    echo.
    pause
    exit /b 1
)

echo [1/3] Checking CV program...
if not exist "Main-ProgramV7.py" (
    echo [ERROR] Main-ProgramV7.py tidak ditemukan!
    echo Pastikan script ini dijalankan di folder epsight-metric-mainprogram
    pause
    exit /b 1
)

echo [2/3] Starting CV program...
start "CV Program" cmd /k "python Main-ProgramV7.py"
timeout /t 5 /nobreak >nul

echo [3/3] Starting ngrok tunnel...
echo.
echo ========================================
echo   COPY URL NGROK DI BAWAH INI:
echo ========================================
echo.
echo Ganti di frontend (operator/+page.svelte):
echo   const streamUrl = "https://YOUR-NGROK-URL.ngrok.io"
echo.
echo ========================================
echo.

ngrok http 5000

REM Cleanup on exit
taskkill /FI "WINDOWTITLE eq CV Program*" /T /F >nul 2>nul
