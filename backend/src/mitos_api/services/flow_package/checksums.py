"""SHA-256 checksum helpers for ``.flow`` archives (Phase 29)."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from mitos_api.services.flow_package.constants import CHECKSUMS_JSON
from mitos_api.services.flow_package.paths import FlowPackageError


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_checksums(members: Mapping[str, bytes]) -> dict[str, str]:
    """
    Build ``checksums.json`` content: sha256 for every member except itself.

    Keys are sorted for stable archives.
    """
    return {
        path: sha256_hex(data)
        for path, data in sorted(members.items())
        if path != CHECKSUMS_JSON
    }


def checksums_json_bytes(checksums: Mapping[str, str]) -> bytes:
    """Serialize checksums with stable key order and trailing newline."""
    payload = {k: checksums[k] for k in sorted(checksums)}
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def verify_checksums(members: Mapping[str, bytes]) -> None:
    """
    Verify ``checksums.json`` against member bytes.

    Raises ``FlowPackageError`` with code ``checksum_mismatch`` on any failure.
    """
    raw = members.get(CHECKSUMS_JSON)
    if raw is None:
        raise FlowPackageError(
            f"Missing '{CHECKSUMS_JSON}'.",
            code="missing_member",
        )

    try:
        declared = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowPackageError(
            f"Invalid '{CHECKSUMS_JSON}': {exc}",
            code="checksum_mismatch",
        ) from exc

    if not isinstance(declared, dict):
        raise FlowPackageError(
            f"'{CHECKSUMS_JSON}' must be a JSON object.",
            code="checksum_mismatch",
        )

    expected = build_checksums(members)
    declared_norm = {str(k): str(v) for k, v in declared.items()}

    if set(declared_norm) != set(expected):
        raise FlowPackageError(
            "Checksum file member set does not match archive contents.",
            code="checksum_mismatch",
        )

    for path, digest in expected.items():
        if declared_norm[path].lower() != digest.lower():
            raise FlowPackageError(
                f"Checksum mismatch for '{path}'.",
                code="checksum_mismatch",
            )
