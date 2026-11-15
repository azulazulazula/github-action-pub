#!/usr/bin/env python3
"""Build an ordered deployment plan from changed paths and dependencies.yaml."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

RESOURCE_FILES = {
    "vpc": {
        "workflow": ".github/workflows/create-vpc.yml",
        "template": ".github/workflows/cfm/vpc/vpc.yml",
    },
    "s3": {
        "workflow": ".github/workflows/create-s3.yml",
        "template": ".github/workflows/cfm/s3/s3.yml",
    },
    "ec2": {
        "workflow": ".github/workflows/deploy-ec2.yml",
        "template": ".github/workflows/cfm/ec2.yml",
    },
    "ecs": {
        "workflow": ".github/workflows/deploy-ecs-hello-world.yml",
        "template": None,
    },
}


def changed_paths(before: str, after: str) -> list[str]:
    if re.fullmatch(r"0+", before or ""):
        command = ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", after]
    else:
        command = ["git", "diff", "--name-only", before, after]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line]


def resource_for_path(path: str) -> str | None:
    if path.startswith(".github/workflows/cfm/vpc/"):
        return "vpc"
    if path == ".github/workflows/cfm/ec2.yml":
        return "ec2"
    if path.startswith(".github/workflows/cfm/s3/"):
        return "s3"
    if path == "Dockerfile" or path.startswith("src/") or path.startswith(".github/ecs/"):
        return "ecs"
    return None


def load_graph(path: Path) -> dict[str, list[str]]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error

    if not isinstance(document, dict) or not isinstance(document.get("dependencies"), dict):
        raise ValueError(f"{path} must contain a 'dependencies' mapping")

    graph = document["dependencies"]
    if set(graph) != set(RESOURCE_FILES):
        missing = sorted(set(RESOURCE_FILES) - set(graph))
        unknown = sorted(set(graph) - set(RESOURCE_FILES))
        raise ValueError(f"Invalid resources in {path}; missing={missing}, unsupported={unknown}")

    for resource, dependencies in graph.items():
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise ValueError(f"Dependencies for '{resource}' must be a list of resource names")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError(f"Duplicate dependency listed for '{resource}'")
        unknown = sorted(set(dependencies) - set(graph))
        if unknown:
            raise ValueError(f"Unknown dependencies for '{resource}': {unknown}")

    return graph


def topological_order(graph: dict[str, list[str]]) -> list[str]:
    pending = list(graph)
    completed: set[str] = set()
    result: list[str] = []

    while pending:
        ready = next((name for name in pending if set(graph[name]) <= completed), None)
        if ready is None:
            raise ValueError("Dependency cycle detected in dependencies.yaml")
        pending.remove(ready)
        completed.add(ready)
        result.append(ready)

    return result


def include_prerequisites(graph: dict[str, list[str]], requested: set[str]) -> set[str]:
    selected: set[str] = set()

    def include(resource: str) -> None:
        if resource in selected:
            return
        selected.add(resource)
        for dependency in graph[resource]:
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

    graph = load_graph(Path(".github/deploy/dependencies.yaml"))
    ordered_all = topological_order(graph)

    changed = {
        resource
        for path in changed_paths(args.before, args.after)
        if (resource := resource_for_path(path)) is not None
    }
    selected = include_prerequisites(graph, changed)
    ordered = [resource for resource in ordered_all if resource in selected]

    steps = []
    for resource in ordered:
        definition = RESOURCE_FILES[resource]
        steps.append(
            {
                "resource": resource,
                "workflow": definition["workflow"],
                "template": definition["template"],
                "request_id": f"{args.run_id}-{args.run_attempt}-{resource}",
                "status": "pending",
            }
        )

    plan = {
        "schema_version": 1,
        "source_commit": args.after,
        "changed_resources": [resource for resource in ordered_all if resource in changed],
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
