"""Utility script to clear local account quarantine state.

Examples:
  python scripts/reset_cooldowns.py --all
  python scripts/reset_cooldowns.py --username someone@example.com
"""

import argparse
from core.quarantine import clear_all_quarantines, clear_quarantine


def reset() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="clear all quarantined accounts")
    parser.add_argument("--username", type=str, default="", help="clear one quarantined account")
    args = parser.parse_args()

    if args.all:
        count = clear_all_quarantines()
        print(f"Cleared quarantine for {count} account(s)")
        return

    if args.username:
        if clear_quarantine(args.username):
            print(f"Cleared quarantine for {args.username}")
        else:
            print(f"No quarantine entry for {args.username}")
        return

    print("No action specified. Use --all or --username.")


if __name__ == '__main__':
    reset()
