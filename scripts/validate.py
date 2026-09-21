"""Run engineering validation and write evidence/validation-summary.json.

Runs `pytest tests/validation` — the known-answer/fixture/variance-
decomposition suite (NIST worked examples for I-MR/EWMA/CUSUM/capability,
a hand-verified fixture for Xbar-R, and the T1 variance-decomposition
checks) — as the one mandatory check. tests/unit is intentionally NOT part
of this check: `make test` already gates every PR on tests/unit, and this
script's job is specifically the engineering-validation layer Overview
section 3.2 describes, not a second copy of the fast test suite.

Still not covered by this check (until Gate T4 lands): no case study has
been run yet, so no run_id/config_hash/random_seed here refers to a real
case — this script validates the underlying methods, not a case result.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("jsonschema not installed — run `make setup` first.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "evidence" / "validation-summary.schema.json"
OUTPUT_PATH = ROOT / "evidence" / "validation-summary.json"


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def run_validation_suite() -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/validation", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    summary_line = next(
        (
            line
            for line in reversed(result.stdout.splitlines())
            if "passed" in line or "failed" in line
        ),
        result.stdout.strip()[-200:],
    )
    return result.returncode == 0, summary_line


def build_summary() -> dict:
    passed, detail = run_validation_suite()
    return {
        "run_id": f"validate-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "app_version": "0.0.0",
        "checks": [
            {
                "name": "tests_validation_suite",
                "mandatory": True,
                "passed": passed,
                "detail": f"pytest tests/validation: {detail}",
            }
        ],
        "warnings": [
            (
                "random_seed has NOT been recorded — no case run exists yet "
                "(Gate T4); see Overview §3.3."
            ),
        ],
    }


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    summary = build_summary()
    jsonschema.validate(instance=summary, schema=schema)

    OUTPUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")

    mandatory_failures = [c for c in summary["checks"] if c["mandatory"] and not c["passed"]]
    if mandatory_failures:
        print(f"FAILED mandatory checks: {mandatory_failures}", file=sys.stderr)
        return 1

    print("all mandatory checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
