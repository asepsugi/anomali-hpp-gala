# CLAUDE.md — Deteksi Anomali HPP (Toko SERBA INDAH)

Panduan konteks untuk Claude / developer yang mengerjakan project ini. Baca dulu
sebelum mengubah kode atau menafsirkan data. Banyak keputusan di sini adalah hasil
investigasi yang sudah terbukti, termasuk beberapa kesimpulan yang SEMPAT SALAH lalu
dikoreksi — bagian "Sejarah kesimpulan yang salah" ada supaya tidak diulang.

## Tujuan project

Aplikasi terpisah (read-only) untuk mendeteksi baris penjualan yang HPP-nya salah
tampil di laporan "Laba Penjualan" aplikasi kasir existing. BUKAN memodifikasi
aplikasi kasirnya. Output: file Excel/CSV berisi daftar anomali untuk diaudit manual.

Konteks orang:
- Pemilik toko: non-teknis ("gaptek"). Butuh 1 file .exe yang tinggal dobel-klik.
- Pengembang tool ini (user): membangun sendiri. Rencana rebuild aplikasi kasir
  DITUNDA (owner tidak paham detail alur bisnis aplikasi jadinya).

## Sistem yang diaudit

- Aplikasi kasir "SERBA INDAH", dibuat dengan Visual FoxPro 8 (lihat VFP8R.DLL,
  VFP8T.DLL). EXE: `sip-new2023.exe`. Footer: `Copyright (c) 2014 - MIFTACHUDDIN`.
- Data = file DBF/CDX (format FoxPro/dBase), di-share via Samba dari server Ubuntu,
  ter-mapping sebagai drive `Z:` (`\\UBUNTU`) di komputer Windows.
- VFP sudah end-of-life (Microsoft stop support 2015). DBF multi-user via network
  rawan index corrupt (ada banyak file .BAK). JUAL.DBF ~93 MB (limit DBF 2 GB/tabel).

### Batasan legal/etis
EXE adalah milik developer lain (MIFTACHUDDIN). Membaca string/formula dari EXE untuk
DIAGNOSIS itu wajar. JANGAN mendekompilasi penuh, memodifikasi, atau mendistribusikan
ulang source-nya. Perbaikan permanen pada aplikasi kasir = domain developer aslinya.

## Tabel DBF yang relevan

- `JUAL.DBF` — baris penjualan (sumber utama). Field dipakai: TANGGAL, NOFAKTUR,
  KODEBRG, NAMABRG, SATUAN, JUMLAH, ISISATUAN, HARGABELI, HARGAJUAL, GANTI, NAMAUSER.
  Rentang data ~2009 s/d sekarang. Faktur diawali `R` = retur, `T` = transfer
  (dikecualikan dari analisis).
- `STOK.DBF` — master barang. Field penting: KODEBRG, NAMABRG, SATUAN (satuan dasar),
  HARGABELI (harga pokok per satuan dasar, TERKINI), HARGARATA2, SATUAN2 + ISISAT2,
  SATUAN3 + ISISAT3 (satuan ke-2/ke-3 + faktor konversi ke satuan dasar), NONSTOK.
- `BELI.DBF` — pembelian ke supplier (KODESUPPL, KODEBRG, HARGABELI, TANGGAL, ...).
- `masterbl.DBF` — harga beli per supplier. `masterjl.DBF` — harga jual per customer.
- `kas.DBF`, `produksi.dbf`, `tranpiut.dbf` (piutang) — tidak dipakai tool ini.

### Model data yang membingungkan (SUMBER BUG)
`ISISATUAN` dan `JUMLAH` maknanya TIDAK konsisten antar-jalur input. Kadang
ISISATUAN = JUMLAH (penjualan satuan dasar), kadang ISISATUAN = faktor/jumlah unit
lain. `HARGABELI` di JUAL kadang berisi TOTAL, kadang PER-SATUAN. Inkonsistensi ini,
terutama pada barang multi-satuan (PCS/LSN/DUS), adalah akar semua anomali HPP.
Tombol "Ganti HPP" di layar laporan menimpa HARGABELI manual (menandai `GANTI=True`).

