# ADR-005: The delays are chosen, not observed, and that is the boundary

Status: accepted. This is the boundary ADR the charter of every repository
in this set requires: the claim the offline design cannot make, stated
rather than implied.

## What is chosen

Every arrival delay in the committed world is a configured distribution:
lognormal medians per event type, a 30 day median for incidents, hours for
activity, and the corrections' own clock for backdated status rows. The
fabricated AUC published in the README is therefore a property of a chosen
world, E4 publishes its sensitivity to the choice, and no sentence in this
repository extrapolates the committed numbers to anyone's production
traffic.

## Why observation was not an option, which is the finding

Measuring real arrival delays requires a schema that records arrival, and
the premise of this repository is that most schemas do not. Where the
column is absent the delay is not merely unknown; the question is
unrepresentable, which is exit code 2 running as an epistemic statement.
Where ingestion logs exist as a side channel, the delay one can reconstruct
from them is itself censored: rows that have not arrived yet are exactly
the rows missing from today's measurement, and the censoring is not random,
because slow facts are systematically the late ones. An estimate built
naively on arrived rows is biased short in precisely the region that
matters.

## What measuring it for real would require

1. An append-only ingestion log with a load timestamp per row, retained
   longer than the slowest fact.
2. A fact timestamp whose own correction history is kept, because a
   backdated correction rewrites the quantity under study.
3. A delay estimator that treats not-yet-arrived rows as censored
   observations rather than absent ones.
4. A freeze of the warehouse's merge behaviour, since an upsert that
   overwrites in place destroys the arrival record as it lands.

Item 1 is the feature store argument from the pivot wearing different
clothes: arrival time as a first class column, written once, never updated.

## The one claim this ADR licenses

With chosen delays, every number is exactly reproducible and the leak's
mechanism is known rather than conjectured. That is a fair trade for a
study of the mechanism, and it is the whole trade: the committed gap says
what this class of leak can do, not what any particular warehouse's leak
is doing.
