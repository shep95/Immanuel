"""Pattern Forge — the second, non-AI algorithm.

Runs alongside the crawler. Instead of piling raw facts, it abstracts the
*structure* responsible for the data being useful into reusable Universal Pattern
Objects, following the trained loop:

    experience -> outcome -> causal analysis -> abstract the mechanism ->
    formalize the pattern -> test it -> scope it -> store it -> retrieve it -> adapt it

It is fully deterministic (statistics + rules over the collected corpus), never a
model. Validated patterns can be exported as a downloadable skill file
(``/skills-download``).
"""

from .ontology import PatternObject, SCOPES, STATUSES  # noqa: F401
from .forge import run_pass  # noqa: F401
