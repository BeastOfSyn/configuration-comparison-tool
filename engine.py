"""
Configuration Comparison Engine v12.3
Author: BeastOfSyn
Deterministic AST-aware diffing engine for configuration exports.
"""
from __future__ import annotations

__author__ = "BeastOfSyn"
__version__ = "12.3"
__engine_seal__ = "BSN-CORE-42656173744f6653796e"

from collections import Counter
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Any
import json
import math
import re
import xml.etree.ElementTree as ET

import pandas as pd

HIDDEN_OWNER_ID = 477
EXCEL_CELL_TRUNCATION_THRESHOLD = 32750  # Excel's hard cell limit is 32767 chars; anything this close is a truncation red flag.
# Real observed data (layout_group_view Jun25/Phase2 exports) tops out at exactly
# 32,759 chars - one char under the old 32,760 threshold, meaning the exact
# corruption this guard exists to catch was silently passing through. Lowered
# with margin so both re-checks (line ~600, ~658) actually fire on real cases.


@dataclass(frozen=True)
class TableConfig:
    key: tuple[str, ...]
    functional: tuple[str, ...]
    xml_fields: tuple[str, ...] = ()
    json_fields: tuple[str, ...] = ()
    audit: tuple[str, ...] = ("LastModifiedBy", "LastModifiedOn")
    scalar: tuple[str, ...] = ()
    display_candidates: tuple[str, ...] = ()
    aliases: tuple[tuple[str, tuple[str, ...]], ...] = ()
    hidden_owner: int = HIDDEN_OWNER_ID  # OwnerID value that is compared normally but suppressed from display


TABLE_CONFIGS: dict[str, TableConfig] = {
    "pmr": TableConfig(
        key=("RuleID",),
        functional=("FilterExpression", "MandatoryFieldList"),
        xml_fields=("FilterExpression", "MandatoryFieldList"),
        scalar=("FiredOption",),
        display_candidates=("RuleName", "RuleDescription", "Name"),
    ),
    "alert_rule": TableConfig(
        key=("OwnerId", "RuleId"),
        functional=("FilterCondition", "FieldColorMapping"),
        xml_fields=("FilterCondition",),
        scalar=("FieldColorMapping",),
        display_candidates=("RuleName", "RuleDescription", "Name", "RuleId"),
    ),
    "process": TableConfig(
        key=("OwnerID", "ProcessID"),
        functional=("MappingXML", "GeographyMappingFields", "AdditionalSettings"),
        xml_fields=("MappingXML", "GeographyMappingFields"),
        json_fields=("AdditionalSettings",),
        display_candidates=("ProcessName", "Name", "Process"),
        aliases=(("OwnerID", ("OwnerID", "Process")),),
    ),
    "translator_actions": TableConfig(
        key=("TranslatorID", "ActionID"),
        functional=("UIDMapping", "ActionXML", "NewToObjectMappingXML", "InputParamXML"),
        xml_fields=("UIDMapping", "ActionXML", "NewToObjectMappingXML", "InputParamXML"),
        audit=("LastModifiedBy", "LastModifiedOn"),
        display_candidates=("Name", "Description"),
        hidden_owner=0,
    ),
    "translators": TableConfig(
        key=("OwnerID", "TranslatorID"),
        functional=(),
        audit=("LastModifiedBy", "LastModifiedOn"),
        display_candidates=("Name", "Description"),
        hidden_owner=0,
    ),
    "cis_job": TableConfig(
        key=("OwnerID", "JobID"),
        functional=("DesignerXml",),
        xml_fields=("DesignerXml",),
        audit=("LastModifiedBy", "LastModifiedOn"),
        display_candidates=("JobName", "Description"),
        hidden_owner=0,
    ),
    "bre": TableConfig(
        key=("RuleId",),
        functional=("FilterCriteria", "MappingXml", "ApplyCriteria", "SourceExpression"),
        xml_fields=("FilterCriteria", "MappingXml", "ApplyCriteria", "SourceExpression"),
        audit=("LastmodifiedBy", "LastModifiedOn"),  # exact export casing - lowercase 'm', do not "fix"
        display_candidates=("RuleName", "Description"),
        hidden_owner=0,
    ),
    "rrd": TableConfig(
        key=("RuleID",),
        functional=("SourceExpression",),
        xml_fields=("SourceExpression",),
        audit=("LastModifiedBy", "LastModifiedOn"),
        display_candidates=("Name",),
        hidden_owner=0,
    ),
    "user_layout": TableConfig(
        key=("OwnerID", "LayoutID"),
        functional=(),  # no XML/JSON fields - rest of columns auto-diffed generically
        audit=("LastModifiedBy", "LastModifiedOn"),
        display_candidates=("Name", "Description"),
        hidden_owner=0,
    ),
    "assignment_rule": TableConfig(
        key=("UniqueID",),  # independently unique in both exports - no composite needed
        functional=("SourceExpression", "AssignmentExpression", "MappingXML", "OperationsXML", "AdditionalField"),
        xml_fields=("SourceExpression", "AssignmentExpression", "MappingXML", "OperationsXML", "AdditionalField"),
        audit=("LastModifiedBy", "RuleLastmodifiedOn"),
        display_candidates=("Name",),
        hidden_owner=0,
    ),
    "template_master": TableConfig(
        key=("TemplateID",),  # independently unique in both exports - no composite needed
        functional=("Filters", "XMLExpression", "AttachmentCriteria"),
        xml_fields=("Filters", "XMLExpression", "AttachmentCriteria"),
        audit=("LastModifiedBy", "LastModifiedOn"),
        display_candidates=("TemplateName", "Description"),
        hidden_owner=0,
    ),
    "layout_group_view": TableConfig(
        # No single/independent PK is safe here: UniqueID has real duplicates
        # and, separately, collapses further under pandas dup-detection because
        # thousands of rows are blank UniqueID (Excel 32,767-char cell-limit
        # truncation splits oversized LayoutXML/DesignerXML into continuation
        # rows, which shifts XML fragments into unrelated columns).
        # This 7-field composite is the one candidate confirmed to have ZERO
        # duplicates across BOTH exports whenever every component is present -
        # verified directly against the Jun25/Phase2 exports (2,220 / 2,437
        # fully-keyed rows respectively, 0 collisions on either side).
        # Rows missing any component are corruption artifacts, not real
        # records; _key_valid() already drops them into the skipped-rows
        # counter instead of comparing them as if they were legitimate.
        key=("OwnerID", "ItemTypeID", "LayoutID", "GroupId", "LayoutType", "ViewType", "RowIndex"),
        functional=("LayoutXML", "DesignerXML", "BindingFields", "RedirectTo", "StateID", "IsHide", "FormMode"),
        xml_fields=("LayoutXML", "DesignerXML"),
        json_fields=("DesignerJSON",),  # observed empty in both exports; wired for when it isn't
        # LastModifiedByType rides along as audit/system metadata (sentinel
        # values like -1 observed) - excluded from the functional diff same
        # as LastModifiedBy/LastModifiedOn.
        audit=("LastModifiedBy", "LastModifiedOn", "LastModifiedByType"),
        display_candidates=(),  # no Name/Description column on this table
        hidden_owner=0,  # OwnerID=0 is the dominant system/default owner here, same convention as translator_actions/cis_job
    ),
}


