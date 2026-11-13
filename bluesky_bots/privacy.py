"""Anonymous account IDs, shared by the review and reports services.

Guide: docs/13-reports.md (step 1).
"""
from __future__ import annotations

import hashlib
import hmac
import os

from . import config  # noqa: F401  (importing it loads .env, where ANON_SALT lives)


def anon_id(did: str, salt: str | None = None) -> str:
    """A stable label for an account, such as acct_3f9a1c0b77de, that cannot be turned back into the DID.

    The same DID always gives the same label. The secret comes from `salt`,
    or from ANON_SALT in .env.
    """
    raise NotImplementedError("anon_id is a task in docs/13-reports.md.")
