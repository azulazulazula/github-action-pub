#!/usr/bin/env python3
"""Execute resource workflows in deploy-plan.json order."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def gh_api(*args: str) -> dict:
    try:
        result = subprocess.run(
            ["gh", "api", *args], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout).strip()
        command = " ".join(error.cmd)
        message = f"gh api command failed (exit {error.returncode}): {command}"
        if details:
            message += f"\n{details}"
        raise RuntimeError(message) from error
    return json.loads(result.stdout) if result.stdout.strip() else {}


def save(plan: dict, path: Path) -> None:
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def dispatch_and_wait(step: dict, ref: str, timeout: int) -> int:
    workflow = step["workflow"].rsplit("/", 1)[-1]
    request_id = step["request_id"]
    run_title = f"Deploy {step['resource']} request {request_id}"

    gh_api(
        "--method", "POST",
        f"repos/{__import__('os').environ['GITHUB_REPOSITORY']}/actions/workflows/{workflow}/dispatches",
        "-f", f"ref={ref}",
        "-f", f"inputs[request_id]={request_id}",
    )

    deadline = time.monotonic() + timeout
    run_id = None
    while time.monotonic() < deadline and run_id is None:
        runs = gh_api(
            "--method", "GET",
            f"repos/{__import__('os').environ['GITHUB_REPOSITORY']}/actions/workflows/{workflow}/runs",
            "-f", f"branch={ref}",
            "-f", "event=workflow_dispatch",
            "-f", "per_page=100",
        )
        matches = [
            run for run in runs.get("workflow_runs", [])
            if run.get("display_title") == run_title
        ]
        if matches:
            run_id = matches[0]["id"]
        else:
            time.sleep(5)

    if run_id is None:
        raise TimeoutError(f"Could not find dispatched run: {run_title}")

    while time.monotonic() < deadline:
        run = gh_api(
            f"repos/{__import__('os').environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}"
        )
        if run.get("status") == "completed":
            if run.get("conclusion") != "success":
                raise RuntimeError(
                    f"{step['resource']} workflow concluded: {run.get('conclusion')}"
                )
            return run_id
        time.sleep(10)

    raise TimeoutError(f"Timed out waiting for run {run_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or not isinstance(plan.get("steps"), list):
        raise ValueError("Unsupported or malformed deployment plan")

    for step in plan["steps"]:
        step["status"] = "in_progress"
        save(plan, args.plan)
        print(f"Deploying {step['resource']} using {step['workflow']}", flush=True)
        try:
            step["run_id"] = dispatch_and_wait(step, args.ref, args.timeout_seconds)
            step["status"] = "success"
        except Exception as error:
            step["status"] = "failure"
            step["error"] = str(error)
            plan["status"] = "failure"
            save(plan, args.plan)
            raise
        save(plan, args.plan)

    plan["status"] = "success" if plan["steps"] else "no_changes"
    save(plan, args.plan)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Deployment plan execution failed: {error}", file=sys.stderr)
        raise SystemExit(1)
