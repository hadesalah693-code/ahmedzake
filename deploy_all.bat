@echo off
chcp 65001 >nul
title نشر كامل - الوسام
cd /d "%~dp0"

echo.
echo ========================================
echo   نشر الوسام على GitHub + Render
echo ========================================
echo.

where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [خطأ] Git غير مثبت
    pause
    exit /b 1
)

git add .
git commit -m "update" 2>nul

set GH=%TEMP%\gh-cli\bin\gh.exe
if not exist "%GH%" (
    echo جاري تحميل GitHub CLI...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cli/cli/releases/download/v2.97.0/gh_2.97.0_windows_amd64.zip' -OutFile '%TEMP%\gh.zip'; Expand-Archive -Path '%TEMP%\gh.zip' -DestinationPath '%TEMP%\gh-cli' -Force"
)

echo.
echo === الخطوة 1: تسجيل الدخول لـ GitHub ===
"%GH%" auth status >nul 2>&1
if %errorlevel% neq 0 (
    echo افتح المتصفح وسجّل دخول GitHub...
    "%GH%" auth login -p https -h github.com -w
)

echo.
echo === الخطوة 2: رفع المشروع على GitHub ===
git remote remove origin 2>nul
git remote add origin https://github.com/hadesalah693-code/ahmedzake.git
git push -u origin main

echo.
echo === الخطوة 3: النشر على Render ===
echo افتح Render وسجّل دخول GitHub ثم:
echo 1) New ^> Blueprint
echo 2) اختر مستودع ahmedzake
echo 3) عيّن ADMIN_PASSWORD
echo 4) Deploy
echo.
start https://dashboard.render.com/blueprints
echo.
echo تم! بعد النشر افتح الرابط وادخل: admin / كلمة المرور
pause
