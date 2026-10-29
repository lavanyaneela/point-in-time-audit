# Failure modes

What breaks, how it announces itself, and what the repository already does
about it. Ordered by how expensive the silence would be.

## 1. Session timezone arithmetic clips windows at daylight saving

**Symptom.** Window aggregates disagree between engines, or between runs of
the same SQL on hosts configured with different timezones: identical
counts, different sums, only for entities whose window spans a transition.

**Mechanism.** `INTERVAL n DAY` on a timezone-aware timestamp is calendar
arithmetic in the session timezone. Across a spring forward transition a
calendar day loses an hour, so the window's lower bound lands one hour late
and every event inside that hour is silently excluded. On the committed
world a New York session clips 20 windows, and the first affected entity
loses an event worth 16.59965 of summed value, sitting 26 minutes inside
the lost hour.

**Defence here.** Both engines pin their sessions to UTC, where a day is
86400 seconds on every day of the year, and the reconstruction test re-runs
the broken session so the defence is re-proven on every verify. The hazard
transfers to any warehouse that runs the committed dialect SQL: run it in a
UTC session, and treat a non-UTC default as a finding about the warehouse.

## 2. The analyzer certifies by silence when it sees nothing

**Symptom.** A scan over known-leaking SQL exits 0 with an empty report.

**Mechanism.** The analyzer only judges scopes where it can see a
registered event table. A parsing regression that hides relations from it,
which happened once via a dependency rename, turns the whole corpus into a
quiet pass.

**Defence here.** Clean joins receive an explicit OK finding, so an empty
report over SQL that should contain joins is visibly wrong; a regression
test asserts the corpus run produces findings at all; and unregistered
relations with no provenance are refused rather than ignored, so "the
analyzer saw nothing" and "the analyzer approved" render differently.

## 3. Relay sites read as clean to a hurried reader

**Symptom.** A pipeline full of staging tables scans with no leak findings
and a scatter of out-of-scope notices nobody reads.

**Mechanism.** The structural blindness of ADR-004: a leak baked upstream
has no event table at its consumption site. The notices are the only trace.

**Defence here.** The notices name the traceable event ancestry and state
that the site is not certified; the pivot number puts a ceiling on how much
relaying the tool tolerates before it is the wrong tool; and the README's
blind class table keeps the miss rate where a reader cannot avoid it.
Operationally: treat a rising notice count as the trigger condition, not as
noise.

## 4. The fixture drifts out from under its numbers

**Symptom.** Experiments run clean but disagree with the README.

**Mechanism.** A generator or configuration edit without regeneration, or a
regeneration without re-measurement.

**Defence here.** The manifest pins the configuration hash and refuses to
load a drifted world; `make fixture` plus a CI diff makes regeneration
idempotent; every experiment output carries the configuration hash it was
measured under and a test asserts they all match; and `check_numbers.py`
fails the build on the first stale sentence.

## 5. A measured zero gets read as a zero

**Symptom.** "No false positives" hardens into "the analyzer never false
positives" three retellings later.

**Mechanism.** 0 false positives over the 7 clean cases bounds the rate
only below 34.8% at 95 percent confidence, and nothing about a small
corpus licenses more.

**Defence here.** The bound is computed in the collector, anchored in the
README beside the zero, and this entry exists so the limitation is a
documented behaviour rather than a reviewer's catch.

## 6. The exit codes get collapsed by automation

**Symptom.** A CI wrapper treats any nonzero exit as failure, and refusals
(2) start being "fixed" by deleting tables from the registry, which turns
refusals into silence.

**Mechanism.** Exit 2 is an answer, not an error, and `make` itself cannot
tell them apart.

**Defence here.** The README documents the contract and the demo recipe
shows the pattern: branch on the console script's code, never on a make
target's. The registry stays honest only if refusals stay loud; a wrapper
that cannot represent "refused" should fail the build on 2 as well, loudly,
rather than swallowing it.
