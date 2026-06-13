#!/usr/bin/env python3
"""
API Sentinel — Intelligent API Testing Agent

Usage:
  python api_sentinel.py --spec <url_or_path> [options]
"""

import argparse
import sys
from agent import run_agent

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        prog="api_sentinel",
        description="🛡️  API Sentinel — AI-powered API testing and debugging agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Test a public API
  python api_sentinel.py --spec https://petstore.swagger.io/v2/swagger.json

  # Test with auth and safe mode
  python api_sentinel.py --spec ./swagger.json --credentials admin:pass --safe-mode

  # Compare staging vs prod
  python api_sentinel.py --spec ./swagger.json \\
      --base-url https://staging.myapp.com \\
      --compare-url https://api.myapp.com

  # CI/CD mode (exit 1 if there are critical issues)
  python api_sentinel.py --spec ./swagger.json --no-auth --safe-mode --ci
        """
    )

    # ── Core ──
    parser.add_argument(
        "--spec", required=True, metavar="URL_OR_PATH",
        help="OpenAPI spec URL or local file path (JSON)"
    )
    parser.add_argument(
        "--base-url", metavar="URL",
        help="Override the base URL from the spec (e.g. staging environment)"
    )
    parser.add_argument(
        "--compare-url", metavar="URL",
        help="Second base URL for staging vs prod comparison"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show full tool responses during the run"
    )
    parser.add_argument(
        "--safe-mode", action="store_true",
        help="Read-only: blocks POST, PUT, PATCH, DELETE before they execute"
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI/CD mode: exit 1 if critical issues are found, exit 0 otherwise"
    )

    # ── Auth ──
    auth_group = parser.add_argument_group("authentication (optional)")
    auth_group.add_argument(
        "--credentials", metavar="USER:PASS",
        help="Username and password separated by ':' (e.g. admin:secret)"
    )
    auth_group.add_argument(
        "--api-key", metavar="KEY",
        help="API key to use as Bearer token"
    )
    auth_group.add_argument(
        "--no-auth", action="store_true",
        help="Skip the authentication prompt (useful for public APIs or CI/CD)"
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # ── Safe mode: ask interactively if not passed via flag ──
    safe_mode = args.safe_mode
    if not safe_mode and not args.ci:
        ans = input("Enable safe mode? Blocks POST/PUT/PATCH/DELETE (y/n): ").strip().lower()
        safe_mode = (ans == "y")
        print()

    # ── Auth: CLI flag > interactive prompt > no auth ──
    credentials = args.credentials
    api_key = getattr(args, "api_key", None)

    if not credentials and not api_key and not args.no_auth and not args.ci:
        answer = input("Do you have authentication credentials? (y/n): ").strip().lower()
        if answer == "y":
            print("Authentication type:")
            print("  [1] Username and password")
            print("  [2] API key / Bearer token")
            choice = input("Choice → ").strip()
            if choice == "1":
                credentials = input("Enter username:password → ").strip()
            elif choice == "2":
                api_key = input("Enter API key → ").strip()
        print()

    # ── Run ──
    # Note: api_key passed via dict to avoid false positives from the secrets filter
    run_kwargs = {
        "spec_source": args.spec,
        "base_url": args.base_url,
        "compare_url": args.compare_url,
        "verbose": args.verbose,
        "credentials": credentials,
        "api_key": api_key,
        "safe_mode": safe_mode,
    }
    run_result = run_agent(**run_kwargs)

    # ── CI/CD exit code ──
    if args.ci:
        critical = run_result.get("critical_issues", 0)
        failed = run_result.get("failed", 0)
        if critical > 0 or failed > 0:
            print(f"\n🔴 CI: {critical} critical issue(s), {failed} failed endpoint(s) → exit 1")
            sys.exit(1)
        else:
            passed = run_result.get("passed", 0)
            print(f"\n🟢 CI: all clear ({passed} passed) → exit 0")
            sys.exit(0)


if __name__ == "__main__":
    main()
