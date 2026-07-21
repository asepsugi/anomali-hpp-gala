# CLAUDE.md — Audit Data Toko SERBA INDAH

Konteks untuk Claude Code / developer yang melanjutkan project ini. Baca dulu sebelum
mengubah kode atau menafsirkan data. Banyak isi di sini hasil investigasi yang sudah
terbukti dari data + string aplikasi, termasuk beberapa kesimpulan yang SEMPAT SALAH
lalu dikoreksi (lihat "Sejarah kesimpulan yang salah") — jangan diulang.

> Catatan gabungan: dokumen ini hasil MERGE dua sesi Claude. Pemahaman data model +
> engine dari sesi audit (folder `serba-indah-audit/`, kini terserap), dan GUI gabungan
> + fitur aplikasi dari sesi Claude Code. Folder `serba-indah-audit/` dibiarkan sebagai
> arsip pembanding; boleh dihapus bila sudah tidak perlu.

## Tujuan

Kumpulan tool terpisah (read-only) untuk mengaudit data penjualan aplikasi kasir
existing. Dua detektor sudah dibangun:
1. Deteksi anomali HPP (harga pokok salah tampil di laporan Laba) — `hpp_engine.py`.
2. Deteksi kesalahan input satuan (satuan jual salah pilih) — `DeteksiAnomaliSatuan.py`.

BUKAN memodifikasi aplikasi kasir. Output: Excel/CSV daftar temuan untuk audit manual.

Konteks orang: pemilik toko non-teknis (butuh .exe dobel-klik). Developer (user) membangun
sendiri. Rencana rebuild aplikasi kasir DITUNDA (alur bisnis existing belum terpetakan).

## Sistem yang diaudit

Aplikasi kasir "SERBA INDAH", Visual FoxPro 8, EXE `sip-new2023.exe`,
`Copyright (c) 2014 - MIFTACHUDDIN`. Data = file DBF/CDX, di-share Samba dari server
Ubuntu, ter-mapping drive `Z:` (`\\UBUNTU`). VFP end-of-life; DBF multi-user rawan corrupt.

BATAS LEGAL: EXE milik developer lain. Membaca string/formula untuk diagnosis = wajar.
JANGAN dekompilasi penuh / modifikasi / distribusi ulang source. Perbaikan aplikasi
kasir = domain developer aslinya.

## Tabel & field penting (di ./data)

- `JUAL.DBF` — baris penjualan. Field: TANGGAL, NOFAKTUR, KODEBRG, NAMABRG, SATUAN,
  JUMLAH, ISISATUAN, HARGABELI, HARGAJUAL, GANTI, NAMAUSER. Faktur diawali `R`/`T` =
  retur/transfer (dikecualikan).
- `STOK.DBF` — master (1 baris per barang, 721 barang). Field kunci:
  - SATUAN (satuan dasar), ISISAT2/SATUAN2, ISISAT3/SATUAN3 (satuan ke-2/3 + faktor isi)
  - HARGABELI, HARGARATA2 (harga pokok per satuan dasar, TERKINI)
  - HARGAJUAL1/2/3 (harga JUAL per satuan tingkat 1/2/3, TERKINI)
  - HRGKHS*/DISC* (harga khusus & diskon), TGLHARGA (tgl harga terakhir diubah)
  - NONSTOK, SERVICE (penanda jasa/non-stok)
- `BELI.DBF` — pembelian ke supplier (bertanggal).
- `masterjl.DBF` — harga jual per-customer bertanggal (KODECUST, KODEBRG, HARGAJUAL,
  TANGGAL). Ada beberapa baris per pasangan = semacam riwayat, tapi BERANTAKAN
  (per-customer, satuan tercampur, tidak lengkap).
- `masterbl.DBF` — harga beli per-supplier bertanggal.
- `kas.DBF`, `produksi.dbf`, `tranpiut.dbf` (piutang) — belum dipakai.

