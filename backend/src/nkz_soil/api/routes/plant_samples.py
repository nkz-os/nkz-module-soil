"""Leaf (plant tissue) analyses as AgriPlantSample: CSV import with preview, per-zone export.

The CSV carries lab units (see models/agri_plant_sample.py); every sample names its tree(s)
by ``plantCode`` within the parcel (several with ``;`` for a composite). The export gives one
row per sample in lab units with the zone of its tree for a chosen zoning (default: the
latest automatic one), for statistical analysis.
"""
from __future__ import annotations

import csv
import io
import logging
import math
from datetime import date

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from nkz_platform_sdk import AuthContext
from nkz_platform_sdk.gis import default_zoning, fetch_zonings, zone_of

from nkz_soil.api.dependencies import require_auth
from nkz_soil.config import BATCH_MAX_BYTES, BATCH_MAX_ROWS
from nkz_soil.models.agri_plant_sample import (
    MANAGED_ATTRS,
    RESULT_HEADERS,
    TISSUES,
    UnitError,
    check_unit,
    convert,
    parse_header,
    to_entity,
    to_rows,
)
from nkz_soil.storage.orion import OrionClient, parcel_ref_query

logger = logging.getLogger(__name__)
router = APIRouter()
_REQUIRE_AUTH = require_auth()
_FILE = File(...)

_REQUIRED = ("plantCode", "dateSampled", "sampleCode")
_META = {"plantCode", "dateSampled", "sampleCode", "plantTissue", "phenologicalStage",
         "numberOfSubsamples", "laboratory", "dateAnalysed", "analysisMethod"}
EXPORT_COLUMNS = ("sampleId", "plantCodes", "dateSampled", "plantTissue", "sampleCode",
                  "phenologicalStage", "numberOfSubsamples", "laboratory", "dateAnalysed",
                  "analysisMethod", "lat", "lon", "zoneLabel", "zoneMixed", "zoningRunId",
                  *RESULT_HEADERS)
NO_ZONING = "none"


def _parcel_urn(parcel_id: str) -> str:
    return parcel_id if parcel_id.startswith("urn:") else f"urn:ngsi-ld:AgriParcel:{parcel_id}"


def _value(entity: dict, attr: str):
    v = entity.get(attr)
    return v.get("value", v.get("object")) if isinstance(v, dict) else v


def _num(text: str) -> float:
    """A lab result: finite and not negative; decimal comma accepted (Spanish spreadsheets)."""
    v = float(text.replace(",", "."))
    if not math.isfinite(v) or v < 0:
        raise ValueError(text)
    return v


