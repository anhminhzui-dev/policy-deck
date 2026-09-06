"""Make the src-layout package importable for tests without an install.

`src/policy_deck` may exist as an implicit namespace package (PEP 420) before G1 lands its
`__init__.py`, or as a regular package once it does -- either way, putting `src/` on `sys.path`
is enough for `import policy_deck...` to work under pytest with no `pip install`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
