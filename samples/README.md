# Samples

Place short audio snippets here (`.wav`, `.mp3`, or `.flac`) for local testing. These files are ignored by Git to prevent large binaries in version control.

Recommendations:

- Keep clips under 30 seconds to minimize analysis time.
- Normalize audio to avoid clipping and produce consistent statistics.
- Use filenames that describe the source, e.g., `artist_track_hook.wav`.

Example workflow:

```bash
ffmpeg -i full_track.wav -ss 00:01:00 -t 00:00:20 samples/snippet.wav
electro analyze samples/snippet.wav
```
