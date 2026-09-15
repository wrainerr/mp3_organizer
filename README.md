# MP3 Metadata Organizer

A Python script that cleans MP3 metadata and organizes music files into a consistent folder structure.

I built this project to make local music libraries easier to manage. MP3 files from different sources can have inconsistent artist names, album names, titles, and track numbers. This script reads that metadata, cleans it up, detects true duplicates (even when the filename or tags don't match), pulls out embedded cover art, and files everything into a consistent Artist/Album layout.

## Features

* Reads title, artist, album, and track number metadata
* Removes unnecessary spacing from metadata
* Updates metadata stored in MP3 files
* Renames songs using a consistent format
* Organizes songs into artist and album folders
* Searches through subfolders for MP3 files
* Prevents existing files from being overwritten (or renames on collision, your choice)
* Handles missing, corrupted, or malformed metadata without crashing
* Sanitizes filenames for cross-platform compatibility (Windows reserved names, illegal characters, path length limits)
* Detects true duplicate tracks by hashing audio content, not just matching filenames, so two copies of the same song with different tags or filenames are still caught
* Extracts embedded cover art into each album folder as `cover.jpg`/`cover.png`
* Supports a `--dry-run` mode that previews every action without touching any files
* Safe to re-run on the same library — already-organized files and previously-seen duplicates are detected and skipped
* Command-line flags for scripting, alongside the original interactive prompts

## Example

Before:

```text
music/
├── song1.mp3
├── track_final.mp3
└── another_song.mp3
```

After:

```text
organized_music/
├── Kendrick Lamar/
│   └── DAMN./
│       ├── cover.jpg
│       ├── 01 - BLOOD.mp3
│       ├── 02 - DNA.mp3
│       └── 03 - YAH.mp3
│
└── The Weeknd/
    └── After Hours/
        ├── cover.jpg
        ├── 01 - Alone Again.mp3
        └── 02 - Too Late.mp3
```

## Requirements

* Python 3
* Mutagen
* pytest (only needed to run the test suite)

Install the required packages with:

```bash
pip install -r requirements.txt
```

## Installation

Clone the repository:

```bash
git clone https://github.com/wrainerr/mp3_organizer.git
```

Move into the project:

```bash
cd mp3_organizer
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Interactive mode

Run the script with no arguments and it will prompt you for everything, same as before:

```bash
python mp3_organizer.py
```

```text
Folder containing your MP3 files:
Folder for the organized library:
If a song already exists at its destination, (s)kip it or (r)ename the new copy? [s]:
```

### Command-line mode

For scripting, automation, or just skipping the prompts, pass flags directly:

```bash
python mp3_organizer.py --source ./music --output ./organized_music
```

Available flags:

| Flag | Description |
|---|---|
| `-s`, `--source` | Folder containing your MP3 files |
| `-o`, `--output` | Folder for the organized library |
| `--on-duplicate {skip,rename}` | What to do on a filename or content duplicate (default: `skip`) |
| `--dry-run` | Preview every action (organizing, renaming, cover art) without changing any files |
| `--no-dedupe` | Disable content-based duplicate detection (filename collision handling still applies) |
| `--no-artwork` | Don't extract embedded cover art into album folders |

Example dry run:

```bash
python mp3_organizer.py --source ./music --output ./organized_music --dry-run
```

```text
Found 42 MP3 file(s).

Dry run: no files, tags, or folders will actually be changed.

Would organize: Tyler, The Creator - EARFQUAKE (IGOR) -> Tyler, The Creator/IGOR/02 - EARFQUAKE.mp3
Skipped (duplicate content): earfquake_copy.mp3 matches already-organized 02 - EARFQUAKE.mp3
...
```

The program organizes songs using this structure:

```text
Artist/
└── Album/
    ├── cover.jpg
    └── Track Number - Title.mp3
```

For example:

```text
Tyler, The Creator/
└── IGOR/
    ├── cover.jpg
    ├── 01 - IGOR'S THEME.mp3
    ├── 02 - EARFQUAKE.mp3
    └── 03 - I THINK.mp3
```

## How duplicate detection works

Rather than only checking whether a destination filename is already taken, the script hashes each file's actual audio data (excluding the ID3v2/ID3v1 tag bytes) with SHA-256. Two files with identical audio but completely different filenames, titles, or tag formatting will still hash the same and get flagged as duplicates — including duplicates already sitting in the output folder from a previous run. 

## Testing

The core logic (metadata cleaning, filename sanitization, hashing, cover art extraction, and full library organization) is covered by a pytest suite:

```bash
pip install -r requirements.txt
pytest
```

## Technologies

* Python
* Mutagen
* pathlib
* shutil
* argparse
* hashlib
* Regular expressions
* pytest

## What I Learned

This project gave me experience working with:

* File and directory manipulation
* MP3 metadata and binary file formats (parsing raw ID3v2 headers for hashing)
* Third-party Python packages
* Error handling and defensive programming
* Directory traversal
* Data cleaning
* Automation
* Building a dual interactive/CLI interface with argparse
* Writing an automated test suite with pytest

## Future Improvements

Possible future additions include:

* A graphical interface
* Automatic online metadata lookup (e.g. MusicBrainz)
* FLAC and other audio format support
