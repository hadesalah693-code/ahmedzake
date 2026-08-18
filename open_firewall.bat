@echo off
chcp 65001 >nul
title فتح المنفذ للشبكة
echo.
echo ========================================
echo   السماح بالوصول من الشبكة (مرة واحدة)
echo ========================================
echo.
echo يحتاج صلاحيات المسؤول...
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo شغّل هذا الملف بالضغط يمين ^> تشغيل كمسؤول
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="AlWisam Port 5000" >nul 2>&1
netsh advfirewall firewall add rule name="AlWisam Port 5000" dir=in action=allow protocol=TCP localport=5000

echo.
echo تم فتح المنفذ 5000 بنجاح!
echo الآن يمكن فتح البرنامج من الموبايل على نفس الواي فاي.
echo.
pause
