"""The pivot arithmetic: when does static analysis stop being the right tool.

The deliberately out-of-scope feature is a feature store. The honest version
of "roadmap" is a computed trigger condition: once enough of an estate's
temporal joins pass through intermediate tables, the undetected share of
leak sites exceeds the detected share, static analysis is the wrong tool,
and the fix is structural, which is to make arrival time a first class
column that a store enforces.

With c the measured catch rate on direct join sites and f the fraction of an
estate's leak sites routed through intermediates (which the analyzer misses
entirely), the detected share is (1 - f) * c and the undetected share is
everything else. They cross at

    f* = 1 - 1 / (2c)

which E3 evaluates at the measured c and publishes. A c at or below one half
makes f* nonpositive: static analysis would already be the wrong tool before
the first intermediate table exists.
"""

from __future__ import annotations


def crossover_intermediate_share(direct_catch_rate: float) -> float:
    """f* as defined above, clamped into [0, 1]."""
    if not 0.0 <= direct_catch_rate <= 1.0:
        raise ValueError("catch rate must be a proportion")
    if direct_catch_rate == 0.0:
        return 0.0
    f_star = 1.0 - 1.0 / (2.0 * direct_catch_rate)
    return min(1.0, max(0.0, f_star))
