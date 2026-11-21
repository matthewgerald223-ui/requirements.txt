import hashlib
import os
from typing import Any, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from supabase import Client, create_client

load_dotenv()

app = FastAPI(title="Kogi EC8A Audit Vault")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class EC8AResultIn(BaseModel):
    polling_unit_code: str
    lga_name: str
    ward_name: str
    sdp_votes: int = Field(default=0, ge=0)
    apc_votes: int = Field(default=0, ge=0)
    pdp_votes: int = Field(default=0, ge=0)
    lp_votes: int = Field(default=0, ge=0)
    other_party_votes: int = Field(default=0, ge=0)
    total_accredited_voters: int = Field(default=0, ge=0)
    total_valid_votes: int = Field(default=0, ge=0)
    rejected_votes: int = Field(default=0, ge=0)
    source_image_url: str
    raw_image_bytes_hex: str
    anomaly_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_votes_exceeding_accredited(self) -> "EC8AResultIn":
        total_votes_cast = self.total_valid_votes + self.rejected_votes
        if total_votes_cast > self.total_accredited_voters:
            raise ValueError(
                f"Rejected: total votes cast ({total_votes_cast}) exceeds "
                f"total accredited voters ({self.total_accredited_voters})."
            )
        return self


def compute_sha256_from_hex(raw_hex: str) -> str:
    cleaned = raw_hex.strip()
    if cleaned.startswith(("0x", "0X")):
        cleaned = cleaned[2:]
    try:
        raw_bytes = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid hex string in raw_image_bytes_hex"
        ) from exc
    return hashlib.sha256(raw_bytes).hexdigest()


def evaluate_audit_flags(
    payload: EC8AResultIn,
    existing_hash_rows: List[dict[str, Any]],
    existing_pu_rows: List[dict[str, Any]],
) -> List[str]:
    flags: List[str] = list(payload.anomaly_flags or [])

    party_sum = (
        payload.sdp_votes
        + payload.apc_votes
        + payload.pdp_votes
        + payload.lp_votes
        + payload.other_party_votes
    )
    if party_sum != payload.total_valid_votes:
        flags.append("party_sum_mismatch")

    if existing_hash_rows:
        flags.append("duplicate_image_hash")

    if existing_pu_rows:
        flags.append("duplicate_polling_unit")

    return list(dict.fromkeys(flags))


@app.post("/ingest-result")
def ingest_result(payload: EC8AResultIn):
    image_sha256 = compute_sha256_from_hex(payload.raw_image_bytes_hex)

    dup_hash_res = (
        supabase.table("kogi_ec8a_results")
        .select("id, polling_unit_code, ingested_at")
        .eq("image_sha256", image_sha256)
        .limit(5)
        .execute()
    )
    dup_pu_res = (
        supabase.table("kogi_ec8a_results")
        .select("id, image_sha256, ingested_at")
        .eq("polling_unit_code", payload.polling_unit_code)
        .limit(5)
        .execute()
    )

    existing_hash_rows = dup_hash_res.data or []
    existing_pu_rows = dup_pu_res.data or []

    computed_flags = evaluate_audit_flags(
        payload=payload,
        existing_hash_rows=existing_hash_rows,
        existing_pu_rows=existing_pu_rows,
    )

    record = {
        "polling_unit_code": payload.polling_unit_code,
        "lga_name": payload.lga_name,
        "ward_name": payload.ward_name,
        "sdp_votes": payload.sdp_votes,
        "apc_votes": payload.apc_votes,
        "pdp_votes": payload.pdp_votes,
        "lp_votes": payload.lp_votes,
        "other_party_votes": payload.other_party_votes,
        "total_accredited_voters": payload.total_accredited_voters,
        "total_valid_votes": payload.total_valid_votes,
        "rejected_votes": payload.rejected_votes,
        "source_image_url": payload.source_image_url,
        "image_sha256": image_sha256,
        "anomaly_flags": computed_flags,
    }

    insert_res = supabase.table("kogi_ec8a_results").insert(record).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Failed to seal record in vault")

    saved_row = insert_res.data[0]
    return {
        "status": "sealed",
        "anomaly_flags": computed_flags,
        "has_anomalies": len(computed_flags) > 0,
        "duplicate_hash_count": len(existing_hash_rows),
        "duplicate_pu_count": len(existing_pu_rows),
        "record": saved_row,
    }


@app.get("/center/{polling_unit_code}")
def get_center_dossier(polling_unit_code: str):
    res = (
        supabase.table("kogi_ec8a_results")
        .select("*")
        .eq("polling_unit_code", polling_unit_code)
        .order("id", desc=True)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No records found for polling unit '{polling_unit_code}'",
        )

    latest = rows[0]
    flagged_submissions = [r for r in rows if r.get("anomaly_flags")]
    unique_hashes = list(
        {r.get("image_sha256") for r in rows if r.get("image_sha256")}
    )

    return {
        "polling_unit_code": polling_unit_code,
        "lga_name": latest.get("lga_name"),
        "ward_name": latest.get("ward_name"),
        "submission_count": len(rows),
        "unique_image_hashes": len(unique_hashes),
        "flagged_submission_count": len(flagged_submissions),
        "latest_submission": latest,
        "history": rows,
    }