### MODEL DATA JUMLAH vs ISISATUAN (penting, sudah diverifikasi 100%)
- `JUMLAH`   = jumlah dalam SATUAN DASAR (mis. PCS).
- `ISISATUAN`= jumlah dalam SATUAN JUAL (angka "Banyak" yang tampil di layar).
- `JUMLAH / ISISATUAN` = faktor isi per satuan jual (selalu bilangan bulat).
- Penjualan satuan dasar: `ISISATUAN == JUMLAH` (100% dari 113rb baris).
- Contoh: 6 PAK @ 2 PCS  -> JUMLAH=12, ISISATUAN=6, SATUAN=PAK.
Jadi kolom "JUMLAH" mentah = satuan dasar; untuk cocok dgn faktur pakai ISISATUAN.
(Koreksi atas versi lama yang menyebut ISISATUAN/JUMLAH "tidak konsisten" — TIDAK, sudah
terverifikasi konsisten seperti di atas.)

### NO price-history untuk harga master
STOK hanya simpan harga TERKINI (+TGLHARGA). Tidak ada tabel riwayat perubahan harga
jual/beli master. Riwayat terbaik = HARGAJUAL/HARGABELI di JUAL/BELI itu sendiri.

## Cara aplikasi menghitung HPP di laporan Laba (FAKTA KUNCI)

HPP yang DITAMPILKAN = operasi pada JUAL.HARGABELI per baris:
    HPP_LAYAR = IIF(ISISATUAN<>JUMLAH, HARGABELI/ISISATUAN, HARGABELI/JUMLAH)
(Terbukti: layar menampilkan 13.699 = 13699,63/1.) Nilai ini BISA SALAH karena
HARGABELI tersimpan tidak konsisten (kadang total, kadang per-satuan).
HPP yang BENAR = harga pokok master x faktor konversi satuan.

### Sejarah kesimpulan yang salah (JANGAN diulang)
1. "HPP dominan = modus per (barang,satuan,bulan)" -> SALAH pada sampel kecil.
2. "Laporan menghitung HPP dari master, bukan HARGABELI" -> SALAH; dipicu jawaban user
   yang keliru. Screenshot membuktikan laporan pakai HARGABELI mentah.
3. Detektor satuan versi lama membandingkan harga faktur dgn harga jual MASTER TERKINI
   -> banyak false positive saat harga berubah. Sudah diganti dgn median riwayat (lihat
   Detektor 2). File engine satuan lama (berbasis HARGAJUAL1/2/3) sudah TIDAK dipakai.
4. "HPP_LAYAR utk baris satuan-tingkat = HARGABELI x faktor (bukan HARGABELI/ISISATUAN)"
   -> SALAH sbg aturan umum. Dipicu 1 contoh (LABEL KOALA BALL: app tampil 73.750 =
   2.950 x 25). Investigasi 20.840 baris satuan-tingkat: HARGABELI tersimpan sebagai TOTAL
   pada ~74% (formula HARGABELI/ISISATUAN benar), hanya ~3% per-satuan-dasar (spt LABEL
   KOALA). Mengubah formula ke HARGABELI x faktor meledakkan anomali 10x (381 -> ~3.540 di
   2024). DIBATALKAN: HARGABELI tak konsisten & tak bisa dibedakan andal dari data. LABEL
   KOALA BALL tetap ter-flag tapi berlabel "NILAI POKOK BENAR" (benign, bukan perlu koreksi).

