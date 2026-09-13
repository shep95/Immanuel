"""Media acquisition: download & import media files, YouTube transcripts.

These are optional, best-effort capabilities. Heavy/optional third-party
libraries (Pillow, youtube-transcript-api, yt-dlp) are imported lazily so the
deterministic core and the test suite never require them.
"""
