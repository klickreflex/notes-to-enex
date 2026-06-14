#!/usr/bin/env python3
"""
dayone_to_enex.py  —  Markdown / Day One  ->  Apple Notes (.enex)
=================================================================

Convert either

  (a) a **Day One JSON export** (entries + photos/ videos/ pdfs/), or
  (b) **plain Markdown** files that reference attachments by **relative path**

into a single Evernote `.enex` file that Apple Notes imports natively
(`File -> Import to Notes...`), keeping every attachment (images, PDFs,
videos, audio) as a real Notes attachment.

WHY ENEX?
    Apple Notes can't take attachments through scripting: AppleScript has no
    way to attach PDFs or videos, and it silently strips inline base64 images
    from a note's body. The Evernote .enex import path is the only route that
    brings text AND every attachment type in as genuine attachments.

USAGE
    # Day One JSON export folder
    python3 dayone_to_enex.py /path/to/DayOneExportFolder

    # A single Markdown file (attachments relative to the file)
    python3 dayone_to_enex.py /path/to/note.md

    # A folder of Markdown files -> one note per .md
    python3 dayone_to_enex.py /path/to/MarkdownFolder

    # Force a format / pick output path
    python3 dayone_to_enex.py SRC --format markdown -o /path/Out.enex

    Format is auto-detected: a .json (or folder with one) -> Day One;
    a .md file or a folder containing .md files -> Markdown.

THEN, in Apple Notes:  File -> Import to Notes...  -> pick the .enex.
Notes creates an "Imported Notes" folder; rename or move it afterwards
(Apple always imports into its own new folder).

MARKDOWN MODE DETAILS
    * Title  = first `# heading`, else YAML frontmatter `title:`, else filename.
    * Date   = YAML frontmatter `date:` (ISO-ish) if present, else file mtime.
    * Attachments: `![alt](rel/path.png)` and local `[label](rel/path.pdf)`
      links are embedded; paths are resolved relative to the .md file's folder
      (URL-encoded spaces like %20 are handled). `http(s):`/`mailto:` links
      stay as links.
"""

import argparse, json, os, re, hashlib, base64, html, sys, urllib.parse
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# attachment extension -> MIME
MIME = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg",
        "heic": "image/heic", "heif": "image/heif", "gif": "image/gif",
        "webp": "image/webp", "tiff": "image/tiff", "bmp": "image/bmp",
        "mp4": "video/mp4", "mov": "video/quicktime", "m4v": "video/x-m4v",
        "pdf": "application/pdf",
        "m4a": "audio/mp4", "mp3": "audio/mpeg", "wav": "audio/wav"}


# ----------------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------------
def real_md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def mime_for(path):
    return MIME.get(path.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def add_attachment(path, atts):
    """Register a file in the note's attachment table (deduped by MD5).
    Returns the attachment record."""
    md5 = real_md5(path)
    if md5 not in atts:
        atts[md5] = {"path": path, "mime": mime_for(path),
                     "md5": md5, "fname": os.path.basename(path)}
    return atts[md5]


def en_media(att):
    return f'<en-media hash="{att["md5"]}" type="{att["mime"]}"/>'


def inline_format(escaped):
    """Bold/italic on already-HTML-escaped text (links handled separately)."""
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!_)_(?!_)(.+?)_(?!_)", r"<i>\1</i>", escaped)
    return escaped


# ----------------------------------------------------------------------------
# Day One JSON mode
# ----------------------------------------------------------------------------
DO_SUBDIR = {"photos": "photos", "videos": "videos", "pdfAttachments": "pdfs"}
DO_MOMENT = re.compile(
    r"!\[[^\]]*\]\(dayone-moment:(?://|/video/|/pdfAttachment/|/audio/)([A-Fa-f0-9]+)\)")


def dayone_unescape(s):
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!>~|])", r"\1", s)


