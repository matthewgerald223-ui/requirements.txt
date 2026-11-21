import hashlib
import os
from typing import Any, Dict, List

import requests

VAULT_INGEST_URL = os.environ.get(
    "VAULT_INGEST_URL",
    "https://txt-w86d.onrender.com/ingest-result",
)


def fetch_external_results() -> List[Dict[str, Any]]:
    """
    Replace this mock list with your real data/image source
    (e.g., external JSON feed, CSV/API, or downloaded EC8A image bytes).
    """
    sample_image_bytes = b"sample-ec8a-sheet-001"
    return [
        {
            "polling_unit_code": "22-01-01-001",
            "lga_name": "Idah",
            "ward_name": "Idah",
            "sdp_votes": 10,
            "apc_votes": 25,
            "pdp_votes": 15,
            "lp_votes": 5,
            "other_party_votes": 0,
            "total_accredited_voters": 100,
            "total_valid_votes": 55,
            "rejected_votes": 5,
            "source_image_url": "https://example.com/ec8a/22-01-01-001.jpg",
            "raw_image_bytes": sample_image_bytes,
            "anomaly_flags": [],
        }
    ]


def build_ingest_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    raw_bytes: bytes = item["raw_image_bytes"]
    return {
        "polling_unit_code": item["polling_unit_code"],
        "lga_name": item["lga_name"],
        "ward_name": item["ward_name"],
        "sdp_votes": item.get("sdp_votes", 0),
        "apc_votes": item.get("apc_votes", 0),
        "pdp_votes": item.get("pdp_votes", 0),
        "lp_votes": item.get("lp_votes", 0),
        "other_party_votes": item.get("other_party_votes", 0),
        "total_accredited_voters": item.get("total_accredited_voters", 0),
        "total_valid_votes": item.get("total_valid_votes", 0),
        "rejected_votes": item.get("rejected_votes", 0),
        "source_image_url": item["source_image_url"],
        "raw_image_bytes_hex": raw_bytes.hex(),
        "anomaly_flags": item.get("anomaly_flags", []),
    }


def push_to_vault(payload: Dict[str, Any]) -> None:
    res = requests.post(VAULT_INGEST_URL, json=payload, timeout=30)
    print(f"PU={payload['polling_unit_code']} -> HTTP {res.status_code}: {res.text}")


def main() -> None:
    for item in fetch_external_results():
        payload = build_ingest_payload(item)
        push_to_vault(payload)


if __name__ == "__main__":
    main()
