"""Strict, dependency-free contract for the public MIGIELS tariff catalog."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = 2
MAX_MANIFEST_BYTES = 512 * 1024
MAX_OBJECT_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


class ContractError(RuntimeError):
    """Raised when published catalog data cannot be trusted."""


def read_json(path: Path, maximum: int = MAX_OBJECT_BYTES) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise ContractError(f"{path} exceeds the size limit")
    try:
        value = json.loads(raw, parse_constant=_invalid_number)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{path} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("document is not canonical JSON") from exc


def validate_catalog(root: dict[str, Any]) -> None:
    _exact(root, {"schema_version", "data_version", "records"}, "catalog")
    _schema(root["schema_version"], "catalog")
    _identifier(root["data_version"], "catalog data version")
    records = _list(root["records"], "catalog records", allow_empty=False)
    identities: set[tuple[str, int]] = set()
    for index, value in enumerate(records):
        record = _object(value, f"record {index}")
        _validate_record(record, identities)


def validate_sources(root: dict[str, Any]) -> None:
    _exact(root, {"schema_version", "allowed_hosts", "sources"}, "sources")
    _schema(root["schema_version"], "sources")
    hosts = _strings(root["allowed_hosts"], "allowed hosts", allow_empty=False)
    if any(host != host.lower() or "." not in host for host in hosts):
        raise ContractError("allowed host is invalid")
    sources = _list(root["sources"], "sources", allow_empty=False)
    ids: set[str] = set()
    for index, value in enumerate(sources):
        item = _object(value, f"source {index}")
        _exact(
            item,
            {"id", "url", "sha256", "size", "media_type", "verified_at", "covers"},
            f"source {index}",
        )
        source_id = _identifier(item["id"], "source id")
        if source_id in ids:
            raise ContractError("source identifiers are duplicated")
        ids.add(source_id)
        _https_url(item["url"], hosts, "source URL")
        _sha256(item["sha256"], "source checksum")
        size = _integer(item["size"], "source size")
        if not 1 <= size <= MAX_SOURCE_BYTES:
            raise ContractError("source size is invalid")
        if item["media_type"] != "application/pdf":
            raise ContractError("source media type is unsupported")
        _timestamp(item["verified_at"], "source verification")
        for identity in _strings(item["covers"], "covered records", allow_empty=False):
            if not re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,127}:[1-9][0-9]*", identity):
                raise ContractError("covered record identity is invalid")


def validate_publication(root: dict[str, Any]) -> None:
    _exact(
        root,
        {"schema_version", "data_version", "published_at", "object_id"},
        "publication",
    )
    _schema(root["schema_version"], "publication")
    _identifier(root["data_version"], "publication data version")
    _timestamp(root["published_at"], "publication timestamp")
    _identifier(root["object_id"], "publication object id")


def validate_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    manifest = read_json(manifest_path, MAX_MANIFEST_BYTES)
    _exact(
        manifest,
        {"schema_version", "data_version", "published_at", "objects"},
        "manifest",
    )
    _schema(manifest["schema_version"], "manifest")
    data_version = _identifier(manifest["data_version"], "manifest data version")
    _timestamp(manifest["published_at"], "manifest publication")
    objects = _list(manifest["objects"], "manifest objects", allow_empty=False)
    ids: set[str] = set()
    paths: set[str] = set()
    for index, value in enumerate(objects):
        item = _object(value, f"manifest object {index}")
        _exact(item, {"id", "path", "sha256", "size"}, f"manifest object {index}")
        object_id = _identifier(item["id"], "manifest object id")
        if object_id in ids:
            raise ContractError("manifest object identifiers are duplicated")
        ids.add(object_id)
        path = _object_path(item["path"])
        if path in paths:
            raise ContractError("manifest object paths are duplicated")
        paths.add(path)
        checksum = _sha256(item["sha256"], "manifest object checksum")
        size = _integer(item["size"], "manifest object size")
        if not 1 <= size <= MAX_OBJECT_BYTES:
            raise ContractError("manifest object size is invalid")
        payload_path = root.joinpath(*PurePosixPath(path).parts)
        payload = payload_path.read_bytes()
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != checksum:
            raise ContractError("manifest object integrity failed")
        catalog = json.loads(payload, parse_constant=_invalid_number)
        if not isinstance(catalog, dict):
            raise ContractError("catalog object must be a JSON object")
        validate_catalog(catalog)
        if catalog["data_version"] != data_version:
            raise ContractError("manifest and object data versions differ")
    return manifest


def _validate_record(record: dict[str, Any], identities: set[tuple[str, int]]) -> None:
    _exact(
        record,
        {
            "country",
            "currency",
            "osd_ids",
            "seller",
            "brand",
            "offer",
            "price_list",
            "tariff_group",
            "schedule",
            "zones",
            "published_at",
            "retrieved_at",
            "verified_at",
            "valid_from",
            "valid_until",
            "source_documents",
            "verification_state",
            "declared_coverage",
        },
        "catalog record",
    )
    if record["country"] != "PL" or record["currency"] != "PLN":
        raise ContractError("catalog geography or currency is unsupported")
    _strings(record["osd_ids"], "OSD identifiers", allow_empty=False, identifiers=True)
    _named(record["seller"], "seller")
    brand = _object(record["brand"], "brand")
    _exact(brand, {"id", "name", "aliases"}, "brand")
    _identifier(brand["id"], "brand id")
    _text(brand["name"], "brand name")
    _strings(brand["aliases"], "brand aliases", allow_empty=True)
    _named(record["offer"], "offer")
    price_list = _object(record["price_list"], "price list")
    _exact(price_list, {"id", "revision"}, "price list")
    price_list_id = _identifier(price_list["id"], "price list id")
    revision = _integer(price_list["revision"], "price list revision")
    if revision < 1 or (price_list_id, revision) in identities:
        raise ContractError("price list identity is invalid or duplicated")
    identities.add((price_list_id, revision))
    _text(record["tariff_group"], "tariff group")
    zones = _list(record["zones"], "zones", allow_empty=False)
    zone_ids: set[str] = set()
    for value in zones:
        zone = _object(value, "zone")
        _exact(
            zone, {"id", "label", "price", "semantic", "tax_treatment", "unit"}, "zone"
        )
        zone_id = _identifier(zone["id"], "zone id")
        if zone_id in zone_ids:
            raise ContractError("zone identifiers are duplicated")
        zone_ids.add(zone_id)
        _text(zone["label"], "zone label")
        try:
            price = Decimal(_text(zone["price"], "zone price"))
        except InvalidOperation as exc:
            raise ContractError("zone price is invalid") from exc
        price_exponent = price.as_tuple().exponent
        if (
            not price.is_finite()
            or price <= 0
            or not isinstance(price_exponent, int)
            or price_exponent < -6
        ):
            raise ContractError("zone price is invalid")
        if zone["semantic"] != "gross_active_energy":
            raise ContractError("only gross active-energy prices are supported")
        if zone["tax_treatment"] != "gross" or zone["unit"] != "PLN/kWh":
            raise ContractError("zone tax treatment or unit is invalid")
    _validate_schedule(_object(record["schedule"], "schedule"), zone_ids)
    published = _timestamp(record["published_at"], "record publication")
    retrieved = _timestamp(record["retrieved_at"], "record retrieval")
    verified = _timestamp(record["verified_at"], "record verification")
    valid_from = _timestamp(record["valid_from"], "record validity start")
    valid_until = (
        None
        if record["valid_until"] is None
        else _timestamp(record["valid_until"], "record validity end")
    )
    if (
        retrieved < published
        or verified < published
        or (valid_until is not None and valid_until <= valid_from)
    ):
        raise ContractError("record timestamps are inconsistent")
    _strings(
        record["source_documents"], "source documents", allow_empty=False, urls=True
    )
    if record["verification_state"] != "verified_official":
        raise ContractError("record is not officially verified")
    _text(record["declared_coverage"], "declared coverage")


def _validate_schedule(schedule: dict[str, Any], zone_ids: set[str]) -> None:
    _exact(
        schedule,
        {
            "profile_id",
            "timezone",
            "default_zone_id",
            "rules",
            "meter_clock_mode",
        },
        "schedule",
    )
    _identifier(schedule["profile_id"], "schedule profile id")
    if schedule["timezone"] != "Europe/Warsaw":
        raise ContractError("schedule timezone is unsupported")
    meter_clock_mode = schedule["meter_clock_mode"]
    if meter_clock_mode not in {"not_applicable", "operator_choice"}:
        raise ContractError("schedule meter clock mode is unsupported")
    default = _identifier(schedule["default_zone_id"], "default zone id")
    if default not in zone_ids:
        raise ContractError("default zone is missing")
    rules = _list(schedule["rules"], "schedule rules", allow_empty=True)
    if (meter_clock_mode == "not_applicable") != (not rules):
        raise ContractError("schedule meter clock mode does not match its rules")
    for value in rules:
        rule = _object(value, "schedule rule")
        _exact(
            rule,
            {
                "zone_id",
                "start_local",
                "end_local",
                "weekdays",
                "holiday",
                "season_start",
                "season_end",
                "dates",
                "priority",
            },
            "schedule rule",
        )
        if _identifier(rule["zone_id"], "rule zone id") not in zone_ids:
            raise ContractError("schedule rule references an unknown zone")
        if (
            TIME_PATTERN.fullmatch(_text(rule["start_local"], "rule start")) is None
            or TIME_PATTERN.fullmatch(_text(rule["end_local"], "rule end")) is None
        ):
            raise ContractError("schedule time is invalid")
        weekdays = (
            []
            if rule["weekdays"] is None
            else _list(rule["weekdays"], "rule weekdays", allow_empty=False)
        )
        if any(
            isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6
            for day in weekdays
        ) or len(weekdays) != len(set(weekdays)):
            raise ContractError("schedule weekdays are invalid")
        if rule["holiday"] is not None and not isinstance(rule["holiday"], bool):
            raise ContractError("schedule holiday selector is invalid")
        for field in ("season_start", "season_end"):
            if rule[field] is not None:
                boundary = _list(rule[field], field, allow_empty=False)
                if (
                    len(boundary) != 2
                    or any(isinstance(item, bool) or not isinstance(item, int) for item in boundary)
                    or not 1 <= boundary[0] <= 12
                    or not 1 <= boundary[1] <= 31
                ):
                    raise ContractError("schedule season boundary is invalid")
        if (rule["season_start"] is None) != (rule["season_end"] is None):
            raise ContractError("schedule season boundaries are incomplete")
        if rule["dates"] is not None:
            dates = _strings(rule["dates"], "schedule dates", allow_empty=False)
            for value in dates:
                try:
                    datetime.fromisoformat(value).date()
                except ValueError as exc:
                    raise ContractError("schedule date is invalid") from exc
        _integer(rule["priority"], "schedule priority")


def _named(value: Any, label: str) -> None:
    item = _object(value, label)
    _exact(item, {"id", "name"}, label)
    _identifier(item["id"], f"{label} id")
    _text(item["name"], f"{label} name")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{label} must be an object")
    return value


def _list(value: Any, label: str, *, allow_empty: bool) -> list[Any]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ContractError(f"{label} must be a list")
    return value


def _strings(
    value: Any,
    label: str,
    *,
    allow_empty: bool,
    identifiers: bool = False,
    urls: bool = False,
) -> list[str]:
    values = _list(value, label, allow_empty=allow_empty)
    result = [_text(item, label) for item in values]
    if len(result) != len(set(result)):
        raise ContractError(f"{label} contains duplicates")
    if identifiers:
        for item in result:
            _identifier(item, label)
    if urls:
        for item in result:
            _https_url(item, None, label)
    return result


def _text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 4096
    ):
        raise ContractError(f"{label} is invalid")
    return value


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label)
    if ID_PATTERN.fullmatch(result) is None:
        raise ContractError(f"{label} is invalid")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{label} is invalid")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    raw = _text(value, label)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label} is invalid") from exc
    if result.utcoffset() is None:
        raise ContractError(f"{label} must include a timezone")
    return result


def _https_url(value: Any, hosts: list[str] | None, label: str) -> str:
    raw = _text(value, label)
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ContractError(f"{label} must be credential-free HTTPS")
    if hosts is not None and parsed.hostname.lower() not in hosts:
        raise ContractError(f"{label} host is not allowed")
    return raw


def _sha256(value: Any, label: str) -> str:
    raw = _text(value, label)
    if HASH_PATTERN.fullmatch(raw) is None:
        raise ContractError(f"{label} is invalid")
    return raw


def _object_path(value: Any) -> str:
    raw = _text(value, "object path")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or path.suffix != ".json"
        or any(part in {"", ".", ".."} for part in path.parts)
        or not raw.startswith("objects/")
    ):
        raise ContractError("object path is invalid")
    return raw


def _schema(value: Any, label: str) -> None:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise ContractError(f"{label} schema is unsupported")


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ContractError(f"{label} fields are invalid")


def _invalid_number(_: str) -> None:
    raise ContractError("non-finite JSON number is invalid")