def dayone_index(entry, base, atts):
    """identifier(UPPER) -> attachment record; also fills `atts`."""
    idx = {}
    for key, sub in DO_SUBDIR.items():
        for a in entry.get(key, []):
            path = os.path.join(base, sub, a["md5"] + "." + a["type"])
            if not os.path.exists(path):
                print(f"  WARNING: missing attachment {path}", file=sys.stderr)
                continue
            rec = add_attachment(path, atts)
            # nicer filename when Day One provides one
            nice = a.get("pdfName") or a.get("filename")
            if nice:
                rec["fname"] = nice + "." + a["type"]
            idx[a["identifier"].upper()] = rec
    return idx


def dayone_note(entry, base):
    atts = {}
    idx = dayone_index(entry, base, atts)
    parts, title = [], None
    for ln in entry.get("text", "").split("\n"):
        m = DO_MOMENT.search(ln)
        if m:
            rec = idx.get(m.group(1).upper())
            parts.append(f"<div>{en_media(rec)}</div>" if rec else "<div><br/></div>")
            continue
        if ln.strip() == "":
            parts.append("<div><br/></div>"); continue
        h = re.match(r"^(#{1,6})\s+(.*)$", ln.strip())
        if h:
            txt = dayone_unescape(h.group(2))
            if title is None: title = txt
            parts.append(f"<div><b>{inline_format(html.escape(txt))}</b></div>"); continue
        parts.append(f"<div>{inline_format(html.escape(dayone_unescape(ln)))}</div>")

    if title is None:
        for ln in entry.get("text", "").split("\n"):
            if ln.strip():
                title = dayone_unescape(ln.strip())[:80]; break
    title = title or "Eintrag"

    dt = datetime.strptime(entry["creationDate"], "%Y-%m-%dT%H:%M:%SZ")
    local, tz = dt, entry.get("timeZone")
    if ZoneInfo and tz:
        try: local = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
        except Exception: pass
    header = f'<div><b>{html.escape(local.strftime("%d.%m.%Y"))}</b></div><div><br/></div>'
    created = dt.strftime("%Y%m%dT%H%M%SZ")
    md = entry.get("modifiedDate")
    try:
        updated = datetime.strptime(md, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%dT%H%M%SZ") if md else created
    except Exception:
        updated = created
    return {"title": title, "enml": header + "".join(parts),
            "created": created, "updated": updated, "atts": atts}


def dayone_notes(base):
    jf = next((f for f in os.listdir(base) if f.lower().endswith(".json")), None)
    if not jf:
        sys.exit(f"No .json found in {base}")
    data = json.load(open(os.path.join(base, jf), encoding="utf-8"))
    return [dayone_note(e, base) for e in data.get("entries", [])]


# ----------------------------------------------------------------------------
# Markdown mode
# ----------------------------------------------------------------------------
IMG_RE  = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
FM_RE   = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _resolve_local(target, base_dir):
    """Return an existing local file path for a markdown target, else None."""
    target = target.strip()
    # drop optional  "title"  after the path
    if " " in target and not os.path.exists(os.path.join(base_dir, target)):
        target = target.split()[0]
    if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
        return None
    target = urllib.parse.unquote(target)
    path = target if os.path.isabs(target) else os.path.join(base_dir, target)
    return path if os.path.isfile(path) else None


def _md_line(line, base_dir, atts):
    """Convert one Markdown line to an ENML fragment, embedding local files."""
    store = []  # raw html fragments referenced by sentinel \x00N\x00

    def img_sub(m):
        p = _resolve_local(m.group(1), base_dir)
        if p:
            store.append(en_media(add_attachment(p, atts)))
            return f"\x00{len(store)-1}\x00"
        return ""  # broken/remote image reference -> drop the markup
    line = IMG_RE.sub(img_sub, line)

    def link_sub(m):
        text, target = m.group(1), m.group(2)
        p = _resolve_local(target, base_dir)
        if p:
            store.append(en_media(add_attachment(p, atts)))
            return f"\x00{len(store)-1}\x00"
        if re.match(r"^(https?://|mailto:)", target.strip()):
            store.append(f'<a href="{html.escape(target.strip())}">{html.escape(text)}</a>')
            return f"\x00{len(store)-1}\x00"
        return html.escape(text)
    line = LINK_RE.sub(link_sub, line)

    line = inline_format(html.escape(line))
    line = re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], line)
    return line


