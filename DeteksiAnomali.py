# -*- coding: utf-8 -*-
"""
Deteksi Anomali - Aplikasi GUI (gabungan)
Owner tinggal: pilih folder database -> pilih jenis cek -> pilih tanggal -> klik ANALISA.
Hasil keluar sebagai file Excel dan langsung terbuka.

Dua jenis cek dalam satu aplikasi:
  1. HPP    -> hpp_engine.detect_anomalies (HPP salah hitung di laporan Laba)
  2. SATUAN -> DeteksiAnomaliSatuan.detect_unit_errors (salah pilih satuan saat input)
"""
import os
import sys
import json
import threading
import queue
import datetime as dt
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd
import hpp_engine
import DeteksiAnomaliSatuan as satuan_engine

try:
    from tkcalendar import DateEntry   # widget kalender (opsional)
    HAS_CALENDAR = True
except Exception:
    HAS_CALENDAR = False               # fallback: ketik manual

APP_TITLE = "Deteksi Anomali - SERBA INDAH"
DEFAULT_FOLDER = "Z:\\"

# Folder tempat program berjalan: untuk .exe = folder .exe, untuk .py = folder skrip
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".deteksi_anomali.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass  # gagal simpan setelan bukan masalah kritis


def parse_tanggal(s):
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Tanggal '{s}' tidak valid. Pakai format HARI/BULAN/TAHUN, mis. 01/01/2024")


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.cfg = load_config()
        root.title(APP_TITLE)
        root.geometry("560x500")
        root.resizable(False, False)

        # Judul
        head = tk.Label(root, text="DETEKSI ANOMALI", font=("Segoe UI", 16, "bold"), fg="#1F4E78")
        head.pack(pady=(16, 2))
        tk.Label(root, text="Cari HPP salah hitung atau kesalahan input satuan",
                 font=("Segoe UI", 9), fg="#555").pack()

        frm = tk.Frame(root)
        frm.pack(fill="x", padx=24, pady=(14, 4))

        # Folder database
        tk.Label(frm, text="Folder database (berisi JUAL.DBF & STOK.DBF):", anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.folder_var = tk.StringVar(value=self.cfg.get("folder", DEFAULT_FOLDER))
        self.folder_entry = tk.Entry(frm, textvariable=self.folder_var, width=48)
        self.folder_entry.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 10))
        tk.Button(frm, text="Pilih...", command=self.pilih_folder, width=8).grid(row=1, column=2, padx=(6, 0))

        # Jenis cek
        tk.Label(frm, text="Jenis pemeriksaan:", anchor="w").grid(row=2, column=0, columnspan=3, sticky="w")
        self.mode_var = tk.StringVar(value="HPP")
        modefrm = tk.Frame(frm)
        modefrm.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))
        tk.Radiobutton(modefrm, text="Anomali HPP (HPP salah hitung di laporan Laba)",
                       variable=self.mode_var, value="HPP", command=self._on_mode).pack(anchor="w")
        tk.Radiobutton(modefrm, text="Kesalahan Satuan (salah pilih satuan saat input)",
                       variable=self.mode_var, value="SATUAN", command=self._on_mode).pack(anchor="w")

        # Tanggal
        today = dt.date.today()
        awal_default = today.replace(day=1)
        tk.Label(frm, text="Tanggal MULAI:", anchor="w").grid(row=4, column=0, sticky="w")
        tk.Label(frm, text="Tanggal SAMPAI:", anchor="w").grid(row=5, column=0, sticky="w")
        if HAS_CALENDAR:
            cal_opts = dict(width=14, date_pattern="dd/mm/yyyy", locale="id_ID",
                            background="#1F4E78", foreground="white", borderwidth=2)
            self.dari_entry = DateEntry(frm, **cal_opts)
            self.dari_entry.set_date(awal_default)
            self.dari_entry.grid(row=4, column=1, sticky="w", pady=4)
            self.sampai_entry = DateEntry(frm, **cal_opts)
            self.sampai_entry.set_date(today)
            self.sampai_entry.grid(row=5, column=1, sticky="w", pady=4)
            tk.Label(frm, text="(klik kotak tanggal untuk memilih dari kalender)",
                     font=("Segoe UI", 8), fg="#888").grid(row=6, column=0, columnspan=3, sticky="w")
        else:
            self.dari_var = tk.StringVar(value=awal_default.strftime("%d/%m/%Y"))
            tk.Entry(frm, textvariable=self.dari_var, width=16).grid(row=4, column=1, sticky="w", pady=4)
            self.sampai_var = tk.StringVar(value=today.strftime("%d/%m/%Y"))
            tk.Entry(frm, textvariable=self.sampai_var, width=16).grid(row=5, column=1, sticky="w", pady=4)
            tk.Label(frm, text="(format: HARI/BULAN/TAHUN, contoh 01/01/2024)",
                     font=("Segoe UI", 8), fg="#888").grid(row=6, column=0, columnspan=3, sticky="w")

        # Sensitivitas (label & pilihan berubah menurut mode)
        self.tol_label = tk.Label(frm, text="Ambang anomali (selisih HPP minimal):", anchor="w")
        self.tol_label.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.tol_var = tk.StringVar()
        self.tol_combo = ttk.Combobox(frm, textvariable=self.tol_var, state="readonly", width=30)
        self.tol_combo.grid(row=8, column=0, columnspan=2, sticky="w")

        frm.columnconfigure(0, weight=1)

        # Tombol utama
        self.btn = tk.Button(root, text="ANALISA", font=("Segoe UI", 12, "bold"),
                             bg="#1F4E78", fg="white", activebackground="#163a5c",
                             command=self.jalankan, height=2)
        self.btn.pack(fill="x", padx=24, pady=(14, 6))

        # Status
        self.status = tk.Label(root, text="Siap.", anchor="w", fg="#333", font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=24)
        self.bar = ttk.Progressbar(root, mode="indeterminate")
        self.bar.pack(fill="x", padx=24, pady=(4, 10))

        self._on_mode()  # isi combobox sesuai mode awal
        self.root.after(120, self._poll)

    # ---- pilihan ambang per mode ----
    HPP_OPTS = ["0.1%  (super teliti, semua selisih)", "30%  (lebih teliti, banyak noise)",
                "50%  (disarankan)", "70%  (paling parah saja)", "90%  (hampir pasti bug)"]
    HPP_MAP = {"0.1": 0.001, "30": 0.30, "50": 0.50, "70": 0.70, "90": 0.90}
    SAT_OPTS = ["0.1%  (super teliti, semua selisih)", "40%  (lebih teliti, banyak noise)",
                "60%  (disarankan)", "80%  (paling parah saja)"]
    SAT_MAP = {"0.1": 0.001, "40": 0.40, "60": 0.60, "80": 0.80}

    def _on_mode(self):
        if self.mode_var.get() == "HPP":
            self.tol_label.config(text="Ambang anomali (selisih HPP minimal):")
            self.tol_combo["values"] = self.HPP_OPTS
            self.tol_var.set(self.HPP_OPTS[2])   # 50%
        else:
            self.tol_label.config(text="Ambang (selisih harga jual minimal):")
            self.tol_combo["values"] = self.SAT_OPTS
            self.tol_var.set(self.SAT_OPTS[2])   # 60%

    def pilih_folder(self):
        d = filedialog.askdirectory(title="Pilih folder yang berisi JUAL.DBF")
        if d:
            self.folder_var.set(d)
            self.cfg["folder"] = d
            save_config(self.cfg)

    def set_status(self, msg):
        self.q.put(("status", msg))

    def jalankan(self):
        folder = self.folder_var.get().strip()
        if not os.path.isfile(os.path.join(folder, "JUAL.DBF")):
            messagebox.showerror("Folder salah",
                                 f"Tidak menemukan JUAL.DBF di:\n{folder}\n\nPastikan folder database sudah benar.")
            return
        if not os.path.isfile(os.path.join(folder, "STOK.DBF")):
            messagebox.showerror("Folder salah",
                                 f"Tidak menemukan STOK.DBF di:\n{folder}\n\nButuh JUAL.DBF DAN STOK.DBF.")
            return
        try:
            if HAS_CALENDAR:
                d1 = dt.datetime.combine(self.dari_entry.get_date(), dt.time())
                d2 = dt.datetime.combine(self.sampai_entry.get_date(), dt.time())
            else:
                d1 = parse_tanggal(self.dari_var.get())
                d2 = parse_tanggal(self.sampai_var.get())
        except ValueError as e:
            messagebox.showerror("Tanggal salah", str(e))
            return
        if d1 > d2:
            messagebox.showerror("Tanggal salah", "Tanggal MULAI tidak boleh setelah tanggal SAMPAI.")
            return

        # folder valid -> simpan supaya tidak perlu pilih ulang lain kali
        self.cfg["folder"] = folder
        save_config(self.cfg)

        mode = self.mode_var.get()
        key = self.tol_var.get().split("%")[0].strip()
        tol = (self.HPP_MAP if mode == "HPP" else self.SAT_MAP)[key]

        self.btn.config(state="disabled")
        self.bar.start(12)
        t = threading.Thread(target=self._worker, args=(mode, folder, d1, d2, tol), daemon=True)
        t.start()

    def _worker(self, mode, folder, d1, d2, tol):
        try:
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(BASE_DIR, "output")
            os.makedirs(out_dir, exist_ok=True)
            if mode == "HPP":
                anom, ring = hpp_engine.detect_anomalies(
                    folder, pd.Timestamp(d1), pd.Timestamp(d2), tolerance=tol,
                    progress=self.set_status)
                self.set_status("Menulis file Excel ...")
                out = os.path.join(out_dir, f"Anomali_HPP_{d1:%Y%m%d}-{d2:%Y%m%d}_{stamp}.xlsx")
                hpp_engine.write_report(anom, ring, out)
                self.q.put(("done_hpp", (out, ring)))
            else:
                res, ring = satuan_engine.detect_unit_errors(
                    folder, pd.Timestamp(d1), pd.Timestamp(d2), dev_threshold=tol,
                    progress=self.set_status)
                self.set_status("Menulis file Excel ...")
                out = os.path.join(out_dir, f"Anomali_Satuan_{d1:%Y%m%d}-{d2:%Y%m%d}_{stamp}.xlsx")
                satuan_engine.write_report(res, ring, out)
                self.q.put(("done_satuan", (out, ring)))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _open_file(self, out):
        try:
            os.startfile(out)  # Windows
        except AttributeError:
            import subprocess
            subprocess.call(["xdg-open", out])

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self.status.config(text=payload)
                elif kind == "done_hpp":
                    out, ring = payload
                    self.bar.stop()
                    self.btn.config(state="normal")
                    self.status.config(text=f"Selesai. {ring['total_anomali']:,} anomali ditemukan.")
                    msg = (f"Analisa HPP selesai.\n\n"
                           f"Baris penjualan diperiksa   : {ring['total_baris']:,}\n"
                           f"Anomali ditemukan            : {ring['total_anomali']:,}\n"
                           f"  - HAMPIR PASTI (dev >90%)  : {ring.get('hampir_pasti', 0):,}\n"
                           f"  - HARGA POKOK SALAH        : {ring.get('harga_pokok_salah', 0):,}\n"
                           f"Satuan tak terdaftar (dicek terpisah): {ring.get('satuan_tak_dikenal', 0):,}\n\n"
                           f"File disimpan di:\n{out}\n\nBuka sekarang?")
                    if messagebox.askyesno("Selesai", msg):
                        self._open_file(out)
                elif kind == "done_satuan":
                    out, ring = payload
                    self.bar.stop()
                    self.btn.config(state="normal")
                    self.status.config(text=f"Selesai. {ring['total']:,} kesalahan satuan ditemukan.")
                    msg = (f"Analisa Satuan selesai.\n\n"
                           f"Baris diperiksa (punya harga satuan): {ring['diperiksa']:,}\n"
                           f"Total temuan                 : {ring['total']:,}\n"
                           f"  - SALAH SATUAN (yakin)     : {ring['salah_satuan']:,}\n"
                           f"  - HARGA JANGGAL (cek manual): {ring['harga_janggal']:,}\n"
                           f"Barang jasa/non-stok dikecualikan: {ring['jasa_dikecualikan']:,}\n\n"
                           f"File disimpan di:\n{out}\n\nBuka sekarang?")
                    if messagebox.askyesno("Selesai", msg):
                        self._open_file(out)
                elif kind == "error":
                    self.bar.stop()
                    self.btn.config(state="normal")
                    self.status.config(text="Gagal.")
                    messagebox.showerror("Terjadi kesalahan", payload)
        except queue.Empty:
            pass
        self.root.after(120, self._poll)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
