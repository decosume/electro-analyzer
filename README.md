# Electro Analyzer

[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build](https://img.shields.io/badge/CI-ready-success.svg)](#)

Electro Analyzer is a Python CLI for inspecting electronic music tracks. It estimates BPM, key, structural sections, and identifies energy peaks such as drops. The tool also generates waveform, spectrogram, and chromagram visualizations for quick inspection.

## Features

- Command-line interface powered by Typer (`electro`)
- Librosa-based audio analysis pipeline for BPM, key, section, RMS, and mix-quality heuristics
- Visualization helpers for waveform, spectrogram, and chroma plots
- Lightweight mastering chain for quick loudness polish, including bass-balance and gentle transient-preserving modes
- Pluggable architecture for future model backends (e.g., Essentia)
- Production-ready : Ruff, Black, MyPy, pytest, pre-commit, Hatch

## Getting Startedtooling

```bash
git clone https://github.com/your-org/electro-analyzer.git
cd electro-analyzer
make setup
```

```bash
electro analyze path/to/track.wav
electro plot path/to/track.wav --out outputs/
electro master path/to/track.wav --out outputs/mastered.wav --match-bass
electro master path/to/track.wav --out outputs/mastered.wav --gentle
electro playlist --dry-run  # verify Spotify playlist candidates
```

The mastering command keeps the source's bass balance by default. Override it with `--bass-target 0.3` (ratio of low-frequency energy, 0.05–0.9) or disable matching via `--no-match-bass` if you want a deliberately different low end. Use `--gentle` to dial back pre-emphasis and compression when you want to preserve kick transients.

## Spotify Playlist Automation

The `electro playlist` command uses the Spotify Web API to create and periodically refresh a confident Barber Shop playlist packed with soul, funk, and modern R&B.

1. Create a Spotify application at <https://developer.spotify.com/dashboard/> and whitelist a redirect URI (e.g., `http://localhost:8080/callback`).
2. Export the credentials to your shell:

   ```bash
   export SPOTIFY_CLIENT_ID="..."
   export SPOTIFY_CLIENT_SECRET="..."
   export SPOTIFY_REDIRECT_URI="http://localhost:8080/callback"
   ```

3. Run the command (Spotify recently deprecated their public recommendations API, so the playlist now relies entirely on the curated tracks plus a rotating subset of the `rotation_queries` you configure):

   ```bash
   electro playlist --rotation-tracks 15 --profile-config profiles/your_profile.json
   ```

   The CLI opens a browser window the first time so you can authorize the app. Subsequent runs reuse the cached token at `~/.cache-barbershop-playlist`, which makes it straightforward to schedule a cron job (e.g., weekly) that keeps the vibes fresh.
   Use `--rotation-cadence weekly` to preserve the original ISO-week behavior or `--rotation-cadence daily` for a fresh deterministic mix every day. Add `--for-date YYYY-MM-DD` when a cron job or cloud scheduler should render the exact playlist for a specific run date.

   Cap the playlist with `--max-tracks` or target a specific runtime with `--target-duration-hours`. For example, the Duques Sta Fe profile sets `target_duration_minutes: 540` (nine hours) so the shop soundtrack covers the entire workday.

Pass `--dry-run` to preview the track list without modifying Spotify, or point `--profile-config` at a JSON file to override the curated songs, seeds, and description:

```json
{
  "playlist_name": "Fade & Flow Fridays",
  "description": "High-confidence cuts with smooth transitions.",
  "curated_queries": [
    "Al Green Love and Happiness",
    "Anderson .Paak Come Down",
    "Bruno Mars Versace on the Floor"
  ],
  "rotation_queries": ["FKJ Ylang Ylang", "Moonchild The Other Side"],
  "seed_genres": ["neo-soul", "funk"]
}
```

Profiles can also define `weekday_profiles` overrides so each weekday can swap curated tracks, block layouts, or descriptions while sharing the same base playlist metadata and rotation pool.

### Building profiles for other businesses

Use `scripts/build_client_profile.py` to turn a structured brief into a profile file. Define your mood blocks and language preferences (see `docs/profile_builder.md`), generate the profile, then call `electro playlist --profile-config ...` to push it to Spotify.

### Operations runbook

For day-to-day operator commands, troubleshooting, promo separation, and common playlist maintenance tasks, see [docs/spotify_playlists_runbook.md](docs/spotify_playlists_runbook.md).

### GitHub publishing

The repository includes a GitHub Actions workflow at `.github/workflows/ci.yml` and a short publishing checklist in [docs/github_setup.md](docs/github_setup.md). Large local audio/video artifacts and generated caches are intentionally ignored so the repository stays lightweight and cheap to host.

## Development

- `make setup` installs the project in a virtual environment with dev dependencies.
- `make lint` runs Ruff and Black in check mode.
- `make format` auto-formats with Black and Ruff.
- `make test` executes pytest.
- `make typecheck` runs MyPy.

## Project Layout

- `src/electro_analyzer/` – library and CLI implementation
- `tests/` – pytest suite
- `samples/` – place test audio snippets (not tracked by Git)
- `outputs/` – generated artifacts from `electro plot`

## License

Electro Analyzer is released under the [MIT License](LICENSE).
