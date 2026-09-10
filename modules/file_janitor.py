import os
import shutil
import winshell
import subprocess
from pathlib import Path

USER_HOME = str(Path.home())

# Folders where it is 100% safe to automatically delete EVERYTHING inside daily
CACHE_TARGETS = [
    os.path.join(USER_HOME, ".cache", "huggingface"),
    os.path.join(USER_HOME, ".cache", "pip"),
    os.path.join(USER_HOME, "AppData", "Local", "Temp"),
    os.path.join(USER_HOME, "AppData", "Local", "npm-cache"),
    os.path.join(USER_HOME, "AppData", "Local", "CrashDumps"),
    os.path.join(USER_HOME, ".conda", "pkgs"),
    "C:\\Windows\\Temp",
    "C:\\Windows\\SoftwareDistribution\\Download",
    # Added the Spotify cache folders here to keep them from growing again!
    os.path.join(USER_HOME, "AppData", "Local", "Packages", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0", "LocalCache", "Spotify"),
    os.path.join(USER_HOME, "AppData", "Local", "Packages", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0", "LocalState", "Spotify", "Storage")
]

def force_delete_file(filepath):
    try:
        os.chmod(filepath, 0o777)
        os.remove(filepath)
        return True
    except Exception:
        return False

def purge_developer_caches():
    print("   -> Purging Python Pip & Conda Caches...")
    try:
        subprocess.run(["pip", "cache", "purge"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["conda", "clean", "--all", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def aggressive_clean():
    print("\n🧹 Starting Deep System Janitor...")
    purge_developer_caches()

    for folder in CACHE_TARGETS:
        if os.path.exists(folder):
            try:
                for item in os.listdir(folder):
                    item_path = os.path.join(folder, item)
                    try:
                        if os.path.isfile(item_path):
                            force_delete_file(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                    except Exception:
                        pass
            except Exception:
                pass

    print("   -> Emptying Windows Recycle Bin...")
    try:
        winshell.recycle_bin().empty(confirm=False, show_progress=False, sound=False)
    except Exception:
        pass
    print("✅ Daily System Clean Complete!")

def run_janitor():
    aggressive_clean()

if __name__ == "__main__":
    run_janitor()
