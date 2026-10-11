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
from distribution_contract import (
    validate_distribution,
    validate_distribution_manifest,
    validate_distribution_publication,
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
    distribution = read_json(ROOT / "distribution" / "catalog.json")
    validate_distribution(distribution, energy_catalog=catalog, sources=sources)
    validate_distribution_publication(
        read_json(ROOT / "distribution" / "publication.json")
    )
    distribution_manifest = validate_distribution_manifest(ROOT / "distribution")
    print("CATALOG_VALIDATION=PASS")
    print(f"DATA_VERSION={manifest['data_version']}")
    print(f"RECORDS={len(catalog['records'])}")
    print(f"DISTRIBUTION_DATA_VERSION={distribution_manifest['data_version']}")
    print(f"DISTRIBUTION_RECORDS={len(distribution['records'])}")


if __name__ == "__main__":
    main()
