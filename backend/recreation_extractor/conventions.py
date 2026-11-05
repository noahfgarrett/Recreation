"""Naming conventions of the drawing package the extraction rules expect.

Several rules key off the project code at the start of sheet numbers and
equipment tags (for example ``DEMO-ME-4CHW01`` or ``R-DEMO-CHW-P-01``) and off
the building codes that start electrical equipment tags (``RW4MDP4C6``).
They live here so a different package only needs these values changed.
The defaults match the synthetic sample package in ``samples/``.
"""

from __future__ import annotations

import re

PROJECT_CODE = "DEMO"
BUILDING_CODES = ("RS", "RW")

PROJECT_CODE_PATTERN = re.escape(PROJECT_CODE)
BUILDING_CODE_PATTERN = "(?:" + "|".join(re.escape(code) for code in BUILDING_CODES) + ")"
