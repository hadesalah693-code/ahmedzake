@echo off
chcp 65001 >nul
title نشر على Render
echo.
echo ========================================
echo   نشر الوسام للخدمات الجامعية على Render
echo ========================================
echo.
echo الخطوات:
echo.
echo 1) ارفع المشروع على GitHub:
echo    - افتح https://github.com/new
echo    - اسم المستودع: alwisam
echo    - اختر Private او Public
echo    - لا تضف README
echo    - اضغط Create repository
echo.
echo 2) في Terminal داخل مجلد المشروع نفّذ:
echo    git remote add origin https://github.com/USERNAME/alwisam.git
echo    git push -u origin main
echo.
echo 3) افتح Render واربط المستودع:
echo    https://dashboard.render.com/blueprints
echo    - New Blueprint Instance
echo    - اختر المستودع alwisam
echo    - عيّن ADMIN_PASSWORD بكلمة مرور قوية
echo    - Deploy
echo.
echo 4) بعد النشر افتح الرابط وادخل:
echo    admin / كلمة المرور التي عيّنتها
echo.
start https://github.com/new
start https://dashboard.render.com/blueprints
pause
