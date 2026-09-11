# MP3 Metadata Organizer

A Python script that cleans MP3 metadata and organizes music files into a consistent folder structure.

I built this project to make local music libraries easier to manage. MP3 files from different sources can have inconsistent artist names, album names, titles, and track numbers. This script reads that metadata and automatically creates a more organized music library.

## Features

* Reads title, artist, album, and track number metadata
* Removes unnecessary spacing from metadata
* Updates metadata stored in MP3 files
* Renames songs using a consistent format
* Organizes songs into artist and album folders
* Searches through subfolders for MP3 files
* Prevents existing files from being overwritten
* Handles missing metadata

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
│       ├── 01 - BLOOD.mp3
│       ├── 02 - DNA.mp3
│       └── 03 - YAH.mp3
│
└── The Weeknd/
    └── After Hours/
        ├── 01 - Alone Again.mp3
        └── 02 - Too Late.mp3
```

## Requirements

* Python 3
* Mutagen

Install the required package with:

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

Run:

```bash
python mp3_organizer.py
```

The program will ask for the folder containing your MP3 files:

```text
Folder containing your MP3 files:
```

Then it will ask where you want the organized library:

```text
Folder for the organized library:
```

The program organizes songs using this structure:

```text
Artist/
└── Album/
    └── Track Number - Title.mp3
```

For example:

```text
Tyler, The Creator/
└── IGOR/
    ├── 01 - IGOR'S THEME.mp3
    ├── 02 - EARFQUAKE.mp3
    └── 03 - I THINK.mp3
```

## Technologies

* Python
* Mutagen
* pathlib
* shutil
* Regular expressions

## What I Learned

This project gave me experience working with:

* File and directory manipulation
* MP3 metadata
* Third-party Python packages
* Error handling
* Directory traversal
* Data cleaning
* Automation

## Future Improvements

Possible future additions include:

* Album artwork support
* Duplicate song detection
* A graphical interface
* Automatic online metadata lookup
* Preview mode before modifying files
* FLAC and other audio format support
