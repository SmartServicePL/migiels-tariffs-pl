"""Build immutable objects first and the public manifest second."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from catalog_contract import (
    ContractError,
    canonical_bytes,
    read_json,
    validate_catalog,
    validate_manifest,
    validate_publication,
)

ROOT = Path(__file__).resolve().parents[1]


def pretty(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def build(*, check: bool) -> None:
    catalog = read_json(ROOT / "catalog" / "catalog.json")
    publication = read_json(ROOT / "catalog" / "publication.json")
    validate_catalog(catalog)
    validate_publication(publication)
    if catalog["data_version"] != publication["data_version"]:
        raise ContractError("catalog and publication data versions differ")

    payload = canonical_bytes(catalog)
    checksum = hashlib.sha256(payload).hexdigest()
    relative_path = f"objects/catalog-{checksum}.json"
    object_path = ROOT / relative_path
    manifest = {
        "schema_version": 1,
        "data_version": catalog["data_version"],
        "published_at": publication["published_at"],
        "objects": [
            {
                "id": publication["object_id"],
                "path": relative_path,
                "sha256": checksum,
                "size": len(payload),
            }
        ],
    }
    manifest_bytes = pretty(manifest)
    manifest_path = ROOT / "manifest.json"

    if manifest_path.exists():
        previous = read_json(manifest_path)
        if (
            previous.get("data_version") == manifest["data_version"]
            and previous != manifest
        ):
            raise ContractError("one data version cannot be rewritten in place")
        previous_ids = {
            item["id"]
            for item in previous.get("objects", [])
            if isinstance(item, dict) and "id" in item
        }
        incoming_ids = {item["id"] for item in manifest["objects"]}
        if not previous_ids <= incoming_ids:
            raise ContractError("historical manifest object identifier was removed")

    changes: list[str] = []
    if not object_path.exists():
        changes.append(relative_path)
        if not check:
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(payload)
    elif object_path.read_bytes() != payload:
        raise ContractError("immutable catalog object was rewritten")

    if not manifest_path.exists() or manifest_path.read_bytes() != manifest_bytes:
        changes.append("manifest.json")
        if not check:
            manifest_path.write_bytes(manifest_bytes)

    if check and changes:
        raise ContractError("generated catalog is stale: " + ", ".join(changes))
    validate_manifest(ROOT)
    print(f"CATALOG_DATA_VERSION={manifest['data_version']}")
    print(f"CATALOG_OBJECT_SHA256={checksum}")
    print(f"CATALOG_BUILD_CHANGED={'true' if changes else 'false'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    build(check=arguments.check)
