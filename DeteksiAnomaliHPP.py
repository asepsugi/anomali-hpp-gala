# -*- coding: utf-8 -*-
"""
Deteksi Anomali HPP - Aplikasi GUI
Owner tinggal: pilih folder database -> pilih tanggal -> klik ANALISA.
Hasil keluar sebagai file Excel dan langsung terbuka.
"""
import os
import sys
import threading
import queue
import datetime as dt
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd
import hpp_engine

APP_TITLE = "Deteksi Anomali HPP - SERBA INDAH"
DEFAULT_FOLDER = "Z:\\"


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
        root.title(APP_TITLE)
        root.geometry("560x430")
        root.resizable(False, False)

        pad = {'padx': 12, 'pady': 6}

        # Judul
        head = tk.Label(root, text="DETEKSI ANOMALI HPP", font=("Segoe UI", 16, "bold"), fg="#1F4E78")
        head.pack(pady=(16, 2))
        tk.Label(root, text="Cari HPP yang salah hitung pada periode tertentu",
                 font=("Segoe UI", 9), fg="#555").pack()

        frm = tk.Frame(root)
        frm.pack(fill="x", padx=24, pady=(16, 4))

        # Folder database
        tk.Label(frm, text="Folder database (berisi JUAL.DBF):", anchor="w").grid(row=0, column=0, columnspan=3, sticky="w")
        self.folder_var = tk.StringVar(value=DEFAULT_FOLDER)
        self.folder_entry = tk.Entry(frm, textvariable=self.folder_var, width=48)
        self.folder_entry.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 10))
        tk.Button(frm, text="Pilih...", command=self.pilih_folder, width=8).grid(row=1, column=2, padx=(6, 0))

        # Tanggal
        today = dt.date.today()
        awal_default = today.replace(day=1)
        tk.Label(frm, text="Tanggal MULAI:", anchor="w").grid(row=2, column=0, sticky="w")
        self.dari_var = tk.StringVar(value=awal_default.strftime("%d/%m/%Y"))
        tk.Entry(frm, textvariable=self.dari_var, width=16).grid(row=2, column=1, sticky="w", pady=4)

        tk.Label(frm, text="Tanggal SAMPAI:", anchor="w").grid(row=3, column=0, sticky="w")
        self.sampai_var = tk.StringVar(value=today.strftime("%d/%m/%Y"))
        tk.Entry(frm, textvariable=self.sampai_var, width=16).grid(row=3, column=1, sticky="w", pady=4)

        tk.Label(frm, text="(format: HARI/BULAN/TAHUN, contoh 01/01/2024)",
                 font=("Segoe UI", 8), fg="#888").grid(row=4, column=0, columnspan=3, sticky="w")

        # Sensitivitas
        tk.Label(frm, text="Ambang anomali (selisih HPP minimal):", anchor="w").grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.tol_var = tk.StringVar(value="50%  (disarankan)")
        self.tol_combo = ttk.Combobox(frm, textvariable=self.tol_var, state="readonly", width=22,
                                       values=["30%  (lebih teliti, banyak noise)", "50%  (disarankan)", "70%  (paling parah saja)", "90%  (hampir pasti bug)"])
        self.tol_combo.grid(row=6, column=0, sticky="w")

        frm.columnconfigure(0, weight=1)

        # Tombol utama
        self.btn = tk.Button(root, text="ANALISA ANOMALI", font=("Segoe UI", 12, "bold"),
                             bg="#1F4E78", fg="white", activebackground="#163a5c",
                             command=self.jalankan, height=2)
        self.btn.pack(fill="x", padx=24, pady=(14, 6))

        # Status
        self.status = tk.Label(root, text="Siap.", anchor="w", fg="#333", font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=24)
        self.bar = ttk.Progressbar(root, mode="indeterminate")
        self.bar.pack(fill="x", padx=24, pady=(4, 10))

        self.root.after(120, self._poll)

    def pilih_folder(self):
        d = filedialog.askdirectory(title="Pilih folder yang berisi JUAL.DBF")
        if d:
            self.folder_var.set(d)

    def set_status(self, msg):
        self.q.put(("status", msg))

    def jalankan(self):
        folder = self.folder_var.get().strip()
        if not os.path.isfile(os.path.join(folder, "JUAL.DBF")):
            messagebox.showerror("Folder salah",
                                 f"Tidak menemukan JUAL.DBF di:\n{folder}\n\nPastikan folder database sudah benar.")
            return
        try:
            d1 = parse_tanggal(self.dari_var.get())
            d2 = parse_tanggal(self.sampai_var.get())
        except ValueError as e:
            messagebox.showerror("Tanggal salah", str(e))
            return
        if d1 > d2:
            messagebox.showerror("Tanggal salah", "Tanggal MULAI tidak boleh setelah tanggal SAMPAI.")
            return
        tol = {"30": 0.30, "50": 0.50, "70": 0.70, "90": 0.90}[self.tol_var.get().split("%")[0].strip()]

        self.btn.config(state="disabled")
        self.bar.start(12)
        t = threading.Thread(target=self._worker, args=(folder, d1, d2, tol), daemon=True)
        t.start()

    def _worker(self, folder, d1, d2, tol):
        try:
            anom, ring = hpp_engine.detect_anomalies(
                folder, pd.Timestamp(d1), pd.Timestamp(d2), tolerance=tol,
                progress=self.set_status)
            self.set_status("Menulis file Excel ...")
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out = os.path.join(os.path.expanduser("~"), "Documents",
                               f"Anomali_HPP_{d1:%Y%m%d}-{d2:%Y%m%d}_{stamp}.xlsx")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            hpp_engine.write_report(anom, ring, out)
            self.q.put(("done", (out, ring)))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self.status.config(text=payload)
                elif kind == "done":
                    out, ring = payload
                    self.bar.stop()
                    self.btn.config(state="normal")
                    self.status.config(text=f"Selesai. {ring['total_anomali']:,} anomali ditemukan.")
                    msg = (f"Analisa selesai.\n\n"
                           f"Baris penjualan diperiksa   : {ring['total_baris']:,}\n"
                           f"Anomali ditemukan            : {ring['total_anomali']:,}\n"
                           f"  - HAMPIR PASTI (dev >90%)  : {ring.get('hampir_pasti', 0):,}\n"
                           f"  - HARGA POKOK SALAH        : {ring.get('harga_pokok_salah', 0):,}\n"
                           f"Satuan tak terdaftar (dicek terpisah): {ring.get('satuan_tak_dikenal', 0):,}\n\n"
                           f"File disimpan di:\n{out}\n\nBuka sekarang?")
                    if messagebox.askyesno("Selesai", msg):
                        try:
                            os.startfile(out)  # Windows
                        except AttributeError:
                            import subprocess
                            subprocess.call(["xdg-open", out])
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
