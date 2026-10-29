"""point-in-time-audit: measures the AUC a feature pipeline fabricates by
reading facts that had not yet arrived, and refuses when the schema cannot
even pose the question.

The package exists because a feature table joined on entity id cannot say
whether a value was knowable at prediction time. The moment a fact became
true and the moment it landed in the warehouse are different timestamps, and
most schemas keep only one. Everything in here is organised around that gap:
a generator that carries both timestamps, two feature pipelines that differ
only in which timestamps they respect, and a static analyzer that flags SQL
which cannot be respecting both because it never mentions the second one.
"""

__version__ = "0.3.0"
