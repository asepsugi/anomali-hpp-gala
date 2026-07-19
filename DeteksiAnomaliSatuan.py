# -*- coding: utf-8 -*-
"""
Engine deteksi KESALAHAN INPUT SATUAN pada data penjualan.

Ide: tiap barang di master (STOK.DBF) punya sampai 3 tingkat satuan beserta
harga jual acuannya: HARGAJUAL1 (satuan dasar), HARGAJUAL2 (+ISISAT2/SATUAN2),
HARGAJUAL3 (+ISISAT3/SATUAN3). Kalau harga jual di faktur (JUAL.HARGAJUAL) jauh
dari harga satuan yang DIINPUT, tapi cocok dengan harga satuan LAIN, berarti
satuannya kemungkinan salah pilih saat input.

Barang jasa/non-stok (mis. ONGKOS) dikecualikan karena harganya wajar berubah.
"""
import os
import numpy as np
import pandas as pd
from dbfread import DBF


def _load_dbf(path):
    df = pd.DataFrame(iter(DBF(path, ignore_missing_memofile=True, char_decode_errors='replace')))
    df.columns = [c.upper() for c in df.columns]
    return df


def _num(v):
    try:
        v = float(v); return v if v > 0 else np.nan
    except Exception:
        return np.nan


def _truthy(v):
    return str(v).strip().lower() in ('true', 't', '1', '1.0', 'y', 'yes')


def _build_units(stok):
    """kode -> list[(satuan, harga_acuan)] untuk 3 tingkat; dan set barang jasa/non-stok."""
    units, excl = {}, set()
    for _, r in stok.iterrows():
        k = r['KODEBRG']
        nm = str(r.get('NAMABRG', '')).upper()
        if _truthy(r.get('NONSTOK')) or _truthy(r.get('SERVICE')) or 'ONGKOS' in nm or 'JASA' in nm:
            excl.add(k)
        h1 = _num(r.get('HARGAJUAL1')); s1 = str(r.get('SATUAN', '')).strip()
        lst = []
        if s1:
            lst.append((s1, h1))
        for sN, iN, hN in (('SATUAN2', 'ISISAT2', 'HARGAJUAL2'), ('SATUAN3', 'ISISAT3', 'HARGAJUAL3')):
            su = str(r.get(sN, '')).strip(); iso = _num(r.get(iN)); hh = _num(r.get(hN))
            if su and su not in ('0', 'nan', 'None'):
                if np.isnan(hh) and not np.isnan(h1) and not np.isnan(iso):
                    hh = h1 * iso          # harga satuan turunan = harga dasar x isi
                lst.append((su, hh))
        units[k] = lst
    return units, excl


def detect_unit_errors(db_folder, date_from, date_to, dev_threshold=0.60,
                       match_tol=0.20, progress=None):
    """
    dev_threshold : seberapa jauh harga jual dari harga satuan diinput agar dicurigai (0.60=60%).
    match_tol     : toleransi agar harga jual dianggap 'cocok' satuan lain (0.20=20%, menampung diskon).
    """
    def say(m):
        if progress: progress(m)

    say("Membuka JUAL.DBF ...")
    jual = _load_dbf(os.path.join(db_folder, 'JUAL.DBF'))
    jual['TANGGAL'] = pd.to_datetime(jual['TANGGAL'], errors='coerce')

    say("Membaca master STOK.DBF ...")
    stok = _load_dbf(os.path.join(db_folder, 'STOK.DBF'))
    units, excl = _build_units(stok)

    say("Menyaring periode ...")
    d = jual[(jual['TANGGAL'] >= date_from) & (jual['TANGGAL'] <= date_to)].copy()
    nf = d['NOFAKTUR'].astype(str).str.strip().str.upper()
    d = d[~nf.str.startswith(('R', 'T'))]
    d = d[~d['KODEBRG'].isin(excl)]
    d['SATUAN'] = d['SATUAN'].astype(str).str.strip()
    d['HJ'] = pd.to_numeric(d['HARGAJUAL'], errors='coerce')

    say("Membandingkan harga jual dengan daftar harga satuan ...")
    out = []
    diperiksa = 0
    for x in d.itertuples(index=False):
        lst = units.get(x.KODEBRG)
        hj = x.HJ; sat = x.SATUAN
        if not lst or pd.isna(hj) or hj <= 0:
            continue
        exp = next((h for (s, h) in lst if s == sat and not np.isnan(h)), np.nan)
        if np.isnan(exp):
            continue
        diperiksa += 1
        dev = abs(hj - exp) / exp
        if dev <= dev_threshold:
            continue
        # cari satuan lain yang harganya cocok dengan harga jual
        matches = [(s, h) for (s, h) in lst if (not np.isnan(h)) and h > 0 and s != sat
                   and abs(hj - h) / h <= match_tol]
        if matches:
            s_benar, h_benar = min(matches, key=lambda sh: abs(hj - sh[1]))
            kategori = 'SALAH SATUAN'
        else:
            s_benar, h_benar = '', np.nan
            kategori = 'HARGA JANGGAL (cek manual)'
        out.append({
            'TANGGAL': x.TANGGAL, 'NOFAKTUR': x.NOFAKTUR, 'KODEBRG': x.KODEBRG,
            'NAMABRG': x.NAMABRG, 'SATUAN_DIINPUT': sat,
            'BANYAK': getattr(x, 'ISISATUAN', np.nan),
            'HARGA_JUAL': round(hj, 0),
            'HRG_UTK_SATUAN_INI': round(exp, 0),
            'SATUAN_SEHARUSNYA': s_benar,
            'HRG_UTK_SATUAN_SEHARUSNYA': round(h_benar, 0) if not np.isnan(h_benar) else '',
            'KATEGORI': kategori,
            'NAMAUSER': getattr(x, 'NAMAUSER', ''),
        })

    res = pd.DataFrame(out)
    if len(res):
        res = res.sort_values(['KATEGORI', 'TANGGAL'])
    ring = {
        'periode': (date_from, date_to),
        'diperiksa': int(diperiksa),
        'total': int(len(res)),
        'salah_satuan': int((res['KATEGORI'] == 'SALAH SATUAN').sum()) if len(res) else 0,
        'harga_janggal': int((res['KATEGORI'] != 'SALAH SATUAN').sum()) if len(res) else 0,
        'jasa_dikecualikan': len(excl),
    }
    return res, ring


