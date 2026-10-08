# Verifying the claims

This README makes two claims that are checkable, so here is how to check them.
Nothing here needs to be taken on trust, including the tool's own output.

## 1. That it cannot reach a network

### The quick check

```bash
never-leaves check
```

It re-executes itself into a network namespace first, then reports what it finds
there. Expect `isolated yes`, one interface named `lo`, `interfaces up` empty,
`routes 0`, `open IP sockets 0`. Exit status is 0 when isolated and 1 when not, so
it can be used as a gate in a script.

### Read the kernel tables yourself

Do not trust the tool's summary. Ask the kernel inside the same kind of namespace:

```bash
unshare -rn sh -c 'cat /proc/net/dev; echo ---; cat /proc/net/route; echo ---; cat /proc/net/tcp'
```

Expect a single `lo` line with zero counters, an empty route table and an empty
TCP table. That is the state the tool runs in.

### Prove a connection attempt fails

```bash
unshare -rn python3 -c "
import socket
try:
    socket.create_connection(('1.1.1.1', 443), timeout=3)
    print('REACHABLE, the claim is false')
except OSError as exc:
    print('BLOCKED:', exc)
"
```

Expect `BLOCKED: [Errno 101] Network is unreachable`.

### Watch it while it works

Run the whole job with no network at all and watch it succeed anyway. With Docker:

```bash
docker run --rm --network none -v "$PWD:/w" -w /w python:3.12 \
  sh -c 'pip install -q llama-cpp-python &&
         python -m never_leaves quote examples/site-visit-note.txt'
```

With `--network none` there is not even a loopback route to the outside, so if it
finishes, it finished with nowhere to send anything.

### The hostile version

Try to make it phone home. Add a network call anywhere in the code path and run
the suite. It will fail, because the process has no route to make the call over.
The two isolation tests in `tests/test_isolation.py` do exactly this and they
assert the block from inside the namespace rather than from outside it.

## 2. That the draft is checked against your notes

```bash
python -m pytest tests/test_claims.py -v
```

The important test is `test_an_invented_price_is_flagged`. It feeds the checker a
draft containing `$95` and `$570` against notes containing no price at all and
asserts that both are reported.

To see it on a live run, the demo in the README is reproducible:

```bash
never-leaves quote examples/site-visit-note.txt --client Jenna
```

Every figure in the output is looked up in the notes before you see it. Gemma 3 4B
kept the figures straight on both runs recorded in the README, so the list came
back with placeholders to fill in and no unsourced figure. A smaller or differently
quantised model can insert a figure that is not there. Then it appears under
`FIGURE TO CHECK`, money first. Behaviour varies by model and by run, so do not rely
on a particular number appearing. The check is what makes a model this small safe to
use at all.

## 3. That nothing is written anywhere else

```bash
never-leaves quote examples/site-visit-note.txt --ledger /tmp/runs.jsonl
cat /tmp/runs.jsonl | python3 -m json.tool --json-lines
```

One line per run, with the source digest, the draft digest, the model, the token
counts and the isolation state. The default location is
`~/.local/share/never-leaves/runs.jsonl`, mode 0600. There is no other output path.

## What this does not prove

Being straight about the edges:

- Namespaces are a Linux feature. On macOS this refuses to run rather than pretend.
- The guarantee covers this process. If you run it on a machine you do not trust,
  the machine is still not yours.
- A 4B model is a drafter. It is not a surveyor, an electrician or a lawyer and
  the tool is built on the assumption that a human reads the output.
- The claim check compares figures, which is the failure that costs money. It does
  not compare prose against your notes sentence by sentence, so a wrong sentence
  with no numbers in it can still get through.
- It catches what the draft adds, not what it leaves out. A figure or a scope item
  in your notes that never reaches the draft is not reported. That happened on both
  runs recorded in the README: the 400mm access note and the 90mm cutouts did not
  make the quote. A guard for omission is the next thing this needs.
