import argparse
import re
import shutil
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError


def clean_text(text: str) -> str:
    """Remove unnecessary whitespace and blank values."""
    if not text or not text.strip():
        return "Unknown"

    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned if cleaned else "Unknown"


def safe_filename(name: str, fallback: str = "Unknown") -> str:
    """Remove reserved OS characters and trailing dots/spaces."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "")

    cleaned = name.strip().strip(".")
    return cleaned if cleaned else fallback


def parse_track_number(raw_track: str) -> int:
    """Extract a valid track integer from formats like '01', '1/12', or '1-02'."""
    if not raw_track:
        return 0

    # Extract first sequence of digits
    match = re.search(r"\d+", str(raw_track))
    if match:
        try:
            return int(match.group())
        except ValueError:
            return 0
    return 0


def get_metadata(file_path: Path) -> dict:
    """Read title, artist, album, and track number safely from an MP3."""
    try:
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()
        tags.save(file_path)
        audio = EasyID3(file_path)
    except Exception:
        audio = EasyID3()  # Fallback to an empty EasyID3 object rather than a dict

    title_val = audio.get("title", [file_path.stem])[0]
    artist_val = audio.get("artist", ["Unknown Artist"])[0]
    album_val = audio.get("album", ["Unknown Album"])[0]

    title = clean_text(title_val if title_val else file_path.stem)
    artist = clean_text(artist_val if artist_val else "Unknown Artist")
    album = clean_text(album_val if album_val else "Unknown Album")

    raw_track = audio.get("tracknumber", ["0"])[0]
    track = parse_track_number(raw_track)

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


def organize_file(
    file_path: Path, output_folder: Path, move_files: bool = False
) -> None:
    """Organize a single MP3 file into Artist/Album/Track - Title structure."""
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
        print(f"Skipped: {destination.name} already exists in target directory.")
        return

    if move_files:
        shutil.move(file_path, destination)
        action = "Moved"
    else:
        shutil.copy2(file_path, destination)
        action = "Copied"

    print(f"{action}: {metadata['artist']} - {metadata['title']} ({metadata['album']})")


def organize_library(
    source_folder: str, output_folder: str, move_files: bool = False
) -> None:
    source_path = Path(source_folder).resolve()
    output_path = Path(output_folder).resolve()

    if not source_path.exists():
        print("Error: The source folder does not exist.")
        return

    mp3_files = [
        p for p in source_path.rglob("*") if p.is_file() and p.suffix.lower() == ".mp3"
    ]

    if not mp3_files:
        print("No MP3 files found.")
        return

    print(f"Found {len(mp3_files)} MP3 file(s).\n")

    for file_path in mp3_files:
        try:
            organize_file(file_path, output_path, move_files=move_files)
        except Exception as error:
            print(f"Could not process {file_path.name}: {error}")

    print("\nFinished organizing the music library.")


if __name__ == "__main__":
    source = input("Folder containing your MP3 files: ").strip()
    output = input("Folder for the organized library: ").strip()
    mode = input("Move files instead of copying? (y/N): ").strip().lower()

    should_move = mode == "y"
    organize_library(source, output, move_files=should_move)
