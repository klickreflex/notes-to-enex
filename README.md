# Markdown / Day One → Apple Notes import (`dayone_to_enex.py`)

Converts your notes — from **Day One JSON exports**, **plain Markdown**, or
**TextBundle / TextPack** — into a single Evernote **`.enex`** file that Apple
Notes imports natively (`File → Import to Notes…`), keeping every attachment
(images, PDFs, videos, audio) as a real Notes attachment.

Use it from the command line, or **double-click `Launch Notes Converter.command`**
for a small GUI (see [Run it with a GUI](#run-it-with-a-gui-no-terminal)).

**Files in this folder:** `dayone_to_enex.py` (the converter),
`dayone_to_enex_gui.py` (GUI), `Launch Notes Converter.command` (double-click
launcher), and this README. Keep them together.

## Why this route

Apple Notes can't take attachments through scripting: AppleScript has no way to
attach PDFs or videos, and it silently strips inline base64 images from a note's
body (tested — the image just disappears). The Evernote **`.enex` import** path
is the only method that brings text *and* all attachment types in as genuine
attachments.

## Supported inputs (auto-detected)

| Input | Example | Notes |
|-------|---------|-------|
| Day One JSON export folder | `python3 dayone_to_enex.py ExportFolder/` | folder has `<Name>.json` + `photos/ videos/ pdfs/` |
| Day One `.json` file | `python3 dayone_to_enex.py Export.json` | |
| Single Markdown file | `python3 dayone_to_enex.py note.md` | one note; attachments relative to the file |
| Folder of Markdown files | `python3 dayone_to_enex.py NotesFolder/` | one note per `.md` |
| TextBundle | `python3 dayone_to_enex.py Note.textbundle` | reads `text.md` + `assets/` |
| TextPack | `python3 dayone_to_enex.py Note.textpack` | zipped bundle, unpacked automatically |
| Folder of bundles | `python3 dayone_to_enex.py BundlesFolder/` | one note per `.textbundle` / `.textpack` |

Force a mode with `--format dayone|markdown`. Choose the output with
`-o /path/Out.enex` (default: next to the source).

Requires Python 3 only — no external packages.

### Large libraries: split into one file per note

A single huge `.enex` (hundreds of MB) can make Apple Notes' importer hang or
silently fail. Use `--split` to write **one `.enex` per note** into a folder:

```bash
python3 dayone_to_enex.py trips --split            # -> trips_enex/ folder
python3 dayone_to_enex.py trips --split -o ~/out    # custom folder
```

Then in Apple Notes select **all** the `.enex` files at once when importing.
This is more reliable for big exports and lets you retry just one note if needed.

## Run it with a GUI (no terminal)

Prefer clicking to typing? Two extra files in this folder give you a desktop app:

- **`Launch Notes Converter.command`** — **double-click this** to open the GUI.
  It auto-finds a Python with a modern Tk (≥ 8.6), so the window renders
  correctly. First launch only: macOS Gatekeeper may warn about an
  unidentified developer — right-click → **Open** → **Open** once.
- **`dayone_to_enex_gui.py`** — the Tkinter GUI itself (you can also run it with
  `python3 dayone_to_enex_gui.py`).

In the window: pick a **source** (File… or Folder…), the **format** is
auto-detected (with a manual override), choose an **output** path, optionally
tick **“One .enex per note”** (the split option), then **Convert**. A result log
shows the notes/attachments count and integrity check, with **Reveal in Finder**
and **Open Apple Notes** buttons afterward.

Keep all three files together — the launcher and GUI load `dayone_to_enex.py`
from the same folder.

> **Blank GUI window?** That means it used Apple's deprecated **Tk 8.5**. Install
> a modern Tk for your Python (`brew install python-tk`) and relaunch — the
> launcher will then prefer it and the window will draw properly.

## Import into Apple Notes

`File → Import to Notes…`, pick the `.enex` (or select all files in the split
folder), confirm. Notes drops everything into a new **"Imported Notes"** folder —
Apple always creates its own folder here and can't import straight into an
existing one — so afterwards rename that folder or move the notes into your
target folder (e.g. `💬 Feedback`).

> **"My .enex looks like 0 bytes in Finder":** if your Desktop/Documents are
> synced to iCloud Drive, Finder may briefly show a freshly written large file
> as 0 bytes until the local write is flushed and sync settles. The script now
> `fsync`s every file so the real size appears immediately; confirm with
> `ls -la` in Terminal (authoritative) rather than Finder's first reading.

## What each note looks like

- **Title** — first `# heading`; for Markdown, falls back to frontmatter
  `title:` then the filename.
- **Date header** (`YYYY-MM-DD`) and note timestamps:
  - Day One → the entry's creation date (already UTC in the export).
  - Markdown / TextBundle → YAML frontmatter `date:` if present, otherwise the
    **file's date**: for a `.textbundle` that's the **bundle folder's** creation
    (birth) time — for a standalone `.md`, the file's own. Modified date uses the
    corresponding mtime. This is fully generic (Bear, Craft, anything that
    produces TextBundles) — no app-specific lookups.
  - Note: TextBundle is just text + assets; it does **not** carry the original
    per-note creation date. So the date you get is whatever the filesystem holds
    — typically the **export date** (which is what Finder shows for the bundle),
    not the note's historical date. Add a YAML `date:` to a note if you need a
    specific one.
  - All timestamps are written as true UTC, so Apple Notes won't shift the day
    when it re-localizes them (an earlier version mislabeled local time as UTC,
    which could roll a late-evening note over to the next day).
- Body text with basic `**bold**` / `*italic*` / `[links](…)` converted.
- Attachments embedded inline where they appeared.

## Markdown / TextBundle attachment rules

- `![alt](relative/path.png)` images and local `[label](relative/path.pdf)`
  links are embedded; paths resolve relative to the Markdown file (URL-encoded
  spaces like `%20` handled).
- `http(s):` and `mailto:` links stay as clickable links.
- Broken/remote references degrade gracefully (image dropped, link text kept).
- Recognized attachment types: png, jpg/jpeg, heic/heif, gif, webp, tiff, bmp,
  mp4, mov, m4v, pdf, m4a, mp3, wav. Add more in the `MIME` map at the top.

## Day One format quirks (handled automatically)

- Attachment files are named `<md5>.<ext>`, but that `md5` is Day One's
  internal identifier, **not** the file's real MD5. ENEX requires the
  `en-media hash` to be the true MD5 of the bytes, so the script recomputes it.
- Inline references: `dayone-moment://<ID>` (photo),
  `dayone-moment:/video/<ID>`, `dayone-moment:/pdfAttachment/<ID>`,
  `dayone-moment:/audio/<ID>` — matched to each attachment's `identifier`.
- Day One's Markdown backslash-escaping (`\.`, `\!`, …) is cleaned up.

## Integrity check

After writing, the script verifies every inline `en-media` reference resolves to
an embedded resource (MD5-matched) and prints `Integrity: OK`. If anything fails
to resolve it tells you which notes are affected.

## Tweaks

- **Date format** — change the `strftime("%Y-%m-%d")` calls.
- **Richer header** — Day One entries also carry `location`, `weather`, `tags`;
  add them to the `header` line in `dayone_note()`.