## Detektor 1: anomali HPP (`hpp_engine.py :: detect_anomalies`)
- HPP_LAYAR = formula aplikasi di atas (HARGABELI/ISISATUAN bila beda, else HARGABELI/JUMLAH).
- FAKTOR dari master (dasar=1, SATUAN2->ISISAT2, SATUAN3->ISISAT3).
- BASIS = HPP_LAYAR/FAKTOR.
- REF_DASAR = SADAR-WAKTU: median BASIS per barang dlm jendela WAKTU MUNDUR (trailing
  `WINDOW_REF`=180 hari) sebelum/saat tanggal faktur, DIPELAJARI dari SELURUH riwayat
  (bukan hanya periode terpilih; periode hanya menyaring baris yg dilaporkan). Fallback:
  bila jendela mundur <3 sampel -> median seluruh riwayat, lalu harga pokok master.
  Alasan: harga pokok berubah antar-batch; median seluruh masa salah-tuduh penjualan di
  masa harga tinggi. Contoh terbukti: LOOSE LEAF A5 (faktur 2401-000546/000605, Jan 2024)
  batch saat itu 6.250 (bukan 3.250 rata2 sepanjang masa) -> dulu HAMPIR PASTI, kini lolos.
  (Perubahan ini count-neutral: 2024 ~385 anomali, hampir sama dgn 381 versi median-periode.)
- HPP_BENAR = REF_DASAR x FAKTOR. DEV_PCT = |HPP_LAYAR-HPP_BENAR|/HPP_BENAR.
- Anomali bila DEV_PCT > ambang (default 50%). KEYAKINAN: >90% HAMPIR PASTI, >70% TINGGI.
- SEBAB: TOTAL BENAR (HARGABELI/JUMLAH~ref) / NILAI POKOK BENAR (HARGABELI~ref) /
  HARGA POKOK SALAH (tak cocok -> perlu koreksi angka; ini prioritas audit).
- GUARD konsistensi kuantitas (penting): satuan jual menyiratkan jumlah dasar =
  ISISATUAN x FAKTOR. Bila JUMLAH tercatat LEBIH KECIL dari itu (undercount, mis. 1 BALL
  faktor 25 tapi JUMLAH=1, HARGABELI 3.600), maka HARGABELI/JUMLAH cocok ref HANYA gara-
  gara JUMLAH-nya salah -> jangan dicap "TOTAL BENAR", paksa ke HARGA POKOK SALAH (biaya
  understated, perlu koreksi). JUMLAH lebih BESAR dari tersirat = label satuan salah tapi
  jumlah dasar benar -> tetap boleh TOTAL BENAR. Contoh terbukti: faktur 2602-001094
  (LABEL KOALA 103 POLOS, BALL, JUMLAH=1) semula salah dicap TOTAL BENAR, kini HARGA
  POKOK SALAH. Lawannya 2601-000810 (BUSSINES FILE, PCS, JUMLAH=24) tetap TOTAL BENAR.
- DAMPAK_RL = KASAR, hanya untuk urutan prioritas (bukan nominal rugi).
- Zona 30-50% didominasi variasi harga wajar; makanya default 50%, bukan 30%.

## Detektor 2: kesalahan input satuan (`DeteksiAnomaliSatuan.py :: detect_unit_errors`)
Versi TAHAN HARGA-USANG (median riwayat penjualan, bukan master). Signature & output
kompatibel drop-in dengan GUI: `detect_unit_errors(db_folder, date_from, date_to,
dev_threshold=0.60, match_tol=0.25, progress=None)` + `write_report(res, ring, out)`.
- "Wajar/tidak untuk satuan yg diinput" -> median HARGAJUAL per (barang,satuan) dari
  RIWAYAT PENJUALAN (JUAL), BUKAN harga master. -> tahan harga usang (mis. BATRE PAK
  yang lazimnya 12.700 tidak lagi salah-tuduh walau master masih 6.500).
- PENTING: patokan median dipelajari dari SELURUH riwayat (semua tanggal); periode
  terpilih hanya menyaring baris yang DILAPORKAN. Kalau median dibatasi periode, periode
  pendek bisa menyembunyikan anomali (baris rusak jadi satu-satunya sampel -> median =
  harga rusak -> lolos). Contoh terbukti: faktur 2601-000810 (BUSSINES FILE RED, diinput
  PCS @31.500 padahal itu harga LSN) hilang saat median per-periode, muncul lagi setelah
  median seluruh riwayat.
- "Satuan yg seharusnya" -> diutamakan MEDIAN ASLI satuan lain di riwayat (mis. LSN
  31.500 cocok persis), fallback ke struktur faktor isi x harga dasar bila tak berdata.
