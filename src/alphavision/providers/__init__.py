"""Data providers — one module per upstream data source.

Each provider exposes a ``fetch_<thing>(ticker) -> Snapshot`` function
that returns a Pydantic snapshot model. Failures are logged and yield
sensible defaults so a single bad endpoint cannot drop a row from the
universe.
"""

from __future__ import annotations
