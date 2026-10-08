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
ollama pull qwen3:4b-instruct      # or point NEVER_LEAVES_MODEL at any .gguf

never-leaves check                                  # prove the isolation, then exit
never-leaves quote examples/site-visit-note.txt     # draft a quote from your notes
never-leaves report notes.txt --client "Jenna"      # or a site report
never-leaves models                                 # what weights are on this machine
never-leaves runs                                   # what you produced, from what
```

Output is Markdown, stamped as a draft, with a run record and a list of things you
still have to check.

## What it actually produced

Real run, real note, no staging. The notes said this about access under a house:

```
- access under the house is tight, about 400mm
```

The 4B model drafted this:

```
## Scope of work
Access under house is about 40 short 400mm.
```

It invented a `40` and mangled the sentence. The tool caught it before it could
reach a client:

```
BEFORE YOU SEND IT
 - FIGURE TO CHECK. These appear in the draft and not in your notes: 40
 - FILL THESE IN. [DEPOSIT], [EXCLUSIONS], [RATE], [TIMEFRAME], [TOTAL]
```

That is the honest picture of a small local model. It is fast, private and free
and it will occasionally state a number it made up. So the draft is checked, not
trusted.

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
tests/           34 tests, including two that assert isolation from inside it
examples/        the notes used in the demo above
docs/VERIFY.md   how to check the claims in this README
```

## Requirements

- Linux with user namespaces enabled (any current distribution)
- Python 3.10 or newer
- `llama-cpp-python`, which is free and installs from a wheel
- Any GGUF model. The default is `qwen3:4b-instruct` if you already have ollama

There is no service, no account, no API key and no bill.

## Status

Alpha and honest about it. Two document types, quote and site report. Output is
Markdown. PDF rendering and offline voice input are the next two things worth
having, in that order.

## Licence

MIT. See [LICENSE](LICENSE).

Written by Edward Wade at Empire Labs Pty Ltd.