def _parse_frontmatter(text):
    meta = {}
    m = FM_RE.match(text)
    if m:
        for ln in m.group(1).split("\n"):
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip('"\'')
        text = text[m.end():]
    return meta, text


def _parse_date(s):
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            continue
    return None


def markdown_note(path):
    base_dir = os.path.dirname(os.path.abspath(path))
    text = open(path, encoding="utf-8").read()
    meta, body = _parse_frontmatter(text)

    atts, parts, title = {}, [], None
    for ln in body.split("\n"):
        stripped = ln.strip()
        if stripped == "":
            parts.append("<div><br/></div>"); continue
        h = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if h:
            frag = _md_line(h.group(2), base_dir, atts)
            if title is None:
                title = re.sub(r"<[^>]+>", "", frag)  # plain-text title
            parts.append(f"<div><b>{frag}</b></div>"); continue
        parts.append(f"<div>{_md_line(ln, base_dir, atts)}</div>")

    title = meta.get("title") or title or os.path.splitext(os.path.basename(path))[0]

    # Creation date: explicit frontmatter `date:` wins; otherwise the date of
    # the file (for a .textbundle, the BUNDLE FOLDER, which exporters like Bear
    # stamp with the note's real date — the inner text.md is just written at
    # export time and would wrongly read as "today").
    date_src = _date_source(path)
    created_local = _parse_date(meta.get("date", "")) if meta.get("date") else None
    if created_local is None:
        created_local = _file_birth_dt(date_src)
    updated_local = datetime.fromtimestamp(os.path.getmtime(date_src))

    header = f'<div><b>{html.escape(created_local.strftime("%d.%m.%Y"))}</b></div><div><br/></div>'
    return {"title": title, "enml": header + "".join(parts),
            "created": _utc_stamp(created_local), "updated": _utc_stamp(updated_local),
            "atts": atts}


def _date_source(md_path):
    """For a markdown file inside a .textbundle, dates live on the bundle folder,
    not on the inner text.md. Return the path whose timestamps to use."""
    parent = os.path.dirname(os.path.abspath(md_path))
    return parent if parent.lower().endswith(".textbundle") else os.path.abspath(md_path)


def _file_birth_dt(path):
    """Creation time as a naive *local* datetime (macOS st_birthtime; falls back
    to mtime on filesystems/sandboxes without a birth time)."""
    st = os.stat(path)
    ts = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.fromtimestamp(ts)


def _utc_stamp(dt):
    """Format a datetime as an ENEX UTC timestamp. A naive datetime is treated
    as local time and converted to real UTC, so Apple Notes won't shift the
    day when it re-localizes the value."""
    if dt.tzinfo is None:
        dt = dt.astimezone()          # interpret as local, make tz-aware
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _bundle_md(bundle_dir):
    """The markdown file inside a .textbundle (conventionally text.md)."""
    for pref in ("text.md", "text.markdown"):
        p = os.path.join(bundle_dir, pref)
        if os.path.isfile(p):
            return p
    for f in sorted(os.listdir(bundle_dir)):
        if f.lower().endswith((".md", ".markdown")):
            return os.path.join(bundle_dir, f)
    return None


def _expand_textpack(pack_path, tmpdirs):
    """Unzip a .textpack to a temp dir and return the inner .textbundle path."""
    import tempfile, zipfile
    d = tempfile.mkdtemp(prefix="textpack_")
    tmpdirs.append(d)
    with zipfile.ZipFile(pack_path) as z:
        z.extractall(d)
    for root, dirs, _ in os.walk(d):
        for dd in dirs:
            if dd.lower().endswith(".textbundle"):
                return os.path.join(root, dd)
    return d  # fallback: maybe extracted directly


