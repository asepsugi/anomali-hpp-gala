# -*- coding: utf-8 -*-
"""
Engine deteksi anomali HPP - logika murni, tanpa GUI.
Formula HPP diambil persis dari aplikasi VFP:
    HPP_tampil = iif(isisatuan<>jumlah, hargabeli/isisatuan, hargabeli/jumlah)
"""
import os
import numpy as np
import pandas as pd
from dbfread import DBF


def _load_dbf(path):
    tbl = DBF(path, ignore_missing_memofile=True, char_decode_errors='replace')
    df = pd.DataFrame(iter(tbl))
    df.columns = [c.upper() for c in df.columns]
    return df


def detect_anomalies(db_folder, date_from, date_to, tolerance=0.30, progress=None):
    """
    db_folder : folder berisi JUAL.DBF & BELI.DBF (mis. 'Z:\\')
    date_from, date_to : pandas Timestamp / datetime
    tolerance : ambang deviasi (0.02 = 2%)
    progress : callable(str) opsional utk update status ke GUI
    return : (anomali_df, ringkasan_dict)
    """
    def say(msg):
        if progress:
            progress(msg)

    say("Membuka JUAL.DBF ...")
    jual = _load_dbf(os.path.join(db_folder, 'JUAL.DBF'))
    jual['TANGGAL'] = pd.to_datetime(jual['TANGGAL'], errors='coerce')

    say("Menyaring periode ...")
    d = jual[(jual['TANGGAL'] >= date_from) & (jual['TANGGAL'] <= date_to)].copy()
    # buang faktur retur (R) & transfer (T), samakan dgn report aslinya
    nf = d['NOFAKTUR'].astype(str).str.strip().str.upper()
    d = d[~nf.str.startswith(('R', 'T'))]
    if len(d) == 0:
        return d, {'total_baris': 0, 'total_anomali': 0, 'periode': (date_from, date_to)}

    say("Menghitung HPP (formula aplikasi) ...")
    isis = pd.to_numeric(d['ISISATUAN'], errors='coerce')
    juml = pd.to_numeric(d['JUMLAH'], errors='coerce')
    hb = pd.to_numeric(d['HARGABELI'], errors='coerce')
    d['HPP_TAMPIL'] = np.where(isis != juml,
                               np.where(isis != 0, hb / isis, np.nan),
                               np.where(juml != 0, hb / juml, np.nan))
    d['SATUAN'] = d['SATUAN'].astype(str).str.strip()
    d['BULAN'] = d['TANGGAL'].dt.to_period('M')
    d['HPP_R'] = d['HPP_TAMPIL'].round(0)

    say("Mencari nilai HPP dominan per barang/satuan/bulan ...")
    grp = d.groupby(['KODEBRG', 'SATUAN', 'BULAN'])
    dom = grp['HPP_R'].agg(lambda s: s.mode().iloc[0] if len(s.mode()) else np.nan).rename('HPP_DOMINAN')
    ndist = grp['HPP_R'].nunique().rename('N_NILAI_HPP')
    d = d.merge(dom, on=['KODEBRG', 'SATUAN', 'BULAN']).merge(ndist, on=['KODEBRG', 'SATUAN', 'BULAN'])

    dev = np.where(d['HPP_DOMINAN'] > 0,
                   (d['HPP_R'] - d['HPP_DOMINAN']).abs() / d['HPP_DOMINAN'], np.nan)
    d['DEV_PCT'] = (dev * 100).round(1)

    # anomali: menyimpang > toleransi ATAU HPP tidak wajar (<=0), DAN memang ada >1 nilai HPP di grup itu
    anom = d[((dev > tolerance) | (d['HPP_R'] <= 0)) & (d['N_NILAI_HPP'] > 1)].copy()

    say("Mengecek pembelian ke supplier ...")
    try:
        beli = _load_dbf(os.path.join(db_folder, 'BELI.DBF'))
        beli['TANGGAL'] = pd.to_datetime(beli['TANGGAL'], errors='coerce')
        beli['BULAN'] = beli['TANGGAL'].dt.to_period('M')
        beli_set = set(zip(beli['KODEBRG'].astype(str), beli['BULAN'].astype(str)))
        anom['ADA_BELI_BLN_INI'] = [
            (str(k), str(b)) in beli_set for k, b in zip(anom['KODEBRG'], anom['BULAN'])
        ]
    except Exception as e:
        anom['ADA_BELI_BLN_INI'] = None

    anom['DAMPAK_RL'] = ((anom['HPP_DOMINAN'] - anom['HPP_R']) * pd.to_numeric(anom['ISISATUAN'], errors='coerce')).round(0)
    anom['BULAN'] = anom['BULAN'].astype(str)
    anom = anom.sort_values('TANGGAL')

    has_ganti = 'GANTI' in anom.columns
    has_user = 'NAMAUSER' in anom.columns
    cols = ['TANGGAL', 'NOFAKTUR', 'KODEBRG', 'NAMABRG', 'SATUAN', 'JUMLAH', 'ISISATUAN',
            'HARGABELI', 'HPP_TAMPIL', 'HPP_DOMINAN', 'DEV_PCT', 'HARGAJUAL', 'DAMPAK_RL']
    if has_ganti:
        cols.append('GANTI')
    cols.append('ADA_BELI_BLN_INI')
    if has_user:
        cols.append('NAMAUSER')
    cols = [c for c in cols if c in anom.columns]
    anom_out = anom[cols].copy()
    anom_out['HPP_TAMPIL'] = anom_out['HPP_TAMPIL'].round(0)

    ringkasan = {
        'periode': (date_from, date_to),
        'total_baris': int(len(d)),
        'total_anomali': int(len(anom_out)),
        'tanpa_pembelian': int((anom_out.get('ADA_BELI_BLN_INI') == False).sum()) if 'ADA_BELI_BLN_INI' in anom_out else 0,
        'per_bulan': anom_out.groupby('BULAN' if 'BULAN' in anom_out else anom['BULAN']).size() if len(anom_out) else None,
    }
    return anom_out, ringkasan


