#!/usr/bin/env python3
"""
Local test runner for Claude PR Reviewer.
Run this to test against a real PR without GitHub Actions.

Usage:
  python scripts/test_local.py --repo owner/repo --pr 42
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Test Claude PR Reviewer locally")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr",   required=True, type=int, help="PR number")
    parser.add_argument("--model", default="claude-opus-4-5", help="Claude model")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print reviews but do NOT post to GitHub")
    args = parser.parse_args()

    # Inject into environment so reviewer.py picks them up
    os.environ["GITHUB_REPOSITORY"] = args.repo
    os.environ["PR_NUMBER"]          = str(args.pr)
    os.environ["CLAUDE_MODEL"]       = args.model

    if args.dry_run:
        os.environ["DRY_RUN"] = "1"
        print("🔵 DRY RUN — comments will NOT be posted to GitHub\n")

    # Import after env is set
    from src.reviewer import ClaudePRReviewer
    reviewer = ClaudePRReviewer()

    if args.dry_run:
        # Monkey-patch post methods
        reviewer._post_main_comment      = lambda r: print("\n=== MAIN COMMENT ===\n" + reviewer._build_main_body(r))
        reviewer._post_inline_comments   = lambda frs: print(f"\n[DRY RUN] Would post {sum(len(f.issues) for f in frs)} inline comments")
        reviewer._post_security_summary  = lambda frs: print(f"\n[DRY RUN] Security flags: {sum(len(f.security_flags) for f in frs)}")

    reviewer.run()


if __name__ == "__main__":
    main()
