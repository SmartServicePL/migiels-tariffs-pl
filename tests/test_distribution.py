from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from catalog_contract import ContractError, read_json  # noqa: E402
from distribution_contract import (  # noqa: E402
    validate_distribution,
    validate_distribution_manifest,
)


class DistributionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.distribution = read_json(ROOT / "distribution" / "catalog.json")
        self.energy = read_json(ROOT / "catalog" / "catalog.json")
        self.sources = read_json(ROOT / "catalog" / "sources.json")

    def validate(self, document: dict) -> None:
        validate_distribution(document, energy_catalog=self.energy, sources=self.sources)

    def record(self, osd: str, group: str) -> dict:
        return next(
            item
            for item in self.distribution["records"]
            if item["osd"]["id"] == osd and item["tariff_group"] == group
        )

    def test_published_distribution_and_manifest_are_valid(self) -> None:
        self.validate(self.distribution)
        manifest = validate_distribution_manifest(ROOT / "distribution")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(len(self.distribution["records"]), 14)

    def test_every_energy_profile_of_the_four_dsos_has_distribution(self) -> None:
        covered = {item["schedule_profile_id"] for item in self.distribution["records"]}
        expected = {
            record["schedule"]["profile_id"]
            for record in self.energy["records"]
            if record["osd_ids"][0] != "stoen-operator"
        }
        self.assertEqual(covered, expected)

    def test_rates_read_from_the_official_tables(self) -> None:
        energa = self.record("energa-operator", "G12")
        self.assertEqual(
            {item["zone_id"]: item["price"] for item in energa["network_variable"]},
            {"dzienna": "0.3844", "nocna": "0.0827"},
        )
        self.assertEqual(energa["network_fixed_monthly"], {"single_phase": "14.35", "three_phase": "20.17"})
        pge = self.record("pge-dystrybucja", "G12w")
        self.assertEqual(pge["network_fixed_monthly"]["single_phase"], "9.15")
        tauron = self.record("tauron-dystrybucja", "G13")
        self.assertEqual(len(tauron["network_variable"]), 3)
        for record in self.distribution["records"]:
            self.assertEqual(record["tax_treatment"], "net")
            self.assertEqual(record["vat_rate"], "0.23")
            self.assertEqual(record["transition_monthly"], [])

    def test_zones_must_match_the_energy_profile(self) -> None:
        changed = copy.deepcopy(self.distribution)
        changed["records"][1]["network_variable"][0]["zone_id"] = "szczytowa"
        with self.assertRaises(ContractError):
            self.validate(changed)

    def test_unpinned_source_and_unknown_fields_fail_closed(self) -> None:
        changed = copy.deepcopy(self.distribution)
        changed["records"][0]["source_documents"] = ["https://example.com/taryfa.pdf"]
        with self.assertRaises(ContractError):
            self.validate(changed)
        changed = copy.deepcopy(self.distribution)
        changed["records"][0]["private_note"] = "x"
        with self.assertRaises(ContractError):
            self.validate(changed)

    def test_gross_rates_and_broken_brackets_are_rejected(self) -> None:
        changed = copy.deepcopy(self.distribution)
        changed["records"][0]["tax_treatment"] = "gross"
        with self.assertRaises(ContractError):
            self.validate(changed)
        changed = copy.deepcopy(self.distribution)
        changed["records"][0]["capacity_monthly"][1]["up_to_kwh"] = "400"
        with self.assertRaises(ContractError):
            self.validate(changed)


if __name__ == "__main__":
    unittest.main()
