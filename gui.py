from __future__ import annotations

import threading
import queue
import tkinter as tk
from tkinter import filedialog

from .utils import walk_audio, load_meta
from .export_xml import write_rekordbox_xml


def _worker(fn, args, q: queue.Queue):
    try:
        fn(*args)
        q.put(("ok", None))
    except Exception as e:
        q.put(("err", str(e)))


def build_frame(parent: tk.Misc) -> None:
    """Build rbassist controls inside an existing Tk container.
    Schedules background polling on the same parent via after().
    """
    q: queue.Queue = queue.Queue()

    # Controls frame
    frm = tk.Frame(parent)
    frm.pack(padx=10, pady=10, fill=tk.X)

    tk.Label(frm, text="Audio folder:").grid(row=0, column=0, sticky="w")
    folder_var = tk.StringVar()
    tk.Entry(frm, textvariable=folder_var, width=60).grid(row=0, column=1, sticky="we")

    def pick_folder():
        d = filedialog.askdirectory()
        if d:
            folder_var.set(d)

    tk.Button(frm, text="Browse", command=pick_folder).grid(row=0, column=2, padx=5)

    seed_var = tk.StringVar()
    xml_var = tk.StringVar(value="rbassist.xml")

    log_txt = tk.Text(parent, height=18, width=100, state="disabled")
    log_txt.pack(padx=10, pady=(0, 10), fill=tk.BOTH, expand=True)

    def log(msg: str):
        log_txt.configure(state="normal")
        log_txt.insert(tk.END, msg + "\n")
        log_txt.see(tk.END)
        log_txt.configure(state="disabled")

    def spawn(fn, *args):
        threading.Thread(target=_worker, args=(fn, args, q), daemon=True).start()

    def do_build_embeddings():
        try:
            from .embed import build_embeddings
        except Exception as e:
            log(f"Embed deps missing: install .[ml] (and torch). Error: {e}")
            return
        folder = folder_var.get()
        files = walk_audio([folder]) if folder else []
        if not files:
            log("No audio files found.")
            return
        log(f"Embedding {len(files)} files...")
        spawn(build_embeddings, files)

    def do_build_index():
        try:
            from .recommend import build_index
        except Exception as e:
            log(f"Index deps missing: pip install hnswlib. Error: {e}")
            return
        log("Building index...")
        spawn(build_index)

    def do_recommend():
        try:
            from .recommend import recommend
        except Exception as e:
            log(f"Recommend deps missing: pip install hnswlib. Error: {e}")
            return
        seed = seed_var.get().strip()
        if not seed:
            log("Enter a seed string.")
            return
        log(f"Recommending for: {seed}")
        spawn(recommend, seed)

    def do_export_xml():
        meta = load_meta()
        out = xml_var.get().strip() or "rbassist.xml"
        log(f"Writing XML -> {out}")
        spawn(write_rekordbox_xml, meta, out)

    tk.Button(frm, text="Build Embeddings", command=do_build_embeddings).grid(row=1, column=0, pady=5)
    tk.Button(frm, text="Build Index", command=do_build_index).grid(row=1, column=1, sticky="w", pady=5)
    tk.Label(frm, text="Seed:").grid(row=2, column=0, sticky="w")
    tk.Entry(frm, textvariable=seed_var, width=40).grid(row=2, column=1, sticky="w")
    tk.Button(frm, text="Recommend", command=do_recommend).grid(row=2, column=2, padx=5)
    tk.Label(frm, text="XML Out:").grid(row=3, column=0, sticky="w")
    tk.Entry(frm, textvariable=xml_var, width=40).grid(row=3, column=1, sticky="w")
    tk.Button(frm, text="Export Rekordbox XML", command=do_export_xml).grid(row=3, column=2, padx=5)

    def poll():
        try:
            while True:
                s, data = q.get_nowait()
                if s == "ok":
                    log("Done")
                else:
                    log(f"Error: {data}")
        except queue.Empty:
            pass
        finally:
            parent.after(200, poll)

    parent.after(150, poll)


def main() -> None:
    root = tk.Tk()
    root.title("rbassist")
    build_frame(root)
    tk.Button(root, text="Exit", command=root.destroy).pack(pady=(0, 10))
    root.mainloop()


if __name__ == "__main__":
    main()

