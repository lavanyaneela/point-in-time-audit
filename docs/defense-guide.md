# Defense guide: point-in-time-audit

For the author, before any conversation about this repository. Every figure
here is re-measured by `make verify` and checked against this document by
`tools/check_numbers.py`, so what you say aloud cannot drift from what the
code produces.

## The one-breath version

Training tables cannot represent whether a value was knowable at prediction
time, because becoming true and arriving are different timestamps and
schemas keep one. I built a world where both exist, measured what ignoring
arrival fabricates, 12.45 points of AUC on the pipeline that passes code
review, then built the CI gate that flags joins which cannot be correct,
and published the gate's own blind spots: 3 structurally invisible leak
classes, measured at zero detection, with the crossover computed for when
static analysis stops being the right tool. The gate catches 70.8% of the
corpus leak cases, and the missing share is named, not hidden.

## The numbers, with their derivations

| Figure | Where it comes from |
| --- | --- |
| 12.45 points of AUC fabricated | E1: paired entity splits, fact-only minus point-in-time, mean over all 5 seeds; per-seed gaps are published, from a floor that is never below 11.66 points to 14.13 |
| an AUC of 0.8913 for the naive pipeline | E1, same splits; the honest AUC is 0.7668 and the latest-value join scores 0.9457 |
| worst offender is incident_count_90d, 10.47 points by itself | E2: swap that one honest column for its naive column on an otherwise honest table |
| parts sum to 20.8 against the 12.45 joint gap | E2: the difference is interaction between redundant incident features, published, not normalised away |
| 2.21 points remain at zero incident delay | E4: the backdated corrections and the slower status and assessment tails leak on their own clocks; only the arrival predicate removes them |
| names 17 of the 24 leak cases, 100.0% of direct sites | E3 over the 36 corpus cases with declared ground truth; misses 7 cases across the 3 leak classes it structurally cannot see |
| flags 3 of the 10 cases whose ground truth is clean | E3; every flag a wrapped correct predicate; the 7 bare-predicate clean cases show 0 false positives, a zero bounded only below 34.8% at 95 percent confidence |
| crossover sits at 50.0% | the pivot arithmetic at the measured direct catch rate; past 50.0% of temporal joins routed through intermediates, the blind share dominates |
| 3 of 3 dialects agree | E5: Spark executed for real locally, Snowflake and BigQuery transpiled onto DuckDB, value for value against the reference |
| 239 tests, 98.7% line coverage | the junit XML and coverage JSON, collected counts, coverage floored not rounded |

## Questions you should expect, with the honest answers

**"Your gap is a property of a generator you control. Why should I care?"**
Because the mechanism, not the magnitude, is the claim. No public dataset
records both timestamps, so any study of this leak needs ground truth it
can only get by construction (ADR-001). The magnitude's sensitivity to the
construction is itself published: E4 sweeps the delay and the gap moves
from 2.21 to a climb to 15.26 points. What transfers to production is the
contract and the gate, and the gate's accuracy is measured against declared
ground truth, not against the generator's labels.

**"Couldn't the analyzer just evaluate the UDFs?"** It flags 3 semantically
correct predicates in the corpus, and that is the designed trade (ADR-004):
evaluating arbitrary expressions is how gates learn to certify leaks.
Refusing to guess costs precision, the cost is measured, and the
operational fix is bare predicates or a reviewed-site register, not a
smarter guesser.

**"What does exit code 2 buy that exit code 1 doesn't?"** It separates "the
answer is no" from "the question cannot be asked of this data". Most
detectors assume the one visible timestamp is the truth, which blesses
exactly the schemas that should be refused. The measurement half honours
the same contract: pointed at a registry with no arrival column, it
refuses rather than reporting a number it cannot mean.

**"The relay misses look fatal. Why ship a gate that misses 7 of the 24 leak cases?"**
Because the alternative gates miss them too and do not say so. The misses
are structural at table grain, the scan marks every relay site as
uncertified rather than silent, and the pivot number tells a team exactly
when their estate's shape has outgrown static analysis. A tool that prices
its own replacement is more useful than one that promises forever.

**"Was Spark really necessary for 119,540 events?"** Local mode is the
production shape of as-of feature construction, not a performance claim;
the resume already evidences PySpark and this is depth on it. The honest
engineering content is the referee arrangement (ADR-002): two independent
compilers of one spec, which caught the daylight saving clip on their
first disagreement.

## The war stories, told precisely

**Daylight saving.** Interval arithmetic on timezone-aware timestamps
follows the session timezone's calendar, DuckDB inherits the session
timezone from the runner, and every 30 day window spanning the spring
forward transition ran one hour short. The referee pair surfaced it as
a disagreement on the activity window features for a subset of
entities; on the committed world the broken session clips 20 windows,
and entity 139 alone drops an event worth 16.59965 of summed value,
26.0 minutes inside the lost hour. The contemporaneous fix commit
describes the first sighting on the pre-calibration world as a
sums-only disagreement; the committed reconstruction, which every
verify re-runs, moves both the count and the sum, and the committed
description follows the reconstruction because commit messages are
immutable and measurements are not. The fix is a
UTC pin in both engines; the reconstruction test re-runs the broken
session on every verify. If asked for the original sighting: it was found
on the pre-calibration world during the first parity run, with a different
entity and a smaller sum, and the figures quoted anywhere in this
repository are the re-derived ones from the committed world, because
commit messages are immutable and measurements are not.

**The analyzer that saw nothing.** A dependency renamed the field holding
a query's FROM clause; the analyzer read the old name and found zero
relations, so its first corpus run passed everything by finding nothing.
The ground truth corpus predates the working analyzer, which is the only
reason a broken gate looked broken instead of quiet. The regression pin is
deliberately crude: the corpus run must produce findings at all.

**The planted answer key.** The first world's corrections fired for most
positives and never for negatives, and E2 attributed essentially the whole
gap to that one feature, which is a label copy, not a leak. The world was
recalibrated, corrections now fire wrongly for some negatives, and the
generator tests pin it. Keep this story: a measurement that can convict
its own fixture is the strongest sentence in the repository.

## Build provenance, if asked

The repository was built in one concentrated working session from a fully
prepared design. That is why the history looks the way it does, and the
honest description is the defensible one: commits mark completed and
verified units in build order, not wall-clock effort, so adjacent commits
can land seconds apart and several share a minute; the three tags were
all minted at the end of the session, each placed on the commit where its
capability completed, so their tagger timestamps are simultaneous while
the commits they point at are not. Nothing was backdated, squashed,
reordered or force-pushed, and nothing should ever be. Two specific
reconciliations a reader of the log deserves: the engine commit and the
timezone fix sit seconds apart because the engine was committed at its
pre-fix state after the bug was already found, so both states are real
and the order is the build order; and the corpus commit postdates the
analyzer fix it enabled because files are committed after the debugging
they serve, so commit order understates the corpus's age.

## What you can safely promise a team tomorrow

Register your tables' fact and arrival columns, run `pit-audit scan` in
CI, branch on all four exit codes, keep refusals loud, and watch the
out-of-scope notice count as the pivot's early warning. What you should
not promise: that the gate catches relayed leaks, that the committed gap
predicts their gap, or anything about Kafka beyond a round trip, because
this repository does not claim those either.
