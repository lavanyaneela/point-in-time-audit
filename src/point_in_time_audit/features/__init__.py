"""Feature construction under an explicit visibility policy.

Two independent implementations of the same declarative spec live here, one
on Spark DataFrames and one on DuckDB SQL. Neither is a wrapper over the
other on purpose: the whole repository rests on the as-of semantics being
correct, so the two engines referee each other and an experiment refuses to
publish when they disagree (ADR-002).
"""

from .spec import FEATURES, FeatureSpec, visibility_predicate_text

__all__ = ["FEATURES", "FeatureSpec", "visibility_predicate_text"]
