"""Former SMI Properties fleet reseed script — retired.

Customer deal did not close. Fleet seed data and this reseed path were removed.
Import carts via Admin → Fleet Import or POST /api/carts.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "reseed_fleet_demo.py is disabled.\n"
        "SMI Properties / SMIP customer data was purged from MaintainSMIP.\n"
        "Use Admin → Fleet Import or the Fleet UI to add inventory.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