def _decode(content: bytes) -> str:
    """UTF-8 (with or without BOM); Spanish Excel's plain "CSV" is Windows-1252."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _point(loc) -> tuple[float, float] | None:
    coords = loc.get("coordinates") if isinstance(loc, dict) else None
    return (coords[0], coords[1]) if isinstance(coords, (list, tuple)) and len(coords) >= 2 else None


def _day(text: str) -> str | None:
    """YYYY-MM-DD from a date or an ISO date-time."""
    try:
        return date.fromisoformat(text.strip()[:10]).isoformat()
    except ValueError:
        return None


async def _plants(orion: OrionClient, parcel_urn: str) -> dict[str, dict]:
    plants = await orion.query_all("AgriPlant", q=parcel_ref_query(parcel_urn))
    return {str(_value(p, "plantCode")): p for p in plants if _value(p, "plantCode")}


def _parse_row(row: dict, row_num: int, plants: dict, results_cols: list, other_cols: list) -> tuple[dict | None, str | None]:
    codes = [c.strip() for c in row.get("plantCode", "").split(";") if c.strip()]
    if not codes:
        return None, f"Row {row_num}: plantCode is required"
    unknown = [c for c in codes if c not in plants]
    if unknown:
        return None, f"Row {row_num}: unknown plant code {', '.join(unknown)} in this parcel"
    day = _day(row.get("dateSampled", ""))
    if not day:
        return None, f"Row {row_num}: dateSampled must be YYYY-MM-DD"
    sample_code = row.get("sampleCode", "").strip()
    if not sample_code:
        return None, f"Row {row_num}: sampleCode is required"
    tissue = row.get("plantTissue", "").strip() or "leaf"
    if tissue not in TISSUES:
        return None, f"Row {row_num}: plantTissue must be one of {', '.join(TISSUES)}"
    parsed: dict = {"plant_codes": codes, "date_sampled": day, "plant_tissue": tissue,
                    "sample_code": sample_code, "results": {}, "other_results": []}
    for key, name in (("phenologicalStage", "phenological_stage"), ("laboratory", "laboratory"),
                      ("analysisMethod", "analysis_method")):
        if row.get(key, "").strip():
            parsed[name] = row[key].strip()
    if row.get("numberOfSubsamples", "").strip():
        try:
            n = int(row["numberOfSubsamples"])
            if n < 1:
                raise ValueError
            parsed["number_of_subsamples"] = n
        except ValueError:
            return None, f"Row {row_num}: numberOfSubsamples must be a whole number >= 1"
    if row.get("dateAnalysed", "").strip():
        analysed = _day(row["dateAnalysed"])
        if not analysed:
            return None, f"Row {row_num}: dateAnalysed must be YYYY-MM-DD"
        parsed["date_analysed"] = analysed
    try:
        for col, attr, unit in results_cols:
            raw = row.get(col, "").strip()
            if raw:
                parsed["results"][attr] = convert(attr, _num(raw), unit, column=col)
        for col, name, unit in other_cols:
            raw = row.get(col, "").strip()
            if raw:
                check_unit(unit, col)
                parsed["other_results"].append({"name": name, "value": _num(raw), "unit": unit})
    except UnitError as exc:
        return None, f"Row {row_num}: {exc}"
    except ValueError:
        return None, f"Row {row_num}: a result is not a number >= 0"
    if not parsed["results"] and not parsed["other_results"]:
        return None, f"Row {row_num}: no result values"
    return parsed, None


@router.post("/plant-samples/batch")
async def import_plant_samples(
    parcel_id: str = Query(..., max_length=200),
    dry_run: bool = True,
    file: UploadFile = _FILE,
    auth: AuthContext = _REQUIRE_AUTH,
):
    """Preview (dry_run=true) or write leaf analyses of one parcel from a CSV."""
    tenant = auth.tenant_id
    parcel_urn = _parcel_urn(parcel_id)
    content = await file.read()
    if len(content) > BATCH_MAX_BYTES:
        raise HTTPException(status_code=422, detail=f"CSV exceeds maximum size of {BATCH_MAX_BYTES} bytes")
    text = _decode(content)
    header = text.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if header.count(";") > header.count(",") else ",")
    fields = [f.strip() for f in (reader.fieldnames or [])]
    missing = [c for c in _REQUIRED if c not in fields]
    if missing:
        raise HTTPException(status_code=422, detail=f"CSV needs the columns {', '.join(missing)}")

    results_cols, other_cols, warnings = [], [], []
    for col in fields:
        if col in _META:
            continue
        attr, name, unit = parse_header(col)
        if attr:
            results_cols.append((col, attr, unit))
        elif unit:
            other_cols.append((col, name, unit))
            warnings.append({"code": "stored_as_other", "column": col})
        elif col:
            warnings.append({"code": "ignored_column", "column": col})

    async with OrionClient(tenant) as orion:
        plants = await _plants(orion, parcel_urn)
        existing = {e["id"]: e for e in await orion.query_all("AgriPlantSample", q=parcel_ref_query(parcel_urn))}
        accepted, entities, rejected = [], [], []
        first_row: dict[str, int] = {}
        for row_num, raw in enumerate(reader, start=2):
            if len(accepted) >= BATCH_MAX_ROWS:
                rejected.append({"row": row_num, "error": f"Exceeded maximum of {BATCH_MAX_ROWS} rows per upload"})
                break
            if any((v or "").strip() for v in (raw.get(None) or [])):
                rejected.append({"row": row_num, "error": f"Row {row_num}: more values than columns "
                                 "(a decimal comma needs ';' as the delimiter)"})
                continue
            row = {k.strip(): (v or "") for k, v in raw.items() if k is not None}
            parsed, error = _parse_row(row, row_num, plants, results_cols, other_cols)
            if error:
                rejected.append({"row": row_num, "error": error})
                continue
            first = plants[parsed["plant_codes"][0]]
            entity = to_entity(tenant, parcel_urn, parsed, [plants[c]["id"] for c in parsed["plant_codes"]],
                               location=_value(first, "location"))
            if entity["id"] in first_row:
                rejected.append({"row": row_num, "error": f"Row {row_num}: duplicate of row {first_row[entity['id']]}"})
                continue
            first_row[entity["id"]] = row_num
            accepted.append({"row": row_num, "id": entity["id"], "plantCodes": parsed["plant_codes"],
                             "dateSampled": parsed["date_sampled"],
                             "action": "update" if entity["id"] in existing else "create"})
            entities.append(entity)

        created = 0
        if entities and not dry_run:
            result = await orion.upsert_entities_batch(entities)
            failed = {(e.get("entityId") or e.get("id")) for e in result.get("errors", []) if isinstance(e, dict)}
            created = len(entities) - len(failed)
            for a in accepted:
                if a["id"] in failed:
                    rejected.append({"row": a["row"], "error": f"Row {a['row']}: could not be stored"})
            if failed:
                logger.error("leaf samples not stored tenant=%s parcel=%s count=%d", tenant, parcel_urn, len(failed))
            accepted = [a for a in accepted if a["id"] not in failed]
            # options=update merges: a value the corrected sheet leaves empty is removed here
            rows_by_id = {a["id"]: a["row"] for a in accepted}
            for entity in entities:
                old = existing.get(entity["id"])
                if old is None or entity["id"] in failed:
                    continue
                for attr in (a for a in MANAGED_ATTRS if a in old and a not in entity):
                    try:
                        await orion.delete_entity_attr(entity["id"], attr)
                    except Exception:
                        logger.exception("stale leaf value not removed tenant=%s id=%s attr=%s",
                                         tenant, entity["id"], attr)
                        warnings.append({"code": "stale_not_removed", "column": attr,
                                         "row": rows_by_id.get(entity["id"])})
    logger.info("leaf samples %s tenant=%s parcel=%s accepted=%d rejected=%d",
                "previewed" if dry_run else "written", tenant, parcel_urn, len(accepted), len(rejected))
    return {"accepted": accepted, "rejected": rejected, "warnings": warnings, "created": created}


@router.get("/parcel/{parcel_id}/plant-samples/export.csv")
async def export_plant_samples(
    parcel_id: str,
    zoning_run_id: str | None = Query(None, max_length=120),
    auth: AuthContext = _REQUIRE_AUTH,
):
    """One row per leaf sample in lab units, with its tree's zone for the chosen zoning."""
    parcel_urn = _parcel_urn(parcel_id)
    async with OrionClient(auth.tenant_id) as orion:
        samples = await orion.query_all("AgriPlantSample", q=parcel_ref_query(parcel_urn))
        plants = await _plants(orion, parcel_urn)
        zonings = [] if zoning_run_id == NO_ZONING else await fetch_zonings(orion._sdk, parcel_urn)
    if zoning_run_id == NO_ZONING:
        zoning = None
    elif zoning_run_id:
        zoning = next((z for z in zonings if z.run_id == zoning_run_id), None)
        if zoning is None:
            raise HTTPException(status_code=404, detail="zoning not found for this parcel")
    else:
        zoning = default_zoning(zonings)
    by_id = {p["id"]: p for p in plants.values()}

    rows = []
    for s in sorted(samples, key=lambda e: (str(_value(e, "dateSampled")), e.get("id", ""))):
        row = to_rows(s)
        refs = _value(s, "hasAgriPlant")
        refs = refs if isinstance(refs, list) else [refs] if refs else []
        # the trees' current positions (a re-surveyed tree moves its samples' zone);
        # the location stored on the sample only when no tree is found
        points = [_point(_value(by_id.get(r, {}), "location")) for r in refs]
        points = [p for p in points if p] or [p for p in [_point(_value(s, "location"))] if p]
        lon, lat = points[0] if points else (None, None)
        row.update(lat=lat, lon=lon, zoneLabel="", zoneMixed="false", zoningRunId=zoning.run_id if zoning else "")
        if zoning and points:
            labels = {((z.label or "") if (z := zone_of(x, y, zoning)) else "") for x, y in points}
            if len(labels) == 1:
                row["zoneLabel"] = labels.pop()
            else:
                row["zoneMixed"] = "true"  # a composite whose trees fall in different zones
        rows.append(row)
    extra = sorted({k for r in rows for k in r} - set(EXPORT_COLUMNS))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[*EXPORT_COLUMNS, *extra], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    filename = f"leaf-analyses-{parcel_urn.rsplit(':', 1)[-1]}.csv"
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
