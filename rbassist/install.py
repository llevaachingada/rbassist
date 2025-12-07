import os
import sys
import subprocess
import platform
import shutil
import venv

VENV_DIR = ".venv"

COMMON_DEPS = [
    "numpy",
    "scipy",
    "tqdm",
    "librosa",
    "soundfile",
    "hnswlib",
    "typer",
]


def run(cmd, check=True, capture_output=False):
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)


def ensure_venv():
    if not os.path.isdir(VENV_DIR):
        print(f"Creating virtual environment at {VENV_DIR} ...")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    else:
        print(f"Using existing virtual environment at {VENV_DIR}")
    if platform.system() == "Windows":
        py = os.path.join(VENV_DIR, "Scripts", "python.exe")
        pip = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    else:
        py = os.path.join(VENV_DIR, "bin", "python")
        pip = os.path.join(VENV_DIR, "bin", "pip")
    return py, pip


def has_nvidia_smi():
    try:
        out = run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            check=False,
            capture_output=True,
        )
        return out.returncode == 0 and out.stdout.strip() != ""
    except Exception:
        return False


def decide_torch_args(sysname, machine):
    """Return pip args to install torch with the correct accelerator."""
    pkgs = ["torch"]
    if sysname == "Windows" and has_nvidia_smi():
        index = "https://download.pytorch.org/whl/cu121"
        return ["-i", index, *pkgs]
    if sysname == "Darwin" and machine == "arm64":
        return [*pkgs]  # MPS support included in default wheel
    return [*pkgs]  # CPU wheel


def pip_install(pip, *packages):
    run([pip, "install", "--upgrade", "pip"])
    if packages:
        run([pip, "install", *packages])


def which(cmd):
    return shutil.which(cmd) is not None


def auto_install_ffmpeg(sysname):
    """Install ffmpeg if missing, using platform package managers when available."""
    if shutil.which("ffmpeg"):
        print("ffmpeg found in PATH")
        return True

    print("ffmpeg not found; attempting automatic installation ...")
    try:
        if sysname == "Darwin":
            if which("brew"):
                run(["brew", "update"], check=False)
                run(["brew", "install", "ffmpeg"])
                return shutil.which("ffmpeg") is not None
            print(
                'Homebrew not found. Install with: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            )
            return False

        if sysname == "Windows":
            if which("winget"):
                # Winget ID for Gyan FFmpeg builds
                run(["winget", "install", "-e", "--id", "Gyan.FFmpeg"], check=False)
                return shutil.which("ffmpeg") is not None
            if which("choco"):
                run(["choco", "install", "-y", "ffmpeg"])
                return shutil.which("ffmpeg") is not None
            print(
                "winget/choco not found. Install winget from Microsoft Store or Chocolatey from https://chocolatey.org/install"
            )
            return False

        # Linux: try apt, dnf, yum, pacman
        if which("apt"):
            run(["sudo", "apt", "update"], check=False)
            run(["sudo", "apt", "install", "-y", "ffmpeg"])
            return shutil.which("ffmpeg") is not None
        if which("dnf"):
            run(["sudo", "dnf", "install", "-y", "ffmpeg"])
            return shutil.which("ffmpeg") is not None
        if which("yum"):
            run(["sudo", "yum", "install", "-y", "ffmpeg"], check=False)
            return shutil.which("ffmpeg") is not None
        if which("pacman"):
            run(["sudo", "pacman", "-Sy", "--noconfirm", "ffmpeg"])
            return shutil.which("ffmpeg") is not None

        print("No known package manager found. Install ffmpeg manually via your distro.")
        return False
    except subprocess.CalledProcessError as e:
        print("Automatic ffmpeg install failed:", e)
        return False


def main():
    sysname = platform.system()
    machine = platform.machine().lower()
    print(f"Detected platform: {sysname} / {machine}")

    py, pip = ensure_venv()
    print(f"Using interpreter: {py}")

    torch_args = decide_torch_args(sysname, machine)
    print(f"Installing torch with args: {torch_args}")
    pip_install(pip, *torch_args)

    pip_install(pip, *COMMON_DEPS)

    repo_root = os.getcwd()
    pyproject = os.path.join(repo_root, "pyproject.toml")
    setup_py = os.path.join(repo_root, "setup.py")
    if os.path.isfile(pyproject) or os.path.isfile(setup_py):
        print("Installing local package in editable mode (-e) ...")
        run([py, "-m", "pip", "install", "-e", "."])
    else:
        print("No pyproject.toml/setup.py found; skipping editable install.")

    ok = auto_install_ffmpeg(sysname)
    if not ok:
        print("WARNING: ffmpeg is still missing. Some audio operations may fail until you install it.")

    print("\nInstall complete.")
    print("Next steps:")
    if sysname == "Windows":
        print(r"  .venv\Scripts\activate")
        print(r'  python -m rbassist.cli analyze --input "D:\\Music" --profile club_hifi_150s --device auto --workers 6 --rebuild-index')
    elif sysname == "Darwin":
        print(r"  source .venv/bin/activate")
        print(r'  python -m rbassist.cli analyze --input "/Volumes/Music" --profile club_hifi_150s --device auto --workers 6 --rebuild-index')
    else:
        print(r"  source .venv/bin/activate")
        print(r'  python -m rbassist.cli analyze --input "/path/to/Music" --profile club_hifi_150s --device auto --workers 6 --rebuild-index')


if __name__ == "__main__":
    main()
