"""
agent.py — The agent loop for API Sentinel.

Uses litellm: swap models by changing LLM_MODEL in .env — no code changes needed.
"""

import os
import sys
import json
from litellm import completion
from litellm.exceptions import APIError
from dotenv import load_dotenv, find_dotenv
from tools import TOOL_DEFINITIONS, execute_tool

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv(find_dotenv())

MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4-5")
MAX_TURNS = 60
SAFE_MODE_BLOCKED = {"POST", "PUT", "PATCH", "DELETE"}

SYSTEM_PROMPT = """You are API Sentinel, an expert API testing and debugging agent.

Your workflow:
1. Call fetch_spec to download and parse the OpenAPI specification
2. Identify the base URL (from spec servers or any --base-url override in the prompt)

3. AUTHENTICATION (only if credentials were provided in the prompt):
   - Find the authentication endpoint in the spec (e.g. /auth/login, /auth/token, /oauth/token,
     /token, /users/login, /api/login)
   - Call it FIRST with the provided credentials
   - Extract the Bearer token (look for: token, access_token, data.token, jwt, id_token, bearer)
   - Add "Authorization: Bearer <token>" to ALL subsequent http_request calls
   - If auth fails, note it clearly and continue testing what you can without auth

4. ENVIRONMENT COMPARISON (only if two base URLs are provided in the prompt):
   - Test every endpoint against BOTH URLs
   - Compare status codes, response times, and response structure
   - Highlight discrepancies in the report's Comparison section

5. Test endpoints systematically with http_request:
   - Prioritize GET endpoints (safe, no side effects)
   - For POST/PUT/PATCH: build realistic payloads from the schema's example values
   - Skip endpoints that require complex auth you cannot obtain
   - For path parameters (e.g. /pets/{id}), use a realistic placeholder like "1"
   - If a tool returns {"blocked": "safe_mode"}, mark endpoint as "skipped (safe mode)"

6. Diagnose every response:
   - 2xx: note what it returns, flag structure mismatches vs spec
   - 3xx: note redirect destination
   - 4xx: identify exact issue + concrete fix
   - 5xx: flag as server error
   - network error: diagnose connectivity/DNS/SSL issue

7. Call save_report with the full Markdown report (filename WITHOUT extension)

8. Call finish_run as the VERY LAST step with the final counts

--- REPORT FORMAT ---

Write a proper technical document, not a table dump:

# API Sentinel Report — {API title}
**Date:** {date} | **Base URL:** {url} | **Spec:** {spec source}

## Overview
3-5 sentences describing the API, what it does, how many endpoints were tested,
and overall impression. Write like a human engineer who just explored it.

## Health Summary
Overall verdict: Healthy / Degraded / Down — one sentence why.
- X of Y endpoints reachable
- X passed / X failed / X skipped (reason for skipped)

## Endpoint Results
| Endpoint | Method | Status | Latency | Assessment |
|----------|--------|--------|---------|------------|

After the table, 2-4 sentences on patterns noticed (response times, error consistency, surprises).

## Environment Comparison (only if two URLs were tested)
| Endpoint | Method | Primary Status | Compare Status | Primary Latency | Compare Latency | Diff |
|----------|--------|---------------|----------------|-----------------|-----------------|------|
Then a paragraph summarizing the key differences found.

## Issues & Findings
For each issue, a short paragraph: symptom → diagnosis → concrete fix.
Group by severity: Critical / Warning / Info.
If no issues, say so and explain what makes the API well-behaved.

## Recommendations
2-4 actionable recommendations. Reference actual endpoint names and status codes.

Tone: technical but readable. Senior dev reads the summary, carefully reads Issues.
No fluff, complete sentences.
"""


