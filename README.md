# MP3 Metadata Organizer

A Python script that cleans and standardizes MP3 metadata and organizes music files into a consistent folder structure.

I created this project to make large local music libraries easier to manage. MP3 files from different sources can have inconsistent artist names, album names, track numbers, and file names. This script reads the metadata from each file, cleans it, and creates an organized music library automatically.

## Features

* Reads MP3 metadata including title, artist, album, and track number
* Removes extra spaces and standardizes text formatting
* Updates cleaned metadata inside the MP3 file
* Renames tracks using a consistent naming format
* Creates folders based on artist and album
* Searches through subfolders automatically
* Avoids overwriting existing files
* Handles missing metadata with default values

## Example

An unorganized music folder might contain:

```text
music/
├── song1.mp3
├── track_final.mp3
└── another_song.mp3
```

After running the program, the output could look like:

```text
organized_music/
├── Kendrick Lamar/
│   └── DAMN./
│       ├── 01 - Blood.mp3
│       ├── 02 - DNA.mp3
│       └── 03 - Yah.mp3
│
└── The Weeknd/
    └── After Hours/
        ├── 01 - Alone Again.mp3
        └── 02 - Too Late.mp3
```

## Requirements

* Python 3
* Mutagen

Install the required dependency with:

```bash
pip install -r requirements.txt
```

Or install Mutagen directly:

```bash
pip install mutagen
```

## How to Run

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/mp3-metadata-organizer.git
```

Move into the project folder:

```bash
cd mp3-metadata-organizer
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the script:

```bash
python mp3_organizer.py
```

The program will ask for two locations:

```text
Folder containing your MP3 files:
Folder for the organized library:
```

Enter the folder containing the original music files and then choose where the organized library should be created.

## File Organization

The program uses the following structure:

```text
Artist/
└── Album/
    └── Track Number - Title.mp3
```

For example:

```text
Tyler, The Creator/
└── IGOR/
    ├── 01 - Igor's Theme.mp3
    ├── 02 - Earfquake.mp3
    └── 03 - I Think.mp3
```

## Why I Built This

I wanted a simple way to clean and organize MP3 libraries without manually editing every file. This project also gave me experience working with Python file handling, metadata, external libraries, directory traversal, and error handling.

## Technologies

* Python
* Mutagen
* pathlib
* shutil
* Regular expressions

## Future Improvements

Some features I would like to add include:

* Album artwork support
* Duplicate song detection
* A graphical interface
* Automatic metadata lookup
* Preview mode before changing files
* Support for FLAC and other audio formats

## License

This project is available for personal and educational use.
