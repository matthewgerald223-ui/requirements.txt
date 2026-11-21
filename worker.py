import hashlib
import os
import requests

API_BASE_URL = os.getenv("API_URL", "https://txt-w86d.onrender.com").rstrip("/")

# Replace "/your-post-route" with the exact @app.post("...") path from main.py
PREFERRED_ENDPOINT = os.getenv("API_ENDPOINT", "/your-post-route")

# Fallback paths to try only if PREFERRED_ENDPOINT is still a placeholder or returns 404
CANDIDATE_ENDPOINTS = [
    PREFERRED_ENDPOINT,
    "/ingest",
    "/submit",
    "/ec8a",
    "/ec8a/submit",
    "/results",
    "/results/submit",
    "/audit",
]

sample_image_bytes = b"sample-kogi-ec8a-sheet-bytes"
image_sha256 = hashlib.sha256(sample_image_bytes).hexdigest()

payload = {
    "polling_unit_code": "22-01-01-001",
    "ward": "Sample Ward",
    "lga": "Idah",
    "accredited_voters": 250,
    "party_votes": {
        "APC": 100,
        "PDP": 90,
        "LP": 40,
    },
    "image_sha256": image_sha256,
}

seen = set()
for endpoint in CANDIDATE_ENDPOINTS:
    if not endpoint or endpoint == "/your-post-route" or endpoint in seen:
        continue
    seen.add(endpoint)

    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(
            f"PU={payload['polling_unit_code']} endpoint={endpoint} -> "
            f"HTTP {response.status_code}: {response.text}"
        )
        if response.status_code != 404:
            break
    except requests.RequestException as exc:
        print(
            f"PU={payload['polling_unit_code']} endpoint={endpoint} -> "
            f"Request error: {exc}"
        )
