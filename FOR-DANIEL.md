# For Daniel — Building `notes-to-enex`, end to end

What we built: a zero-dependency tool that converts Day One journals, plain
Markdown, and TextBundle/TextPack exports into a single Evernote `.enex` file that
Apple Notes imports natively — keeping every attachment (images, PDFs, videos) as
a real attachment. Plus a Tkinter GUI, a double-click launcher, and a published,
relocated git repo. This covers the whole arc, not just the last step.

## 1. Approach
The job lived or died on one question: *what can actually carry an attachment
**into** Apple Notes?* Text is trivial; attachments are the hard currency. So
before designing anything, I (a) read `Feedback.json` to learn Day One's shape —
Markdown text with inline placeholders like `![](dayone-moment://ID)` plus
separate photo/video/pdf objects on disk — and (b) tested the riskiest assumption
immediately: I created one note through the Apple Notes integration with an inline
base64 image and read it back. The image was silently stripped. That five-minute
test killed the obvious plan and set the architecture.

The winning route: Apple Notes' **File → Import to Notes…** accepts Evernote
`.enex`, an XML format that base64-embeds every attachment. So I generate one
`.enex` and let Notes' own importer do the work. Everything else (Markdown,
TextBundle, GUI, date fixes) grew from that decision.

## 2. Roads not taken (the important part)
- **Notes integration / AppleScript to attach files.** The integration strips
  inline images (tested). AppleScript can set an HTML body but `attachment` is
  read-only and it drops `data:` image URIs. Dead end for anything but plain text.
- **Clipboard-paste robot** (desktop-control copy each file, `Cmd+V` into the
  right note). Works, but 35 paste ops where one misclick misfiles an attachment.
  Brittle and non-repeatable.
- **Apple Shortcuts' "Create Note"** can attach files, but it's fiddly to build
  and hard to hand over as a clean reusable artifact.
- **Bear's SQLite DB** to recover true note dates for TextBundles: more accurate,
  but app-specific — breaks for Craft or anything else. Rejected for reusability.
- **`replace_all` for the date-format change.** The `%d.%m.%Y` literal also lives
  in `_parse_date`'s *input* formats; a global swap would silently break parsing.
  Grepped, then edited only the two header lines.
- **Single huge `.enex` as the only mode.** A 155MB file can hang Notes' importer,
  so I added `--split` (one file per note) rather than forcing one giant blob.

## 3. Structure
A funnel. Each input format has its own parser, but all produce the **same
internal note shape**: `{title, ENML body, created, updated, attachments}`. After
that point nothing cares where the note came from — the ENEX writer, the integrity
check, and the split feature all operate on that shape. That's why adding
TextBundle later was cheap: new parser at the wide end, untouched machinery at the
narrow end. The GUI is a separate layer that only calls converter functions; the
`.command` launcher is a layer above that, only finding the right Python and
opening the GUI. Three layers, each ignorant of the one above.

## 4. Tools
- **Pure Python stdlib** (`json`, `base64`, `hashlib`, `xml`) — no `pip install`
  anything. For a tool you run occasionally on your own Mac, "it just runs" beats
  elegant. A dependency is a future breakage and a setup step.
- **ENEX/ENML standard**, not a homemade format — speak a language Notes already
  understands.
- **Tkinter** for the GUI (also stdlib). PyQt/Electron would look nicer but drag
  in installs and a build step for a "pick folder, click Convert" window.
- **`.command` launcher**, not a signed `.app` — 90% of the convenience for 5% of
  the effort.
- **git in place; `gh` on your Mac.** Anything needing your identity runs on the
  host, not the sandbox.

## 5. Tradeoffs
- **Single vs. split `.enex`:** tidiness vs. import reliability — exposed as a
  per-run choice instead of decided for you.
- **Generic filesystem dates vs. app-specific date lookup:** I use the file's
  creation (birth) time, which on macOS appears to be the note's real created date
  (pending your `stat -f %SB` check) — generic across Bear, Craft, etc. The
  rejected alternative was reading Bear's SQLite DB, which is more guaranteed but
  app-specific.
- **Light Markdown vs. full CommonMark:** handles bold/italic/links/images, not
  nested lists/tables — covers ~95% of journal content for a fraction of the work.
- **One squashed initial commit:** clean to publish, loses the fix-by-fix history.

## 6. The mess (where the learning is)
- **Inline images stripped** by the Notes integration → the whole ENEX pivot.
- **Day One's `md5` field is not the file's MD5** — it's an internal ID. ENEX
  requires the real MD5 as the `en-media` hash, so I recompute it from the bytes.
