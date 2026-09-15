"""
Test suite for mp3_organizer.py.

Run with:
    pytest 

These tests build tiny synthetic MP3 files in a temp directory (a minimal
valid MPEG frame header plus real ID3 tags written via mutagen) so the
whole pipeline can be exercised without needing real audio files.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mp3_organizer as organizer

from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, APIC


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

# A minimal MPEG audio frame header + a little silence, just enough for
# mutagen to recognize the file as an MP3 and for our hashing code to have
# real bytes to hash.
_FAKE_AUDIO_FRAMES = b"\xff\xfb\x90\x00" + b"\x00" * 200


def make_mp3(
    path,
    title=None,
    artist=None,
    album=None,
    track=None,
    cover=None,
    audio_bytes=_FAKE_AUDIO_FRAMES,
):
    """Write a synthetic MP3 file with the given ID3 tags."""
    path.write_bytes(audio_bytes)

    tags = ID3()
    if title is not None:
        tags.add(TIT2(encoding=3, text=title))
    if artist is not None:
        tags.add(TPE1(encoding=3, text=artist))
    if album is not None:
        tags.add(TALB(encoding=3, text=album))
    if track is not None:
        tags.add(TRCK(encoding=3, text=track))
    if cover is not None:
        mime, data, pic_type = cover
        tags.add(APIC(encoding=3, mime=mime, type=pic_type, desc="Cover", data=data))
    tags.save(path)
    return path


# --------------------------------------------------------------------------
# clean_text
# --------------------------------------------------------------------------

def test_clean_text_none_falls_back_to_unknown():
    assert organizer.clean_text(None) == "Unknown"


def test_clean_text_strips_and_collapses_whitespace():
    assert organizer.clean_text("  Weird   Spacing  ") == "Weird Spacing"


def test_clean_text_strips_control_characters():
    assert organizer.clean_text("Bad\x00Name\x01") == "BadName"


def test_clean_text_empty_after_cleaning_falls_back():
    assert organizer.clean_text("   \x00\x01  ") == "Unknown"


def test_clean_text_handles_non_string_input():
    assert organizer.clean_text(42) == "42"


# --------------------------------------------------------------------------
# safe_filename
# --------------------------------------------------------------------------

def test_safe_filename_removes_illegal_characters():
    assert organizer.safe_filename('Bad:/Name<>|?*.mp3') == "BadName.mp3"


def test_safe_filename_falls_back_on_empty():
    assert organizer.safe_filename("") == "Unknown"


def test_safe_filename_falls_back_on_dot_or_dotdot():
    assert organizer.safe_filename(".") == "Unknown"
    assert organizer.safe_filename("..") == "Unknown"


def test_safe_filename_escapes_windows_reserved_names():
    assert organizer.safe_filename("CON") == "_CON"
    assert organizer.safe_filename("com1") == "_com1"


def test_safe_filename_strips_trailing_dots_and_spaces():
    assert organizer.safe_filename("Track Name.. ") == "Track Name"


def test_safe_filename_enforces_max_length():
    long_name = "A" * 500
    result = organizer.safe_filename(long_name, max_length=20)
    assert len(result) <= 20


# --------------------------------------------------------------------------
# get_metadata
# --------------------------------------------------------------------------

def test_get_metadata_reads_clean_tags(tmp_path):
    path = make_mp3(tmp_path / "a.mp3", title="Song", artist="Artist", album="Album", track="3")
    metadata = organizer.get_metadata(path)
    assert metadata == {"title": "Song", "artist": "Artist", "album": "Album", "track": 3}


def test_get_metadata_handles_missing_tags(tmp_path):
    path = make_mp3(tmp_path / "b.mp3")
    metadata = organizer.get_metadata(path)
    assert metadata["artist"] == "Unknown Artist"
    assert metadata["album"] == "Unknown Album"
    assert metadata["track"] == 0
    # Falls back to the filename stem when there's no title tag.
    assert metadata["title"] == "b"


def test_get_metadata_parses_track_with_total(tmp_path):
    path = make_mp3(tmp_path / "c.mp3", track="3/12")
    metadata = organizer.get_metadata(path)
    assert metadata["track"] == 3


def test_get_metadata_handles_garbage_track_number(tmp_path):
    path = make_mp3(tmp_path / "d.mp3", track="not-a-number")
    metadata = organizer.get_metadata(path)
    assert metadata["track"] == 0


def test_get_metadata_rejects_absurd_track_number(tmp_path):
    path = make_mp3(tmp_path / "e.mp3", track="99999")
    metadata = organizer.get_metadata(path)
    assert metadata["track"] == 0


# --------------------------------------------------------------------------
# unique_destination
# --------------------------------------------------------------------------

def test_unique_destination_returns_same_path_if_free(tmp_path):
    target = tmp_path / "song.mp3"
    assert organizer.unique_destination(target) == target


def test_unique_destination_increments_on_collision(tmp_path):
    target = tmp_path / "song.mp3"
    target.write_bytes(b"x")
    (tmp_path / "song (2).mp3").write_bytes(b"x")
    result = organizer.unique_destination(target)
    assert result == tmp_path / "song (3).mp3"


# --------------------------------------------------------------------------
# audio_content_hash
# --------------------------------------------------------------------------

def test_audio_content_hash_ignores_tag_differences(tmp_path):
    """Two files with identical audio but different tags should hash the same."""
    a = make_mp3(tmp_path / "a.mp3", title="Song A", artist="Artist A")
    b = make_mp3(tmp_path / "b.mp3", title="Totally Different Title", artist="Someone Else")
    assert organizer.audio_content_hash(a) == organizer.audio_content_hash(b)


def test_audio_content_hash_differs_for_different_audio(tmp_path):
    a = make_mp3(tmp_path / "a.mp3", audio_bytes=b"\xff\xfb\x90\x00" + b"\x00" * 200)
    b = make_mp3(tmp_path / "b.mp3", audio_bytes=b"\xff\xfb\x90\x00" + b"\x01" * 200)
    assert organizer.audio_content_hash(a) != organizer.audio_content_hash(b)


def test_audio_content_hash_returns_none_for_missing_file(tmp_path):
    assert organizer.audio_content_hash(tmp_path / "does_not_exist.mp3") is None


# --------------------------------------------------------------------------
# extract_cover_art
# --------------------------------------------------------------------------

def test_extract_cover_art_returns_none_when_absent(tmp_path):
    path = make_mp3(tmp_path / "a.mp3", title="Song")
    assert organizer.extract_cover_art(path) is None


def test_extract_cover_art_returns_embedded_image(tmp_path):
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"
    path = make_mp3(
        tmp_path / "a.mp3",
        title="Song",
        cover=("image/png", image_bytes, 3),
    )
    result = organizer.extract_cover_art(path)
    assert result is not None
    mime, data = result
    assert mime == "image/png"
    assert data == image_bytes


def test_extract_cover_art_prefers_front_cover_type(tmp_path):
    front = b"front-cover-bytes"
    other = b"other-picture-bytes"
    path = tmp_path / "a.mp3"
    path.write_bytes(_FAKE_AUDIO_FRAMES)
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=4, desc="Other", data=other))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Front", data=front))
    tags.save(path)

    mime, data = organizer.extract_cover_art(path)
    assert data == front


# --------------------------------------------------------------------------
# organize_library (end-to-end)
# --------------------------------------------------------------------------

def test_organize_library_creates_artist_album_structure(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()

    make_mp3(source / "a.mp3", title="Song One", artist="Artist A", album="Album B", track="3")

    organizer.organize_library(str(source), str(output))

    expected = output / "Artist A" / "Album B" / "03 - Song One.mp3"
    assert expected.exists()


def test_organize_library_is_idempotent(tmp_path):
    """Running twice on the same source should not create duplicate files."""
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    make_mp3(source / "a.mp3", title="Song One", artist="Artist A", album="Album B", track="3")

    organizer.organize_library(str(source), str(output))
    organizer.organize_library(str(source), str(output))

    all_mp3s = list(output.rglob("*.mp3"))
    assert len(all_mp3s) == 1


def test_organize_library_dry_run_makes_no_changes(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    make_mp3(source / "a.mp3", title="Song One", artist="Artist A", album="Album B", track="3")

    organizer.organize_library(str(source), str(output), dry_run=True)

    # Dry run should not create the output folder or copy anything.
    assert not output.exists()


def test_organize_library_detects_content_duplicates_across_names(tmp_path):
    """Two differently-named/tagged files with identical audio should be
    detected as duplicates and only one copy kept (skip mode)."""
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()

    make_mp3(source / "a.mp3", title="Song", artist="Artist", album="Album", track="1")
    make_mp3(source / "a_copy.mp3", title="Different Title", artist="Artist", album="Album", track="1")

    organizer.organize_library(str(source), str(output), on_duplicate="skip")

    all_mp3s = list(output.rglob("*.mp3"))
    assert len(all_mp3s) == 1


def test_organize_library_rename_mode_keeps_both_content_duplicates(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()

    make_mp3(source / "a.mp3", title="Song", artist="Artist", album="Album", track="1")
    make_mp3(source / "a_copy.mp3", title="Song", artist="Artist", album="Album", track="1")

    organizer.organize_library(str(source), str(output), on_duplicate="rename")

    all_mp3s = list(output.rglob("*.mp3"))
    assert len(all_mp3s) == 2


def test_organize_library_extracts_cover_art(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()

    image_bytes = b"\xff\xd8\xff\xe0" + b"fake-jpeg-data"
    make_mp3(
        source / "a.mp3",
        title="Song",
        artist="Artist",
        album="Album",
        track="1",
        cover=("image/jpeg", image_bytes, 3),
    )

    organizer.organize_library(str(source), str(output))

    cover_path = output / "Artist" / "Album" / "cover.jpg"
    assert cover_path.exists()
    assert cover_path.read_bytes() == image_bytes


def test_organize_library_handles_missing_source_gracefully(tmp_path, capsys):
    output = tmp_path / "output"
    organizer.organize_library(str(tmp_path / "does_not_exist"), str(output))
    captured = capsys.readouterr()
    assert "does not exist" in captured.out
