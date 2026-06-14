# For Daniel — How We Built `notes-to-enex` (the coffee-chat version)

Pull up a chair. This is the story of how a "just import my Day One journal into
Apple Notes" request turned into a small, sharp little tool — and everything I
learned wrestling with it that you can steal for your next project.

---

## The one-sentence version

You wanted your journal entries (text **plus** photos, videos, PDFs) inside
Apple Notes. Apple Notes is a walled garden that *hates* being automated. So
instead of fighting the front door, we slipped in through a side door it already
trusts: the **Evernote `.enex` import format**. Everything else — Markdown
support, TextBundle, the GUI, the date fixes — grew out of that one decision.

---

## Step 1 — The approach, and how I got there

My starting point was a question, not a plan: *"What can actually carry an
attachment **into** Apple Notes?"* Because the whole job lives or dies on that.
Text is easy; anyone can shove text into Notes. The hard currency here is
attachments.

So before writing anything real, I went looking at the raw material. I opened
your `Feedback.json` and learned how Day One structures an entry: Markdown text
with little inline placeholders like `![](dayone-moment://ABC123)`, and a
separate list of photo/video/pdf objects. The attachments lived in `photos/`,
`videos/`, `pdfs/` folders next to the JSON. Good — the data was all there.

Then I did the single most important thing in the whole project: **I tested the
scary assumption first.** I created one throwaway note through the Apple Notes
integration with an inline base64 image, and read it back. The image was *gone* —
silently stripped. That five-minute test changed the entire architecture.

Think of it like checking whether the bridge holds weight *before* you drive the
truck across, not after. The riskiest unknown gets tested first.

## Step 2 — The roads I considered and abandoned (this is the good part)

Here's the graveyard of approaches, and why each one died:

- **"Just use the Apple Notes integration to create notes with images."**
  Dead on arrival — my test proved it strips inline images. Beautiful in theory,
  useless in practice.

- **AppleScript automation.** Apple Notes *has* an AppleScript dictionary, so
  surely you can script attachments? No. AppleScript can set a note's HTML body,
  but `attachment` is **read-only** — you cannot create one. And the HTML body
  silently drops `data:` image URIs. Two dead ends in one tool.

- **Clipboard-paste robot.** I genuinely considered using desktop control to
  copy each file in Finder and `Cmd+V` it into the right note — 35 paste
  operations, like a tiny robot doing data entry. It would *work*, but it's
  brittle: one wrong click and an attachment lands in the wrong note. Fragile and
  un-repeatable.

- **Apple Shortcuts.** The Shortcuts "Create Note" action *can* attach files.
  But building and running a Shortcut is fiddly to set up and hard to hand you as
  a clean, reusable artifact.

Then the lightbulb: Apple Notes has a **File → Import to Notes…** menu that
accepts Evernote `.enex` files. ENEX is an old XML format that base64-encodes
every attachment *inside* the file. Notes imports images inline, PDFs as PDFs,
videos as media — all as real attachments. One file, one menu click, everything
preserved. **That's the side door.**

The lesson hiding here: when an app fights your automation, stop asking "how do I
force it?" and start asking "what does it *already* accept?" Every walled garden
has a loading dock.

## Step 3 — How the pieces fit together

The architecture ended up shaped like a **funnel**:

```
Day One JSON ─┐
Markdown      ├─► [parse into a common "note" shape] ─► [ENEX writer] ─► .enex
TextBundle    ┘         (title, body, dates, attachments)
```

Each input format has its own little parser, but they all produce the **same
internal shape**: a dict with a title, an ENML body, created/updated timestamps,
and a table of attachments. After that point, *nothing downstream cares where the
note came from.* The ENEX writer, the integrity check, the split feature — they
all operate on that common shape.

That's why adding TextBundle support later was cheap: I only had to write a new
parser at the wide end of the funnel; the narrow end already knew what to do.

