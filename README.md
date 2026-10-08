# Never Leaves

Draft real documents offline, from your own notes, on a local open-weight model.

Two guarantees, both enforced rather than advertised:

1. **Your notes cannot leave the machine.** The tool puts itself inside a Linux
   network namespace that has no usable interface and no route. It proves that
   before it reads a single byte of your data. Not a setting. Not a promise.
2. **The draft is checked against your notes before you send it.** Every figure in
   the draft is looked up in what you actually wrote. Anything that cannot be
   traced is reported, money first.

Built for people whose data genuinely cannot go to somebody else's server: trades,
field work, inspections, rural and remote sites, anywhere the signal is missing and
the client's details are not yours to upload.

## The problem with the obvious approach

A cloud model would do this job well. It would also mean pasting a client's name,
address and phone number into a company you cannot audit, over a connection that
may not exist on site. For a lot of real work that is simply not an option, so
those people get no help from any of it.

A four billion parameter model will run on a laptop with the network switched off.
It costs nothing. Nobody can change it under you, rate limit you or read your
notes. That is the whole argument for open weights. This tool is that argument made
concrete.

## Quick start

```bash
pip install -e .

# Gemma 3 4B as a GGUF file on disk. Any other GGUF works the same way.
mkdir -p ~/models
curl -L -o ~/models/gemma-3-4b-it-Q4_K_M.gguf \
  https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/google_gemma-3-4b-it-Q4_K_M.gguf

never-leaves check                                  # prove the isolation, then exit
never-leaves quote examples/site-visit-note.txt     # draft a quote from your notes
never-leaves report notes.txt --client "Jenna"      # or a site report
never-leaves models                                 # what weights are on this machine
never-leaves runs                                   # what you produced, from what
```

Output is Markdown, stamped as a draft, with a run record and a list of things you
still have to check.

## What it actually produced

Real run, real note, no staging. Gemma 3 4B, 2.5 GB as one Q4_K_M file. The note
was a scribbled site visit:

```
- replace 6 downlights in kitchen ceiling, existing 90mm cutouts
- customer wants warm white, not cool white
- also wants a price to add 3 double GPOs in the shed
- shed has no existing circuit at all, would need to run cable back to the board, approx 18m
- access under the house is tight, about 400mm, will slow the cable run down
```

It drafted a 143 word quote. The scope and the price table, verbatim:

```
## Scope of work
Replace six downlights in kitchen ceiling. Install two new warm white downlights.
Add three double GPOs in the shed. Run cable from switchboard to shed.

## Price
| Item | Rate | Total |
|---|---|---|
| Downlights (6) | [RATE] | [TOTAL] |
| Downlights (2 - Warm White) | [RATE] | [TOTAL] |
| GPOs (3) | [RATE] | [TOTAL] |
| Cable Run (18m) | [RATE] | [TOTAL] |
| Labour | [RATE] | [TOTAL] |
```

Every figure there traces back to the notes: 6, 2, 3 and 18m. Nothing was
invented and no rate was guessed. The tool listed what a human still has to fill
in. That was the whole list:

```
BEFORE YOU SEND IT
 - FILL THESE IN. [AMOUNT], [DEPOSIT], [EXCLUSIONS], [NUMBER], [RATE], [TIMEFRAME], [TOTAL]
```

On a second run the customer had asked for a ballpark figure that day. The tool
still produced `[RATE]` and `[TOTAL]` and no number at all. It does not price
work, on any run, however the notes are worded.

**And what it got wrong.** The access note, tight at about 400mm, never reached
the quote. Neither did the 90mm cutouts. The check cannot see that, because the
opposite fault is the one it was built for: a figure in the draft that is not in
your notes. A figure in your notes that never reaches the draft is a real failure
mode of a small model. It showed up twice here. There is no automated guard
against it yet. Read the draft. That is why it is stamped as one.

So the honest picture: a 4B model that stays faithful to the figures and drops
things, checked by a tool that catches what it adds and not yet what it omits.

## How the no-network claim is enforced

`never-leaves` re-executes itself through `unshare -rn`, which creates a user and
network namespace together. Inside that namespace the loopback device exists and is
down, the route table is empty and no IP sockets are open. There is no path to any
network, local or remote, because there is no route to have a path over.

The check is deliberately suspicious of its own environment variable. A marker says
"we believe we were launched isolated". The kernel tables say whether that is
actually true and only the second one counts. It reads `/proc/net/dev`,
`/proc/net/route` and `/proc/net/tcp{,6}` plus `udp{,6}` directly, so it needs no
extra binaries.

The socket count matters more than it looks. A namespace with no interfaces cannot
stop a process that inherited an already open socket from its parent. Counting open
IP sockets is how that is ruled out. It is part of the pass condition.

It refuses to run without the guarantee. `--no-isolate` exists for debugging and
says loudly in its output that privacy was lost.

If isolation cannot be verified after the draft is written the run is flagged in
the ledger, so a silent failure cannot become a quiet habit.

## Verify it yourself

See [docs/VERIFY.md](docs/VERIFY.md) for the commands. The short version is that
you do not have to believe this README. Put the tool in a container with no network
at all or watch its sockets or read `/proc` yourself. It is designed to survive
all three.

## What it refuses to do

- It does not invent a price. Missing figures become `[RATE]` and `[TOTAL]` and
  every placeholder is listed at the end.
- It does not compute a subtotal from invented rates.
- It does not claim to be a finished document. The draft banner is not removable
  by configuration.
- It does not send, upload, sync or phone home. There is no code path for it.
- It does not pretend a 4B model is a good writer. It is a good drafter.

## Layout

```
never_leaves/
  isolation.py   kernel-enforced no-network guarantee and its proof
  model.py       any local GGUF, loaded in-process. No server, no port
  templates.py   document shapes and the rules the model must follow
  claims.py      checks the draft against your notes, money first
  document.py    renders the draft, the flags and the run record
  ledger.py      local one-line-per-run record
  cli.py         the command
tests/           41 tests, including two that assert isolation from inside it
examples/        the notes used in the demo above
docs/VERIFY.md   how to check the claims in this README
```

## Requirements

- Linux with user namespaces enabled (any current distribution)
- Python 3.10 or newer
- `llama-cpp-python`, which is free and installs from a wheel
- Any GGUF model. The default is Gemma 3 4B, looked for as a `.gguf` file in
  `~/.cache/never-leaves/models`, `~/models` and `./models` first, then as the
  ollama tag `gemma3:4b`
- Ollama weights are found wherever ollama actually keeps them: `$OLLAMA_MODELS`,
  `~/.ollama/models` and, on a system install, `/usr/share/ollama/.ollama/models`
- ollama's own Gemma 3 export does not load on this loader. It omits
  `gemma3.attention.layer_norm_rms_epsilon`, which the loader requires, so the
  same model as a GGUF converted by the llama.cpp toolchain is preferred. The
  tool says so plainly instead of printing a traceback if it is handed one

There is no service, no account, no API key and no bill.

## Status

Alpha and honest about it. Two document types, quote and site report. Output is
Markdown. PDF rendering and offline voice input are the next two things worth
having, in that order.

## Licence

MIT. See [LICENSE](LICENSE).

Written by Edward Wade at Empire Labs Pty Ltd.
