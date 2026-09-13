from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from catalog_contract import (
    ContractError,
    read_json,
    validate_catalog,
    validate_manifest,
    validate_sources,
)


class CatalogContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = read_json(ROOT / "catalog" / "catalog.json")
        self.sources = read_json(ROOT / "catalog" / "sources.json")

    def test_published_catalog_and_manifest_are_valid(self) -> None:
        validate_catalog(self.catalog)
        manifest = validate_manifest(ROOT)
        self.assertEqual(manifest["data_version"], "2026.09.13.1")
        record = self.catalog["records"][0]
        self.assertEqual(record["price_list"]["id"], "energa-obrot.taryfa-ure-2026.g11")
        self.assertEqual(record["zones"][0]["price"], "0.6172")
        self.assertEqual(record["zones"][0]["tax_treatment"], "gross")

    def test_sources_are_official_https_and_hash_pinned(self) -> None:
        validate_sources(self.sources)
        self.assertEqual(self.sources["allowed_hosts"], ["www.energa.pl"])

    def test_unknown_fields_fail_closed(self) -> None:
        changed = copy.deepcopy(self.catalog)
        changed["records"][0]["private_note"] = "must not be published"
        with self.assertRaises(ContractError):
            validate_catalog(changed)

    def test_dynamic_or_net_price_cannot_be_published(self) -> None:
        for field, value in (("semantic", "market_energy"), ("tax_treatment", "net")):
            changed = copy.deepcopy(self.catalog)
            changed["records"][0]["zones"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_catalog(changed)

    def test_manifest_rejects_missing_or_corrupted_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = read_json(ROOT / "manifest.json")
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                validate_manifest(root)


if __name__ == "__main__":
    unittest.main()