The GUI sits on top as a *separate layer* that just calls the converter's
functions. And the `.command` launcher sits on top of *that*, just finding the
right Python and double-clicking into the GUI. Three layers, each ignorant of the
one above it.

## Step 4 — Tools and why these specifically

- **Plain Python standard library, zero dependencies.** No `pip install`
  anything. Why? Because the moment you add a dependency, you've added a setup
  step, a thing that breaks, a thing you have to explain. For a tool you'll run
  occasionally on your own Mac, "it just runs" beats "it's elegant." `json`,
  `base64`, `hashlib`, `xml` — all built in.

- **ENEX/XML over building our own format.** We didn't invent anything; we spoke
  a language Apple Notes already understands. Standing on an existing standard is
  almost always smarter than inventing a private one.

- **Tkinter for the GUI.** Also standard library. A heavier toolkit (PyQt, a web
  frontend in Electron) would look nicer but would drag in installs and bloat.
  For a simple "pick a folder, click Convert" window, Tkinter is right-sized.

- **A `.command` file, not a real `.app` bundle.** A `.command` is just a shell
  script Finder runs on double-click. Building a signed `.app` is a project in
  itself. The `.command` gets you 90% of the convenience for 5% of the effort.

If I'd picked differently — say, a Node/Electron app — you'd have a prettier
window and a 200MB install, a build step, and a thing that rots when dependencies
update. The boring choice aged better.

## Step 5 — The tradeoffs (every choice has a bill)

- **Single `.enex` vs. one-per-note.** A single file is tidy, but a 155MB monster
  can make Apple's importer choke. So we added `--split`. The tradeoff: tidiness
  vs. reliability. We let *you* choose per-run instead of deciding for you.

- **Generic vs. perfect dates.** For TextBundles, we could've dug into Bear's
  SQLite database to get the *true* original note dates. More accurate — but
  Bear-specific, and it'd break the day you export from Craft instead. We chose
  **generic and reusable** over **maximally accurate**, because you explicitly
  value reusability. We sacrificed some date fidelity to keep the tool universal.

- **Light Markdown conversion vs. a full parser.** We handle bold, italic, links,
  images — not nested lists or tables. A full CommonMark parser would be more
  correct but heavier and slower to write. We covered the 95% that journal
  entries actually use.

## Step 6 — The mess (where the real learning lives)

We hit some walls. Honestly, that's most of the story:

1. **The "0-byte file" panic.** You ran it and Finder showed a 0-byte `.enex` —
   but the file was actually a complete 155MB. The culprit: iCloud Drive +
   Finder showing a stale size before the write settled. Fix: we `fsync()` every
   file now so the bytes are *guaranteed* on disk immediately. Lesson: the tool
   was fine; the **environment** was lying.

2. **The blank GUI window.** The launcher grabbed Apple's ancient system Python,
   which ships **Tk 8.5** — and Tk 8.5 renders blank windows on modern macOS.
   Fix: the launcher now *prefers a Python with Tk ≥ 8.6*. Lesson: "Python is
   installed" and "the *right* Python with the right libraries is installed" are
   very different sentences.

3. **The "tomorrow" date bug — twice.** First, we were stamping *local* time with
   a `Z` (which means UTC), so Apple Notes re-converted it and pushed late-evening
   notes to the next day. Fixed by converting to *real* UTC. Then you noticed
   TextBundle notes showed *yesterday* — because we read the inner `text.md`'s
   write-time (export day) instead of the `.textbundle` folder's date. And
   digging in, we found the deeper truth: **TextBundle doesn't store the original
   note date at all** — Bear stamps export time. So "use the file's created date"
   can only ever mean "the export date." We documented that honestly rather than
   pretending.