def config_for(module: str) -> TableConfig:
    key = module.strip().lower().replace(" ", "_")
    aliases = {
        "alert": "alert_rule", "alertrule": "alert_rule", "processes": "process",
        "business_rule_enforcement": "bre", "businessruleenforcement": "bre",
        "translatoraction": "translator_actions", "translatoractions": "translator_actions",
        "translator": "translators", "cisjob": "cis_job", "cis-job": "cis_job",
    }
    key = aliases.get(key, key)
    if key not in TABLE_CONFIGS:
        raise ValueError(f"Unknown module: {module}")
    return TABLE_CONFIGS[key]


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if isinstance(value, float) and math.isnan(value):
            return True
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def clean_scalar(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
    # Some exports (e.g. layout_group_view) write literal "NULL" text instead
    # of leaving the cell blank. Normalize that to a real null so it compares
    # equal to genuinely blank/NaN cells instead of registering as a diff.
    if isinstance(value, str) and value.strip().upper() == "NULL":
        return None
    return value


def text(value: Any) -> str:
    value = clean_scalar(value)
    return "" if value is None else str(value).strip()


def display_value(value: Any, field: str = "") -> str:
    value = clean_scalar(value)
    if value is None:
        return "Not recorded"
    if field.lower().endswith("on") or field.lower().endswith("date"):
        try:
            dt = pd.to_datetime(value)
            if not pd.isna(dt):
                return dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            pass
    return str(value).strip()


def scalar_equal(a: Any, b: Any) -> bool:
    a, b = clean_scalar(a), clean_scalar(b)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return float(a) == float(b)
    except Exception:
        pass
    return str(a).strip() == str(b).strip()


def normalize_list(value: Any) -> str:
    if value is None:
        return ""
    parts = [x.strip() for x in str(value).split(",") if x.strip()]
    normalized = []
    for part in parts:
        part = re.sub(r"^(\d{1,2}/\d{1,2}/\d{4})\s+00:00:00(?:\.0+)?$", r"\1", part)
        normalized.append(part)
    def key(x: str):
        try:
            return (0, int(x), x)
        except ValueError:
            return (1, x)
    return ",".join(sorted(normalized, key=key))


def parse_xml(value: Any) -> ET.Element | None:
    raw = text(value)
    if not raw:
        return None
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def normalize_xml_element(elem: ET.Element) -> ET.Element:
    attrs = {}
    for k, v in sorted(elem.attrib.items()):
        attrs[k] = normalize_list(v) if k.lower() in {"value", "values"} else str(v).strip()
    elem.attrib.clear(); elem.attrib.update(attrs)
    if elem.text:
        elem.text = elem.text.strip()
    for child in list(elem):
        normalize_xml_element(child)
    return elem


def canonical_xml(root: ET.Element | None, field: str) -> ET.Element | None:
    if root is None:
        return None
    root = normalize_xml_element(deepcopy(root))

    if field in {"FilterExpression", "FilterCondition"}:
        def sig(e: ET.Element):
            return (e.tag, e.attrib.get("fieldname", ""), e.attrib.get("field", ""), e.attrib.get("op", ""), normalize_list(e.attrib.get("value", "")))
        def rec(node: ET.Element):
            for child in list(node): rec(child)
            expressions = [c for c in node if c.tag in {"expression", "condition", "FilterCondition"}]
            if len(expressions) > 1:
                others = [c for c in node if c not in expressions]
                expressions.sort(key=sig)
                node[:] = others + expressions
        rec(root)
    elif field in {"MandatoryFieldList", "GeographyMappingFields"}:
        def sig(e: ET.Element):
            return (e.tag, tuple(sorted(e.attrib.items())), (e.text or "").strip())
        def rec(node: ET.Element):
            for child in list(node): rec(child)
            # Treat repeated leaf mapping/mandatory entries as a set-like collection.
            elems = [c for c in node if len(c) == 0]
            if len(elems) > 1:
                others = [c for c in node if c not in elems]
                elems.sort(key=sig)
                node[:] = others + elems
        rec(root)
    return root


def xml_string(root: ET.Element | None) -> str:
    return "" if root is None else ET.tostring(root, encoding="unicode", short_empty_elements=True)


def json_canonical(value: Any) -> tuple[bool, Any, str | None]:
    raw = text(value)
    if not raw:
        return True, None, None
    try:
        obj = json.loads(raw)
        return True, obj, None
    except Exception as exc:
        return False, None, str(exc)


def compare_json(a: Any, b: Any, field: str) -> dict:
    ok_a, obj_a, err_a = json_canonical(a)
    ok_b, obj_b, err_b = json_canonical(b)
    if not ok_a or not ok_b:
        return {
            "changed": not scalar_equal(a, b),
            "summary": "JSON could not be parsed; raw value changed" if not scalar_equal(a, b) else "No change",
            "changes": [] if scalar_equal(a, b) else [{"kind": "changed", "path": field, "detail": "Invalid JSON / raw value changed", "source": display_value(a), "target": display_value(b)}],
            "inconclusive": True,
        }
    if obj_a == obj_b:
        return {"changed": False, "summary": "No change", "changes": []}
    return {"changed": True, "summary": f"{field} changed", "changes": [{"kind": "changed", "path": field, "detail": "JSON structure/value changed", "source": display_value(a), "target": display_value(b)}]}


def _token_set(value: str) -> set[str]:
    return {x.strip() for x in str(value).split(",") if x.strip()}


def compare_xml(a: Any, b: Any, field: str) -> dict:
    raw_a, raw_b = text(a), text(b)
    root_a, root_b = parse_xml(a), parse_xml(b)
    if not raw_a and not raw_b:
        return {"changed": False, "summary": "No change", "changes": []}
    # Alert Rule uses -1 as an intentional FilterCondition sentinel, not malformed XML.
    if field == "FilterCondition" and (raw_a == "-1" or raw_b == "-1"):
        if scalar_equal(a, b):
            return {"changed": False, "summary": "No change", "changes": []}
        return {"changed": True, "summary": "FilterCondition sentinel/value changed", "changes": [{"kind": "changed", "path": field, "detail": "Sentinel/value changed", "source": display_value(a), "target": display_value(b)}]}
    if root_a is None or root_b is None:
        # Blank ↔ valid XML is a legitimate functional difference. Only a
        # non-empty value that fails XML parsing is a data-quality anomaly.
        if not raw_a and root_b is not None:
            return {"changed": True, "summary": f"{field} added to PROD", "changes": [{"kind": "added", "path": field, "detail": field, "source": None, "target": display_value(b, field)}]}
        if not raw_b and root_a is not None:
            return {"changed": True, "summary": f"{field} removed from PROD", "changes": [{"kind": "removed", "path": field, "detail": field, "source": display_value(a, field), "target": None}]}
        if scalar_equal(a, b):
            return {"changed": False, "summary": "No change", "changes": []}
        return {"changed": True, "summary": "Invalid XML / raw value changed", "changes": [{"kind": "changed", "path": field, "detail": "XML could not be parsed", "source": display_value(a), "target": display_value(b)}], "inconclusive": True}

    root_a = canonical_xml(root_a, field); root_b = canonical_xml(root_b, field)
    if xml_string(root_a) == xml_string(root_b):
        return {"changed": False, "summary": "No change", "changes": []}

    changes = []
    if field in {"FilterExpression", "FilterCondition"}:
        def conditions(root):
            result = {}
            for e in root.iter():
                if e.tag not in {"expression", "condition", "FilterCondition"}:
                    continue
                name = e.attrib.get("fieldname") or e.attrib.get("field") or e.attrib.get("name") or e.tag
                op = e.attrib.get("op") or e.attrib.get("operator") or ""
                val = normalize_list(e.attrib.get("value") or e.attrib.get("values") or (e.text or ""))
                result.setdefault(name, []).append((op, val))
            return result
        ca, cb = conditions(root_a), conditions(root_b)
        for name in sorted(set(ca) | set(cb)):
            av = ca.get(name, []); bv = cb.get(name, [])
            if not av:
                changes.append({"kind":"added","path":field,"detail":f"{name}: condition added","source":None,"target":str(bv)})
                continue
            if not bv:
                changes.append({"kind":"removed","path":field,"detail":f"{name}: condition removed","source":str(av),"target":None})
                continue
            aops, bops = sorted({x[0] for x in av}), sorted({x[0] for x in bv})
            if aops != bops:
                changes.append({"kind":"changed","path":field,"detail":f"{name}: operator changed","source":", ".join(aops),"target":", ".join(bops)})
            ats = set().union(*(_token_set(v) for _,v in av)) if av else set()
            bts = set().union(*(_token_set(v) for _,v in bv)) if bv else set()
            if ats - bts:
                changes.append({"kind":"removed","path":field,"detail":f"{name}: value removed","source":", ".join(sorted(ats-bts)),"target":None})
            if bts - ats:
                changes.append({"kind":"added","path":field,"detail":f"{name}: value added","source":None,"target":", ".join(sorted(bts-ats))})
    elif field == "MandatoryFieldList":
        def item(e):
            return (e.attrib.get("name") or e.attrib.get("fieldid") or (e.text or "")).strip()
        aa = {item(e) for e in root_a.iter() if e.tag == "MandatoryField" and item(e)}
        bb = {item(e) for e in root_b.iter() if e.tag == "MandatoryField" and item(e)}
        for x in sorted(aa-bb): changes.append({"kind":"removed","path":field,"detail":x,"source":x,"target":None})
        for x in sorted(bb-aa): changes.append({"kind":"added","path":field,"detail":x,"source":None,"target":x})
    else:
        changes.append({"kind":"changed","path":field,"detail":"XML structure/attributes changed","source":xml_string(root_a),"target":xml_string(root_b)})

    if not changes:
        changes.append({"kind":"changed","path":field,"detail":"XML changed","source":xml_string(root_a),"target":xml_string(root_b)})
    counts = Counter(x["kind"] for x in changes)
    summary = ", ".join(f"{counts[k]} {k}" for k in ("added","removed","changed") if counts[k])
    return {"changed": True, "summary": summary or "XML changed", "changes": changes}


def compare_mixed(a: Any, b: Any, field: str) -> dict:
    def classify(v):
        s = text(v)
        if not s:
            return "blank", None
        if s.startswith("<"):
            return "xml", parse_xml(s)
        if "," in s:
            return "list", normalize_list(s)
        return "scalar", s
    ta, va = classify(a); tb, vb = classify(b)
    if ta == tb == "xml":
        return compare_xml(a, b, field)
    if ta == tb == "list":
        if va == vb: return {"changed":False,"summary":"No change","changes":[]}
        aa, bb = _token_set(va), _token_set(vb)
        changes=[]
        for x in sorted(aa-bb): changes.append({"kind":"removed","path":field,"detail":"Value removed","source":x,"target":None})
        for x in sorted(bb-aa): changes.append({"kind":"added","path":field,"detail":"Value added","source":None,"target":x})
        return {"changed":True,"summary":f"{len(changes)} value changes","changes":changes}
    if ta == tb == "scalar":
        if scalar_equal(a,b): return {"changed":False,"summary":"No change","changes":[]}
        return {"changed":True,"summary":"Value changed","changes":[{"kind":"changed","path":field,"detail":"Scalar value changed","source":display_value(a),"target":display_value(b)}]}
    if scalar_equal(a,b): return {"changed":False,"summary":"No change","changes":[]}
    return {"changed":True,"summary":"Format/value changed","changes":[{"kind":"changed","path":field,"detail":f"Representation changed ({ta} → {tb})","source":display_value(a),"target":display_value(b)}]}


def field_compare(a: Any, b: Any, field: str, cfg: TableConfig) -> dict:
    if field in cfg.xml_fields:
        return compare_xml(a,b,field)
    if field in cfg.json_fields:
        return compare_json(a,b,field)
    if field == "FieldColorMapping":
        return compare_mixed(a,b,field)
    if scalar_equal(a,b):
        return {"changed":False,"summary":"No change","changes":[]}
    return {"changed":True,"summary":"Value changed","changes":[{"kind":"changed","path":field,"detail":"Value changed","source":display_value(a),"target":display_value(b)}]}


def _resolve_columns(df: pd.DataFrame, cfg: TableConfig) -> pd.DataFrame:
    """Normalize incoming Excel headers to the canonical schema.

    Matching is intentionally case-insensitive and whitespace-tolerant so
    exports such as OwnerId/OwnerID and RuleId/RuleID behave identically.
    Explicit aliases are applied first, followed by canonical-name matching.
    """
    df = df.copy()

    # First apply explicit aliases (for example legacy Process -> OwnerID).
    alias_lookup = {}
    for canonical, aliases in cfg.aliases:
        for alias in aliases:
            alias_lookup[str(alias).strip().casefold()] = canonical

    rename_map = {}
    used_targets = set()
    for original in df.columns:
        normalized = str(original).strip().casefold()
        if normalized in alias_lookup:
            target = alias_lookup[normalized]
            # Do not create duplicate canonical columns if both legacy and
            # canonical headers happen to be present. Prefer the canonical
            # header in that situation.
            if target not in used_targets and target not in df.columns:
                rename_map[original] = target
                used_targets.add(target)

    if rename_map:
        df = df.rename(columns=rename_map)

    # Then normalize every configured field name case-insensitively.
    config_fields = list(dict.fromkeys((*cfg.key, *cfg.functional, *cfg.audit)))
    canonical_by_lower = {str(c).strip().casefold(): c for c in config_fields}
    rename_map = {}
    occupied = set(df.columns)
    for original in df.columns:
        normalized = str(original).strip().casefold()
        target = canonical_by_lower.get(normalized)
        if target is None or original == target:
            continue
        # Avoid collisions such as having both OwnerId and OwnerID in the
        # same workbook. The already-canonical column wins.
        if target in occupied:
            continue
        rename_map[original] = target
        occupied.add(target)

    return df.rename(columns=rename_map)


def _required(cfg: TableConfig) -> list[str]:
    return list(dict.fromkeys((*cfg.key, *cfg.functional, *cfg.audit)))


def _diff_fields(cfg: TableConfig, dev_cols, prod_cols) -> list[str]:
    """Full set of fields to diff: declared functional fields, declared scalar
    fields (previously computed but never actually looped over — real bug),
    plus every other column present in BOTH files that isn't a key/audit
    field. This is what makes the tool catch drift in fields nobody
    explicitly configured, instead of only the 2-3 curated ones per table."""
    declared = list(dict.fromkeys((*cfg.functional, *cfg.scalar)))
    excluded = set(cfg.key) | set(cfg.audit)
    shared = [c for c in dev_cols if c in prod_cols and c not in excluded]
    auto = [c for c in shared if c not in declared]
    return list(dict.fromkeys((*declared, *auto)))


def _key_tuple(row: pd.Series, cfg: TableConfig):
    return tuple(clean_scalar(row[k]) for k in cfg.key)


def _key_valid(row: pd.Series, cfg: TableConfig) -> bool:
    return all(not is_missing(row[k]) and text(row[k]) != "" for k in cfg.key)


def _owner_value(row: pd.Series | None) -> Any:
    if row is None:
        return None
    for c in row.index:
        if str(c).strip().casefold() == "ownerid":
            return clean_scalar(row.get(c))
    return None


def _owner_is_hidden_477(row: pd.Series | None, cfg: TableConfig | None = None) -> bool:
    v = _owner_value(row)
    target = cfg.hidden_owner if cfg is not None else HIDDEN_OWNER_ID
    try:
        return v is not None and int(float(v)) == target
    except Exception:
        return False


def _display_name(row: pd.Series, cfg: TableConfig) -> str:
    for c in cfg.display_candidates:
        if c in row.index and text(row[c]): return display_value(row[c], c)
    # For PMR RuleID is intentionally useful even without RuleName.
    if "RuleID" in row.index: return display_value(row["RuleID"])
    if "ProcessID" in row.index: return display_value(row["ProcessID"])
    if "LayoutID" in row.index: return f"Layout {display_value(row['LayoutID'])}"
    return "Unnamed entry"


def _key_display(key: tuple, cfg: TableConfig, row: pd.Series | None = None) -> str:
    parts = []
    owner_hidden = _owner_is_hidden_477(row, cfg)
    for k, v in zip(cfg.key, key):
        if k.lower() == "ownerid" and owner_hidden:
            continue
        parts.append(f"{k}: {display_value(v, k)}")
    return " · ".join(parts)


def _audit(row: pd.Series | None, cfg: TableConfig) -> dict:
    return {
        "last_modified_by": display_value(row.get(cfg.audit[0]), cfg.audit[0]) if row is not None and cfg.audit[0] in row.index else "Not recorded",
        "last_modified_on": display_value(row.get(cfg.audit[1]), cfg.audit[1]) if row is not None and cfg.audit[1] in row.index else "Not recorded",
    }


def _field_dq_reason(field: str, value: Any, cfg: TableConfig) -> str | None:
    """Same corruption rules as _dq_reasons, but scoped to a single field/value
    so a bad cell only takes that one field out of the diff — the row's other
    fields still get compared normally."""
    raw = text(value)
    if field in cfg.xml_fields:
        if field == "FilterCondition" and raw == "-1":
            return None
        if raw and parse_xml(raw) is None:
            return f"{field} contains invalid XML"
        return None
    if field == "FieldColorMapping":
        if raw.startswith("<") and parse_xml(raw) is None:
            return f"{field} contains invalid XML"
        return None
    if field in cfg.json_fields:
        if raw:
            ok, _, _ = json_canonical(raw)
            if not ok:
                return f"{field} contains invalid JSON"
        return None
    if field in ("AppliesTo", "DisplayOrder") and cfg.key == ("OwnerId", "RuleId"):
        is_date = isinstance(value, (pd.Timestamp,)) or bool(re.match(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}(?:\s|$)", raw))
        if is_date:
            return f"{field} contains date-corrupted value"
        return None
    if field == "SchemeProExcludedStatusCode" and cfg.key == ("OwnerID", "ProcessID"):
        huge_numeric = False
        try:
            huge_numeric = abs(float(value)) >= 1e20
        except (TypeError, ValueError):
            pass
        if (raw and re.search(r"[eE][+-]?\d+", raw)) or huge_numeric:
            return "SchemeProExcludedStatusCode contains scientific-notation garbage"
    # Generic Excel export-truncation guard: any long text field sitting at/near
    # Excel's 32,767-char per-cell limit was very likely clipped mid-content on
    # export (seen for real in cis_job.DesignerXml and template_master.Body/PDFText).
    if len(raw) >= EXCEL_CELL_TRUNCATION_THRESHOLD:
        return f"{field} is at/near Excel's cell character limit - likely truncated on export"
    return None


def _dq_reasons(row: pd.Series, cfg: TableConfig, side: str) -> list[str]:
    reasons=[]
    # Generic invalid XML is a DQ issue. Blank XML is legitimate and is not an anomaly.
    for field in cfg.xml_fields:
        raw=text(row.get(field))
        if field == "FilterCondition" and raw == "-1":
            continue
        if raw and parse_xml(raw) is None:
            # PMR's known 155983 garbage and any equivalent malformed XML land here.
            reasons.append(f"{field} contains invalid XML")
    if cfg.key == ("OwnerId", "RuleId"):
        for field in ("AppliesTo", "DisplayOrder"):
            if field in row.index:
                v=row.get(field)
                raw=text(v)
                is_date=isinstance(v, (pd.Timestamp,)) or bool(re.match(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}(?:\s|$)", raw))
                if is_date:
                    reasons.append(f"{field} contains date-corrupted value")

    # Mixed-format fields use their own parser. A value beginning with '<'
    # must be valid XML; comma lists and scalar values remain valid formats.
    for field in cfg.scalar:
        if field != "FieldColorMapping" or field not in row.index:
            continue
        raw=text(row.get(field))
        if raw.startswith("<") and parse_xml(raw) is None:
            reasons.append(f"{field} contains invalid XML")
    for field in cfg.json_fields:
        raw=text(row.get(field))
        if raw:
            ok,_,_=json_canonical(raw)
            if not ok: reasons.append(f"{field} contains invalid JSON")
    if cfg.key == ("OwnerID","ProcessID"):
        value=row.get("SchemeProExcludedStatusCode")
        raw=str(value).strip() if value is not None and not is_missing(value) else ""
        # Excel may materialize the known oversized status-code corruption as a
        # numeric cell, losing the literal "e+41" text. Treat either an
        # exponent-form string or an implausibly huge numeric status code as DQ.
        huge_numeric=False
        try:
            huge_numeric=abs(float(value)) >= 1e20
        except (TypeError, ValueError):
            pass
        if (raw and re.search(r"[eE][+-]?\d+", raw)) or huge_numeric:
            reasons.append("SchemeProExcludedStatusCode contains scientific-notation garbage")
    # Generic Excel export-truncation guard across every column already
    # accounted for above - catches long free-text fields (Body, PDFText, etc.)
    # that aren't declared as xml_fields but can still be clipped on export.
    already = {r.split(" ", 1)[0] for r in reasons}
    for field in row.index:
        if field in already or field in cfg.key or field in cfg.audit:
            continue
        raw = text(row.get(field))
        if len(raw) >= EXCEL_CELL_TRUNCATION_THRESHOLD:
            reasons.append(f"{field} is at/near Excel's cell character limit - likely truncated on export")
    return reasons



def _row_payload(row: pd.Series, cfg: TableConfig, status: str, reasons=None, side: str | None = None) -> dict:
    key = _key_tuple(row, cfg)
    owner = _owner_value(row)
    result = {
        "key": list(key),
        "key_display": _key_display(key, cfg, row),
        "status": status,
        "name": _display_name(row, cfg),
        "owner_id": owner,
        "owner_hidden": _owner_is_hidden_477(row, cfg),
        "audit": _audit(row, cfg),
    }
    if side:
        result["side"] = side
    if reasons:
        result["dq_reasons"] = list(reasons)
    return result


def _field_value(row: pd.Series | None, field: str) -> str:
    if row is None:
        return "Not present"
    return display_value(row.get(field), field)


def _environment_values(dev_row: pd.Series | None, prod_row: pd.Series | None, cfg: TableConfig, fields: list[str]) -> dict:
    return {
        "dev": {f: _field_value(dev_row, f) for f in fields},
        "prod": {f: _field_value(prod_row, f) for f in fields},
    }


def _audit_changes(dev_row: pd.Series | None, prod_row: pd.Series | None, cfg: TableConfig) -> list[dict]:
    if dev_row is None or prod_row is None:
        return []
    out = []
    for f in cfg.audit:
        a = dev_row.get(f) if f in dev_row.index else None
        b = prod_row.get(f) if f in prod_row.index else None
        if not scalar_equal(a, b):
            out.append({"field": f, "source": display_value(a, f), "target": display_value(b, f)})
    return out


def _make_change(field: str, diff: dict) -> dict:
    return {
        "field": field,
        "type": "VALUE" if field not in {"FilterExpression","MandatoryFieldList","FilterCondition","MappingXML","GeographyMappingFields","AdditionalSettings","FieldColorMapping"} else "STRUCTURED",
        "summary": diff["summary"],
        "source": display_value(diff.get("changes", [{}])[0].get("source")) if diff.get("changes") else "Not recorded",
        "target": display_value(diff.get("changes", [{}])[0].get("target")) if diff.get("changes") else "Not recorded",
        "details": diff.get("changes", []),
    }


def _natural_sort_part(value: Any) -> tuple:
    """Sort key for one key-tuple element: numeric strings sort as numbers
    (10 < 11 < 17 < 23 < 100 ...) instead of lexicographically ("10" < "100" < "11"),
    while non-numeric values still sort safely and consistently as text."""
    s = str(value)
    try:
        return (0, float(s), "")
    except (TypeError, ValueError):
        return (1, 0.0, s.lower())


def _read_table(path: str) -> pd.DataFrame:
    """CSV export doesn't hit Excel's 32,767-char-per-cell limit the way
    .xlsx does, so it's the recommended fix for the truncation/corruption
    this module works around elsewhere. Read by extension, not by assuming
    Excel - keep_default_na=False + na_values=[''] matches read_excel's
    default blank handling so downstream is_missing()/text() behave the same
    regardless of which format was uploaded."""
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=True, na_values=[""])
    return pd.read_excel(path)


def compare_files(module: str, dev_file: str, prod_file: str, dev_label: str | None = None, prod_label: str | None = None) -> dict:
    cfg = config_for(module)
    try:
        dev = _read_table(dev_file)
        prod = _read_table(prod_file)
    except Exception as exc:
        raise ValueError(f"Unable to read file: {exc}") from exc

    dev = _resolve_columns(dev, cfg)
    prod = _resolve_columns(prod, cfg)
    required = _required(cfg)
    md = [c for c in required if c not in dev.columns]
    mp = [c for c in required if c not in prod.columns]
    if md or mp:
        parts = []
        if md: parts.append("DEV missing: " + ", ".join(md))
        if mp: parts.append("PROD missing: " + ", ".join(mp))
        raise ValueError(f"{cfg_label(module)} — " + " | ".join(parts))

    skipped = {"dev": 0, "prod": 0}
    skip_reasons = {"dev": Counter(), "prod": Counter()}
    recovered_count = {"dev": 0, "prod": 0}
    dq = []
    diff_fields = _diff_fields(cfg, dev.columns, prod.columns)

    def prepare(df: pd.DataFrame, side: str):
        valid = []
        blank_rows = []
        for _, row in df.iterrows():
            blank_keys = [k for k in cfg.key if is_missing(row[k]) or text(row[k]) == ""]
            if blank_keys:
                blank_rows.append((row, blank_keys))
            else:
                valid.append(row)

        # Recovery pass: a row missing exactly ONE key field can sometimes be
        # safely un-skipped if the OTHER fields already uniquely identify it
        # on this side - i.e. the missing field wasn't actually needed to
        # disambiguate it. Confirmed real pattern in the field: the exporter
        # drops a single field's value whenever a large XML/JSON field on the
        # same physical row hits ~32,759 chars. We never guess field CONTENT -
        # we only skip the disambiguation role of that one field, and only
        # when doing so introduces zero collision risk.
        one_short = [(row, bk[0]) for row, bk in blank_rows if len(bk) == 1]
        proj_counts: dict[str, Counter] = {}
        for row, missing_field in one_short:
            proj = tuple(text(row[k]) for k in cfg.key if k != missing_field)
            proj_counts.setdefault(missing_field, Counter())[proj] += 1
        full_proj: dict[str, set] = {}
        for missing_field in proj_counts:
            full_proj[missing_field] = {
                tuple(text(r[k]) for k in cfg.key if k != missing_field) for r in valid
            }

        still_skipped = [(row, bk) for row, bk in blank_rows if len(bk) > 1]
        for row, missing_field in one_short:
            proj = tuple(text(row[k]) for k in cfg.key if k != missing_field)
            collides = proj_counts[missing_field][proj] > 1 or proj in full_proj[missing_field]
            if collides:
                still_skipped.append((row, [missing_field]))
                continue
            row = row.copy()
            row[missing_field] = f"__RECOVERED_{missing_field}__"
            row["_recovered_field"] = missing_field
            valid.append(row)
            recovered_count[side.lower()] += 1

        for row, blank_keys in still_skipped:
            skipped[side.lower()] += 1
            # tag whether this row also carries a near-32k-char field -
            # the Excel truncation signature - vs. blank keys with no
            # oversized field nearby (points to a genuinely broken export
            # rather than cell-limit truncation)
            truncated = any(
                len(text(row[c])) >= EXCEL_CELL_TRUNCATION_THRESHOLD
                for c in row.index if c not in cfg.key
            )
            tag = "likely_truncation" if truncated else "no_oversized_field"
            for k in blank_keys:
                skip_reasons[side.lower()][f"{k} blank ({tag})"] += 1
        return valid

    dev_rows = prepare(dev, "DEV")
    prod_rows = prepare(prod, "PROD")

    def make_map(rows, side):
        m = {}
        duplicates = []
        for row in rows:
            key = _key_tuple(row, cfg)
            if key in m:
                duplicates.append(key)
            m[key] = row
        if duplicates:
            shown = ", ".join(map(str, duplicates[:5]))
            raise ValueError(f"{cfg_label(module)} — {side} contains duplicate key(s): {shown}")
        return m

    dm = make_map(dev_rows, "DEV")
    pm = make_map(prod_rows, "PROD")
    all_keys = sorted(set(dm) | set(pm), key=lambda k: tuple(_natural_sort_part(x) for x in k))
    rules = []

    def _recovery_reason(d, p):
        f = (d is not None and d.get("_recovered_field")) or (p is not None and p.get("_recovered_field"))
        return f"{f} was missing in the source export; row matched using its other {len(cfg.key)-1} key fields (uniquely identified, no collision)" if f else None

    for key in all_keys:
        d, p = dm.get(key), pm.get(key)
        if d is None:
            item = _row_payload(p, cfg, "ADDED IN PROD")
            item["audit_only"] = False
            item["changes"] = []
            item["environment_values"] = _environment_values(None, p, cfg, diff_fields)
            item["dev_audit"] = _audit(None, cfg)
            item["prod_audit"] = _audit(p, cfg)
            item["audit_changes"] = []
            item["details"] = {"message": "Entry exists in PROD but not in DEV."}
            reasons = [r for f in diff_fields if (r := _field_dq_reason(f, p.get(f), cfg))]
            rec = _recovery_reason(None, p)
            if rec:
                reasons = [rec] + reasons
            item["data_quality_flags"] = len(reasons)
            if reasons:
                dq_item = _row_payload(p, cfg, "DATA_QUALITY", reasons, side="PROD")
                dq_item["raw_values"] = {f: {"dev": "Not present", "prod": _field_value(p, f)} for f in diff_fields}
                dq_item["field_issues"] = {
                    f: {"prod": r, "dev": None, "desc": r}
                    for f in diff_fields if (r := _field_dq_reason(f, p.get(f), cfg))
                }
                dq_item["dev_audit"] = _audit(None, cfg)
                dq_item["prod_audit"] = _audit(p, cfg)
                dq_item["audit_changes"] = []
                dq.append(dq_item)
            rules.append(item)
            continue

        if p is None:
            item = _row_payload(d, cfg, "REMOVED FROM PROD")
            item["audit_only"] = False
            item["changes"] = []
            item["environment_values"] = _environment_values(d, None, cfg, diff_fields)
            item["dev_audit"] = _audit(d, cfg)
            item["prod_audit"] = _audit(None, cfg)
            item["audit_changes"] = []
            item["details"] = {"message": "Entry exists in DEV but not in PROD."}
            reasons = [r for f in diff_fields if (r := _field_dq_reason(f, d.get(f), cfg))]
            rec = _recovery_reason(d, None)
            if rec:
                reasons = [rec] + reasons
            item["data_quality_flags"] = len(reasons)
            if reasons:
                dq_item = _row_payload(d, cfg, "DATA_QUALITY", reasons, side="DEV")
                dq_item["raw_values"] = {f: {"dev": _field_value(d, f), "prod": "Not present"} for f in diff_fields}
                dq_item["field_issues"] = {
                    f: {"dev": r, "prod": None, "desc": r}
                    for f in diff_fields if (r := _field_dq_reason(f, d.get(f), cfg))
                }
                dq_item["dev_audit"] = _audit(d, cfg)
                dq_item["prod_audit"] = _audit(None, cfg)
                dq_item["audit_changes"] = []
                dq.append(dq_item)
            rules.append(item)
            continue

        changes = []
        row_dq_reasons = []
        row_dq_sides = set()
        row_field_issues = {}
        rec = _recovery_reason(d, p)
        if rec:
            row_dq_reasons.append(rec)
            row_dq_sides.add((d.get("_recovered_field") and "DEV") or "PROD")
        for field in diff_fields:
            dev_reason = _field_dq_reason(field, d.get(field), cfg)
            prod_reason = _field_dq_reason(field, p.get(field), cfg)
            if dev_reason or prod_reason:
                if dev_reason:
                    row_dq_reasons.append(dev_reason)
                    row_dq_sides.add("DEV")
                if prod_reason:
                    row_dq_reasons.append(prod_reason)
                    row_dq_sides.add("PROD")
                desc = " & ".join(filter(None, [dev_reason, prod_reason]))
                row_field_issues[field] = {"dev": dev_reason, "prod": prod_reason, "desc": desc}
                continue  # corrupted field skipped, row still diffs its other fields below
            diff = field_compare(d.get(field), p.get(field), field, cfg)
            if diff.get("inconclusive"):
                continue
            if diff["changed"]:
                changes.append(_make_change(field, diff))

        if row_dq_reasons:
            dq_item = _row_payload(p, cfg, "DATA_QUALITY", list(dict.fromkeys(row_dq_reasons)),
                                    side=" & ".join(sorted(row_dq_sides)))
            raw_fields = list(dict.fromkeys((*diff_fields, "AppliesTo", "DisplayOrder", "SchemeProExcludedStatusCode")))
            dq_item["raw_values"] = {
                field: {"dev": _field_value(d, field), "prod": _field_value(p, field)}
                for field in raw_fields if field in d.index or field in p.index
            }
            dq_item["field_issues"] = row_field_issues
            dq_item["dev_audit"] = _audit(d, cfg)
            dq_item["prod_audit"] = _audit(p, cfg)
            dq_item["audit_changes"] = []
            dq.append(dq_item)

        audit_changes = _audit_changes(d, p, cfg)
        audit_only = not changes and bool(audit_changes)
        status = "MODIFIED IN PROD" if changes else "UNCHANGED"
        item = _row_payload(p, cfg, status)
        item["audit_only"] = audit_only
        item["changes"] = changes
        item["audit_changes"] = audit_changes
        item["data_quality_flags"] = len(row_dq_reasons)
        item["dev_audit"] = _audit(d, cfg)
        item["prod_audit"] = _audit(p, cfg)
        item["environment_values"] = _environment_values(d, p, cfg, diff_fields)
        item["details"] = {
            "message": "Functional configuration changed in PROD." if changes else ("Only audit metadata changed." if audit_only else "No functional difference.")
        }
        rules.append(item)

    counts = Counter(r["status"] for r in rules)
    summary = {
        "total": len(rules),
        "modified": counts["MODIFIED IN PROD"],
        "added": counts["ADDED IN PROD"],
        "removed": counts["REMOVED FROM PROD"],
        "unchanged": counts["UNCHANGED"],
        "audit_only": sum(1 for r in rules if r.get("audit_only")),
        "data_quality": len(dq),
        "skipped_dev": skipped["dev"],
        "skipped_prod": skipped["prod"],
        "skipped_dev_reasons": dict(skip_reasons["dev"].most_common()),
        "skipped_prod_reasons": dict(skip_reasons["prod"].most_common()),
        "recovered_dev": recovered_count["dev"],
        "recovered_prod": recovered_count["prod"],
        "dq_total": len(dq),
    }

    return {
        "module": module,
        "module_label": cfg_label(module),
        "dev_label": dev_label or "DEV — Phase 2",
        "prod_label": prod_label or "PROD — Jun25",
        "key_fields": list(cfg.key),
        "functional_fields": diff_fields,
        "audit_fields": list(cfg.audit),
        "summary": summary,
        "rules": rules,
        "data_quality": dq,
        "_engine_seal": __engine_seal__,
    }


def cfg_label(module: str) -> str:
    return {
        "pmr": "PMR", "alert_rule": "Alert Rule", "process": "Process",
        "translator_actions": "Translator Actions", "translators": "Translators",
        "cis_job": "CIS Job", "bre": "BRE", "rrd": "RRD", "user_layout": "User Layout",
        "assignment_rule": "Assignment Rule", "template_master": "Template Master",
        "layout_group_view": "Layout Group View",
    }.get(module, module)