## FAKTA KUNCI: cara aplikasi menghitung HPP di laporan Laba

HPP yang DITAMPILKAN di kolom laporan = operasi pada `JUAL.HARGABELI` per baris:

    HPP_LAYAR = IIF(ISISATUAN <> JUMLAH, HARGABELI/ISISATUAN, HARGABELI/JUMLAH)

Terbukti: screenshot menampilkan HPP 13.699 untuk baris ISISATUAN=1 → 13699,63/1.
Nilai ini BISA SALAH karena HARGABELI tersimpan tidak konsisten.

HPP yang BENAR (seharusnya) = harga pokok master × faktor konversi satuan:

    HPP_BENAR = REF_DASAR × FAKTOR(kode, satuan)

FAKTOR: satuan dasar = 1; SATUAN2 → ISISAT2; SATUAN3 → ISISAT3 (dari STOK.DBF).

### Sejarah kesimpulan yang salah (JANGAN diulang)
1. Sempat pakai "HPP dominan = modus per (barang, satuan, bulan)". SALAH: pada sampel
   kecil, modus memilih nilai rusak sebagai patokan sehingga baris BENAR ter-flag.
   Ganti dengan REF_DASAR (lihat di bawah).
2. Sempat menyimpulkan laporan menghitung HPP dari master (bukan HARGABELI). SALAH —
   dipicu jawaban user yang keliru diingat. Screenshot membuktikan laporan pakai
   HARGABELI mentah (HPP_LAYAR di atas). Master hanya dipakai sebagai PATOKAN BENAR,
   bukan sumber tampilan.

## Metodologi deteksi (versi final & benar)

Diimplementasikan di `hpp_engine.py :: detect_anomalies()`:

1. Muat JUAL.DBF, saring periode, buang faktur R*/T*.
2. `HPP_LAYAR` = formula aplikasi di atas.
3. `FAKTOR` per baris dari master STOK. Baris dengan satuan TIDAK terdaftar di master
   → FAKTOR NaN → TIDAK bisa diverifikasi → dikeluarkan dari daftar (dihitung terpisah).
4. `BASIS` = HPP_LAYAR / FAKTOR (normalisasi ke satuan dasar).
5. `REF_DASAR` = median BASIS per barang sepanjang periode (bila ≥3 baris), else
   harga pokok master. MEDIAN dipilih karena tahan terhadap perubahan harga historis;
   master HARGABELI adalah harga TERKINI (bisa meleset untuk transaksi lama).
6. `HPP_BENAR` = REF_DASAR × FAKTOR. `DEV_PCT` = |HPP_LAYAR−HPP_BENAR|/HPP_BENAR×100.
7. Anomali bila DEV_PCT > ambang (default 50%), FAKTOR diketahui, HPP_BENAR > 0.
8. `KEYAKINAN`: >90% HAMPIR PASTI, >70% TINGGI, selain itu SEDANG.
9. `RASIO` = HPP_LAYAR/HPP_BENAR. Dekat kelipatan bulat (12; 0,08; 0,5) = kuat indikasi
   salah konversi satuan.
10. `SEBAB` (klasifikasi, toleransi cocok 15% terhadap REF_DASAR):
    - `TOTAL BENAR (satuan salah)` — HARGABELI/JUMLAH ≈ REF_DASAR. Biaya total benar,
      hanya ISISATUAN salah. Tidak perlu koreksi angka.
    - `NILAI POKOK BENAR (salah baris satuan)` — HARGABELI ≈ REF_DASAR atau
      HARGABELI/FAKTOR ≈ REF_DASAR. Angka pokok benar, salah satuan. Tidak perlu koreksi.
    - `HARGA POKOK SALAH` — tidak ada interpretasi yang cocok. INI yang perlu koreksi
      angka manual. Prioritas audit.