def write_report(anom, ringkasan, out_path):
    """Tulis hasil ke Excel berformat. Baris paling mencurigakan (tanpa pembelian) di-highlight."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    # --- Sheet Ringkasan ---
    ws = wb.active
    ws.title = "Ringkasan"
    df, dt = ringkasan['periode']
    judul = [
        ("LAPORAN DETEKSI ANOMALI HPP", True),
        (f"Periode: {df:%d/%m/%Y} s/d {dt:%d/%m/%Y}", False),
        ("", False),
        (f"Total baris penjualan diperiksa : {ringkasan['total_baris']:,}", False),
        (f"Total baris ANOMALI ditemukan   : {ringkasan['total_anomali']:,}", False),
        (f"  -> paling mencurigakan (tanpa pembelian bulan itu): {ringkasan['tanpa_pembelian']:,}", False),
        ("", False),
        ("Cara baca:", True),
        ("HPP_TAMPIL  = nilai HPP yang MUNCUL di aplikasi (hasil hitung).", False),
        ("HPP_DOMINAN = nilai HPP yang paling sering / dianggap benar bulan itu.", False),
        ("DEV_PCT     = seberapa jauh menyimpang (%).", False),
        ("DAMPAK_RL   = perkiraan salah hitung laba baris ini (Rp).", False),
        ("ADA_BELI_BLN_INI = FALSE artinya tidak ada pembelian barang itu bulan tsb", False),
        ("                   (HPP harusnya tetap) -> paling kuat indikasi salah hitung.", False),
        ("GANTI = TRUE artinya HPP baris ini pernah diubah manual (tombol Ganti HPP).", False),
    ]
    for i, (txt, bold) in enumerate(judul, 1):
        c = ws.cell(row=i, column=1, value=txt)
        if bold:
            c.font = Font(bold=True, size=12 if i == 1 else 11)
    ws.column_dimensions['A'].width = 75

    # --- Sheet Anomali ---
    ws2 = wb.create_sheet("Anomali")
    if len(anom) == 0:
        ws2.cell(row=1, column=1, value="Tidak ada anomali pada periode ini.")
    else:
        # urutkan berdasar dampak terbesar
        a = anom.reindex(anom['DAMPAK_RL'].abs().sort_values(ascending=False).index).reset_index(drop=True)
        headers = list(a.columns)
        head_fill = PatternFill("solid", fgColor="1F4E78")
        head_font = Font(bold=True, color="FFFFFF")
        thin = Side(style="thin", color="D0D0D0")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for j, h in enumerate(headers, 1):
            c = ws2.cell(row=1, column=j, value=h)
            c.fill = head_fill; c.font = head_font
            c.alignment = Alignment(horizontal="center"); c.border = border
        red = PatternFill("solid", fgColor="FFC7CE")     # tanpa pembelian = paling mencurigakan
        yellow = PatternFill("solid", fgColor="FFEB9C")   # anomali lain
        has_beli = 'ADA_BELI_BLN_INI' in headers
        beli_idx = headers.index('ADA_BELI_BLN_INI') if has_beli else -1
        for i, row in enumerate(a.itertuples(index=False), start=2):
            vals = list(row)
            highlight = red if (has_beli and vals[beli_idx] == False) else yellow
            for j, v in enumerate(vals, 1):
                if hasattr(v, 'strftime'):
                    v = v.strftime('%d/%m/%Y')
                elif isinstance(v, float):
                    v = round(v, 2)
                c = ws2.cell(row=i, column=j, value=v)
                c.fill = highlight; c.border = border
        # lebar kolom
        widths = {'TANGGAL': 12, 'NOFAKTUR': 13, 'KODEBRG': 9, 'NAMABRG': 34, 'SATUAN': 8,
                  'JUMLAH': 9, 'ISISATUAN': 10, 'HARGABELI': 12, 'HPP_TAMPIL': 12,
                  'HPP_DOMINAN': 12, 'DEV_PCT': 9, 'HARGAJUAL': 11, 'DAMPAK_RL': 13,
                  'GANTI': 8, 'ADA_BELI_BLN_INI': 16, 'NAMAUSER': 12}
        for j, h in enumerate(headers, 1):
            ws2.column_dimensions[get_column_letter(j)].width = widths.get(h, 12)
        ws2.freeze_panes = "A2"
        ws2.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(a)+1}"

    wb.save(out_path)
    return out_path
