import re
import shutil
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError


def clean_text(text: str) -> str:
    """Remove unnecessary spaces from metadata."""
    if not text or not text.strip():
        return "Unknown"

    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text if text else "Unknown"


def safe_filename(name: str, fallback: str = "Unknown") -> str:
    """Remove invalid filename characters and ensure name is non-empty."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "")

    cleaned = name.strip().strip(".")
    return cleaned if cleaned else fallback


def get_metadata(file_path: Path) -> dict:
    """Read title, artist, album, and track number safely from an MP3."""
    try:
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        # Create a blank ID3 header before wrapping with EasyID3
        tags = ID3()
        tags.save(file_path)
        audio = EasyID3(file_path)
    except Exception:
        audio = {}

    title_val = audio.get("title", [file_path.stem])[0]
    artist_val = audio.get("artist", ["Unknown Artist"])[0]
    album_val = audio.get("album", ["Unknown Album"])[0]

    title = clean_text(title_val if title_val else file_path.stem)
    artist = clean_text(artist_val if artist_val else "Unknown Artist")
    album = clean_text(album_val if album_val else "Unknown Album")

    raw_track = audio.get("tracknumber", ["0"])[0]
    raw_track = str(raw_track).split("/")[0]

    try:
        track = int(raw_track)
    except ValueError:
        track = 0

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "track": track,
    }


def update_metadata(file_path: Path, metadata: dict) -> None:
    """Write cleaned metadata back to the MP3 file."""
    try:
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()
        tags.save(file_path)
        audio = EasyID3(file_path)

    audio["title"] = metadata["title"]
    audio["artist"] = metadata["artist"]
    audio["album"] = metadata["album"]

    if metadata["track"] > 0:
        audio["tracknumber"] = str(metadata["track"])

    audio.save()


def organize_file(file_path: Path, output_folder: Path) -> None:
    metadata = get_metadata(file_path)
    update_metadata(file_path, metadata)

    artist = safe_filename(metadata["artist"], fallback="Unknown Artist")
    album = safe_filename(metadata["album"], fallback="Unknown Album")
    title = safe_filename(metadata["title"], fallback=file_path.stem)

    destination_folder = output_folder / artist / album
    destination_folder.mkdir(parents=True, exist_ok=True)

    if metadata["track"] > 0:
        filename = f"{metadata['track']:02d} - {title}.mp3"
    else:
        filename = f"{title}.mp3"

    destination = destination_folder / filename

    if destination.resolve() == file_path.resolve():
        print(f"Skipped: {destination.name} is already in place.")
        return

    if destination.exists():
        print(f"Skipped: {destination.name} already exists in target folder.")
        return

    shutil.copy2(file_path, destination)
    print(
        f"Organized: {metadata['artist']} - {metadata['title']} "
        f"({metadata['album']})"
    )


def organize_library(source_folder: str, output_folder: str) -> None:
    source_path = Path(source_folder).resolve()
    output_path = Path(output_folder).resolve()

    if not source_path.exists():
        print("The source folder does not exist.")
        return

    # Case-insensitive search for .mp3 files
    mp3_files = [
        p for p in source_path.rglob("*") if p.suffix.lower() == ".mp3"
    ]

    if not mp3_files:
        print("No MP3 files were found.")
        return

    print(f"Found {len(mp3_files)} MP3 file(s).\n")

    for file_path in mp3_files:
        try:
            organize_file(file_path, output_path)
        except Exception as error:
            print(f"Could not process {file_path.name}: {error}")

    print("\nFinished organizing the music library.")


if __name__ == "__main__":
    source = input("Folder containing your MP3 files: ").strip()
    output = input("Folder for the organized library: ").strip()

    organize_library(source, output)
