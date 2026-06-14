#!/bin/bash
# Double-click this file to open the Markdown / Day One -> Apple Notes (.enex) GUI.
# It runs the GUI that lives in the same folder as this launcher.

cd "$(dirname "$0")" || exit 1
export TK_SILENCE_DEPRECATION=1   # hush Apple's Tk 8.5 deprecation notice

# Pick a Python 3 with Tkinter, PREFERRING a modern Tk (>= 8.6).
# Apple's /usr/bin/python3 ships Tk 8.5, which renders blank windows on recent
# macOS, so we only use it as a last resort.
best=""; best_ver=0; fallback=""
for cand in \
    python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    python3.13 python3.12 python3.11 python3.10 python3.9 \
    /usr/bin/python3; do
  p="$(command -v "$cand" 2>/dev/null || true)"
  [ -z "$p" ] && [ -x "$cand" ] && p="$cand"
  [ -z "$p" ] && continue
  ver="$("$p" -c 'import tkinter,sys; sys.stdout.write(str(int(round(float(tkinter.TkVersion)*10))))' 2>/dev/null)" || continue
  [ -z "$ver" ] && continue
  [ -z "$fallback" ] && fallback="$p"
  if [ "$ver" -ge 86 ] && [ "$ver" -gt "$best_ver" ]; then best="$p"; best_ver="$ver"; fi
done
PY="${best:-$fallback}"

if [ -z "$PY" ]; then
  osascript -e 'display alert "Tkinter not found" message "No Python 3 with Tkinter was found.

Quickest fix — open Terminal and run:

  brew install python-tk

then double-click this launcher again."'
  exit 1
fi

if [ -z "$best" ]; then
  # Only the old Tk 8.5 is available -> the window will likely be blank.
  osascript -e 'display alert "Old Tk detected (blank-window bug)" message "Only Apple’s deprecated Tk 8.5 was found, which renders blank windows.

Fix it once with:

  brew install python-tk

then double-click this launcher again. Trying anyway…"'
fi

echo "Using: $PY  (Tk $("$PY" -c 'import tkinter; print(tkinter.TkVersion)'))"
if ! "$PY" dayone_to_enex_gui.py; then
  osascript -e 'display alert "Could not start the converter" message "Run it from Terminal to see the error:\n\n  '"$PY"' dayone_to_enex_gui.py"'
fi