- TIGA kategori temuan:
  1. SALAH SATUAN: satuan TERDAFTAR di master, HARGAJUAL menyimpang > ambang dari harga
     lazim satuan diinput DAN cocok satuan lain (match_tol 25%). Yakin.
  2. HARGA JANGGAL (cek manual): satuan TERDAFTAR, menyimpang > ambang, tapi tak cocok
     satuan mana pun.
  3. SATUAN TAK DIKENAL (cek master): satuan diinput TIDAK ADA di master barang (mis. LEM
     GLR-50 diinput BOX padahal master cuma PCS/LSN). SELALU di-flag, TAK peduli ambang,
     karena memakai satuan tak-terdaftar = pasti salah input. SATUAN_SEHARUSNYA tetap diisi
     bila ketemu tebakan (BOX -> LSN). Ini menyurface ~329 baris yang DULU jadi blind spot.
- GUARD "satuan plausibel" HANYA utk satuan TERDAFTAR: bila `(barang,satuan diinput)` ADA
  di master DAN HARGAJUAL masih dekat (<= match_tol 25%) harga lazim satuan itu -> TIDAK
  di-flag. Membuang false positive: BP STANDAR BIG GEL (PAK terdaftar, jual 63.000 vs lazim
  PAK 62.500 = 0,8%). Guard TIDAK berlaku utk satuan tak-terdaftar (lihat kategori 3).
  Lantai efektif utk satuan terdaftar = max(dev_threshold, match_tol=25%); default 60% tak
  berubah. (Pelajaran: guard versi awal tanpa syarat "terdaftar" sempat mematikan LEM GLR-50;
  kini dibedakan lewat keanggotaan satuan di master.)
- Output punya kolom DEV_PCT. Warna: MERAH=SALAH SATUAN, ORANYE=HARGA JANGGAL, BIRU=SATUAN
  TAK DIKENAL.
- `MIN_HIST=2`: barang+satuan TERDAFTAR dengan <2 transaksi tidak dinilai (patokan tak layak;
  tak berlaku utk satuan tak-terdaftar yang selalu di-flag).
- Barang jasa/non-stok (ONGKOS, NONSTOK, SERVICE) dikecualikan.
- Batas: andal utk faktor besar (PAK 250, RIM 500); rawan utk faktor kecil (PCS<->PAK
  isi 2) karena perubahan harga ~2x mirip swap.

