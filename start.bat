@echo off
chcp 65001 >nul
title الوسام للخدمات الجامعية
echo.
echo ========================================
echo   الوسام للخدمات الجامعية
echo ========================================
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [خطأ] Python غير مثبت. حمّله من https://python.org
    pause
    exit /b 1
)

if not exist "venv" (
    echo جاري إعداد البيئة...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo جاري تشغيل البرنامج...
echo.
echo على هذا الجهاز:  http://127.0.0.1:5000
echo على الموبايل:    نفس رابط الشبكة الظاهر بالأسفل
echo                    (يجب الاتصال بنفس الواي فاي)
echo.
echo اذا لم يفتح من الموبايل شغّل open_firewall.bat كمسؤول
echo.
echo لإيقاف البرنامج اضغط Ctrl+C
echo.

start http://127.0.0.1:5000
python app.py
