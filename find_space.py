import os
from pathlib import Path

def get_folder_size(path):
    """Calculates the total size of a folder and all its subfolders in MB."""
    total_size = 0
    try:
        # We use os.scandir as it is much faster for large directories
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total_size += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total_size += get_folder_size(entry.path)
            except Exception:
                continue
    except Exception:
        pass
    return total_size

def map_storage():
    user_home = os.path.join(str(Path.home()), "AppData", "Local")
    print(f"\n🔍 Mapping storage in {user_home} ... (This will take 1-2 minutes)")
    
    folder_sizes = []
    
    # Scan the top-level folders in your user directory
    try:
        for entry in os.scandir(user_home):
            if entry.is_dir(follow_symlinks=False):
                print(f"   Scanning: {entry.name} ...")
                size_bytes = get_folder_size(entry.path)
                size_gb = size_bytes / (1024 * 1024 * 1024)
                
                # Only keep track of folders larger than 0.5 GB
                if size_gb > 0.5:
                    folder_sizes.append((size_gb, entry.path))
    except Exception as e:
        print(f"Error reading root: {e}")

    # Sort from largest to smallest
    folder_sizes.sort(reverse=True, key=lambda x: x[0])
    
    print("\n🚨 THE LARGEST FOLDERS ON YOUR PC 🚨")
    print("-" * 60)
    for size, path in folder_sizes:
        print(f"[{size:.2f} GB] -> {path}")
    print("-" * 60)

if __name__ == "__main__":
    map_storage()
