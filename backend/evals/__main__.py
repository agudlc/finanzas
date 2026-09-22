"""`python -m evals`, which is what `make eval` runs."""

import asyncio

from evals.run import main

raise SystemExit(asyncio.run(main()))
