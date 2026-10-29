"""SQL compilation of the feature spec to four dialects.

The warehouses themselves are never contacted (ADR-005 and the README's
boundary table). What is real here is the SQL: each dialect's text is
committed, parses under that dialect's grammar, and, transpiled onto an
engine this repository can run, produces the same rows as every other
dialect. E5 measures exactly that.
"""

from .emit import DIALECTS, emit_feature_sql

__all__ = ["DIALECTS", "emit_feature_sql"]
