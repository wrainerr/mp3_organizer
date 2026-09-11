import re
import shutil
import sys
import unicodedata
from pathlib import Path

from mutagen.id3 import ID3NoHeaderError
from mutagen.easyid3 import EasyID3
from mutagen import MutagenError

# Windows reserved device names (case-insensitive), with or without extension.
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Keep individual path components well under the 255-byte filesystem limit
# and comfortably under Windows' 260-char full-path limit.
_MAX_COMPONENT_LENGTH = 150


def clean_text(text):
    """Normalize and tidy a metadata string, falling back to 'Unknown'."""
    if text is None:
        return "Unknown"

    # Mutagen tag values are usually str, but guard against odd types
    # (e.g. mutagen ID3TimeStamp objects, ints, or bytes).
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return "Unknown"

    # Normalize unicode so visually-identical strings compare/sort the same.
    text = unicodedata.normalize("NFC", text)

    # Strip control characters (including stray null bytes some taggers leave).
    text = "".join(ch for ch in text if ch == "\t" or ord(ch) >= 32)

    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    return text if text else "Unknown"


def safe_filename(name, fallback="Unknown", max_length=_MAX_COMPONENT_LENGTH):
    """Make a string safe to use as a single file/folder name component."""
    if not name:
        name = fallback

    invalid_chars = '<>:"/\\|?*'
    name = "".join(ch for ch in name if ch not in invalid_chars)

    # Strip control characters, which are also invalid on Windows.
    name = "".join(ch for ch in name if ord(ch) >= 32)

    # Collapse whitespace left over from stripped characters.
    name = re.sub(r"\s+", " ", name).strip()

    # Windows disallows trailing dots/spaces on file and folder names.
    name = name.rstrip(" .")

    # Avoid "." / ".." which are special path components.
    if name in ("", ".", ".."):
        name = fallback

    # Avoid Windows reserved device names (CON, PRN, COM1, etc.).
    stem = name.split(".")[0].upper()
    if stem in _RESERVED_NAMES:
        name = f"_{name}"

    # Enforce a max length per path component (count in characters, safe
    # enough for the vast majority of filesystems using UTF-8).
    if len(name) > max_length:
        name = name[:max_length].rstrip(" .")
        if not name:
            name = fallback

    return name or fallback


def _first_value(values, default):
    """Safely pull the first element from a mutagen tag list."""
    if not values:
        return default
    value = values[0]
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    return value


def get_metadata(file_path):
    """Read title, artist, album, and track number from an MP3.

Missing tags use sensible fallback values. Corrupt or unreadable
MP3/ID3 data raises ValueError so the caller can skip the file.
"""
    try:
        try:
            audio = EasyID3(file_path)
        except ID3NoHeaderError:
            audio = EasyID3()
            audio.save(file_path)
            audio = EasyID3(file_path)
    except MutagenError as error:
        raise ValueError(f"unreadable or corrupt MP3/ID3 data ({error})") from error
    except (OSError, PermissionError) as error:
        raise ValueError(f"cannot access file ({error})") from error

    title = clean_text(_first_value(audio.get("title"), file_path.stem))
    artist = clean_text(_first_value(audio.get("artist"), "Unknown Artist"))
    album = clean_text(_first_value(audio.get("album"), "Unknown Album"))

    raw_track = _first_value(audio.get("tracknumber"), "0")
    raw_track = str(raw_track).split("/")[0].strip()
    # Keep only leading digits (handles stray junk like "07 " or "#3").
    digits = re.match(r"\d+", raw_track)
    track = int(digits.group()) if digits else 0

    # Guard against absurd/garbage track numbers.
    if track < 0 or track > 9999:
        track = 0

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "track": track,
    }


def update_metadata(file_path, metadata):
    """Write cleaned metadata back to the MP3 file."""
    try:
        audio = EasyID3(file_path)
    except ID3NoHeaderError:
        audio = EasyID3()
        audio.save(file_path)
        audio = EasyID3(file_path)

    audio["title"] = metadata["title"]
    audio["artist"] = metadata["artist"]
    audio["album"] = metadata["album"]

    if metadata["track"] > 0:
        audio["tracknumber"] = str(metadata["track"])
    elif "tracknumber" in audio:
        del audio["tracknumber"]

    try:
        audio.save()
    except (MutagenError, OSError, PermissionError) as error:
        raise ValueError(f"could not save tags ({error})") from error


