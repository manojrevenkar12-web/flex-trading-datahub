"""Lands raw feeds in the bronze layer: one Parquet file per raw file, with where it came from and when. A file is
landed once: its content hash goes into a manifest, and the same content resent under another name is recorded as a
duplicate delivery and skipped. Running this twice changes nothing.

The layout (lake/bronze/<source>/...) is the one an S3 bucket would hold; DuckDB reads it locally and Athena or
Glue would read it the same way."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

SOURCES = {
    "meters": "meters/mdm=*/received=*/*.csv.gz",
    "hems": "hems/day=*/*.csv.gz",
    "weather": "weather/*.json",
    "day_ahead": "market/day_ahead/*.csv",
    "intraday": "market/intraday/*.csv",
    "rebap": "market/rebap/*.csv",
    "trades": "trades/*.csv",
    "desk_forecasts": "desk_forecasts/*.csv",
}


def _sha(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)          # the same rows compressed twice must hash the same
    return hashlib.sha256(data).hexdigest()


def _read(source: str, path: Path) -> pd.DataFrame:
    if source == "weather":
        doc = json.loads(path.read_text())
        df = pd.DataFrame(doc["values"])
        df["issue_time"] = doc["issue_time"]
        df["run"] = doc["run"]
        return df
    return pd.read_csv(path, dtype=str)


def land(lake: Path) -> dict:
    raw, bronze = lake / "raw", lake / "bronze"
    manifest_path = bronze / "_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}, "hashes": {}}
    stats = {"landed": 0, "duplicate_deliveries": 0, "already_landed": 0}
    for source, pattern in SOURCES.items():
        for path in sorted(raw.glob(pattern)):
            rel = str(path.relative_to(raw))
            if rel in manifest["files"]:
                stats["already_landed"] += 1
                continue
            sha = _sha(path)
            if sha in manifest["hashes"]:
                manifest["files"][rel] = {"sha256": sha, "status": "duplicate", "same_as": manifest["hashes"][sha]}
                stats["duplicate_deliveries"] += 1
                continue
            df = _read(source, path)
            parts = dict(re.findall(r"(\w+)=([^/]+)", rel))
            for k, v in parts.items():
                df[f"_{k}"] = v
            df["_source_file"] = rel
            df["_sha256"] = sha
            out = bronze / source / (sha[:16] + ".parquet")
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out, index=False)
            manifest["files"][rel] = {"sha256": sha, "status": "landed", "rows": len(df)}
            manifest["hashes"][sha] = rel
            stats["landed"] += 1
    bronze.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=0, sort_keys=True))
    pd.DataFrame([{"file": k, **v} for k, v in manifest["files"].items()]).to_parquet(bronze / "_manifest.parquet", index=False)
    return stats