def collect_markdown_files(src, tmpdirs):
    """Resolve `src` to a list of markdown file paths, expanding
    .textbundle folders and .textpack archives."""
    low = src.lower()
    if os.path.isfile(src):
        if low.endswith(".textpack"):
            return [_bundle_md(_expand_textpack(src, tmpdirs))]
        return [src]                                   # plain .md
    if low.endswith(".textbundle"):
        return [_bundle_md(src)]                       # a single bundle folder
    if _bundle_md(src) and os.path.isfile(os.path.join(src, "info.json")):
        return [_bundle_md(src)]                       # src *is* a bundle
    files = []                                         # generic folder
    for f in sorted(os.listdir(src)):
        p = os.path.join(src, f)
        fl = f.lower()
        if fl.endswith((".md", ".markdown")):
            files.append(p)
        elif fl.endswith(".textbundle") and os.path.isdir(p):
            mp = _bundle_md(p)
            if mp:
                files.append(mp)
        elif fl.endswith(".textpack") and os.path.isfile(p):
            mp = _bundle_md(_expand_textpack(p, tmpdirs))
            if mp:
                files.append(mp)
    return [f for f in files if f]


_TMPDIRS = []  # textpack extractions, cleaned up after the ENEX is written


def markdown_notes(src):
    files = collect_markdown_files(src, _TMPDIRS)
    if not files:
        sys.exit(f"No Markdown / TextBundle content found in {src}")
    return [markdown_note(f) for f in files]


def _cleanup_tmp():
    import shutil
    for d in _TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)


# ----------------------------------------------------------------------------
# ENEX assembly
# ----------------------------------------------------------------------------
def _note_to_xml(n):
    """Return (note_xml, num_resources) for one note dict."""
    content = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
               '<en-note>' + n["enml"] + '</en-note>')
    res = []
    for att in n["atts"].values():
        b64 = base64.b64encode(open(att["path"], "rb").read()).decode()
        b64w = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
        res.append('<resource><data encoding="base64">\n' + b64w + "\n</data>"
                   f"<mime>{att['mime']}</mime><resource-attributes>"
                   f"<file-name>{html.escape(att['fname'])}</file-name>"
                   "</resource-attributes></resource>")
    xml = ("<note><title>" + html.escape(n["title"]) + "</title>"
           "<content><![CDATA[" + content + "]]></content>"
           f"<created>{n['created']}</created><updated>{n['updated']}</updated>"
           + "".join(res) + "</note>")
    return xml, len(res)


def _wrap_export(xml_notes, app):
    export_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<!DOCTYPE en-export SYSTEM "http://xml.evernote.com/pub/evernote-export4.dtd">'
            f'<en-export export-date="{export_date}" application="{app}" version="1.0">'
            + "".join(xml_notes) + "</en-export>")


