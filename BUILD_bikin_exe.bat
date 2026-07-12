@echo off
title Build Deteksi Anomali HPP
echo ==================================================
echo   MEMBUAT APLIKASI Deteksi Anomali HPP (.exe)
echo ==================================================
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
echo [1/2] Memasang komponen yang dibutuhkan...
python -m pip install --upgrade pip
python -m pip install pandas dbfread openpyxl pyinstaller
if errorlevel 1 ( echo [!] Gagal memasang komponen. & pause & exit /b )
echo.
echo [2/2] Membuat file EXE (bisa makan beberapa menit)...
python -m PyInstaller --onefile --windowed --name "DeteksiAnomaliHPP" DeteksiAnomaliHPP.py
if errorlevel 1 ( echo [!] Build gagal. & pause & exit /b )
echo.
echo ==================================================
echo   SELESAI!
echo   File EXE ada di:  dist\DeteksiAnomaliHPP.exe
echo   Copy file itu ke komputer server/kasir, dobel-klik utk pakai.
echo ==================================================
pause