11. `DAMPAK_RL` = (HPP_BENAR − HPP_LAYAR) × (JUMLAH/FAKTOR). KASAR — untuk urutan
    prioritas saja, BUKAN nominal rugi. Untuk kategori "TOTAL BENAR" / "NILAI POKOK
    BENAR", dampak ke laba nyata ≈ 0 (uang tidak hilang, hanya laporan salah tampil).

### Kalibrasi ambang
Zona 30–50% didominasi VARIASI HARGA BELI yang wajar (RASIO ~1,3–1,45), BUKAN bug.
Bug satuan asli menumpuk di >90% (RASIO kelipatan bulat). Karena itu default ambang
= 50% (bukan 30%). Ambang di bawah 50% mulai memasukkan noise harga.

## Struktur file project

- `hpp_engine.py` — engine murni (tanpa GUI). `detect_anomalies()`, `write_report()`,
  `_load_dbf()`, `_build_master()`. Bisa diuji headless.
- `DeteksiAnomaliHPP.py` — GUI tkinter: pilih folder DB, tanggal, ambang → Excel.
- `BUILD_bikin_exe.bat` — build .exe via PyInstaller.
- `CARA_PAKAI.txt` — panduan build & pakai (Bahasa Indonesia, untuk owner).
- `requirements.txt` — pandas, dbfread, openpyxl, pyinstaller.

## Build & jalankan

Dependensi: `pip install pandas dbfread openpyxl pyinstaller` (Mac/Linux: `pip3`).

Build .exe:
    pyinstaller --onefile --windowed --name "DeteksiAnomaliHPP" DeteksiAnomaliHPP.py
Hasil di `dist/DeteksiAnomaliHPP.exe`.

PENTING:
- PyInstaller TIDAK bisa cross-compile. Build .exe HARUS di Windows. Build di Mac
  menghasilkan aplikasi Mac (bukan .exe). Owner memakai Windows.
- Antivirus kadang salah-curiga pada .exe --onefile; jika kena, ganti ke `--onedir`.
- Saat pakai: folder database harus berisi JUAL.DBF DAN STOK.DBF (butuh keduanya).

Uji engine tanpa GUI (contoh):
    from hpp_engine import detect_anomalies, write_report
    import pandas as pd
    anom, ring = detect_anomalies(FOLDER, pd.Timestamp('2024-01-01'),
                                  pd.Timestamp('2026-07-11'), tolerance=0.50)

## Gotchas / batasan yang harus diingat

- Selalu KERJA DARI SALINAN DBF; jangan pernah menulis ke file live. Membaca saat
  aplikasi kasir aktif = aman (read-only) tapi idealnya saat sepi (baris yang sedang
  ditulis bisa terbaca setengah).
- `DAMPAK_RL` kasar; jangan dijadikan angka kerugian. Total sangat mudah dijomplangi
  segelintir baris ekstrem.
- Bucket `HARGA POKOK SALAH` paling perlu verifikasi manual: untuk barang yang harga
  belinya sungguh berfluktuasi, patokan median bisa meleset dan salah-flag.
- Barang JASA (mis. ONGKOS POTONG/SISIR) memang berharga pokok 0 — bukan anomali.
  Aplikasi punya filter Jasa/Non-Jasa. HPP_BENAR>0 sudah menyaring ini.
- Barang bersatuan tak terdaftar di master (BOX, PAK, [SN, dll) = blind spot; tidak
  masuk daftar, jumlahnya dilaporkan di sheet Ringkasan.
- UI/label & output pakai Bahasa Indonesia. Mata uang Rupiah.

## Kemungkinan langkah berikutnya (belum dikerjakan)

- Kelompokkan bucket "HARGA POKOK SALAH" per barang → tentukan harga pokok benar
  sekali per barang (koreksi massal, bukan per baris).
- Deteksi terpisah untuk 329 baris satuan-tak-dikenal (lengkapi master dulu).
- (Ditunda) Rebuild aplikasi kasir: PostgreSQL + logika bisnis terpusat + UOM dengan
  satu satuan dasar + kartu stok. Ditunda karena alur bisnis existing belum terpetakan.
