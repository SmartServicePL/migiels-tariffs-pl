from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from catalog_contract import ContractError, read_json, validate_catalog  # noqa: E402
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
        self.assertEqual(len(self.distribution["records"]), 17)

    def test_every_energy_profile_has_distribution_except_stoen_g12as(self) -> None:
        # Stoen G12as: the night network rate depends on the consumption of the
        # same period a year earlier (pkt 7.5, footnotes 2 and 3) - one rate per
        # zone cannot express it, so the record is left out on purpose.
        covered = {item["schedule_profile_id"] for item in self.distribution["records"]}
        expected = {
            record["schedule"]["profile_id"]
            for record in self.energy["records"]
            if record["tariff_group"] != "G12as"
        }
        self.assertEqual(covered, expected)
        self.assertNotIn("stoen-operator.g12as.2026", covered)

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


    def test_stoen_rates_read_from_the_official_table(self) -> None:
        """Biuletyn Branżowy URE nr 264 (4794), taryfa Stoen Operator pkt 7.5."""

        expected = {
            "G11": {"calodobowa": "0.2342"},
            "G12": {"dzienna": "0.2545", "nocna": "0.0555"},
            "G12w": {"dzienna": "0.2570", "nocna": "0.1079"},
        }
        for group, variable in expected.items():
            record = self.record("stoen-operator", group)
            self.assertEqual(
                {item["zone_id"]: item["price"] for item in record["network_variable"]},
                variable,
            )
            self.assertEqual(
                record["network_fixed_monthly"],
                {"single_phase": "11.46", "three_phase": "18.53"},
            )
            self.assertEqual(
                [(item["period"], item["price"]) for item in record["subscription_monthly"]],
                [("1m", "2.88"), ("6m", "0.48"), ("12m", "0.24")],
            )
            self.assertEqual(record["quality_per_kwh"], "0.0331")
            self.assertEqual(record["oze_per_kwh"], "0.0073")
            self.assertEqual(record["cogeneration_per_kwh"], "0.0030")
            self.assertEqual(
                [item["price"] for item in record["capacity_monthly"]],
                ["4.29", "10.31", "17.18", "24.05"],
            )
            self.assertEqual(
                record["source_documents"],
                ["https://bip.ure.gov.pl/download/3/20339/StoenOperator.pdf"],
            )

    def test_g12e_and_g13s_are_not_published(self) -> None:
        # No seller in the catalog publishes a G12e or G13s energy price in a
        # tariff the catalog can hold, so neither group has a record.
        groups = {item["tariff_group"] for item in self.distribution["records"]}
        groups |= {item["tariff_group"] for item in self.energy["records"]}
        self.assertFalse(groups & {"G12e", "G13s"})

    def test_the_zone_model_expresses_seasonal_day_type_rates(self) -> None:
        """TAURON G13s (pkt 2.2.2a, 7.3): the variable network rate depends on
        the season and on the day type - one zone per (season, day type, zone)
        with season and weekday/holiday selectors; night is one zone."""

        energy = copy.deepcopy(self.energy)
        template = next(
            item for item in energy["records"] if item["tariff_group"] == "G13"
        )
        record = copy.deepcopy(template)
        record["tariff_group"] = "G13s"
        record["price_list"] = {"id": "test.g13s", "revision": 1}
        record["schedule"]["profile_id"] = "test.g13s"
        record["schedule"]["default_zone_id"] = "nocna"
        rules = []
        zones = [_zone("nocna")]
        for season, start, end, peaks, offpeak in (
            ("lato", [4, 1], [9, 30], (("07:00", "09:00"), ("17:00", "21:00")), ("09:00", "17:00")),
            ("zima", [10, 1], [3, 31], (("07:00", "10:00"), ("15:00", "21:00")), ("10:00", "15:00")),
        ):
            for day, selectors in (
                ("robocze", [([0, 1, 2, 3, 4], False)]),
                ("wolne", [([5, 6], None), (None, True)]),
            ):
                peak, off = f"{season}_{day}_szczyt", f"{season}_{day}_pozaszczyt"
                zones += [_zone(peak), _zone(off)]
                for weekdays, holiday in selectors:
                    for first, last in peaks:
                        rules.append(_rule(peak, first, last, weekdays, holiday, start, end))
                    rules.append(_rule(off, *offpeak, weekdays, holiday, start, end))
        record["zones"] = zones
        record["schedule"]["rules"] = rules
        energy["records"].append(record)
        validate_catalog(energy)
        distribution = copy.deepcopy(self.distribution)
        rates = copy.deepcopy(self.record("tauron-dystrybucja", "G13"))
        rates["tariff_group"] = "G13s"
        rates["schedule_profile_id"] = "test.g13s"
        rates["network_variable"] = [
            {"zone_id": zone["id"], "price": "0.1000"} for zone in zones
        ]
        distribution["records"].append(rates)
        self.validate_with(distribution, energy)
        rates["network_variable"].pop()
        with self.assertRaises(ContractError):
            self.validate_with(distribution, energy)

    def validate_with(self, distribution: dict, energy: dict) -> None:
        validate_distribution(distribution, energy_catalog=energy, sources=self.sources)


def _zone(zone_id: str) -> dict:
    return {
        "id": zone_id,
        "label": zone_id,
        "price": "0.5000",
        "semantic": "gross_active_energy",
        "tax_treatment": "gross",
        "unit": "PLN/kWh",
    }


def _rule(zone_id, start, end, weekdays, holiday, season_start, season_end) -> dict:  # type: ignore[no-untyped-def]
    return {
        "zone_id": zone_id,
        "start_local": start,
        "end_local": end,
        "weekdays": weekdays,
        "holiday": holiday,
        "season_start": season_start,
        "season_end": season_end,
        "dates": None,
        "priority": 10,
    }


if __name__ == "__main__":
    unittest.main()