## Aplikasi GUI gabungan (`DeteksiAnomali.py`)
Satu GUI, dua mode (radio button): "Anomali HPP" dan "Kesalahan Satuan". Mengimpor
`hpp_engine` dan `DeteksiAnomaliSatuan` sebagai engine.
- Pemilih folder database: default `Z:\`, tombol Pilih, validasi ada JUAL.DBF & STOK.DBF.
- Folder terakhir DISIMPAN di `~/.deteksi_anomali.json` -> tak perlu pilih ulang.
- Tanggal MULAI/SAMPAI pakai widget kalender `tkcalendar` (DateEntry); fallback ke
  ketik-manual bila tkcalendar tak terpasang. Butuh `--hidden-import babel.numbers`
  saat build PyInstaller.
- Pilihan ambang berubah menurut mode: HPP = 0.1/30/50/70/90% (default 50%),
  Satuan = 0.1/40/60/80% (default 60%),
  HARGABELI = tak pakai ambang (combobox dinonaktifkan).
- Output Excel ke sub-folder `output/` di sebelah program (`sys.frozen` -> folder .exe,
  else folder skrip), nama file `Anomali_HPP_...` / `Anomali_Satuan_...`, lalu dibuka.

## Laporan tambahan: HARGABELI salah-satuan (`LaporanHargabeliSatuan.py`)
Bukan detektor hitung, tapi daftar PEMBENAHAN INPUT untuk aplikasi kasir. Menemukan baris
jual satuan-tingkat (BALL/LSN/RIM/DUS) yang HARGABELI-nya diisi PER-SATUAN-DASAR (mis. per
PAK) bukan total -> HPP understated, laba ter-overstate. Ini persis kasus "3% HARGABELI
per-satuan-dasar" (lihat Sejarah kesimpulan salah #4); di layar app HPP tampak benar tapi
angka HARGABELI tersimpan keliru. Deteksi: REFBASE (harga pokok/satuan dasar dari baris
satuan dasar, median riwayat) vs HARGABELI; ditandai bila HARGABELI ~ REFBASE (1x) padahal
mestinya ~ REFBASE x JUMLAH. Output Excel: Ringkasan + Per Barang + Detail. CLI:
`python3 LaporanHargabeliSatuan.py [folder] [mulai] [sampai]` (tanpa tanggal = seluruh data).
Skala terukur (seluruh data): ~691 transaksi, ~142 barang, perkiraan laba ter-overstate
~Rp 135,8 jt (top: LABEL KOALA BALL, BUKU GAMBAR KECIL, SPIDOL W.B). DAMPAK kasar.

## File project
- `hpp_engine.py`, `DeteksiAnomaliSatuan.py` — engine murni (bisa diuji headless).
- `DeteksiAnomali.py` — GUI tkinter GABUNGAN (HPP + Satuan). Ini yang dibuild jadi .exe.
- `analisa.py` — CLI headless (lihat memory: `python3 analisa.py <mulai> <sampai> [ambang]`).
- `LaporanHargabeliSatuan.py` — laporan HARGABELI salah-satuan (lihat bagian di atas).
- `BUILD_bikin_exe.bat`, `requirements.txt`, `CARA_PAKAI.txt`.
- `data/` — salinan DBF untuk pengembangan (JANGAN tulis balik; ini read-only source).
- `serba-indah-audit/` — arsip sesi audit (sumber merge; boleh dihapus).

## Menjalankan
`pip install -r requirements.txt` (Mac/Linux: pip3). Termasuk `tkcalendar`.
Contoh headless HPP:
```
import pandas as pd
from hpp_engine import detect_anomalies, write_report
anom, ring = detect_anomalies('data', pd.Timestamp('2024-01-01'),
                              pd.Timestamp('2026-07-11'), tolerance=0.50)
```
Contoh headless Satuan:
```
import pandas as pd
from DeteksiAnomaliSatuan import detect_unit_errors, write_report
res, ring = detect_unit_errors('data', pd.Timestamp('2024-01-01'),
                               pd.Timestamp('2026-07-31'), dev_threshold=0.60)
```
Build .exe HANYA di Windows (PyInstaller tak bisa cross-compile; build di Mac -> app Mac).
Pakai `BUILD_bikin_exe.bat` (sudah memasang tkcalendar & pakai --hidden-import babel.numbers):
`pyinstaller --onefile --windowed --name "DeteksiAnomali" --hidden-import babel.numbers DeteksiAnomali.py`

## Gotchas
- Kerja dari salinan DBF; jangan tulis ke file live. Baca saat aplikasi aktif = aman
  (read-only) tapi idealnya saat sepi.
- 329 baris bersatuan tak terdaftar di master: DULU blind spot; kini di-flag Detektor 2
  sbg "SATUAN TAK DIKENAL" (satuannya jelas salah, walau harga pokok/koreksi belum tentu jelas).
- DAMPAK_RL kasar; jangan jadi angka rugi.
- Detektor satuan: HARGA JANGGAL itu campur (sebagian variasi harga wajar) -> cek manual.
- Antivirus kadang salah-curiga pada .exe --onefile; jika kena, ganti ke `--onedir`.

## Langkah berikutnya (belum)
- Kelompokkan bucket "HARGA POKOK SALAH" per barang -> tentukan harga pokok benar sekali.
- Deteksi terpisah untuk baris satuan tak-dikenal (lengkapi master dulu).
- (Ditunda) Rebuild kasir: PostgreSQL + UOM satu satuan dasar + kartu stok.