- **"0-byte file" panic:** Finder showed your 155MB `.enex` as 0 bytes — an iCloud
  write/sync race. Fix: `fsync()` every file so the bytes are on disk immediately.
  The tool was fine; the environment was lying.
- **Blank GUI window:** the launcher grabbed Apple's system Python with **Tk 8.5**,
  which renders blank on modern macOS. Fix: prefer a Python with Tk ≥ 8.6 (yours is
  9.0).
- **The "tomorrow"/"yesterday" date saga:** first, local time was stamped with a
  `Z` (UTC), so Notes re-localized it and pushed late-evening notes a day forward →
  fixed by converting to *real* UTC. Then TextBundle notes showed yesterday because
  I read the inner `text.md`'s write-time (export day) → switched to the
  `.textbundle` folder's date. Then a genuine epistemics lesson: Daniel doubted my
  claim that the date was just "export time," so I walked it back and theorized
  birth time probably held the real date. Then we actually *checked* birth time on
  his Mac (`stat -f %SB`) — and all five bundles, spanning 2018–2023, showed one
  identical birth date. So the original claim held after all: the files don't carry
  the real per-note date. The cause is subtle — **macOS resets birth time on
  copy/move**, so the uniform date is just when the bundles landed on disk. The
  true dates live only in the source app's database. Two lessons: (1) don't
  generalize a filesystem claim from the one timestamp your sandbox can read; (2)
  don't over-correct to please a challenge either — run the decisive check before
  re-asserting in either direction.
  - **Key distinction worth pinning:** this whole filesystem-date mess applies
    *only* to Markdown/TextBundle, where the date has to come from the file because
    the format stores none. **Day One is unaffected** — its JSON carries
    `creationDate`, `modifiedDate`, and `timeZone` per entry, and `dayone_note()`
    reads those directly (correctly timezoned, written as real UTC). It never
    touches `st_birthtime`/mtime. So Day One imports keep their true dates; only
    the format that genuinely lacks date metadata falls back to the (fragile)
    filesystem.
- **Git wouldn't commit:** the Cowork mount blocks file deletion, and git needs to
  create/delete lock files; a stuck `index.lock` killed the first commit. Fix:
  request delete permission, clean re-init. **Push** then failed (no creds in
  sandbox) → delegated to your Mac, where it hit a **401** from a stale
  `GITHUB_TOKEN` shadowing `gh auth` → `unset` and re-auth.

## 7. Pitfalls for next time
- Timestamps are a minefield: always know local vs. UTC and label truthfully. A
  "Z" is a promise something downstream will enforce.
- File metadata lies: `md5`, creation dates, Finder's size — verify the bytes,
  don't trust the label.
- "Works on my machine" is usually a library-version story (Tk 8.5 vs 9.0).
- Test the assumption that would invalidate everything *first*.
- iCloud folders behave oddly (0-byte reads, sync races) — check `ls -la` in
  Terminal, not Finder.
- `.gitignore` before the first `add`; env vars override CLI auth; grep before
  find-and-replace.

## 8. What an expert notices
- Reframe "how do I force this app?" into "what does it already accept?" — every
  walled system has an import path.
- A **common internal representation** makes new inputs cheap; without it you'd
  rewrite for each format.
- Build a **self-check** (the integrity pass verifying every `en-media` reference
  resolves to an embedded file) so a 155MB blob can't be silently corrupt.
- **Isolate what changes** — the MIME map, date format, split threshold all live in
  obvious, tweakable spots.
- **Read errors literally**: the 401 was an environment problem, not a login one;
  its headline advice was misleading.

## 9. Transfers to other work
- **Find the loading dock.** When a system resists integration, look for the
  format/channel it already accepts (a CSV import, a webhook, a standard file).
  Beats brute force, in code and in bureaucracy.
- **Build a funnel, not a fork:** many inputs → one common shape → write the hard
  logic once. Applies to data pipelines, importing leads from many sources, etc.
- **Spike the riskiest unknown first** — cheap test, huge information.
- **Distrust labels; verify the bytes.** This alone separates reliable work from
  hopeful work.
- **Prefer boring, dependency-light tools** for things you maintain alone — they
  still run in two years.
- **Document limitations in writing** (the TextBundle date caveat) — a stated limit
  is a feature.
- **Separate where you work from where your credentials live**, and normalize
  config before the first commit.
