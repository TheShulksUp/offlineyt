# OfflineYT · your own offline YouTube library

> Mirror the channels you **actually watch** to a local/iCloud library — driven by your **Google Takeout watch history**.

## Why

YouTube is a stream, but good content isn't. If you want the videos you care about **backed up, ad-free and forever yours**, there was no clean way to do it: downloading a whole channel wastes disk on things you never watch, and manual `yt-dlp` one-offs don't scale across the channels you follow.

OfflineYT solves the *"mirror what I actually watch"* problem:

- **Finds the channels you genuinely watch** — from your real Google Takeout history, not guesses.
- **Continuous budgets, not limits per 100 videos** — budget scales with how much each channel means to you (≈0.17 GB per distinct video watched, clamped to 1–3.5 GB).
- **Auto-rotation** — newest in, oldest out, so your library never grows unbounded.
- **Ad / bot driven junk gets skipped & purged automatically** (incl. the new Google Takeout ad format).
- **Runs itself** — a 6am background daemon keeps everything fresh.

The engine is a single-file Python tool: **[`bin/yosync`](bin/yosync)** — no services, no account, your data stays yours.

---

## Quick peek

```
$ python3 ~/bin/yosync --dry-run

[2026-03-14 09:12:04] resolving 96 unknown channel(s) via yt-dlp
[2026-03-14 09:12:58] would download 2 video(s) (~140 MB) from SomeTechChannel
[2026-03-14 09:12:58] channels: 14 hot, 921 total
[2026-03-14 09:12:58]   * SomeTechChannel    (~3.2 GB budget, 18 vids in 2w)
[2026-03-14 09:12:58]   * CookingWithX       (~1.8 GB budget, 10 vids in 2w)
[2026-03-14 09:12:58]   * TravelVlogger      (~1.1 GB budget,  5 vids in 2w)
[2026-03-14 09:12:58]   ...
[2026-03-14 09:12:58] free on disk: 402.1 GB
[2026-03-14 09:12:58] dry run complete: nothing downloaded
```

