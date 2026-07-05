"""Shared fixtures for API integration tests.

Forces the mock solver backend so the integration tests do not depend on a
local CPLEX license.
"""

from __future__ import annotations

import os

os.environ.setdefault("OPTI_MIND_SOLVER_BACKEND", "mock")
