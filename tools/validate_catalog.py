"""Validate all authored and published catalog documents."""

from __future__ import annotations

from pathlib import Path

from catalog_contract import (
    read_json,
    validate_catalog,
    validate_manifest,
    validate_publication,
    validate_sources,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    catalog = read_json(ROOT / "catalog" / "catalog.json")
    publication = read_json(ROOT / "catalog" / "publication.json")
    sources = read_json(ROOT / "catalog" / "sources.json")
    validate_catalog(catalog)
    validate_publication(publication)
    validate_sources(sources)
    manifest = validate_manifest(ROOT)
    covered = {
        identity for source in sources["sources"] for identity in source["covers"]
    }
    expected = {
        f"{record['price_list']['id']}:{record['price_list']['revision']}"
        for record in catalog["records"]
    }
    if covered != expected:
        raise RuntimeError("source coverage and catalog records differ")
    print("CATALOG_VALIDATION=PASS")
    print(f"DATA_VERSION={manifest['data_version']}")
    print(f"RECORDS={len(catalog['records'])}")


if __name__ == "__main__":
    main()
