#!/usr/bin/env python3
"""
dayone_to_enex_gui.py  —  simple GUI for dayone_to_enex.py
==========================================================

A no-dependency desktop front-end (Tkinter, bundled with Python) for the
Markdown / Day One -> Apple Notes (.enex) converter.

Run:
    python3 dayone_to_enex_gui.py

Pick a source (a Day One export folder/.json, a .md file/folder, or a
.textbundle/.textpack), optionally choose the output path, and click Convert.
Then in Apple Notes: File -> Import to Notes...  and select the .enex.

If Tkinter is missing (rare), install it:
    macOS (Homebrew):  brew install python-tk
    Debian/Ubuntu:     sudo apt install python3-tk
"""

import os, sys, io, threading, traceback, subprocess
from contextlib import redirect_stdout, redirect_stderr

# import the converter that lives next to this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import dayone_to_enex as conv
except Exception as e:
    sys.exit(f"Could not import dayone_to_enex.py (keep it next to this file): {e}")

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:
    sys.exit("Tkinter is not available. Install it: 'brew install python-tk' "
             "(macOS) or 'sudo apt install python3-tk' (Linux).")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Notes → Apple Notes (.enex)")
        root.minsize(620, 460)
        self.last_output = None

        pad = dict(padx=12, pady=6)
        frm = ttk.Frame(root, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Convert Markdown / Day One / TextBundle to an "
                            "Apple Notes-importable .enex file",
                  font=("-size", 12, "-weight", "bold"), wraplength=560)\
            .grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # --- source ---
        ttk.Label(frm, text="Source:").grid(row=1, column=0, sticky="w")
        self.src_var = tk.StringVar()
        self.src_var.trace_add("write", lambda *_: self._on_source_change())
        ttk.Entry(frm, textvariable=self.src_var).grid(row=1, column=1, sticky="ew", padx=6)
        btns = ttk.Frame(frm)
        btns.grid(row=1, column=2, sticky="e")
        ttk.Button(btns, text="File…", command=self.pick_file, width=7).pack(side="left", padx=2)
        ttk.Button(btns, text="Folder…", command=self.pick_folder, width=8).pack(side="left", padx=2)

        # --- detected format ---
        self.fmt_lbl = ttk.Label(frm, text="Format: —", foreground="#666")
        self.fmt_lbl.grid(row=2, column=1, sticky="w", padx=6)

        # --- format override ---
        ttk.Label(frm, text="Mode:").grid(row=3, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="auto")
        mode = ttk.Frame(frm); mode.grid(row=3, column=1, sticky="w", padx=6)
        for val, txt in [("auto", "Auto-detect"), ("dayone", "Day One"), ("markdown", "Markdown")]:
            ttk.Radiobutton(mode, text=txt, value=val, variable=self.mode_var,
                            command=self._on_source_change).pack(side="left", padx=(0, 10))

        # --- output ---
        ttk.Label(frm, text="Output:").grid(row=4, column=0, sticky="w")
        self.out_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.out_var).grid(row=4, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Save As…", command=self.pick_output, width=9)\
            .grid(row=4, column=2, sticky="e")

        # --- split option ---
        self.split_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="One .enex per note (recommended for large libraries — "
                                  "Apple Notes imports many small files more reliably)",
                        variable=self.split_var)\
            .grid(row=5, column=1, columnspan=2, sticky="w", padx=6)

        # --- convert ---
        self.convert_btn = ttk.Button(frm, text="Convert", command=self.run)
        self.convert_btn.grid(row=6, column=0, columnspan=3, pady=10)

        # --- log ---
        ttk.Label(frm, text="Result:").grid(row=7, column=0, sticky="nw")
        self.log = tk.Text(frm, height=12, wrap="word", state="disabled",
                           font=("Menlo", 11), background="#1e1e1e", foreground="#e0e0e0")
        self.log.grid(row=7, column=1, columnspan=2, sticky="nsew", padx=6)
        frm.rowconfigure(7, weight=1)

        # --- post-convert actions ---
        act = ttk.Frame(frm); act.grid(row=8, column=1, columnspan=2, sticky="w", padx=6, pady=(8, 0))
        self.reveal_btn = ttk.Button(act, text="Reveal .enex in Finder",
                                     command=self.reveal, state="disabled")
        self.reveal_btn.pack(side="left", padx=(0, 8))
        self.notes_btn = ttk.Button(act, text="Open Apple Notes", command=self.open_notes)
        self.notes_btn.pack(side="left")

        self._log("Pick a source to begin.\n\nAfter converting, import in Apple "
                  "Notes via  File → Import to Notes…  and choose the .enex.")

    # ---------- helpers ----------
    def _log(self, text, clear=False):
        self.log.configure(state="normal")
        if clear:
            self.log.delete("1.0", "end")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _detect(self):
        src = self.src_var.get().strip()
        if not src or not os.path.exists(src):
            return None
        if self.mode_var.get() != "auto":
            return self.mode_var.get()
        try:
            return conv.detect_format(os.path.abspath(src))
        except SystemExit:
            return None
        except Exception:
            return None

    def _on_source_change(self):
        fmt = self._detect()
        self.fmt_lbl.configure(text=f"Format: {fmt or '—'}")
        src = self.src_var.get().strip()
        if src and os.path.exists(src) and fmt and not self.out_var.get().strip():
            try:
                self.out_var.set(conv.default_output(os.path.abspath(src), fmt))
            except Exception:
                pass

    # ---------- file pickers ----------
    def pick_file(self):
        p = filedialog.askopenfilename(
            title="Choose a .json, .md, or .textpack file",
            filetypes=[("Supported", "*.json *.md *.markdown *.textpack"),
                       ("All files", "*.*")])
        if p:
            self.src_var.set(p)

    def pick_folder(self):
        p = filedialog.askdirectory(
            title="Choose an export folder or a .textbundle")
        if p:
            self.src_var.set(p)

    def pick_output(self):
        p = filedialog.asksaveasfilename(
            title="Save .enex as", defaultextension=".enex",
            filetypes=[("Evernote export", "*.enex")],
            initialfile=os.path.basename(self.out_var.get() or "Export.enex"))
        if p:
            self.out_var.set(p)

    # ---------- conversion ----------
    def run(self):
        src = self.src_var.get().strip()
        out = self.out_var.get().strip()
        if not src or not os.path.exists(src):
            messagebox.showerror("No source", "Pick a valid source file or folder.")
            return
        fmt = self._detect()
        if not fmt:
            messagebox.showerror("Unknown format",
                                 "Couldn't detect the format. Pick a mode manually.")
            return
        if not out:
            out = conv.default_output(os.path.abspath(src), fmt)
            self.out_var.set(out)

        split = self.split_var.get()
        out_target = out
        if split and out.lower().endswith(".enex"):
            out_target = os.path.splitext(out)[0] + "_enex"   # a folder

        self.convert_btn.configure(state="disabled", text="Converting…")
        self.reveal_btn.configure(state="disabled")
        self._log("", clear=True)
        threading.Thread(target=self._worker,
                         args=(os.path.abspath(src), os.path.abspath(out_target), fmt, split),
                         daemon=True).start()

    def _worker(self, src, out, fmt, split):
        buf = io.StringIO()
        ok = False
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                notes = conv.dayone_notes(src) if fmt == "dayone" else conv.markdown_notes(src)
                try:
                    if split:
                        conv.write_enex_split(notes, out, app=f"{fmt}_to_enex")
                    else:
                        conv.write_enex(notes, out, app=f"{fmt}_to_enex")
                finally:
                    conv._cleanup_tmp()
            ok = True
        except SystemExit as e:
            buf.write(f"\nStopped: {e}\n")
        except Exception:
            buf.write("\nError:\n" + traceback.format_exc())
        self.root.after(0, self._done, buf.getvalue(), ok, out, split)

    def _done(self, log_text, ok, out, split):
        self.convert_btn.configure(state="normal", text="Convert")
        self._log(log_text)
        if ok:
            self.last_output = out
            self.reveal_btn.configure(state="normal")
            if split:
                self._log("\n✅ Done. In Apple Notes:  File → Import to Notes…  → select all "
                          "the .enex files in this folder.")
            else:
                self._log("\n✅ Done. In Apple Notes:  File → Import to Notes…  → select this .enex.")
        else:
            self.last_output = None

    # ---------- post actions ----------
    def reveal(self):
        if self.last_output and os.path.exists(self.last_output):
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", self.last_output])
            else:
                subprocess.run(["xdg-open", os.path.dirname(self.last_output)])

    def open_notes(self):
        if sys.platform == "darwin":
            subprocess.run(["open", "-a", "Notes"])
        else:
            messagebox.showinfo("Apple Notes", "Apple Notes is macOS-only.")


def main():
    root = tk.Tk()
    try:                       # nicer native look on macOS
        ttk.Style().theme_use("aqua")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
