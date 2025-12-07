
import os, sys, subprocess, platform
import tkinter as tk
from tkinter import filedialog, messagebox

def venv_python():
    root = os.path.dirname(os.path.abspath(__file__))
    if platform.system() == "Windows":
        path = os.path.join(root, ".venv", "Scripts", "python.exe")
    else:
        path = os.path.join(root, ".venv", "bin", "python")
    return path if os.path.exists(path) else sys.executable

def run():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("rbassist", "Select your music folder to analyze.\nThe process may take a while on large libraries.")
    folder = filedialog.askdirectory(title="Select Music Folder")
    if not folder:
        messagebox.showwarning("rbassist", "No folder selected. Exiting.")
        return
    py = venv_python()
    cmd = [py, "-m", "rbassist.cli", "analyze",
           "--input", folder,
           "--profile", "club_hifi_150s",
           "--device", "auto",
           "--workers", "6",
           "--rebuild-index"]
    try:
        # Launch in same console; users can see progress logs
        subprocess.run(cmd, check=True)
        messagebox.showinfo("rbassist", "Analysis complete. You can now use recommendations and exports.")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("rbassist", f"Analysis failed.\n\nCommand: {' '.join(cmd)}\n\nError: {e}")
    except Exception as e:
        messagebox.showerror("rbassist", f"Unexpected error: {e}")

if __name__ == "__main__":
    run()
