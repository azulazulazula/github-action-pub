#!/usr/bin/env python3
"""depend.txtと変更ファイルから実行対象の計画を作成する。"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


SERVICE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def parse_manifest(path: Path) -> list[dict[str, object]]:
    resources: list[dict[str, object]] = []
    seen: set[str] = set()

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        columns = [column.strip() for column in line.split("|")]
        if len(columns) != 3:
            raise ValueError(f"{path}:{line_number}: expected SERVICE | WATCH_PATHS | DEPENDS_ON")

        service, paths_text, dependencies_text = columns
        if not SERVICE_NAME.fullmatch(service):
            raise ValueError(f"{path}:{line_number}: invalid service name {service!r}")
        if service in seen:
            raise ValueError(f"{path}:{line_number}: duplicate service {service!r}")

        watch_paths = [item.strip() for item in paths_text.split(",") if item.strip()]
        if not watch_paths:
            raise ValueError(f"{path}:{line_number}: at least one watch path is required")

        dependencies = (
            []
            if dependencies_text in ("", "-")
            else [item.strip() for item in dependencies_text.split(",") if item.strip()]
        )
        if service in dependencies:
            raise ValueError(f"{path}:{line_number}: a service cannot depend on itself")

        resources.append(
            {
                "service": service,
                "watch_paths": watch_paths,
                "dependencies": dependencies,
                "order": len(resources),
            }
        )
        seen.add(service)

    if not resources:
        raise ValueError(f"{path}: no resource definitions found")

    known = {resource["service"] for resource in resources}
    for resource in resources:
        for dependency in resource["dependencies"]:
            if dependency not in known:
                raise ValueError(
                    f"{resource['service']}: unknown dependency {dependency!r}"
                )

    return resources


def topological_order(resources: list[dict[str, object]], selected: set[str]) -> list[str]:
    by_name = {str(resource["service"]): resource for resource in resources}
    pending = set(selected)
    result: list[str] = []

    while pending:
        ready = [
            service
            for service in pending
            if not (set(by_name[service]["dependencies"]) & pending)
        ]
        if not ready:
            raise ValueError("dependency cycle detected in selected resources")

        ready.sort(key=lambda service: int(by_name[service]["order"]))
        service = ready[0]
        result.append(service)
        pending.remove(service)

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        resources = parse_manifest(args.manifest)
        changed_paths = [
            line.strip()
            for line in args.changed_files.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        directly_changed = {
            str(resource["service"])
            for resource in resources
            if any(
                fnmatch.fnmatchcase(changed_path, pattern)
                for changed_path in changed_paths
                for pattern in resource["watch_paths"]
            )
        }

        # 依存先が変更された場合、そのリソースを利用する側も実行対象に加える。
        selected = set(directly_changed)
        while True:
            newly_selected = {
                str(resource["service"])
                for resource in resources
                if str(resource["service"]) not in selected
                and set(resource["dependencies"]) & selected
            }
            if not newly_selected:
                break
            selected.update(newly_selected)

        plan = {
            "changed_paths": changed_paths,
            "changed_services": [
                str(resource["service"])
                for resource in resources
                if str(resource["service"]) in directly_changed
            ],
            "execution_order": topological_order(resources, selected),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(plan, indent=2))
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
