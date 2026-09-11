import re
import shutil
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError


def clean_text(text):
    """Remove unnecessary spaces from metadata."""
    if not text:
        return "Unknown"

    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    return text


def safe_filename(name):
    """Remove characters that cannot be used in file names."""
    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        name = name.replace(char, "")

    return name.strip()


def get_metadata(file_path):
    """Read the title, artist, album, and track number from an MP3."""
    try:
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        audio = EasyID3()
        audio.save(file_path)
        audio = EasyID3(file_path)

    title = clean_text(audio.get("title", [file_path.stem])[0])
    artist = clean_text(audio.get("artist", ["Unknown Artist"])[0])
    album = clean_text(audio.get("album", ["Unknown Album"])[0])

    track = audio.get("tracknumber", ["0"])[0]
    track = track.split("/")[0]

    try:
        track = int(track)
    except ValueError:
        track = 0

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "track": track
    }


def update_metadata(file_path, metadata):
    """Write cleaned metadata back to the MP3 file."""
    audio = EasyID3(file_path)

    audio["title"] = metadata["title"]
    audio["artist"] = metadata["artist"]
    audio["album"] = metadata["album"]

    if metadata["track"] > 0:
        audio["tracknumber"] = str(metadata["track"])

    audio.save()


def organize_file(file_path, output_folder):
    metadata = get_metadata(file_path)

    update_metadata(file_path, metadata)

    artist = safe_filename(metadata["artist"])
    album = safe_filename(metadata["album"])
    title = safe_filename(metadata["title"])

    destination_folder = output_folder / artist / album
    destination_folder.mkdir(parents=True, exist_ok=True)

    if metadata["track"] > 0:
        filename = f"{metadata['track']:02d} - {title}.mp3"
    else:
        filename = f"{title}.mp3"

    destination = destination_folder / filename

    # Avoid accidentally overwriting a song that is already there
    if destination.exists():
        print(f"Skipped: {destination.name} already exists")
        return

    shutil.copy2(file_path, destination)

    print(
        f"Organized: {metadata['artist']} - {metadata['title']} "
        f"({metadata['album']})"
    )


def organize_library(source_folder, output_folder):
    source_folder = Path(source_folder)
    output_folder = Path(output_folder)

    if not source_folder.exists():
        print("The source folder does not exist.")
        return

    mp3_files = list(source_folder.rglob("*.mp3"))

    if not mp3_files:
        print("No MP3 files were found.")
        return

    print(f"Found {len(mp3_files)} MP3 file(s).\n")

    for file_path in mp3_files:
        try:
            organize_file(file_path, output_folder)
        except Exception as error:
            print(f"Could not process {file_path.name}: {error}")

    print("\nFinished organizing music library.")


if __name__ == "__main__":
    source = input("Folder containing your MP3 files: ").strip()
    output = input("Folder for the organized library: ").strip()

    organize_library(source, output)
