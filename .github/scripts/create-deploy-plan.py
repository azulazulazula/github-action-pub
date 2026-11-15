#!/usr/bin/env python3
"""Create an ordered deploy-plan.json from changed paths and dependency.yml."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

MANIFEST_PATH = Path(".github/deploy/dependency.yml")


def changed_paths(before: str, after: str) -> list[str]:
    if re.fullmatch(r"0+", before or ""):
        command = ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", after]
    else:
        command = ["git", "diff", "--name-only", before, after]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line]


def load_resources(path: Path) -> dict[str, dict[str, Any]]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error

    resources = document.get("resources") if isinstance(document, dict) else None
    if not isinstance(resources, dict) or not resources:
        raise ValueError(f"{path} must contain a non-empty 'resources' mapping")

    for name, definition in resources.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            raise ValueError("Resource names must map to resource definition objects")

        paths = definition.get("paths")
        dependencies = definition.get("depends_on")
        workflow = definition.get("workflow")
        template = definition.get("template")

        if not isinstance(paths, list) or not paths or not all(isinstance(item, str) for item in paths):
            raise ValueError(f"'{name}.paths' must be a non-empty list of path patterns")
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise ValueError(f"'{name}.depends_on' must be a list of resource names")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError(f"Duplicate dependency listed for '{name}'")
        if not isinstance(workflow, str) or not workflow.startswith(".github/workflows/"):
            raise ValueError(f"'{name}.workflow' must point to a workflow under .github/workflows/")
        if template is not None and not isinstance(template, str):
            raise ValueError(f"'{name}.template' must be a path string or null")

    for name, definition in resources.items():
        unknown = sorted(set(definition["depends_on"]) - set(resources))
        if unknown:
            raise ValueError(f"Unknown dependencies for '{name}': {unknown}")

    return resources


def topological_order(resources: dict[str, dict[str, Any]]) -> list[str]:
    pending = list(resources)
    completed: set[str] = set()
    result: list[str] = []

    while pending:
        ready = next(
            (name for name in pending if set(resources[name]["depends_on"]) <= completed),
            None,
        )
        if ready is None:
            raise ValueError(f"Dependency cycle detected in {MANIFEST_PATH}")
        pending.remove(ready)
        completed.add(ready)
        result.append(ready)

    return result


def include_prerequisites(
    resources: dict[str, dict[str, Any]], requested: set[str]
) -> set[str]:
    selected: set[str] = set()

    def include(resource: str) -> None:
        if resource in selected:
            return
        selected.add(resource)
        for dependency in resources[resource]["depends_on"]:
            include(dependency)

    for resource in requested:
        include(resource)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    resources = load_resources(MANIFEST_PATH)
    ordered_all = topological_order(resources)
    files = changed_paths(args.before, args.after)

    changed = {
        name
        for name, definition in resources.items()
        if any(
            fnmatch.fnmatchcase(path, pattern)
            for path in files
            for pattern in definition["paths"]
        )
    }
    selected = include_prerequisites(resources, changed)
    ordered = [name for name in ordered_all if name in selected]

    steps = []
    for name in ordered:
        definition = resources[name]
        steps.append(
            {
                "resource": name,
                "workflow": definition["workflow"],
                "template": definition.get("template"),
                "request_id": f"{args.run_id}-{args.run_attempt}-{name}",
                "status": "pending",
            }
        )

    plan = {
        "schema_version": 1,
        "source_commit": args.after,
        "changed_resources": [name for name in ordered_all if name in changed],
        "deploy_order": ordered,
        "steps": steps,
        "status": "pending" if steps else "no_changes",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f"Failed to create deploy plan: {error}", file=sys.stderr)
        raise SystemExit(1)
