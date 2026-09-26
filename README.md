# OfflineYT · your own offline YouTube library

Mirror the channels you **actually watch** to a local/iCloud library, driven by your **Google Takeout watch history**.

- Watches only what you genuinely watch or follow — no giant bulk channel grabs.
- Per-channel budgets with automatic rotation (newest in, oldest out).
- Understands the new Google Takeout format (incl. ads, which it skips and purges).
- A 6am background daemon keeps it fresh on its own.

The engine is a single-file Python tool: **[`bin/yosync`](bin/yosync)**.

---

## What it does

`yosync` ingests your YouTube watch history (GitHub→Takeout export), figures out which channels you watched in the last **2 weeks** (hot window, ≥ 4 distinct videos), and downloads each one's recent uploads up to a per-channel budget. Old files are swapped out to stay in budget. Channels you stop watching get pruned after 2 weeks.

```
Google Takeout zip  →  ingest  →  merge history  →  attribute channels  →  analyze
      →  download (yt-dlp, within budgets)  →  rotate/prune  →  report  →  state.json
```

The library looks like this:

```
~/Library/Mobile Documents/com~apple~CloudDocs/OfflineYT/
├── Gohar Khan/
├── ElliotSimms/
├── Mrwhosetheboss/
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

## Setup (5 minutes)

1. **Put the tool on PATH**

   ```sh
   chmod +x bin/yosync
   cp bin/yosync ~/bin/yosync       # or anywhere on PATH
   ```

2. **Create the config** (see [`config.example.json`](config.example.json)):

   ```sh
   mkdir -p ~/.config/yosync
   # edit ~/.config/yosync/config.json —
   # at minimum set "dest" to your library folder
   ```

   Or run the interactive wizard: `python3 ~/bin/yosync --setup`

3. **Export your watch history from Google Takeout**

   - https://takeout.google.com → deselect everything
   - enable **YouTube** and **YouTube Music**, then only **Watch history**
   - delivery frequency: monthly (2-month is the max Google lets you backdate)
   - file type **.zip**, **JSON** format, size **largest**
   - deliver to **Google Drive** (folder `Takeout`) if you want automatic pulls, or download manually

4. **Ingest it**

   ```sh
   # drop the zip into the library's incoming folder, then:
   python3 ~/bin/yosync --ingest /path/to/takeout-*.zip
   # or for everything currently in incoming/:
   python3 ~/bin/yosync
   ```

5. **Enable the daily 6am daemon** (macOS, launchd):

   ```sh
   python3 ~/bin/yosync --daemon
   ```

   (equivalent to the `com.vyom.yosync` LaunchAgent running `yosync --drive --silent`).

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

---

## Budgets, rotation & pruning (the knobs)

| Config key | Default | Meaning |
|---|---|---|
| `hot_weeks` | `2` | hot window = distinct videos watched in the last N weeks |
| `hot_min_watches` | `4` | distinct videos needed to count as "hot" |
| `budget_per_video` | `0.17` | **continuous budget: GB per distinct video watched** |
| `budget_min_gb` / `budget_max_gb` | `1.0` / `3.5` | clamp the formula to this range (GiB) |
| `budget_tiers` | see example | fallback tier list when `budget_per_video` is absent |
| `cold_days` | `14` | prune channels with no watch in this many days |
| `quickfill_*` | see example | parallelism, margins, aria2, cookie source |

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
- The ad's channel name/URL/host is recorded in `state.json → ad_landings`.
- Every run (daemon included) checks all channels against that ban list — any match **deletes its files immediately** and permanently excludes the name.

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
| nothing happens at 6am | check `logs/sync.log`; `launchctl list \| grep yosync` |