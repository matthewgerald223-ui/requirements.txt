import hashlib
import os
from typing import List
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_SECRET_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="Kogi Election Vault Engine", version="0.1.0")


class ResultSubmission(BaseModel):
    polling_unit_code: str = Field(..., min_length=3, max_length=50)
    lga_name: str = Field(..., min_length=2, max_length=100)
    ward_name: str = Field(..., min_length=2, max_length=100)
    sdp_votes: int = Field(0, ge=0)
    apc_votes: int = Field(0, ge=0)
    pdp_votes: int = Field(0, ge=0)
    lp_votes: int = Field(0, ge=0)
    other_party_votes: int = Field(0, ge=0)
    total_accredited_voters: int = Field(0, ge=0)
    total_valid_votes: int = Field(0, ge=0)
    rejected_votes: int = Field(0, ge=0)
    source_image_url: str = Field(..., min_length=5)
    raw_image_bytes_hex: str | None = Field(
        default=None,
        description="Optional raw image bytes in hex to compute exact SHA-256 fingerprint",
    )


def compute_sha256(payload: ResultSubmission) -> str:
    if payload.raw_image_bytes_hex:
        raw_bytes = bytes.fromhex(payload.raw_image_bytes_hex.strip())
        return hashlib.sha256(raw_bytes).hexdigest()
    # Fallback deterministic fingerprint if raw image bytes aren't passed yet
    fallback_seed = f"{payload.polling_unit_code}|{payload.source_image_url}".encode("utf-8")
    return hashlib.sha256(fallback_seed).hexdigest()


def run_math_audit(data: ResultSubmission) -> List[str]:
    flags: List[str] = []
    party_sum = (
        data.sdp_votes
        + data.apc_votes
        + data.pdp_votes
        + data.lp_votes
        + data.other_party_votes
    )
    total_cast = party_sum + data.rejected_votes

    if data.total_valid_votes != party_sum:
        flags.append(
            f"VALID_VOTE_MISMATCH: stated={data.total_valid_votes}, party_sum={party_sum}"
        )

    if data.total_accredited_voters > 0 and total_cast > data.total_accredited_voters:
        flags.append(
            f"POSSIBLE_OVER_VOTING: cast={total_cast}, accredited={data.total_accredited_voters}"
        )

    return flags


@app.get("/")
def root():
    return {
        "status": "online",
        "system": "Kogi State Automated Election Monitoring Engine",
        "vault_connected": supabase is not None,
    }


@app.post("/ingest-result")
def ingest_result(submission: ResultSubmission):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Missing SUPABASE_URL or SUPABASE_SECRET_KEY environment variables.",
        )

    sha256_hash = compute_sha256(submission)
    anomaly_flags = run_math_audit(submission)

    record = {
        "polling_unit_code": submission.polling_unit_code.strip(),
        "lga_name": submission.lga_name.strip(),
        "ward_name": submission.ward_name.strip(),
        "sdp_votes": submission.sdp_votes,
        "apc_votes": submission.apc_votes,
        "pdp_votes": submission.pdp_votes,
        "lp_votes": submission.lp_votes,
        "other_party_votes": submission.other_party_votes,
        "total_accredited_voters": submission.total_accredited_voters,
        "total_valid_votes": submission.total_valid_votes,
        "rejected_votes": submission.rejected_votes,
        "source_image_url": submission.source_image_url.strip(),
        "image_sha256": sha256_hash,
        "anomaly_flags": anomaly_flags,
    }

    response = supabase.table("kogi_ec8a_results").insert(record).execute()
    return {
        "message": "Record sealed in append-only Kogi vault",
        "image_sha256": sha256_hash,
        "anomaly_flags": anomaly_flags,
        "inserted": response.data,
}
  
