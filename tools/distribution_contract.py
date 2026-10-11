"""Strict contract for the public catalog of DSO distribution rates (G groups).

The distribution catalog is published next to the energy catalog under
``distribution/`` with its own manifest, so App versions that know only the
energy catalog never download it. Every record holds the net rates of one
tariff group of one DSO from the URE-approved tariff, the VAT rate stated
explicitly, and the schedule profile of the energy catalog whose zones the
variable network rate follows.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

from catalog_contract import (
    MAX_MANIFEST_BYTES,
    MAX_OBJECT_BYTES,
    ContractError,
    _exact,
    _https_url,
    _identifier,
    _integer,
    _invalid_number,
    _list,
    _object,
    _sha256,
    _text,
    _timestamp,
    read_json,
)

DISTRIBUTION_SCHEMA_VERSION = 1
MAX_RATE = Decimal("100")
RECORD_FIELDS = {
    "country",
    "currency",
    "osd",
    "tariff",
    "tariff_group",
    "schedule_profile_id",
    "tax_treatment",
    "vat_rate",
    "network_variable",
    "network_fixed_monthly",
    "quality_per_kwh",
    "oze_per_kwh",
    "cogeneration_per_kwh",
    "capacity_monthly",
    "transition_monthly",
    "subscription_monthly",
    "published_at",
    "retrieved_at",
    "verified_at",
    "valid_from",
    "valid_until",
    "source_documents",
    "source_reference",
    "group_change_rule",
    "verification_state",
    "declared_coverage",
}


def validate_distribution(
    root: dict[str, Any],
    *,
    energy_catalog: dict[str, Any] | None = None,
    sources: dict[str, Any] | None = None,
) -> None:
    """Validate one distribution catalog; with the energy catalog and the
    pinned sources also the cross-references."""

    _exact(root, {"schema_version", "data_version", "records"}, "distribution")
    _schema(root["schema_version"], "distribution")
    _identifier(root["data_version"], "distribution data version")
    records = _list(root["records"], "distribution records", allow_empty=False)
    identities: set[tuple[str, str, str, int]] = set()
    profiles: dict[str, set[str]] = {}
    if energy_catalog is not None:
        for record in energy_catalog["records"]:
            schedule = record["schedule"]
            zones = {zone["id"] for zone in record["zones"]}
            known = profiles.setdefault(schedule["profile_id"], zones)
            if known != zones:
                raise ContractError("one schedule profile has different zones")
    pinned: set[str] | None = None
    if sources is not None:
        pinned = {item["url"] for item in sources["sources"]}
    for index, value in enumerate(records):
        record = _object(value, f"distribution record {index}")
        _validate_record(record, identities, profiles if energy_catalog else None, pinned)


def _validate_record(
    record: dict[str, Any],
    identities: set[tuple[str, str, str, int]],
    profiles: dict[str, set[str]] | None,
    pinned: set[str] | None,
) -> None:
    _exact(record, RECORD_FIELDS, "distribution record")
    if record["country"] != "PL" or record["currency"] != "PLN":
        raise ContractError("distribution geography or currency is unsupported")
    osd = _object(record["osd"], "osd")
    _exact(osd, {"id", "name"}, "osd")
    osd_id = _identifier(osd["id"], "osd id")
    _text(osd["name"], "osd name")
    tariff = _object(record["tariff"], "tariff")
    _exact(tariff, {"id", "revision"}, "tariff")
    tariff_id = _identifier(tariff["id"], "tariff id")
    revision = _integer(tariff["revision"], "tariff revision")
    group = _text(record["tariff_group"], "tariff group")
    identity = (osd_id, group, tariff_id, revision)
    if revision < 1 or identity in identities:
        raise ContractError("distribution record identity is invalid or duplicated")
    identities.add(identity)
    profile_id = _identifier(record["schedule_profile_id"], "schedule profile id")
    if record["tax_treatment"] != "net":
        raise ContractError("distribution rates must be net with an explicit VAT")
    vat = _decimal(record["vat_rate"], "VAT rate")
    if not Decimal(0) < vat < Decimal(1):
        raise ContractError("VAT rate is invalid")
    variable = _list(record["network_variable"], "network variable", allow_empty=False)
    zone_ids: set[str] = set()
    for value in variable:
        item = _object(value, "network variable rate")
        _exact(item, {"zone_id", "price"}, "network variable rate")
        zone_id = _identifier(item["zone_id"], "zone id")
        if zone_id in zone_ids:
            raise ContractError("network variable zones are duplicated")
        zone_ids.add(zone_id)
        _rate(item["price"], "network variable rate")
    if profiles is not None:
        known = profiles.get(profile_id)
        if known is None:
            raise ContractError("distribution profile has no energy record")
        if known != zone_ids:
            raise ContractError("distribution zones differ from the energy profile")
    fixed = _object(record["network_fixed_monthly"], "network fixed")
    _exact(fixed, {"single_phase", "three_phase"}, "network fixed")
    for key in ("single_phase", "three_phase"):
        _rate(fixed[key], "network fixed rate")
    for key in ("quality_per_kwh", "oze_per_kwh", "cogeneration_per_kwh"):
        _rate(record[key], key)
    _brackets(record["capacity_monthly"], "capacity", allow_empty=False)
    _brackets(record["transition_monthly"], "transition", allow_empty=True)
    periods: set[str] = set()
    for value in _list(record["subscription_monthly"], "subscription", allow_empty=False):
        item = _object(value, "subscription rate")
        _exact(item, {"period", "label", "price"}, "subscription rate")
        period = _identifier(item["period"], "subscription period")
        if period in periods:
            raise ContractError("subscription periods are duplicated")
        periods.add(period)
        _text(item["label"], "subscription label")
        _rate(item["price"], "subscription rate")
    published = _timestamp(record["published_at"], "publication")
    retrieved = _timestamp(record["retrieved_at"], "retrieval")
    verified = _timestamp(record["verified_at"], "verification")
    valid_from = _timestamp(record["valid_from"], "validity start")
    valid_until = (
        None
        if record["valid_until"] is None
        else _timestamp(record["valid_until"], "validity end")
    )
    if (
        retrieved < published
        or verified < retrieved
        or (valid_until is not None and valid_until <= valid_from)
    ):
        raise ContractError("distribution timestamps are inconsistent")
    documents = _list(record["source_documents"], "source documents", allow_empty=False)
    for document in documents:
        url = _https_url(document, None, "source document")
        if pinned is not None and url not in pinned:
            raise ContractError("distribution source is not a pinned official source")
    _text(record["source_reference"], "source reference")
    _text(record["group_change_rule"], "group change rule")
    if record["verification_state"] != "verified_official":
        raise ContractError("distribution record is not officially verified")
    _text(record["declared_coverage"], "declared coverage")


def _brackets(value: Any, label: str, *, allow_empty: bool) -> None:
    items = _list(value, label, allow_empty=allow_empty)
    previous: Decimal | None = None
    for index, raw in enumerate(items):
        item = _object(raw, f"{label} bracket")
        _exact(item, {"up_to_kwh", "upper_inclusive", "price"}, f"{label} bracket")
        _rate(item["price"], f"{label} rate")
        if not isinstance(item["upper_inclusive"], bool):
            raise ContractError(f"{label} bracket bound is invalid")
        last = index == len(items) - 1
        if item["up_to_kwh"] is None:
            if not last or item["upper_inclusive"]:
                raise ContractError(f"{label} open bracket must be the last")
            continue
        if last:
            raise ContractError(f"{label} brackets must end open")
        bound = _decimal(item["up_to_kwh"], f"{label} bound")
        if bound <= 0 or (previous is not None and bound <= previous):
            raise ContractError(f"{label} brackets are not ascending")
        previous = bound


def _rate(value: Any, label: str) -> Decimal:
    rate = _decimal(value, label)
    if rate < 0 or rate > MAX_RATE:
        raise ContractError(f"{label} is out of range")
    return rate


def _decimal(value: Any, label: str) -> Decimal:
    raw = _text(value, label)
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ContractError(f"{label} is invalid") from exc
    exponent = result.as_tuple().exponent
    if not result.is_finite() or not isinstance(exponent, int) or exponent < -6:
        raise ContractError(f"{label} is invalid")
    return result


def _schema(value: Any, label: str) -> None:
    if isinstance(value, bool) or value != DISTRIBUTION_SCHEMA_VERSION:
        raise ContractError(f"{label} schema is unsupported")


def validate_distribution_publication(root: dict[str, Any]) -> None:
    _exact(
        root,
        {"schema_version", "data_version", "published_at", "object_id"},
        "distribution publication",
    )
    _schema(root["schema_version"], "distribution publication")
    _identifier(root["data_version"], "distribution publication data version")
    _timestamp(root["published_at"], "distribution publication timestamp")
    _identifier(root["object_id"], "distribution publication object id")


def validate_distribution_manifest(root: Path) -> dict[str, Any]:
    """``root`` is the ``distribution`` directory; object paths are relative."""

    manifest = read_json(root / "manifest.json", MAX_MANIFEST_BYTES)
    _exact(
        manifest,
        {"schema_version", "data_version", "published_at", "objects"},
        "distribution manifest",
    )
    _schema(manifest["schema_version"], "distribution manifest")
    data_version = _identifier(manifest["data_version"], "manifest data version")
    _timestamp(manifest["published_at"], "manifest publication")
    objects = _list(manifest["objects"], "manifest objects", allow_empty=False)
    ids: set[str] = set()
    for index, value in enumerate(objects):
        item = _object(value, f"manifest object {index}")
        _exact(item, {"id", "path", "sha256", "size"}, f"manifest object {index}")
        object_id = _identifier(item["id"], "manifest object id")
        if object_id in ids:
            raise ContractError("manifest object identifiers are duplicated")
        ids.add(object_id)
        raw_path = _text(item["path"], "object path")
        path = PurePosixPath(raw_path)
        if (
            path.is_absolute()
            or path.suffix != ".json"
            or any(part in {"", ".", ".."} for part in path.parts)
            or not raw_path.startswith("objects/")
        ):
            raise ContractError("object path is invalid")
        checksum = _sha256(item["sha256"], "manifest object checksum")
        size = _integer(item["size"], "manifest object size")
        if not 1 <= size <= MAX_OBJECT_BYTES:
            raise ContractError("manifest object size is invalid")
        payload = root.joinpath(*path.parts).read_bytes()
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != checksum:
            raise ContractError("manifest object integrity failed")
        catalog = json.loads(payload, parse_constant=_invalid_number)
        if not isinstance(catalog, dict):
            raise ContractError("distribution object must be a JSON object")
        validate_distribution(catalog)
        if catalog["data_version"] != data_version:
            raise ContractError("manifest and object data versions differ")
    return manifest
