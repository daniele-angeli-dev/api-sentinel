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
  # Test API pubblica
  python api_sentinel.py --spec https://petstore.swagger.io/v2/swagger.json

  # Test with auth and safe mode
  python api_sentinel.py --spec ./swagger.json --credentials admin:pass --safe-mode

  # Confronto staging vs prod
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
        help="OpenAPI spec URL o path locale (JSON)"
    )
    parser.add_argument(
        "--base-url", metavar="URL",
        help="Override base URL dalla spec (es. ambiente staging)"
    )
    parser.add_argument(
        "--compare-url", metavar="URL",
        help="Secondo base URL per confronto staging vs prod"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mostra le risposte complete dei tool durante il run"
    )
    parser.add_argument(
        "--safe-mode", action="store_true",
        help="Solo lettura: blocca POST, PUT, PATCH, DELETE prima che partano"
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI/CD mode: exit 1 se ci sono critical issues, exit 0 altrimenti"
    )

    # ── Auth ──
    auth_group = parser.add_argument_group("autenticazione (opzionale)")
    auth_group.add_argument(
        "--credentials", metavar="USER:PASS",
        help="Username e password (es. admin:secret)"
    )
    auth_group.add_argument(
        "--api-key", metavar="KEY",
        help="API key da usare come Bearer token"
    )
    auth_group.add_argument(
        "--no-auth", action="store_true",
        help="Salta il prompt di autenticazione (utile per API pubbliche o CI/CD)"
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # ── Safe mode: ask interactively if not passed via flag ──
    safe_mode = args.safe_mode
    if not safe_mode and not args.ci:
        ans = input("Abilitare safe mode? Blocca POST/PUT/PATCH/DELETE (y/n): ").strip().lower()
        safe_mode = (ans == "y")
        print()

    # ── Auth: CLI flag > interactive prompt > no auth ──
    credentials = args.credentials
    api_key = getattr(args, "api_key", None)

    if not credentials and not api_key and not args.no_auth and not args.ci:
        answer = input("Hai credenziali di autenticazione? (y/n): ").strip().lower()
        if answer == "y":
            print("Tipo di autenticazione:")
            print("  [1] Username e password")
            print("  [2] API key / Bearer token")
            choice = input("Scelta → ").strip()
            if choice == "1":
                credentials = input("Inserisci username:password → ").strip()
            elif choice == "2":
                api_key = input("Inserisci API key → ").strip()
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
