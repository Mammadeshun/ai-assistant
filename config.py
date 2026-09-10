import os

# --- API KEYS ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --- FILE JANITOR SETTINGS ---
USER_HOME = os.path.expanduser("~")

# Deep Cleanup Targets (100% safe to delete)
CLEANUP_TARGETS = [
    os.environ.get('TEMP'),                                # User Temp
    r"C:\Windows\Temp",                                    # System Temp
    r"C:\Windows\Prefetch",                                # Windows Prefetch
    r"C:\Windows\SoftwareDistribution\Download",           # Windows Update Cache
    os.path.join(USER_HOME, r"AppData\Local\Temp"),        # AppData Temp
    os.path.join(USER_HOME, r"AppData\Local\CrashDumps"),  # App Crash Dumps
    os.path.join(USER_HOME, r"AppData\Local\npm-cache"),   # Node.js NPM cache
    os.path.join(USER_HOME, r".cache\huggingface"),        # HuggingFace Models (Can be huge)
    os.path.join(USER_HOME, r".keras")                     # Keras Models Cache
]

# Folders to monitor for organizing
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")

# Where things should be moved
DESTINATIONS = {
    "Images": os.path.join(USER_HOME, "Pictures", "Downloaded_Images"),
    "Datasets": os.path.join(USER_HOME, "Documents", "Projects", "Datasets"),
    "Study_Materials": os.path.join(USER_HOME, "Documents", "Study", "Unsorted_PDFs"),
    "Installers": os.path.join(USER_HOME, "Downloads", "Installers")
}

for folder in DESTINATIONS.values():
    os.makedirs(folder, exist_ok=True)
