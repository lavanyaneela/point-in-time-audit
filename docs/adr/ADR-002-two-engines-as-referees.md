# ADR-002: Two as-of implementations, Spark and DuckDB, as mutual referees

Status: accepted.

## Decision

The feature spec is compiled twice, independently: a PySpark DataFrame job
in local mode, working in float day arithmetic, and DuckDB executing the
committed timestamp SQL. Experiments build with both and refuse to publish
on any disagreement; the measurement module raises rather than averaging,
and the E4 sweep runs the pair at every point.

## Why redundancy is worth its cost here

Every number in this repository rests on the as-of join being correct. A
single implementation is a single point of failure for all of them, and the
failure mode of as-of logic is the quiet kind: a boundary off by one
comparison produces plausible features and a plausible AUC. With two
implementations that share nothing but the spec, a disagreement indicts
exactly one compiler, and agreement is evidence rather than hope.

Independence is total on purpose. The engines do not share a SQL string, a
join strategy, or even a time representation: one compares timestamps, the
other compares float days, and the fixture writer rounds day values onto
exact microsecond boundaries so the two representations are provably
interchangeable (a generator test pins the invariant). If the engines were
one wrapper over the other, their agreement would be a tautology.

## The decision paid for itself in its first hour

The first parity run disagreed on the activity window features for a
subset of entities, one engine consistently larger. The cause was
session timezone calendar arithmetic clipping one hour from every
window that crossed the spring forward transition, detailed in `docs/failure-modes.md` and reconstructed by a test
that re-runs the broken session. Neither engine alone would have surfaced
it; the numbers were plausible both ways. That is the referee arrangement
doing the only job it has.

## Costs and the line not crossed

The cost is a second implementation to maintain and roughly doubled feature
build time in experiments. Both are accepted. What the arrangement does not
claim: agreement between two engines is not correctness, it is consistency.
The paper-checkable tiny world in the test suite carries the correctness
argument case by case; the referees guard against one engine drifting from
it at scale.
