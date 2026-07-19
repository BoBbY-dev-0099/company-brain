"""Source-backed operational memory adapters.

The package deliberately keeps source acquisition separate from Qwen memory
compilation and from the deterministic action gateway.  Adapters may read
company evidence, but they never perform a downstream company action.
"""