def unique_destination(destination):
    """Return a non-colliding path by appending ' (2)', ' (3)', etc."""
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent

    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def organize_file(file_path, output_folder, stats):
    metadata = get_metadata(file_path)

    try:
        update_metadata(file_path, metadata)
    except ValueError as error:
        # Tagging failed (e.g. read-only file) but we can still file the
        # track away using the metadata we already read.
        print(f"Warning: {file_path.name}: {error} (copying without retagging)")

    artist = safe_filename(metadata["artist"], fallback="Unknown Artist")
    album = safe_filename(metadata["album"], fallback="Unknown Album")
    title = safe_filename(metadata["title"], fallback=file_path.stem or "Untitled")

    destination_folder = output_folder / artist / album

    try:
        destination_folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"could not create destination folder ({error})") from error

    if metadata["track"] > 0:
        filename = f"{metadata['track']:02d} - {title}.mp3"
    else:
        filename = f"{title}.mp3"

    destination = destination_folder / filename

    try:
        same_file = file_path.resolve() == destination.resolve()
    except OSError:
        same_file = False

    if same_file:
        print(f"Skipped: {file_path.name} is already at its destination")
        stats["skipped"] += 1
        return

    if destination.exists():
        print(f"Skipped: {destination.name} already exists")
        stats["skipped"] += 1
        return

    try:
        shutil.copy2(file_path, destination)
    except (OSError, PermissionError, shutil.Error) as error:
        # Clean up a partially-written file, if any.
        if destination.exists():
            try:
                destination.unlink()
            except OSError:
                pass
        raise ValueError(f"could not copy file ({error})") from error

    stats["organized"] += 1
    print(
        f"Organized: {metadata['artist']} - {metadata['title']} "
        f"({metadata['album']})"
    )


def organize_library(source_folder, output_folder):
    source_folder = Path(source_folder).expanduser()
    output_folder = Path(output_folder).expanduser()

    if not source_folder.exists():
        print("The source folder does not exist.")
        return
    if not source_folder.is_dir():
        print("The source path is not a folder.")
        return

    try:
        output_folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"Could not create the output folder: {error}")
        return

    try:
        source_resolved = source_folder.resolve()
        output_resolved = output_folder.resolve()
    except OSError:
        source_resolved = source_folder
        output_resolved = output_folder

    # Case-insensitive match for .mp3 / .MP3 / .Mp3, and skip files that
    # already live inside the output folder to avoid re-processing copies
    # on repeated runs.
    seen = set()
    mp3_files = []
    for path in source_folder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".mp3":
            continue
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved == output_resolved or output_resolved in resolved.parents:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        mp3_files.append(path)

    if not mp3_files:
        print("No MP3 files were found.")
        return

    print(f"Found {len(mp3_files)} MP3 file(s).\n")

    stats = {"organized": 0, "skipped": 0, "failed": 0}

    for file_path in mp3_files:
        try:
            if not file_path.exists():
                # File could have been moved/deleted mid-run.
                print(f"Could not process {file_path.name}: file no longer exists")
                stats["failed"] += 1
                continue
            organize_file(file_path, output_folder, stats)
        except KeyboardInterrupt:
            raise
        except Exception as error:
            print(f"Could not process {file_path.name}: {error}")
            stats["failed"] += 1

    print(
        f"\nFinished organizing the music library. "
        f"{stats['organized']} organized, "
        f"{stats['skipped']} skipped, "
        f"{stats['failed']} failed."
    )


if __name__ == "__main__":
    try:
        source = input("Folder containing your MP3 files: ").strip()
        output = input("Folder for the organized library: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)

    if not source or not output:
        print("Both a source and an output folder are required.")
        sys.exit(1)

    try:
        organize_library(source, output)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
