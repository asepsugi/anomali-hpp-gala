@echo off
cd /d "%~dp0"
title Build Deteksi Anomali
echo ==================================================
echo   MEMBUAT APLIKASI Deteksi Anomali (.exe)
echo   (HPP + Satuan dalam satu aplikasi)
echo ==================================================
echo.
echo [1/3] Mengambil kode terbaru dari GitHub (git pull)...
git --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo ==================================================
  echo   [!] GIT TIDAK DITEMUKAN - kode TIDAK diperbarui.
  echo       Build akan memakai kode yang ADA di folder ini.
  echo ==================================================
  echo.
  echo   Tekan sembarang tombol untuk TETAP lanjut build,
  echo   atau TUTUP jendela ini untuk batal ^& perbaiki dulu.
  pause >nul
  goto after_pull
)
git pull origin main
if errorlevel 1 (
  echo.
  echo ==================================================
  echo   [!] GIT PULL GAGAL - KODE MUNGKIN BELUM TERUPDATE.
  echo       Kemungkinan ada perubahan lokal / tidak ada internet.
  echo ==================================================
  echo.
  echo   Tekan sembarang tombol untuk TETAP lanjut build,
  echo   atau TUTUP jendela ini untuk batal ^& perbaiki dulu.
  pause >nul
)
:after_pull
echo.
python --version >nul 2>&1
if errorlevel 1 (
  echo [!] Python belum terpasang.
  echo     Download di https://www.python.org/downloads/
  echo     Saat install, CENTANG "Add Python to PATH".
  echo.
  pause
  exit /b
)
echo [2/3] Memasang komponen yang dibutuhkan...
python -m pip install --upgrade pip
python -m pip install pandas dbfread openpyxl pyinstaller numpy tkcalendar
if errorlevel 1 ( echo [!] Gagal memasang komponen. & pause & exit /b )
echo.
echo [3/3] Membuat file EXE (bisa makan beberapa menit)...
echo     Menutup aplikasi lama bila masih berjalan...
taskkill /IM DeteksiAnomali.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul
if exist "dist\DeteksiAnomali.exe" del /f /q "dist\DeteksiAnomali.exe" >nul 2>&1
if exist "build" rmdir /s /q "build" >nul 2>&1
python -m PyInstaller --onefile --windowed --noconfirm --name "DeteksiAnomali" --hidden-import babel.numbers DeteksiAnomali.py
if errorlevel 1 (
  echo.
  echo [!] Build gagal.
  echo     Jika error "Access is denied" pada DeteksiAnomali.exe:
  echo       - Pastikan aplikasi DeteksiAnomali TIDAK sedang terbuka.
  echo       - Tutup jendela Explorer yang membuka folder dist.
  echo       - Matikan sementara antivirus, atau ganti --onefile menjadi --onedir.
  echo.
  pause
  exit /b
)
echo.
echo ==================================================
echo   SELESAI!
echo   File EXE ada di:  dist\DeteksiAnomali.exe
echo   Copy file itu ke komputer server/kasir, dobel-klik utk pakai.
echo ==================================================
pause
