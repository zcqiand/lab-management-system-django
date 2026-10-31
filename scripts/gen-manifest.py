#!/usr/bin/env python
"""OpenAPI -> API manifest 生成器（routes parity 的 SSOT，rails/laravel 同构）。

读 shared 仓 emit 的 openapi.yaml，产 generated/api_manifest.json：
  { "schema": 1, "operations": [ { operationId, method, path, tag,
      requestSchema, responseSchema, requiredFields } ] }

确定性产物（L4.codegen.idempotent 字节比对，laravel/rails 同约束）：
- 键序固定；operations 按 [tag, operationId] 排序；无时间戳；LF；UTF-8。

用法：python scripts/gen-manifest.py <openapi.yaml> [--out generated]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
SCHEMA = 1


def _ref_name(ref: object) -> str | None:
    """#/components/schemas/X -> X；非 ref 返回 None。"""
    if not isinstance(ref, str) or not ref.startswith("#/components/schemas/"):
        return None
    return ref.rsplit("/", 1)[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("openapi")
    ap.add_argument("--out", default="generated")
    args = ap.parse_args()

    spec = yaml.load(Path(args.openapi).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    schemas = spec.get("components", {}).get("schemas", {})

    operations = []
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            request_schema = None
            required_fields: list[str] = []
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            req_name = _ref_name(body.get("schema", {}).get("$ref"))
            if req_name:
                request_schema = req_name
                required_fields = sorted(schemas.get(req_name, {}).get("required", []))
            resp = op.get("responses", {}).get("200", {}).get("content", {}).get(
                "application/json", {}
            )
            response_schema = _ref_name(resp.get("schema", {}).get("$ref"))
            operations.append(
                {
                    "operationId": op["operationId"],
                    "method": method.upper(),
                    "path": path,
                    "tag": op.get("tags", [None])[0],
                    "requestSchema": request_schema,
                    "responseSchema": response_schema,
                    "requiredFields": required_fields,
                }
            )

    operations.sort(key=lambda o: (o["tag"] or "", o["operationId"]))
    manifest = {"schema": SCHEMA, "operations": operations}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "api_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[gen-manifest] {len(operations)} operations -> {out / 'api_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
