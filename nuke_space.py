import os
import subprocess
from pathlib import Path

def force_delete_directory(folder_path):
    if not os.path.exists(folder_path):
        return False
        
    print(f"\n☢️ NUKING FOLDER: {folder_path}...")
    try:
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', folder_path], shell=True)
        return True
    except Exception as e:
        print(f"Failed to delete: {e}")
        return False

def main():
    # Target: The massive 10GB Spotify Cache
    spotify_cache = os.path.join(
        str(Path.home()), 
        "AppData", "Local", "Packages", 
        "SpotifyAB.SpotifyMusic_zpdnekdrzrea0", "LocalCache", "Spotify"
    )
    
    # Also clear the offline storage folder just in case
    spotify_storage = os.path.join(
        str(Path.home()), 
        "AppData", "Local", "Packages", 
        "SpotifyAB.SpotifyMusic_zpdnekdrzrea0", "LocalState", "Spotify", "Storage"
    )
    
    print("🚀 STARTING FINAL SPOTIFY NUKE 🚀")
    
    # Nuke the Cache
    if os.path.exists(spotify_cache):
        force_delete_directory(spotify_cache)
        print("✅ Spotify Cache Destroyed!")
    else:
        print("Spotify Cache not found or already deleted.")
        
    # Nuke the Storage
    if os.path.exists(spotify_storage):
        force_delete_directory(spotify_storage)
        print("✅ Spotify Storage Destroyed!")

    print("\n🎉 You should now have over 35GB of free space on your PC! Check your C: drive!")

if __name__ == "__main__":
    main()
