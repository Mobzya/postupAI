"""Dependency-free semantic validation; rejects unknown, missing and conflicting evidence."""
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "config/catalog_scope.json").read_text())


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_registry(registry: dict) -> None:
    require(registry.get("schema_version") == 1, "source schema version")
    sources = registry.get("sources")
    require(isinstance(sources, list), "sources array")
    seen = set()
    institutions = set()
    fields = {"id", "institution_id", "institution_name", "url", "document_type", "years", "last_checked_at",
              "extraction_method", "parsing_status", "original_url", "completeness", "reliability", "notes", "discovery_status"}
    for source in sources:
        require(isinstance(source, dict) and fields <= source.keys(), "source required fields")
        require(source["id"] not in seen, "duplicate source")
        seen.add(source["id"])
        require(source["institution_id"] in SCOPE["institution_ids"], "unknown institution")
        institutions.add(source["institution_id"])
        for key in ("url", "original_url"):
            parsed = urlparse(source[key])
            require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password, "https source URL")
        require(isinstance(source["years"], list) and all(type(y) is int and 2000 <= y <= 2100 for y in source["years"]), "source years")
        if source["last_checked_at"] is not None:
            date.fromisoformat(source["last_checked_at"])
        require(source["parsing_status"] in {"not_started", "success", "partial", "blocked", "error", "manual_review"}, "parsing status")
        require(source["reliability"] in {"unassessed", "official_unverified", "verified", "conflict"}, "reliability")
        completeness = source["completeness"]
        require(completeness is None or (number(completeness) and 0 <= completeness <= 1), "source completeness")
    require(institutions == set(SCOPE["institution_ids"]), "registry must cover ten institutions")


def validate_measurement(cell: dict, year: int, known_sources: set[str]) -> None:
    require(isinstance(cell, dict), "measurement object")
    require({"value", "status", "unit", "source_id", "year", "methodology"} <= cell.keys(), "measurement provenance")
    require(cell["source_id"] in known_sources, "measurement source")
    require(cell["year"] == year, "measurement year mismatch")
    require(cell["unit"] in {"competition_points", "exam_points", "people", "places", "applications"}, "measurement unit")
    require(isinstance(cell["methodology"], str) and bool(cell["methodology"].strip()), "measurement methodology")
    require(cell["status"] in {"verified", "unverified", "conflict", "missing"}, "measurement status")
    if cell["value"] is None:
        require(cell["status"] == "missing" and bool(cell.get("missing_reason")), "missing reason")
    else:
        require(number(cell["value"]) and cell["value"] >= 0 and cell["status"] != "missing", "invalid measurement value")


def validate_catalog(catalog: dict, registry: dict) -> None:
    require(catalog.get("schema_version") == 1, "catalog schema version")
    require(type(catalog.get("catalog_complete")) is bool and type(catalog.get("is_synthetic")) is bool, "catalog labels")
    require(isinstance(catalog.get("records"), list), "catalog records")
    sources = {s["id"] for s in registry["sources"]}
    keys = set()
    for row in catalog["records"]:
        required = {"program_id", "institution_id", "year", "revision", "track_category", "campus", "degree", "source_id", "verification_status", *SCOPE["required_audit_fields"]}
        require(isinstance(row, dict) and required <= row.keys(), "catalog required fields")
        require(row["institution_id"] in SCOPE["institution_ids"] and row["source_id"] in sources, "catalog reference")
        require(type(row["year"]) is int and 2000 <= row["year"] <= 2100, "catalog year")
        require(type(row["revision"]) is int and row["revision"] >= 1, "catalog revision")
        require(row["track_category"] in {"general_budget", "special_quota", "separate_quota", "targeted", "bvi", "paid", "grant", "special_selection"}, "catalog track")
        require(row["degree"] in SCOPE["degrees"], "catalog degree")
        require(row["verification_status"] in {"verified", "unverified", "conflict"}, "catalog verification")
        key = (row["program_id"], row["year"], row["track_category"], row["revision"])
        require(key not in keys, "duplicate catalog revision")
        keys.add(key)
        for field in ("seats_budget", "seats_paid", "cutoff", "mean_score", "applications", "enrolled"):
            if row[field] is not None:
                validate_measurement(row[field], row["year"], sources)
        for field in ("name", "official_code"):
            require(row[field] is None or (isinstance(row[field], str) and bool(row[field].strip())), "catalog text field")


def validate_distribution(points: list[dict], maximum: float = 100) -> None:
    require(isinstance(points, list) and len(points) > 0, "empty distribution")
    seen = set()
    for point in points:
        require(number(point.get("score")) and 0 <= point["score"] <= maximum, "score outside support")
        require(point["score"] not in seen, "duplicate score")
        seen.add(point["score"])
        require(number(point.get("probability")) and 0 <= point["probability"] <= 1, "invalid probability")
    require(abs(sum(p["probability"] for p in points) - 1) <= 1e-9, "unnormalized distribution")


def validate_all() -> None:
    registry = load(ROOT / "data/source_registry.json")
    validate_registry(registry)
    validate_catalog(load(ROOT / "data/normalized/catalog.json"), registry)
    assumptions = load(ROOT / "config/progress.assumptions.json")
    require(assumptions["enabled"] is False and assumptions["status"] == "unvalidated_assumptions", "stage 0 model must stay disabled")
    require(assumptions["target_role"] == "diagnostics_only_never_used_in_growth", "target must not inflate growth")
    print("Validated: source registry, empty catalog, disabled assumptions. No real admission metrics or models.")


if __name__ == "__main__":
    validate_all()