*(sample output — run it on your own data to see yours; budgets shown are decimal, matching the tool's own report)*

---

## What it does

`yosync` ingests your YouTube watch history (GitHub→Takeout export), figures out which channels you watched in the last **2 weeks** (hot window, ≥ 4 distinct videos), and downloads each one's recent uploads up to a per-channel budget. Old files are swapped out to stay in budget. Channels you stop watching get pruned after 2 weeks.

```
Google Takeout zip  →  ingest  →  merge history  →  attribute channels  →  analyze
      →  download (yt-dlp, within budgets)  →  rotate/prune  →  report  →  state.json
```

The library looks like this:

```
~/Movies/OfflineYouTube/
├── SomeChannel/
├── AnotherChannel/
├── ThirdChannel/
│     └── Title [videoID].mp4
├── inbox/              # scratch, normally empty
└── .yosync/
      ├── state.json          # the track database (precious — never reformat)
      ├── dl-archive.txt      # yt-dlp "already downloaded" archive
      ├── incoming/           # takeout zips waiting to be ingested
      ├── takeout/            # already-processed zips
      └── logs/sync.log       # run logs — read first when something breaks
```

---

## Requirements & download links

| Requirement | Why | Get it |
|---|---|---|
| **Python 3.10+** | runs `yosync` | https://www.python.org/downloads/ |
| **yt-dlp** | downloads the videos | `pip install -U yt-dlp` or https://github.com/yt-dlp/yt-dlp/releases |
| **ffmpeg** | merges video + audio, formats MP4 | `brew install ffmpeg` or https://evermeet.cx/ffmpeg/ |
| **aria2** (optional) | faster parallel downloads for quickfill | `brew install aria2` |
| **rclone** (optional) | `--drive` auto-pull of fresh takeout zips | https://rclone.org/downloads/ |
| **Google Takeout** | your watch history | https://takeout.google.com |

> `yosync` prepends `/opt/homebrew/bin` and `/usr/local/bin` to `PATH` itself, so those tools resolve no matter your shell.

---

## Setup (two options)

### A) One-click (macOS) — recommended

Grab **`Setup.command`** from the repo root and double-click it. It installs Homebrew,
Python, yt-dlp, ffmpeg (+ optional aria2 & rclone), drops `yosync` into `~/bin`, creates a
sane starting config and library folders, and asks if you want the 6am background daemon on.
Safe to run twice; nothing is overwritten. (Preview it with `SETUP_DRY_RUN=1 ./Setup.command`.)

> If macOS complains on first open: right-click → **Open** → Open once, or run
> `xattr -d com.apple.quarantine Setup.command`.

### B) One-liner (Linux) — recommended

```sh
curl -fsSL https://raw.githubusercontent.com/TheShulksUp/offlineyt/main/setup.sh | bash
```

Installs `yt-dlp` + `ffmpeg` via your package manager, drops `yosync` in `~/.local/bin`,
writes a starting config, and sets up a **systemd user timer** that runs the sync daily at
6am (falls back to a crontab entry where timers aren't available).
Preview it first with `DRY_RUN=1 bash setup.sh`.

### C) Manual (Linux/Windows/macOS, ~5 minutes)

1. **Install the dependencies** (see table above): Python 3.10+, `yt-dlp`, `ffmpeg`. Optional: `aria2`, `rclone`.

2. **Put the tool on PATH**

   ```sh
   chmod +x bin/yosync
   cp bin/yosync ~/bin/yosync       # or anywhere on PATH
   ```

3. **Create the config** (see [`config.example.json`](config.example.json)):

   ```sh
   mkdir -p ~/.config/yosync
   # edit ~/.config/yosync/config.json —
   # at minimum set "dest" to your library folder
   ```

   Or run the interactive wizard: `python3 ~/bin/yosync --setup`

4. **Export your watch history from Google Takeout**

   - https://takeout.google.com → deselect everything
   - enable **YouTube** and **YouTube Music**, then only **Watch history**
   - delivery frequency: monthly (2-month is the max Google lets you backdate)
   - file type **.zip**, **JSON** format, size **largest**
   - deliver to **Google Drive** (folder `Takeout`) if you want automatic pulls, or download manually

5. **Ingest it**

   ```sh
   # drop the zip into the library's incoming folder, then:
   python3 ~/bin/yosync --ingest /path/to/takeout-*.zip
   # or for everything currently in incoming/:
   python3 ~/bin/yosync
   ```

6. **Enable the daily 6am daemon**

   ```sh
   python3 ~/bin/yosync --daemon     # macOS: launchd · Linux: systemd user timer
   ```

   (macOS runs the `com.vyom.yosync` LaunchAgent with `yosync --drive --silent`; on Linux it
   installs a `yosync.service` / `yosync.timer` pair under `~/.config/systemd/user`.)

7. **Or skip the config file entirely**

   ```sh
   python3 ~/bin/yosync --serve     # every setting, editable in your browser
   ```

---

## Crazy useful flags

| Flag | What it does |
|---|---|
| `--dry-run` | preview everything, download nothing |
| `--ingest <zip>` | ingest one specific takeout file |
| `--drive` | first pull the newest takeout from Google Drive via rclone |
| `--quickfill` | dedicated fast fill — parallel workers + aria2 (+ `--logs` to watch it) |
| `--topup` | ignore the 2-week rotation lock and fill hot channels toward budget now |
| `--no-rotate` | download in budget but skip the old-file swap |
| `--silent` | headless, logs to `logs/sync.log` |
| `--daemon` / `--no-daemon` | toggle the launchd background agent |

Quickfill one-liner used in production:

```sh
python3 ~/bin/yosync --quickfill --logs
```

| Flag | What it does |
|---|---|
| `--serve` | open the settings page: every knob, live status, help & troubleshooting |
| `--verify` | integrity-check the library: ffprobe each file, drop broken ones, re-scan disk |
| `--inbox` | only process URL files you dropped into `<library>/inbox/`, then exit |

### Settings without a config file

`yosync --serve` starts a local-only web page (binds `127.0.0.1`, nothing leaves your machine)
with every setting in the schema — budgets, per-channel overrides, audio-only channels,
subtitles, Shorts, protection lists — plus a status panel, help and troubleshooting.
Saving writes straight to `config.json`. Change the port with `settings_port`.

The **Status** tab answers "is this thing actually working?": videos and size on disk, channels
tracked, hot channels and their budgets, free space, ad tracking, when the last sync and ingest
ran, and whether a background sync is really scheduled. It asks the OS about the schedule rather
than trusting the config, so it can't tell you "off" while your 6am job is installed and running.

`--serve` deliberately does *not* take the sync lock, so you can open it while a sync or a
`--verify` is running — the page starts immediately instead of waiting its turn.

### Grab things on demand

Drop a file with one or more YouTube links into `<library>/inbox/`:

```
# links.txt
https://www.youtube.com/watch?v=abcdefghijk
@SomeChannel
https://www.youtube.com/playlist?list=PLxxxxxxx
```

The next run (or `yosync --inbox`) grabs the video, and asks how many uploads to take from
each channel/playlist (defaults: 50, configurable via `inbox_channel_count` /
`inbox_playlist_count`). Processed files move to `.yosync/inbox-consumed/`.

---

## Budgets, rotation & pruning (the knobs)

| Config key | Default | Meaning |
|---|---|---|
| `hot_weeks` | `2` | hot window = distinct videos watched in the last N weeks |
| `hot_min_watches` | `4` | distinct videos needed to count as "hot" |
| `budget_per_video` | `0.17` | **continuous budget: GB per distinct video watched** |
| `budget_min_gb` / `budget_max_gb` | `1.0` / `3.5` | clamp the formula to this range (GiB) |
| `budget_tiers` | see example | fallback tier list when `budget_per_video` is absent |
| `channel_budget_overrides` | `{}` | per-channel budgets: channel name/URL → GB (never clamped) |
| `audio_only_channels` | `[]` | names/URLs mirrored as mp3 (podcast-style) instead of video |
| `include_shorts` | `true` | set false to skip videos shorter than 60s |
| `subtitles` | `false` | download subs; `subtitle_langs` (default `["en"]`) picks languages |
| `verify_media` | `true` | integrity-check new downloads (ffprobe); failed files are re-queued |
| `cold_days` | `14` | prune channels with no watch in this many days |
| `stale_grace_days` | `30` | extra pause before pruning when history has gone stale |
| `pack_margin` | `0.92` | keep this fraction of budget headroom per download pack |
| `quickfill_*` | see example | parallelism, margins, aria2, cookie source |
| `settings_port` | `8765` | localhost port for the `--serve` settings page |

> All of these (and everything else) can be edited from the in-browser settings page: **`yosync --serve`** — no JSON editing required.

Rotation model:

- Each channel is kept under its budget. `download` pulls the newest uploads, then swaps out old files to stay in budget.
- After a channel rotates, it's locked for `hot_weeks × 7` days until its next rotation (use `--topup` or `--quickfill` to override).
- `prune` removes files from channels inactive for `cold_days`+, but pauses deletions if the feed looks stopped (no fresh history for `cold_days + stale_grace_days`).

> Report shows budgets in decimal GB; the tool tracks binary GiB — that's why "3.8 GB" and "3.5 GiB" are the same number.

---

## Anti-bot cookies (YouTube rate limiting)

Bots get 429/-blocked fast. Export your browser's YouTube cookies once and point `quickfill_cookies` at the file:

```sh
# in your browser, export www.youtube.com cookies to ~/.config/yosync/cookies.txt
chmod 600 ~/.config/yosync/cookies.txt
```

Then in config:

```json
"quickfill_cookies": "/Users/YOU/.config/yosync/cookies.txt"
```

`yosync` passes `--cookies <file>` if that path exists, else treats the value as a browser name for `--cookies-from-browser`. Downloads also run with `--retries 5 --fragment-retries 10 --extractor-retries 3`.

---

## Ad detection & auto-purge

Ads that sneak into watch history are handled automatically:

- Records tagged **"From Google Ads"**, plus non-YouTube landing URLs, are never merged into your history.
- **Newer Takeout exports carry no channel name for ads** — only the watched video. yosync keeps
  those video ids in `state.json → ad_videos` and looks the channels up with yt-dlp
  (`ad_resolve_limit` per run), recording them in `ad_landings`.
- Ad-served videos are purged **by video id**, not by channel: a channel you genuinely watch can
  also serve you an ad, and a video you watched on purpose is never deleted. A video must be
  ad-served *and* never watched organically before it goes.
- **A channel you actually watch is never auto-purged**, even if it served you an ad. Plenty of
  channels run both, and ad records name no channel at all, so every advertiser becomes a
  candidate; an inferred ban is only ever allowed to touch a channel with no organic watch
  history (matched by channel URL, since display names collide).
- Channels listed in `ad_channel_names` are purged wholesale, even against organic history —
  naming one there is explicit intent. Only use that for channels you never actually want.

Manual overrides in config:

```json
"ad_channel_names": ["Some Spam Channel", "https://www.youtube.com/channel/UC..."],
"ad_keywords": ["sponsored", "promo"]
```

Channels listed in `exclude_channels` are always kept safe (never purged).

---

## Grabbing a single video or whole channel by hand

```sh
yt-dlp -f "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[vcodec^=avc1]" \
  --merge-output-format mp4 \
  -o "[DESTINATION]/%(uploader)s/%(title)s.%(ext)s" \
  "[VIDEO OR CHANNEL URL]"
```

---

## Care & maintenance notes

- **The library is precious.** Don't bulk-delete or casually re-run full syncs. Verify changes with `--dry-run` first.
- **`state.json` is the database** (~11 MB); never reformat it by hand.
- `.yosync/dl-archive.txt` is what keeps videos from being re-downloaded — don't truncate it casually.
- Never run two `yosync` processes at once — it takes a lock (`~/.config/yosync/.lock`).
- Watch out: the ad/purge code writes back to the config file; keep a backup of your `config.json`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ERROR: [youtube] ...: Sign in to confirm...` | add cookies (see above) |
| "all channels locked" on a normal run | that's rotation doing its job — `--topup` / `--quickfill` to override |
| channels never reach budget | they're mostly Shorts or the videos are deleted — nothing left to download |
| nothing happens at 6am | check `logs/sync.log`; `launchctl list \| grep yosync` (macOS) or `systemctl --user list-timers \| grep yosync` (Linux) |
| a file is corrupt or won't play | `yosync --verify` — ffprobes everything, removes broken files, re-scans disk |
| the settings page says the port is in use | close the other tab, or change `settings_port` in the page |

---

## Tests

The budget math, download-argument builder, settings page and integrity check are covered
by a pytest suite:

```sh
python3 -m pip install pytest
python3 -m pytest tests -q
```

## Roadmap & PRs welcome

Ideas worth building next — pitch or submit one:

- **Watched-progress import** of the new Takeout **.csv** format.
- **Windows daemon** (Task Scheduler) to pair with the macOS and Linux ones.
- **Budget presets** (feather / balanced / hoarder) as a single config flag.
- **Portable bundles** (PyInstaller) so non-technical people can skip the install.

Found a bug or have an idea? Open an [issue](https://github.com/TheShulksUp/offlineyt/issues) or start a [discussion](https://github.com/TheShulksUp/offlineyt/discussions).

If this saved your back catalog, **give the repo a ⭐** — it's what keeps side-projects like this alive.