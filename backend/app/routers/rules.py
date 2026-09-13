"""审计规则配置 CRUD"""
import json

from fastapi import APIRouter, HTTPException

from ..database import db
from ..schemas import RuleCreate, RuleUpdate

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _serialize(rows):
    for r in rows:
        if isinstance(r.get("params"), str):
            r["params"] = json.loads(r["params"] or "{}")
        r["enabled"] = bool(r["enabled"])
    return rows


@router.get("")
def list_rules():
    rows = db.query("SELECT * FROM audit_rules ORDER BY id")
    return {"items": _serialize(rows)}


@router.get("/{rule_id}")
def get_rule(rule_id: int):
    row = db.query_one("SELECT * FROM audit_rules WHERE id = %s", (rule_id,))
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _serialize([row])[0]


@router.post("")
def create_rule(rule: RuleCreate):
    rid = db.insert(
        "INSERT INTO audit_rules (name, rule_type, event_type, description, params, enabled, severity) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (rule.name, rule.rule_type, rule.event_type, rule.description,
         json.dumps(rule.params, ensure_ascii=False), int(rule.enabled), rule.severity),
    )
    return get_rule(rid)


@router.put("/{rule_id}")
def update_rule(rule_id: int, rule: RuleUpdate):
    existing = db.query_one("SELECT * FROM audit_rules WHERE id = %s", (rule_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="规则不存在")

    fields, params = [], []
    data = rule.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k == "params":
            fields.append("params = %s")
            params.append(json.dumps(v, ensure_ascii=False))
        elif k == "enabled":
            fields.append("enabled = %s")
            params.append(int(v))
        else:
            fields.append(f"{k} = %s")
            params.append(v)
    params.append(rule_id)
    db.execute(f"UPDATE audit_rules SET {', '.join(fields)} WHERE id = %s", tuple(params))
    return get_rule(rule_id)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int):
    db.execute("DELETE FROM audit_rules WHERE id = %s", (rule_id,))
    return {"ok": True}