def _durable_write(path, doc):
    """Write text and force it to disk (flush + fsync), so Finder/iCloud see the
    full size immediately and a partial buffer can never be left behind."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
        f.flush()
        os.fsync(f.fileno())


def _integrity_bad(xml_notes):
    bad = 0
    for n in xml_notes:
        media = set(re.findall(r'<en-media hash="([0-9a-f]+)"', n))
        rhash = set()
        for r in re.findall(r"<resource>.*?</resource>", n, re.S):
            b = re.search(r'<data encoding="base64">(.*?)</data>', r, re.S).group(1)
            rhash.add(hashlib.md5(base64.b64decode(b)).hexdigest())
        if not media <= rhash:
            bad += 1
    return bad


def _safe_name(title, used):
    base = re.sub(r'[/\\:*?"<>|]', "_", title).strip() or "note"
    base = base[:80]
    name = base
    i = 2
    while name.lower() in used:
        name = f"{base} ({i})"; i += 1
    used.add(name.lower())
    return name


def write_enex(notes, out_path, app="dayone_to_enex"):
    """Write all notes into a single .enex file."""
    xml_notes, total_att = [], 0
    for n in notes:
        xml, nres = _note_to_xml(n)
        xml_notes.append(xml); total_att += nres
    _durable_write(out_path, _wrap_export(xml_notes, app))
    bad = _integrity_bad(xml_notes)
    print(f"Wrote {out_path}")
    print(f"  Notes: {len(xml_notes)}   Attachments embedded: {total_att}   "
          f"Size: {os.path.getsize(out_path)/1e6:.1f} MB")
    print(f"  Integrity: {'OK - all references resolve' if bad == 0 else f'{bad} notes with unresolved refs!'}")


def write_enex_split(notes, out_dir, app="dayone_to_enex"):
    """Write one .enex per note into out_dir (safer for very large libraries)."""
    os.makedirs(out_dir, exist_ok=True)
    used, total_att, bad = set(), 0, 0
    for n in notes:
        xml, nres = _note_to_xml(n)
        total_att += nres
        bad += _integrity_bad([xml])
        path = os.path.join(out_dir, _safe_name(n["title"], used) + ".enex")
        _durable_write(path, _wrap_export([xml], app))
    size = sum(os.path.getsize(os.path.join(out_dir, f))
               for f in os.listdir(out_dir) if f.endswith(".enex"))
    print(f"Wrote {len(notes)} .enex files into {out_dir}")
    print(f"  Attachments embedded: {total_att}   Total size: {size/1e6:.1f} MB")
    print(f"  Integrity: {'OK - all references resolve' if bad == 0 else f'{bad} notes with unresolved refs!'}")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def detect_format(src):
    low = src.lower()
    if os.path.isfile(src):
        return "dayone" if low.endswith(".json") else "markdown"
    if low.endswith(".textbundle"):
        return "markdown"
    names = os.listdir(src)
    if any(f.lower().endswith(".json") for f in names):
        return "dayone"
    if any(f.lower().endswith((".md", ".markdown", ".textbundle", ".textpack")) for f in names):
        return "markdown"
    if _bundle_md(src):                      # src is itself a .textbundle-like folder
        return "markdown"
    sys.exit(f"Could not detect format in {src} (no .json / .md / .textbundle found)")


def default_output(src, fmt):
    if os.path.isfile(src):
        return os.path.splitext(src)[0] + ".enex"
    if fmt == "dayone":
        jf = next((f for f in os.listdir(src) if f.lower().endswith(".json")), "Export.json")
        return os.path.join(src, os.path.splitext(jf)[0] + ".enex")
    return os.path.join(src, os.path.basename(os.path.normpath(src)) + ".enex")


def main():
    ap = argparse.ArgumentParser(
        description="Convert Day One JSON or Markdown (+ relative attachments) to an Apple Notes .enex")
    ap.add_argument("source", help="Day One export folder/.json, or a .md file / folder of .md files")
    ap.add_argument("-f", "--format", choices=["auto", "dayone", "markdown"], default="auto")
    ap.add_argument("-o", "--output", help="Output .enex path (or output folder when --split)")
    ap.add_argument("--split", action="store_true",
                    help="Write one .enex per note into a folder (recommended for large "
                         "libraries; Apple Notes imports many small files more reliably than "
                         "one huge one)")
    args = ap.parse_args()

    src = os.path.abspath(args.source)
    if not os.path.exists(src):
        sys.exit(f"Not found: {src}")
    fmt = detect_format(src) if args.format == "auto" else args.format
    notes = dayone_notes(src) if fmt == "dayone" else markdown_notes(src)
    print(f"Format: {fmt}")
    try:
        if args.split:
            base = os.path.splitext(default_output(src, fmt))[0]
            out = os.path.abspath(args.output) if args.output else base + "_enex"
            write_enex_split(notes, out, app=f"{fmt}_to_enex")
        else:
            out = os.path.abspath(args.output) if args.output else default_output(src, fmt)
            write_enex(notes, out, app=f"{fmt}_to_enex")
    finally:
        _cleanup_tmp()


if __name__ == "__main__":
    main()
