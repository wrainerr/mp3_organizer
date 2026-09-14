import argparse
import hashlib
import re
import shutil
import sys
import unicodedata
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError
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

# Chunk size used when hashing audio data, so large files don't need to be
# read into memory all at once.
_HASH_CHUNK_SIZE = 1024 * 1024


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
    """Read the title, artist, album, and track number from an MP3.

    Never raises for tag-related problems: any read/parse issue results in
    sensible fallback values so the caller can still file the track away.
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


def _id3v2_tag_size(file_path):
    """Return the byte length of a file's ID3v2 header + body, or 0 if the
    file doesn't start with one. Ignores extended-header edge cases, which
    is fine for hashing purposes (worst case: a few extra header bytes get
    included in the hash, which does not affect duplicate detection since
    it is applied consistently to every file)."""
    try:
        with open(file_path, "rb") as handle:
            header = handle.read(10)
    except OSError:
        return 0

    if len(header) < 10 or header[0:3] != b"ID3":
        return 0

    size = 0
    for byte in header[6:10]:
        # ID3v2 tag size is a "syncsafe" integer: 4 bytes, 7 usable bits each.
        if byte & 0x80:
            return 0  # malformed syncsafe byte; don't trust the size
        size = (size << 7) | (byte & 0x7F)

    return 10 + size


def audio_content_hash(file_path, chunk_size=_HASH_CHUNK_SIZE):
    """Hash the audio frame data of an MP3, excluding ID3v2/ID3v1 tags.

    Two copies of the same song saved with different metadata (different
    titles, re-ordered tags, re-encoded ID3 versions, etc.) will still
    produce the same hash, which is what makes this useful for detecting
    real duplicates rather than just duplicate filenames.

    Returns None if the file can't be read.
    """
    try:
        size = file_path.stat().st_size
        start = min(_id3v2_tag_size(file_path), size)
        end = size

        # Exclude a trailing 128-byte ID3v1 tag, if present.
        if end - start >= 128:
            with open(file_path, "rb") as handle:
                handle.seek(end - 128)
                if handle.read(3) == b"TAG":
                    end -= 128

        hasher = hashlib.sha256()
        with open(file_path, "rb") as handle:
            handle.seek(start)
            remaining = end - start
            while remaining > 0:
                chunk = handle.read(min(chunk_size, remaining))
                if not chunk:
                    break
                hasher.update(chunk)
                remaining -= len(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def build_hash_index(output_folder):
    """Hash every MP3 already in output_folder, so duplicates can be caught
    even across separate runs, not just within a single run."""
    index = {}
    if not output_folder.exists():
        return index

    for path in output_folder.rglob("*.mp3"):
        if not path.is_file():
            continue
        digest = audio_content_hash(path)
        if digest:
            index.setdefault(digest, path)

    return index


def _extension_for_mime(mime_type):
    mime_type = (mime_type or "").lower()
    if "png" in mime_type:
        return "png"
    if "gif" in mime_type:
        return "gif"
    return "jpg"


def extract_cover_art(file_path):
    """Return (mime_type, image_bytes) for an MP3's embedded cover art, or
    None if there isn't one. Never raises: any read/parse failure is
    treated as "no artwork found" so it can't break the main organize flow.
    """
    try:
        tags = ID3(file_path)
    except (MutagenError, ID3NoHeaderError, OSError):
        return None

    pictures = tags.getall("APIC")
    if not pictures:
        return None

    # Prefer the frame explicitly marked as the front cover (type 3);
    # fall back to whichever picture is embedded first.
    front_cover = next((pic for pic in pictures if getattr(pic, "type", None) == 3), None)
    picture = front_cover or pictures[0]

    if not getattr(picture, "data", None):
        return None

    return picture.mime or "image/jpeg", picture.data


def organize_file(
    file_path,
    output_folder,
    stats,
    on_duplicate="skip",
    dry_run=False,
    hash_index=None,
    dedupe=True,
    extract_art=True,
):
    """Copy and (re)tag an single MP3 into output_folder/Artist/Album/.

    on_duplicate controls what happens when the destination filename
    already exists, OR when dedupe finds a file with identical audio
    content already organized:
      - "skip"   (default): leave the existing file alone, skip this one.
      - "rename": copy alongside it as "Title (2).mp3", "Title (3).mp3", etc.

    dry_run previews every action (including cover art extraction) without
    touching the filesystem: no folders are created, no tags are written,
    no files are copied.

    hash_index maps content hash -> path already organized, and is mutated
    in place so later files in the same run see earlier ones.
    """
    if on_duplicate not in ("skip", "rename"):
        raise ValueError(f"invalid on_duplicate value: {on_duplicate!r}")

    if hash_index is None:
        hash_index = {}

    metadata = get_metadata(file_path)

    content_hash = audio_content_hash(file_path) if dedupe else None
    duplicate_of = hash_index.get(content_hash) if content_hash else None

    if duplicate_of is not None and on_duplicate == "skip":
        print(
            f"Skipped (duplicate content): {file_path.name} "
            f"matches already-organized {duplicate_of.name}"
        )
        stats["skipped"] += 1
        stats["duplicate_content"] = stats.get("duplicate_content", 0) + 1
        return

    if duplicate_of is not None:
        print(
            f"Note: {file_path.name} has the same audio content as "
            f"{duplicate_of.name}; keeping both copies (rename mode)."
        )
        stats["duplicate_content"] = stats.get("duplicate_content", 0) + 1

    if not dry_run:
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

    if not dry_run:
        try:
            destination_folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ValueError(f"could not create destination folder ({error})") from error

    if extract_art:
        _maybe_save_cover_art(file_path, destination_folder, output_folder, stats, dry_run)

    if destination.exists():
        if on_duplicate == "rename":
            original_name = destination.name
            destination = unique_destination(destination)
            print(f"Renamed on collision: {original_name} -> {destination.name}")
        else:
            print(f"Skipped: {destination.name} already exists")
            stats["skipped"] += 1
            return

    if dry_run:
        stats["organized"] += 1
        print(
            f"Would organize: {metadata['artist']} - {metadata['title']} "
            f"({metadata['album']}) -> {destination.relative_to(output_folder)}"
        )
        if content_hash:
            hash_index.setdefault(content_hash, destination)
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

    if content_hash:
        hash_index.setdefault(content_hash, destination)


def _maybe_save_cover_art(file_path, destination_folder, output_folder, stats, dry_run):
    """Save embedded cover art to destination_folder as cover.<ext>, unless
    that album folder already has one. Safe to call once per track; the
    existence check keeps it a no-op after the first track in each album.
    """
    try:
        already_has_cover = destination_folder.is_dir() and any(
            destination_folder.glob("cover.*")
        )
    except OSError:
        already_has_cover = False

    if already_has_cover:
        return

    art = extract_cover_art(file_path)
    if not art:
        return

    mime_type, data = art
    cover_path = destination_folder / f"cover.{_extension_for_mime(mime_type)}"

    if dry_run:
        print(f"Would save cover art: {cover_path.relative_to(output_folder)}")
        return

    try:
        cover_path.write_bytes(data)
    except OSError as error:
        print(f"Warning: could not save cover art for {file_path.name}: {error}")
        return

    stats["artwork_saved"] = stats.get("artwork_saved", 0) + 1
    print(f"Saved cover art: {cover_path.relative_to(output_folder)}")


def organize_library(
    source_folder,
    output_folder,
    on_duplicate="skip",
    dry_run=False,
    dedupe=True,
    extract_art=True,
):
    """on_duplicate, dry_run, dedupe, and extract_art are forwarded to
    organize_file for every track; see its docstring for details."""
    if on_duplicate not in ("skip", "rename"):
        raise ValueError(f"invalid on_duplicate value: {on_duplicate!r}")

    source_folder = Path(source_folder).expanduser()
    output_folder = Path(output_folder).expanduser()

    if not source_folder.exists():
        print("The source folder does not exist.")
        return
    if not source_folder.is_dir():
        print("The source path is not a folder.")
        return

    if not dry_run:
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

    if dry_run:
        print("Dry run: no files, tags, or folders will actually be changed.\n")

    # Pre-populate the dedupe index from what's already organized, so
    # content duplicates are caught across separate runs, not just within
    # a single run.
    hash_index = build_hash_index(output_folder) if dedupe else {}

    stats = {"organized": 0, "skipped": 0, "failed": 0}

    for file_path in mp3_files:
        try:
            if not file_path.exists():
                # File could have been moved/deleted mid-run.
                print(f"Could not process {file_path.name}: file no longer exists")
                stats["failed"] += 1
                continue
            organize_file(
                file_path,
                output_folder,
                stats,
                on_duplicate=on_duplicate,
                dry_run=dry_run,
                hash_index=hash_index,
                dedupe=dedupe,
                extract_art=extract_art,
            )
        except KeyboardInterrupt:
            raise
        except Exception as error:
            print(f"Could not process {file_path.name}: {error}")
            stats["failed"] += 1

    summary = (
        f"\nFinished organizing the music library. "
        f"{stats['organized']} organized, "
        f"{stats['skipped']} skipped, "
        f"{stats['failed']} failed."
    )
    if stats.get("duplicate_content"):
        summary += f" {stats['duplicate_content']} duplicate(s) by content."
    if stats.get("artwork_saved"):
        summary += f" {stats['artwork_saved']} cover image(s) saved."
    print(summary)


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Clean MP3 metadata and organize a library into Artist/Album folders."
    )
    parser.add_argument("-s", "--source", help="folder containing your MP3 files")
    parser.add_argument("-o", "--output", help="folder for the organized library")
    parser.add_argument(
        "--on-duplicate",
        choices=("skip", "rename"),
        default="skip",
        help="what to do when a destination filename or duplicate audio "
        "content is found (default: skip)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview what would happen without changing any files",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="disable content-based duplicate detection (filename collision "
        "handling still applies)",
    )
    parser.add_argument(
        "--no-artwork",
        action="store_true",
        help="don't extract embedded cover art into the album folders",
    )
    return parser.parse_args(argv)


def _prompt_for_missing_args(args):
    """Fall back to interactive prompts for source/output/on_duplicate when
    they weren't supplied as command-line arguments, preserving the original
    interactive experience for anyone running the script without flags.

    If source and output were both given as flags, this is a scripted/
    non-interactive invocation, so on_duplicate is never prompted for even
    though it has a default value; the default (or an explicit
    --on-duplicate) is used as-is.
    """
    interactive_mode = not args.source or not args.output

    if not args.source:
        args.source = input("Folder containing your MP3 files: ").strip()
    if not args.output:
        args.output = input("Folder for the organized library: ").strip()

    if interactive_mode and "--on-duplicate" not in sys.argv:
        duplicate_choice = input(
            "If a song already exists at its destination, "
            "(s)kip it or (r)ename the new copy? [s]: "
        ).strip().lower()
        args.on_duplicate = "rename" if duplicate_choice.startswith("r") else "skip"

    return args


if __name__ == "__main__":
    parsed_args = _parse_args(sys.argv[1:])

    try:
        parsed_args = _prompt_for_missing_args(parsed_args)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)

    if not parsed_args.source or not parsed_args.output:
        print("Both a source and an output folder are required.")
        sys.exit(1)

    try:
        organize_library(
            parsed_args.source,
            parsed_args.output,
            on_duplicate=parsed_args.on_duplicate,
            dry_run=parsed_args.dry_run,
            dedupe=not parsed_args.no_dedupe,
            extract_art=not parsed_args.no_artwork,
        )
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
