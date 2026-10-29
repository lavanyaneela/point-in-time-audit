# ADR-004: Analyzer scope, decided up front and then measured

Status: accepted. E3 is the audit of this decision.

## The scope, as declared before the corpus ran

In scope, flagged with a named verdict:

1. A join between a registered prediction table and a registered event
   table carrying no temporal predicate at all.
2. The same join with a fact predicate and no arrival predicate, which is
   the version that passes code review.
3. An arrival predicate whose comparand is not the prediction instant: a
   wall clock, a literal date, another column.
4. Any temporal predicate the analyzer cannot certify as a bare
   comparison: a UDF, a CASE, a BETWEEN. Flagged, not trusted, including
   the correct ones.
5. A training task with no arrival completeness sensor upstream, at DAG
   grain.

Refused rather than judged: a joined relation the registry does not list
and whose provenance is invisible, and any registered table with no arrival
column, which is exit code 2 and the thesis.

Out of scope, declared as structurally undetectable at this analyzer's
grain, which is tables:

1. A leak baked into an intermediate table upstream; the consumption site
   has no event table in scope.
2. The same relay through a CTE or inline subquery.
3. A sensor wired correctly but waiting on the wrong signal.

Those are the 3 classes it cannot see, and a relay site is answered with an
out-of-scope notice naming the traceable event ancestry, never with
certification.

## Why rule 4 trades precision away on purpose

An analyzer that tries to evaluate arbitrary expressions inherits the
halting problem one SQL function at a time, and every heuristic it adds is
a new way to certify a leak. Flagging what it cannot read is the only
posture consistent with exit code 2, and it has a measurable price: the
corpus's correct-but-wrapped predicates are flagged, E3 publishes that
count, and the operational answer is to rewrite the predicate in bare form
or register the site as reviewed, not to teach the analyzer trust.

## Was the declaration right

E3's answer: direct classes detect at 100.0% of direct joins across varied
syntax, the clean controls produce 0 false positives, the relay classes
detect at zero exactly as declared, and the declaration survived contact
with the corpus unchanged. The one undeclared discovery was procedural, not
semantic: the first corpus run found nothing at all because of a dependency
rename, which is recorded in the README's bug section and pinned by a
regression test. The pivot arithmetic then prices the declaration's limit:
once intermediate routing passes the computed crossover, the blind share
dominates and the scope itself, not the implementation, is what has to
change, in the direction of a store that makes arrival a first class
column.