def write_report(res, ring, out_path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); ws = wb.active; ws.title = "Ringkasan"
    df, dt = ring['periode']
    lines = [
        ("DETEKSI KESALAHAN INPUT SATUAN", 12),
        (f"Periode: {df:%d/%m/%Y} s/d {dt:%d/%m/%Y}", 0),
        ("", 0),
        (f"Baris diperiksa (punya harga satuan): {ring['diperiksa']:,}", 0),
        (f"SALAH SATUAN (harga jual cocok satuan lain): {ring['salah_satuan']:,}", 0),
        (f"HARGA JANGGAL (perlu cek manual): {ring['harga_janggal']:,}", 0),
        (f"Barang jasa/non-stok dikecualikan: {ring['jasa_dikecualikan']:,}", 0),
        ("", 0),
        ("Cara baca:", 11),
        ("SATUAN_DIINPUT     = satuan yang tercatat di faktur.", 0),
        ("BANYAK             = jumlah dalam satuan jual (spt di faktur), bukan satuan dasar.", 0),
        ("HARGA_JUAL         = harga jual di faktur.", 0),
        ("HRG_UTK_SATUAN_INI = harga wajar bila satuannya memang seperti diinput.", 0),
        ("SATUAN_SEHARUSNYA  = satuan yang harganya cocok dengan HARGA_JUAL.", 0),
        ("MERAH  = SALAH SATUAN (yakin). ORANYE = HARGA JANGGAL (cek manual).", 0),
    ]
    for i, (t, sz) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=t)
        if sz: c.font = Font(bold=True, size=sz)
    ws.column_dimensions['A'].width = 70

    ws2 = wb.create_sheet("Kesalahan Satuan")
    if len(res) == 0:
        ws2.cell(row=1, column=1, value="Tidak ada kesalahan satuan pada periode ini.")
    else:
        heads = list(res.columns)
        hf = PatternFill("solid", fgColor="1F4E78"); hfont = Font(bold=True, color="FFFFFF")
        thin = Side(style="thin", color="D0D0D0"); bd = Border(left=thin, right=thin, top=thin, bottom=thin)
        for j, h in enumerate(heads, 1):
            c = ws2.cell(row=1, column=j, value=h); c.fill = hf; c.font = hfont
            c.alignment = Alignment(horizontal="center"); c.border = bd
        red = PatternFill("solid", fgColor="FFC7CE"); org = PatternFill("solid", fgColor="FFD9A0")
        ki = heads.index('KATEGORI')
        for i, row in enumerate(res.itertuples(index=False), start=2):
            vals = list(row); fill = red if vals[ki] == 'SALAH SATUAN' else org
            for j, v in enumerate(vals, 1):
                if hasattr(v, 'strftime'): v = v.strftime('%d/%m/%Y')
                c = ws2.cell(row=i, column=j, value=v); c.fill = fill; c.border = bd
        widths = {'TANGGAL':12,'NOFAKTUR':13,'KODEBRG':9,'NAMABRG':34,'SATUAN_DIINPUT':14,'BANYAK':9,
                  'HARGA_JUAL':12,'HRG_UTK_SATUAN_INI':18,'SATUAN_SEHARUSNYA':17,
                  'HRG_UTK_SATUAN_SEHARUSNYA':24,'KATEGORI':24,'NAMAUSER':11}
        for j, h in enumerate(heads, 1):
            ws2.column_dimensions[get_column_letter(j)].width = widths.get(h, 12)
        ws2.freeze_panes = "A2"; ws2.auto_filter.ref = f"A1:{get_column_letter(len(heads))}{len(res)+1}"
    wb.save(out_path)
    return out_path