def run_agent(
    spec_source: str,
    base_url: str = None,
    compare_url: str = None,
    verbose: bool = False,
    credentials: str = None,
    api_key: str = None,
    safe_mode: bool = False,
) -> dict:
    """Runs the API Sentinel agent. Returns a dict with run results (used for CI/CD exit code)."""

    # ── Build the initial prompt ──
    prompt = f"Analyze and test this API.\nSpec: {spec_source}"

    if base_url:
        prompt += f"\nPrimary base URL: {base_url}"
    if compare_url:
        prompt += f"\nComparison base URL: {compare_url}"
        prompt += "\nTest every endpoint against BOTH URLs and compare results."

    if credentials:
        prompt += f"\nCredentials (username:password): {credentials}"
        prompt += "\nFind the auth endpoint, call it FIRST, get the Bearer token, use it everywhere."
    elif api_key:
        prompt += f"\nAPI key: {api_key}"
        prompt += "\nAdd 'Authorization: Bearer <api_key>' to ALL requests."
    else:
        prompt += "\nNo credentials. If you get 401/403, note it and move on."

    if safe_mode:
        prompt += "\nSAFE MODE ACTIVE: POST/PUT/PATCH/DELETE are blocked at tool level. Mark them as 'skipped (safe mode)'."

    prompt += "\nTest all reachable endpoints, save the report, then call finish_run with final counts."

    # ── Startup output ──
    print(f"\n🛡️  API Sentinel starting...")
    print(f"📋 Spec:    {spec_source}")
    print(f"🤖 Model:   {MODEL}")
    if base_url:
        print(f"🌐 Primary: {base_url}")
    if compare_url:
        print(f"🔀 Compare: {compare_url}")
    if credentials:
        user = credentials.split(":")[0]
        print(f"🔑 Auth:    username/password ({user}:****)")
    elif api_key:
        masked = "****" + api_key[-4:] if len(api_key) > 4 else "****"
        print(f"🔑 Auth:    API key ({masked})")
    else:
        print(f"🔓 Auth:    none")
    print(f"{'🔒' if safe_mode else '🔓'} Safe mode: {'ON' if safe_mode else 'OFF'}")
    print()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    run_result = {}  # populated when the agent calls finish_run

    for turn in range(MAX_TURNS):
        try:
            response = completion(
                model=MODEL,
                max_tokens=8096,
                tools=TOOL_DEFINITIONS,
                messages=messages,
                num_retries=3,
            )
        except APIError as e:
            print(f"\n❌ API error ({MODEL}): {e}")
            print("   Likely a rate limit or insufficient credits. Wait a minute and try again.")
            return run_result

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        messages.append(msg.model_dump())

        # ── Max tokens hit mid-run ──
        if finish_reason == "length":
            print(f"\n⚠️  Max tokens reached at turn {turn + 1}. Stopping early — report may be incomplete.")
            break

        # ── Agent called tools ──
        if finish_reason == "tool_calls" and msg.tool_calls:
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    print(f"   ⚠️  Malformed tool arguments for '{name}': {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"error": f"Invalid JSON arguments: {e}"}),
                    })
                    continue

                _print_tool_call(name, args)

                # ── SAFE MODE: block dangerous methods before they execute ──
                if safe_mode and name == "http_request":
                    method = args.get("method", "").upper()
                    if method in SAFE_MODE_BLOCKED:
                        result_str = json.dumps({
                            "blocked": "safe_mode",
                            "method": method,
                            "url": args.get("url", ""),
                            "reason": f"{method} blocked in safe mode (read-only)"
                        })
                        print(f"   ↳ 🔒 Blocked ({method}) — safe mode active")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_str,
                        })
                        continue

                result_str = execute_tool(name, args)
                _print_tool_result(name, result_str, verbose)

                # Capture finish_run data for CI/CD exit code
                if name == "finish_run":
                    run_result = args.copy()

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str,
                })

            continue

        # ── Agent finished ──
        if msg.content:
            print("\n" + msg.content)
        break

    else:
        print(f"\n⚠️  Reached max turns ({MAX_TURNS}). Stopping.")

    print("\n✅ Done.")
    return run_result


# ─────────────────────────────────────────────
# Helper: human-readable output during run
# ─────────────────────────────────────────────

def _print_tool_call(name: str, inputs: dict):
    if name == "fetch_spec":
        print(f"📥 Fetching spec: {inputs.get('source', '')}")
    elif name == "http_request":
        method = inputs.get("method", "GET")
        url = inputs.get("url", "")
        print(f"🔍 {method:<7} {url}")
    elif name == "save_report":
        print(f"💾 Saving report: {inputs.get('filename', 'report')}")
    elif name == "finish_run":
        p = inputs.get("passed", 0)
        f = inputs.get("failed", 0)
        s = inputs.get("skipped", 0)
        c = inputs.get("critical_issues", 0)
        print(f"🏁 Run complete: {p} passed / {f} failed / {s} skipped / {c} critical")


def _print_tool_result(name: str, result_str: str, verbose: bool):
    if verbose:
        preview = result_str[:400]
        print(f"   ↳ {preview}{'...' if len(result_str) > 400 else ''}")
        return

    try:
        data = json.loads(result_str)
        if name == "http_request":
            if "error" in data:
                print(f"   ↳ ❌ {data['error']}: {data.get('message', '')}")
            else:
                code = data.get("status_code", "?")
                ms = data.get("elapsed_ms", "?")
                icon = "✅" if str(code).startswith("2") else "⚠️" if str(code).startswith("4") else "❌"
                print(f"   ↳ {icon} {code} ({ms}ms)")
        elif name == "fetch_spec":
            if "error" in data:
                print(f"   ↳ ❌ {data['error']}")
            else:
                print(f"   ↳ ✅ {data.get('title', '?')} — {data.get('endpoint_count', 0)} endpoints found")
        elif name == "save_report":
            if "saved_md" in data:
                size = data.get("size_bytes", 0)
                print(f"   ↳ ✅ {data['saved_md']} + {data['saved_html']} ({size:,} bytes)")
        elif name == "finish_run":
            status = data.get("status", "?")
            icon = "✅" if status == "healthy" else "⚠️"
            print(f"   ↳ {icon} Status: {status}")
    except Exception:
        pass
