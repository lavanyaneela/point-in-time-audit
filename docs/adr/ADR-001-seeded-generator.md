# ADR-001: A seeded generator rather than a public dataset

Status: accepted.

## Decision

The world is generated: a seeded process produces entities, events carrying
both a fact time and an arrival time, and outcomes, and the committed
fixture under `fixtures/event_log` is the single world every published
number comes from.

## Why a public dataset cannot do this job

Measuring a point-in-time leak requires knowing, for every event, both when
it became true and when it landed, because the leak is defined as the gap
between those two instants. No public tabular dataset records them as
separate columns; most record neither, and the ones that record one do not
say which one it is. A study built on such data would be estimating the very
quantity it needs as ground truth. The generator makes the leak measurable
by construction: the delay distributions are configuration, so what a
pipeline read and what was knowable both have exact answers.

## What the decision costs

Every headline is a property of a chosen world. The committed configuration
is one point in a space, and a different delay distribution gives a
different gap, which is not a caveat buried here but the subject of E4: the
sweep publishes the gap as a function of the delay, from 3.66 points at zero
incident delay to a climb to 15.26 points at the top of the sweep. The
README quotes the committed default and points at the curve. ADR-005 carries
the second half of the cost: the delays are chosen, not observed, and what
observing them on real traffic would take.

A second cost appeared during the build and is kept on the record: a
generated world can be accidentally rigged. The first calibration let one
feature carry the whole gap as a near copy of the label, and the E2
attribution table is what convicted it. The recalibrated world spreads the
leak across the incident features with the corrections as weaker evidence,
and the generator tests pin the properties that keep it honest, including
that corrections fire wrongly for some negative outcomes.

## Mechanics worth holding to

The fixture manifest pins three identities: file bytes, a writer independent
content hash, and the hash of the generator configuration. A drifted config
refuses to load rather than renaming a different world. Event ids are
assigned after a canonical sort by arrival, so they are a pure function of
the configuration, and the log keeps the full Kafka record envelope because
offset order is arrival order, which is precisely the information a
warehouse schema drops.
