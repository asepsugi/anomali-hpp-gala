# -*- coding: utf-8 -*-
"""
Analisa anomali HPP dari terminal (tanpa GUI).

Berguna di Mac/Linux di mana tkinter (GUI) bisa bermasalah. Engine sama persis
dengan yang dipakai aplikasi GUI (hpp_engine.py).

Contoh pakai:
    python3 analisa.py 2024-01-01 2026-07-14
    python3 analisa.py 2024-01-01 2026-07-14 50
    python3 analisa.py 2024-01-01 2026-07-14 50 --folder data --out hasil.xlsx

Argumen:
    tanggal_mulai   format YYYY-MM-DD (mis. 2024-01-01)
    tanggal_sampai  format YYYY-MM-DD
    ambang          persen deviasi minimal (opsional, default 5)
    --folder        folder berisi JUAL.DBF & STOK.DBF (default: data)
    --out           nama file Excel hasil
                    (default: output/analisa_<ambang>_<mulai>_<sampai>.xlsx)
"""
import argparse
import os
import sys

import pandas as pd

from hpp_engine import detect_anomalies, write_report


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="analisa.py",
        description="Deteksi anomali HPP dari file DBF kasir (JUAL.DBF + STOK.DBF).",
    )
    p.add_argument("mulai", help="tanggal MULAI, format YYYY-MM-DD (mis. 2024-01-01)")
    p.add_argument("sampai", help="tanggal SAMPAI, format YYYY-MM-DD (mis. 2026-07-14)")
    p.add_argument("ambang", nargs="?", type=float, default=5.0,
                   help="ambang deviasi dalam persen (default 5)")
    p.add_argument("--folder", default="data",
                   help="folder berisi JUAL.DBF & STOK.DBF (default: data)")
    p.add_argument("--out", default=None,
                   help="nama file Excel hasil "
                        "(default: output/analisa_<ambang>_<mulai>_<sampai>.xlsx)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    try:
        d1 = pd.Timestamp(args.mulai)
        d2 = pd.Timestamp(args.sampai)
    except ValueError:
        print("ERROR: format tanggal salah. Pakai YYYY-MM-DD, mis. 2024-01-01", file=sys.stderr)
        return 2
    if d1 > d2:
        print("ERROR: tanggal MULAI tidak boleh setelah tanggal SAMPAI.", file=sys.stderr)
        return 2

    tolerance = args.ambang / 100.0
    out = args.out or os.path.join(
        "output", f"analisa_{args.ambang:g}_{d1:%Y-%m-%d}_{d2:%Y-%m-%d}.xlsx")
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    anom, ring = detect_anomalies(
        args.folder, d1, d2, tolerance=tolerance,
        progress=lambda m: print(f"  {m}"),
    )
    write_report(anom, ring, out)

    print("\n" + "=" * 52)
    print(f"  Periode                 : {d1:%Y-%m-%d} s/d {d2:%Y-%m-%d}  (ambang {args.ambang:g}%)")
    print(f"  Baris penjualan diperiksa : {ring['total_baris']:,}")
    print(f"  Anomali ditemukan         : {ring['total_anomali']:,}")
    print(f"    - HAMPIR PASTI (>90%)   : {ring.get('hampir_pasti', 0):,}")
    print(f"    - HARGA POKOK SALAH     : {ring.get('harga_pokok_salah', 0):,}")
    print(f"  Satuan tak terdaftar      : {ring.get('satuan_tak_dikenal', 0):,}")
    print(f"  File hasil                : {out}")
    print("=" * 52)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
