#!/usr/bin/env bash
# The demo run shown in the README and in the competition entry.
#
# Recorded with:
#   asciinema rec --overwrite -i 1 \
#     -t "Never Leaves: a quote drafted with no network route" \
#     -c "bash docs/demo.sh" docs/demo.cast
#
# Converted to a GIF with:
#   agg --font-size 15 --idle-time-limit 3 --theme monokai docs/demo.cast docs/demo.gif
#
# Nothing here is staged. The isolation proof is read from the kernel, the
# weights are loaded inside this process, the draft is checked against the
# notes that were actually given to it. The document shown at the end is
# the file that run wrote.
set -u
cd "$(dirname "$0")/.."

# Put the installed command on PATH so the printed line is literally the one
# that runs, rather than a rewrite of it.
if [ -f .venv/bin/activate ]; then
    . .venv/bin/activate
fi

NOTE="${1:-examples/site-visit-note.txt}"
OUT="docs/demo-quote.md"

printf '$ %s\n' "never-leaves quote ${NOTE} --client Jenna --out ${OUT}"
never-leaves quote "${NOTE}" --client Jenna --out "${OUT}"

printf '\n$ %s\n' "cat ${OUT}"
cat "${OUT}"