4. **The git repo that wouldn't commit.** Cowork's folder mount **blocks file
   deletion** for safety, and git lives and dies by creating/deleting lock files.
   First commit failed with a stuck `index.lock`. Fix: request delete permission
   for the folder. Then the push failed because the sandbox has no GitHub
   credentials — that part genuinely has to happen on your Mac. And your push hit
   a *third* wall: a stale `GITHUB_TOKEN` environment variable shadowing
   `gh auth`. Three different auth/permission gremlins in one small task.

None of these were in the "plan." All of them were the actual work.

## Step 7 — Pitfalls, the "I wish someone told me" list

- **Timestamps are a minefield.** The instant you write a date with a timezone
  marker, *someone downstream will re-interpret it.* Always know whether your
  time is local or UTC, and label it truthfully. A "Z" is a promise.

- **File metadata lies more than you think.** Creation time, modification time,
  the `md5` field in an export — none are guaranteed to mean what the name says.
  Day One's "md5" wasn't the file's MD5. Bear's file dates weren't the note's
  dates. **Verify, don't trust the label.**

- **"It works on my machine" is usually a library-version story.** Tk 8.5 vs 9.0,
  system Python vs Homebrew Python. When something renders or behaves differently,
  suspect the versions before the logic.

- **Test the one assumption that would invalidate everything — first.** If the
  inline-image test had been step 50 instead of step 2, we'd have built the wrong
  thing and thrown it away.

- **iCloud-synced folders behave oddly under the hood.** 0-byte reads, dataless
  placeholders, sync races. If a file looks wrong, check it in Terminal with
  `ls -la`, not Finder.

## Step 8 — What an expert notices that a beginner misses

- **A beginner asks "how do I make Apple Notes do this?" An expert asks "what
  will Apple Notes accept *without a fight*?"** Reframing the problem around the
  target's existing capabilities is the whole game.

- **A beginner writes one big script. An expert builds a funnel** — many inputs,
  one common shape, one output path — so the next format is a small add, not a
  rewrite. That "common internal representation" is the quiet hero of the design.

- **A beginner trusts the happy-path output. An expert builds a self-check.**
  Notice the converter *verifies every attachment reference resolves to an
  embedded file and prints "Integrity: OK."* That check caught problems instantly
  and gave you confidence the 155MB blob wasn't silently corrupt.

- **A beginner hard-codes assumptions. An expert isolates them** — the MIME map,
  the date format, the split threshold all live in obvious, tweakable spots,
  exactly because they're the things most likely to change.

## Step 9 — Lessons that travel to completely different projects

1. **Find the loading dock.** Whenever a system resists integration — an app, an
   API, a bureaucracy — look for the format or channel it *already* accepts.
   You'll almost always find a side door (a CSV import, a webhook, a standard file
   format) that beats brute force. This is true for code *and* for getting things
   done in the real world.

2. **Build a funnel, not a fork.** Whenever you have many inputs heading to one
   outcome, convert everything to a common shape early, then write the hard logic
   once. Works for data pipelines, for importing leads from five sources, for
   normalizing client files before a build.

3. **Spike the riskiest unknown first.** Before committing to a plan, spend ten
   minutes proving the part most likely to kill it. Cheap test, huge information.

4. **Distrust labels; verify the bytes.** "Created date," "md5," "size in Finder"
   — names promise things the data may not deliver. Build a tiny check that
   confirms reality. This habit alone separates reliable work from hopeful work.

5. **Prefer boring, dependency-light tools for things you'll maintain alone.**
   The clever stack impresses today; the boring one still runs in two years
   without a single `npm install` falling over.

6. **Be honest about limits in writing.** We documented "TextBundle can't give
   you the original date" right in the README instead of hiding it. Future-you (or
   future-someone) reads that and saves an afternoon. Documenting a limitation is
   a feature.

---

That's the whole journey — from "Apple Notes won't take my photos" to a tidy,
reusable, version-controlled tool with a double-click launcher. The final code is
the smallest part. The *thinking* — test the scary thing first, find the side
door, build a funnel, distrust the labels — that's the part worth keeping.

Now go push that commit. ☕
