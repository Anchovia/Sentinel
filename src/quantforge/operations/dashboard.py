"""Dependency-free server-rendered operations dashboard."""

from html import escape

from pydantic import BaseModel

from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.operations.models import DashboardSnapshot


def _value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "예" if value else "아니요"
    if isinstance(value, (tuple, list)):
        return ", ".join(_value(item) for item in value) or "—"
    return str(value)


def _table(title: str, rows: tuple[BaseModel, ...]) -> str:
    if not rows:
        return (
            f"<section><h2>{escape(title)}</h2>"
            "<p class='empty'>표시할 항목이 없습니다.</p></section>"
        )
    payloads = [row.model_dump(mode="json") for row in rows]
    columns = tuple(payloads[0])
    head = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(_value(payload[column]))}</td>" for column in columns)
        + "</tr>"
        for payload in payloads
    )
    return (
        f"<section><h2>{escape(title)}</h2><div class='table-wrap'><table>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>"
    )


def render_dashboard(snapshot: DashboardSnapshot) -> str:
    payload = snapshot.model_dump(mode="json")
    assert_runtime_export_safe(payload)
    overview = snapshot.overview.model_dump(mode="json")
    overview_cards = "".join(
        f"<div class='card'><span>{escape(name)}</span>"
        f"<strong>{escape(_value(value))}</strong></div>"
        for name, value in overview.items()
    )
    sections = "".join(
        (
            _table("Markets", snapshot.markets),
            _table("Positions", snapshot.positions),
            _table("Orders", snapshot.orders),
            _table("Strategies", snapshot.strategies),
            _table("Models", snapshot.models),
            _table("System", (snapshot.system,)),
            _table("Incidents", snapshot.incidents),
        )
    )
    generated = escape(snapshot.generated_at_utc.isoformat())
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>QuantForge Operations</title><style>
:root{{--bg:#0b1020;--panel:#141b2d;--line:#28334b;--text:#edf2ff;--muted:#9ba9c4;--accent:#71d6b4}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}}h1{{margin:0}}.stamp,.empty{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;
margin:20px 0}}
.card,section{{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:14px}}
.card span{{display:block;color:var(--muted);font-size:12px}}
.card strong{{display:block;margin-top:7px;color:var(--accent)}}
section{{margin-top:14px}}h2{{font-size:16px;margin:0 0 10px}}.table-wrap{{overflow:auto}}
table{{border-collapse:collapse;width:100%;white-space:nowrap}}
th,td{{padding:8px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--muted);font-size:12px}}@media(max-width:600px){{main{{padding:14px}}}}
</style></head><body><main><h1>QuantForge Operations</h1>
<p class="stamp">읽기 전용 · 생성 시각 {generated}</p>
<div class="cards">{overview_cards}</div>{sections}
</main></body></html>"""
