"""Build the distribution object first and its own manifest second.

The distribution catalog lives under ``distribution/`` with a separate
manifest: App versions that read only ``manifest.json`` (energy prices) never
see it, so publishing it cannot break an installed App.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from build_catalog import pretty
from catalog_contract import ContractError, canonical_bytes, read_json
from distribution_contract import (
    validate_distribution,
    validate_distribution_manifest,
    validate_distribution_publication,
)

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "distribution"


def build(*, check: bool) -> None:
    catalog = read_json(DIRECTORY / "catalog.json")
    publication = read_json(DIRECTORY / "publication.json")
    validate_distribution(
        catalog,
        energy_catalog=read_json(ROOT / "catalog" / "catalog.json"),
        sources=read_json(ROOT / "catalog" / "sources.json"),
    )
    validate_distribution_publication(publication)
    if catalog["data_version"] != publication["data_version"]:
        raise ContractError("distribution and publication data versions differ")
    payload = canonical_bytes(catalog)
    checksum = hashlib.sha256(payload).hexdigest()
    relative_path = f"objects/distribution-{checksum}.json"
    object_path = DIRECTORY / relative_path
    manifest = {
        "schema_version": catalog["schema_version"],
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
    manifest_path = DIRECTORY / "manifest.json"
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
        if not previous_ids <= {item["id"] for item in manifest["objects"]}:
            raise ContractError("historical manifest object identifier was removed")
    changes: list[str] = []
    if not object_path.exists():
        changes.append(f"distribution/{relative_path}")
        if not check:
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(payload)
    elif object_path.read_bytes() != payload:
        raise ContractError("immutable distribution object was rewritten")
    if not manifest_path.exists() or manifest_path.read_bytes() != manifest_bytes:
        changes.append("distribution/manifest.json")
        if not check:
            manifest_path.write_bytes(manifest_bytes)
    if check and changes:
        raise ContractError("generated distribution catalog is stale: " + ", ".join(changes))
    validate_distribution_manifest(DIRECTORY)
    print(f"DISTRIBUTION_DATA_VERSION={manifest['data_version']}")
    print(f"DISTRIBUTION_OBJECT_SHA256={checksum}")
    print(f"DISTRIBUTION_BUILD_CHANGED={'true' if changes else 'false'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    build(check=arguments.check)
