"""Fetch only approved official sources and fail on any unreviewed change."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from catalog_contract import (
    MAX_SOURCE_BYTES,
    ContractError,
    read_json,
    validate_sources,
)

ROOT = Path(__file__).resolve().parents[1]
RETRIES = 3
TIMEOUT_SECONDS = 20


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(
        self, request: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        parsed = urlsplit(newurl)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname.lower() not in self.allowed_hosts
            or parsed.username
            or parsed.password
        ):
            raise ContractError("source redirect left the approved HTTPS boundary")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url: str, allowed_hosts: set[str]) -> tuple[bytes, str]:
    opener = urllib.request.build_opener(SafeRedirect(allowed_hosts))
    request = urllib.request.Request(
        url, headers={"User-Agent": "MIGIELS-Tariff-Catalog/1"}
    )
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                final = urlsplit(response.geturl())
                if (
                    final.scheme != "https"
                    or not final.hostname
                    or final.hostname.lower() not in allowed_hosts
                ):
                    raise ContractError(
                        "source response left the approved HTTPS boundary"
                    )
                content_type = response.headers.get_content_type()
                data = response.read(MAX_SOURCE_BYTES + 1)
                if len(data) > MAX_SOURCE_BYTES:
                    raise ContractError("source exceeds the size limit")
                return data, content_type
        except (OSError, urllib.error.URLError, ContractError) as exc:
            last_error = exc
            if attempt + 1 < RETRIES:
                time.sleep(1 << attempt)
    raise ContractError("official source could not be verified") from last_error


def main(*, write_status: bool) -> None:
    sources_document = read_json(ROOT / "catalog" / "sources.json")
    validate_sources(sources_document)
    catalog = read_json(ROOT / "catalog" / "catalog.json")
    allowed_hosts = set(sources_document["allowed_hosts"])
    results: list[dict[str, str]] = []
    for source in sources_document["sources"]:
        payload, media_type = fetch(source["url"], allowed_hosts)
        checksum = hashlib.sha256(payload).hexdigest()
        if len(payload) != source["size"] or checksum != source["sha256"]:
            raise ContractError(
                f"official source {source['id']} changed and requires review"
            )
        if media_type != source["media_type"]:
            raise ContractError(f"official source {source['id']} changed media type")
        results.append({"id": source["id"], "status": "verified", "sha256": checksum})
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    status = {
        "schema_version": 1,
        "catalog_data_version": catalog["data_version"],
        "last_successful_check_at": now,
        "source_check_result": "verified_unchanged",
        "data_changed": False,
        "sources": results,
    }
    if write_status:
        (ROOT / "status.json").write_text(
            json.dumps(
                status, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
            )
            + "\n",
            encoding="utf-8",
        )
    print("SOURCE_CHECK=PASS")
    print(f"SOURCE_COUNT={len(results)}")
    print(f"LAST_SUCCESSFUL_CHECK_AT={now}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-status", action="store_true")
    arguments = parser.parse_args()
    main(write_status=arguments.write_status)
