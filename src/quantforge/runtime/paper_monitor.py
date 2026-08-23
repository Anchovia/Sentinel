"""Self-contained Korean read-only monitor for the public paper runtime."""

# ruff: noqa: E501 -- the self-contained HTML/CSS template keeps browser markup readable.

import os
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from quantforge.operations.exports import assert_runtime_export_safe
from quantforge.operations.models import DashboardSnapshot, HealthState, MarketView

if TYPE_CHECKING:
    from quantforge.runtime.paper_supervisor import PaperRuntimeSnapshot
    from quantforge.runtime.realtime_decision import RealtimePaperDecisionSnapshot
    from quantforge.runtime.realtime_pipeline import RealtimePipelineSnapshot
    from quantforge.runtime.universe_scanner import RealtimeUniverseSnapshot


def _number(value: int | float | Decimal, *, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}"


def _bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            decimals = 0 if unit == "B" else 1
            return f"{amount:,.{decimals}f} {unit}"
        amount /= 1024
    return f"{value:,} B"


def _event_counts(snapshot: "PaperRuntimeSnapshot") -> str:
    labels = {"ticker": "현재가", "trade": "체결", "orderbook": "호가"}
    counts = dict(snapshot.event_counts)
    return "".join(
        f"<div class='mini'><span>{escape(labels.get(name, name))}</span>"
        f"<strong>{counts.get(name, 0):,}</strong></div>"
        for name in snapshot.streams
    )


def _recovery_label(snapshot: "RealtimePaperDecisionSnapshot") -> str:
    if snapshot.recovery_blocked:
        return "확인 필요"
    return {
        "NOT_CONFIGURED": "미설정",
        "NEW": "신규",
        "VERIFIED_CLEAN": "정상",
        "EMPTY_UNCLEAN_RECOVERED": "빈 상태 복구",
    }.get(snapshot.recovery_status.value, snapshot.recovery_status.value)


def _market_card(market: MarketView) -> str:
    quality = {
        HealthState.HEALTHY: ("정상", "ok"),
        HealthState.DEGRADED: ("지연", "warn"),
        HealthState.BLOCKED: ("차단", "bad"),
        HealthState.UNKNOWN: ("확인 중", "muted"),
    }[market.data_quality]
    coin = market.market.removeprefix("KRW-")
    return f"""
    <article class="market-card">
      <div class="market-head"><div><span class="eyebrow">{escape(market.market)}</span>
      <h2>{escape(coin)} 공개 시세</h2></div><span class="pill {quality[1]}">{quality[0]}</span></div>
      <div class="price">₩{_number(market.price)}</div>
      <div class="market-grid">
        <div><span>호가 차이</span><strong>{_number(market.spread_bps, decimals=2)} bps</strong></div>
        <div><span>최근 1분 체결</span><strong>{_number(market.trade_intensity)}건</strong></div>
        <div><span>24시간 거래대금</span><strong>₩{_number(market.turnover_24h_krw)}</strong></div>
        <div><span>호가 잔량 금액</span><strong>₩{_number(market.depth_krw)}</strong></div>
      </div>
    </article>"""


def render_paper_monitor(
    dashboard: DashboardSnapshot,
    runtime: "PaperRuntimeSnapshot",
    realtime: "RealtimePipelineSnapshot | None" = None,
    decision: "RealtimePaperDecisionSnapshot | None" = None,
    universe: "RealtimeUniverseSnapshot | None" = None,
) -> str:
    """Render only public-market and fail-closed collection information."""

    safe_payload = {
        "dashboard": dashboard.model_dump(mode="json"),
        "runtime": runtime.model_dump(mode="json", exclude={"raw_output", "policy_hash"}),
        "realtime": realtime.model_dump(mode="json") if realtime is not None else None,
        "decision": decision.model_dump(mode="json") if decision is not None else None,
        "universe": universe.model_dump(mode="json") if universe is not None else None,
    }
    assert_runtime_export_safe(safe_payload)
    state = {
        "STARTING": ("시작 중", "warn"),
        "RUNNING": ("수집 중", "ok"),
        "STOPPED": ("중지됨", "muted"),
        "FAILED": ("오류", "bad"),
    }[runtime.state.value]
    connected = ("연결됨", "ok") if runtime.websocket_connected else ("연결 안 됨", "bad")
    last_event = runtime.last_event_at_utc.isoformat() if runtime.last_event_at_utc else ""
    visible_markets = tuple(
        sorted(dashboard.markets, key=lambda market: market.turnover_24h_krw, reverse=True)[:5]
    )
    markets = "".join(_market_card(market) for market in visible_markets)
    if not markets:
        markets = "<div class='empty'>첫 공개 시세를 기다리고 있습니다.</div>"
    generated = runtime.updated_at_utc.isoformat()
    started = runtime.started_at_utc.isoformat()
    disk_free = (
        _bytes(runtime.disk_free_bytes) if runtime.disk_free_bytes is not None else "확인 중"
    )
    storage_limit = _bytes(runtime.storage_max_bytes) if runtime.storage_max_bytes else "미설정"
    deleted_files = runtime.storage_retention_deleted_files + runtime.storage_capacity_deleted_files
    processing_panel = (
        f"""<section class="panel"><h2>밀리초 처리</h2><div class="rows">
<div class="row"><span class="label">처리 지연 p50</span><strong>{realtime.processing_latency_p50_ms:.3f}ms</strong></div>
<div class="row"><span class="label">처리 지연 p95</span><strong>{realtime.processing_latency_p95_ms:.3f}ms</strong></div>
<div class="row"><span class="label">처리 지연 p99</span><strong>{realtime.processing_latency_p99_ms:.3f}ms</strong></div>
<div class="row"><span class="label">처리 예산 초과</span><strong>{realtime.processing_budget_breaches:,}건</strong></div>
<div class="row"><span class="label">현재 판단</span><strong class="warn">{realtime.decision_state.value}</strong></div>
</div></section>"""
        if realtime is not None
        else """<section class="panel"><h2>밀리초 처리</h2>
<p class="label">실시간 처리 코어를 기다리고 있습니다.</p></section>"""
    )
    universe_panel = (
        f"""<section class="panel"><h2>시장 범위</h2><div class="rows">
<div class="row"><span class="label">전체 원화마켓 감시</span><strong>{universe.monitored_market_count:,}개</strong></div>
<div class="row"><span class="label">집중 분석</span><strong>{len(universe.focused_markets):,}개</strong></div>
<div class="row"><span class="label">현재가 수신</span><strong>{universe.ticker_coverage_count:,}개</strong></div>
<div class="row"><span class="label">경보 제외</span><strong>{len(universe.warning_markets):,}개</strong></div>
<div class="row"><span class="label">집중 종목 교체</span><strong>{universe.focus_rotation_count:,}회</strong></div>
</div></section>"""
        if universe is not None
        else ""
    )
    paper_panel = (
        f"""<section class="panel"><h2>모의 판단</h2><div class="rows">
<div class="row"><span class="label">모델 검토</span><strong>{"승인됨" if decision.model_approval_valid else "대기 중"}</strong></div>
<div class="row"><span class="label">모의 주문</span><strong>{"허용" if decision.paper_order_simulation_enabled else "차단"}</strong></div>
<div class="row"><span class="label">재시작 복구</span><strong>{_recovery_label(decision)}</strong></div>
<div class="row"><span class="label">현재 상태</span><strong class="warn">{decision.decision_state.value}</strong></div>
<div class="row"><span class="label">전략 제안</span><strong>{decision.strategy_trade_proposals:,}건</strong></div>
<div class="row"><span class="label">모의 주문 / 체결</span><strong>{decision.paper_orders:,} / {decision.paper_fills:,}</strong></div>
<div class="row"><span class="label">모의 순손익</span><strong>{_number(decision.portfolios[0].net_pnl, decimals=0) if decision.portfolios else "0"}원</strong></div>
</div></section>"""
        if decision is not None
        else """<section class="panel"><h2>모의 판단</h2>
<p class="label">모의 판단 코어를 기다리고 있습니다.</p></section>"""
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="refresh" content="5"><title>QuantForge 공개 데이터 모니터</title><style>
:root{{--bg:#07111f;--panel:#0d1b2d;--panel2:#10243b;--line:#203954;--text:#eff7ff;
--muted:#8da7c0;--green:#53e0ad;--amber:#ffc96b;--red:#ff7c88;--blue:#72b7ff}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 15% 0,#102b45 0,
var(--bg) 42%);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{width:min(1180px,calc(100% - 32px));margin:auto;padding:34px 0 48px}}
header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:24px}}
h1,h2,p{{margin:0}}h1{{font-size:clamp(25px,4vw,38px);letter-spacing:-.04em}}
.sub,.label,.stamp,.eyebrow,.mini span,.market-grid span{{color:var(--muted)}}.sub{{margin-top:7px}}
.live{{display:flex;gap:8px;align-items:center;background:#091827;border:1px solid var(--line);
padding:8px 12px;border-radius:999px;white-space:nowrap}}.dot{{width:8px;height:8px;border-radius:50%;
background:var(--green);box-shadow:0 0 14px var(--green)}}.dot.bad{{background:var(--red)}}
.hero,.market-card,.panel,.safe{{background:linear-gradient(145deg,rgba(16,36,59,.96),
rgba(10,25,42,.96));border:1px solid var(--line);border-radius:18px;box-shadow:0 18px 45px #02091455}}
.hero{{padding:24px;display:grid;grid-template-columns:1.2fr 1fr;gap:24px;margin-bottom:16px}}
.status-line{{display:flex;align-items:center;gap:10px;margin:8px 0 17px}}.status-line strong{{font-size:28px}}
.pill{{font-size:12px;font-weight:800;padding:4px 9px;border-radius:999px;background:#15273a}}
.ok{{color:var(--green)}}.warn{{color:var(--amber)}}.bad{{color:var(--red)}}.muted{{color:var(--muted)}}
.totals{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.total,.mini{{background:#081725;
border:1px solid #1a344e;border-radius:12px;padding:13px}}.total strong,.mini strong{{display:block;
font-size:21px;margin-top:3px}}.events{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.market-card{{padding:22px;margin-bottom:16px}}.market-head{{display:flex;justify-content:space-between;
align-items:flex-start}}.eyebrow{{font-size:12px;font-weight:750;letter-spacing:.08em}}h2{{font-size:19px}}
.price{{font-size:clamp(30px,5vw,48px);font-weight:800;letter-spacing:-.04em;margin:17px 0}}
.market-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.market-grid div{{border-top:1px solid
var(--line);padding-top:11px}}.market-grid strong{{display:block;margin-top:3px}}
.columns{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}.panel,.safe{{padding:20px}}
.panel h2,.safe h2{{margin-bottom:14px}}.rows{{display:grid;gap:0}}.row{{display:flex;justify-content:
space-between;gap:20px;padding:10px 0;border-bottom:1px solid #1a3149}}.row:last-child{{border:0}}
.safe{{margin-top:16px;border-color:#1b684f;background:linear-gradient(145deg,#0b3029,#0a1c27)}}
.safe-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.safe-grid strong{{display:block;
color:var(--green);font-size:18px}}.stamp{{margin-top:18px;font-size:12px}}.empty{{padding:30px;
border:1px dashed var(--line);border-radius:18px;color:var(--muted);margin-bottom:16px}}
@media(max-width:760px){{header{{display:block}}.live{{display:inline-flex;margin-top:14px}}.hero,.columns{{grid-template-columns:1fr}}
.market-grid{{grid-template-columns:1fr 1fr}}.safe-grid{{grid-template-columns:1fr}}}}
@media(max-width:430px){{main{{width:min(100% - 20px,1180px);padding-top:20px}}.totals,.events{{grid-template-columns:1fr}}
.market-grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div><h1>공개 데이터 모니터</h1><p class="sub">업비트 공개 시세 수집 상태를 보여주는 읽기 전용 화면입니다.</p></div>
<div class="live"><span class="dot {"ok" if runtime.websocket_connected else "bad"}"></span>
<span>{connected[0]}</span></div></header>
<section class="hero"><div><span class="label">현재 상태</span><div class="status-line">
<strong class="{state[1]}">{state[0]}</strong><span class="pill">페이퍼 모드</span></div>
<div class="totals"><div class="total"><span class="label">누적 저장 행</span><strong>{runtime.retained_rows:,}</strong></div>
<div class="total"><span class="label">누적 파일</span><strong>{runtime.retained_files:,}</strong></div>
<div class="total"><span class="label">누적 용량</span><strong>{_bytes(runtime.retained_bytes)}</strong></div></div></div>
<div><span class="label">이번 실행에서 받은 메시지</span><div class="events">{_event_counts(runtime)}</div></div></section>
{universe_panel}
{markets}
<div class="columns"><section class="panel"><h2>수집 상태</h2><div class="rows">
<div class="row"><span class="label">마지막 데이터</span><strong><time id="event-age" data-utc="{escape(last_event)}">{escape(last_event or "대기 중")}</time></strong></div>
<div class="row"><span class="label">WebSocket</span><strong class="{connected[1]}">{connected[0]}</strong></div>
<div class="row"><span class="label">파서 오류</span><strong>{runtime.parser_errors:,}건</strong></div>
<div class="row"><span class="label">재연결</span><strong>{runtime.reconnects:,}회</strong></div>
<div class="row"><span class="label">중복 메시지</span><strong>{runtime.duplicate_messages:,}건</strong></div>
</div></section><section class="panel"><h2>보관 상태</h2><div class="rows">
<div class="row"><span class="label">저장 위치</span><strong>{escape(runtime.storage_label)}</strong></div>
<div class="row"><span class="label">보관 한도</span><strong>{runtime.storage_retention_days}일 / {storage_limit}</strong></div>
<div class="row"><span class="label">이번 실행 저장 행</span><strong>{runtime.committed_rows:,}</strong></div>
<div class="row"><span class="label">이번 실행 저장 파일</span><strong>{runtime.committed_files:,}</strong></div>
<div class="row"><span class="label">자동 압축 / 정리</span><strong>{runtime.storage_compacted_source_files:,} / {deleted_files:,}개</strong></div>
<div class="row"><span class="label">회수한 공간</span><strong>{_bytes(runtime.storage_reclaimed_bytes)}</strong></div>
<div class="row"><span class="label">남은 디스크</span><strong>{disk_free}</strong></div>
<div class="row"><span class="label">수집 시작</span><strong><time data-full="true" data-utc="{escape(started)}">{escape(started)}</time></strong></div>
<div class="row"><span class="label">화면 자동 갱신</span><strong>5초</strong></div>
</div></section>{processing_panel}{paper_panel}</div>
<section class="safe"><h2>안전 상태</h2><div class="safe-grid">
<div><span class="label">실제 주문</span><strong>완전 차단</strong></div>
<div><span class="label">API 인증</span><strong>사용 안 함</strong></div>
<div><span class="label">계좌 데이터</span><strong>접근 안 함</strong></div></div></section>
<p class="stamp">상태 기록 <time data-full="true" data-utc="{escape(generated)}">{escape(generated)}</time> · 원본 데이터는 화면에 노출하지 않습니다.</p>
</main><script>
const formatFull=(value)=>new Intl.DateTimeFormat('ko-KR',{{dateStyle:'medium',timeStyle:'medium'}}).format(new Date(value));
document.querySelectorAll('time[data-full]').forEach((node)=>{{if(node.dataset.utc)node.textContent=formatFull(node.dataset.utc);}});
const age=document.getElementById('event-age');if(age&&age.dataset.utc){{const seconds=Math.max(0,Math.floor((Date.now()-new Date(age.dataset.utc))/1000));age.textContent=seconds<60?`${{seconds}}초 전`:formatFull(age.dataset.utc);}}
</script></body></html>"""


def write_paper_monitor(
    dashboard: DashboardSnapshot,
    runtime: "PaperRuntimeSnapshot",
    output_root: Path,
    *,
    realtime: "RealtimePipelineSnapshot | None" = None,
    decision: "RealtimePaperDecisionSnapshot | None" = None,
    universe: "RealtimeUniverseSnapshot | None" = None,
) -> Path:
    """Atomically replace the local monitor so browser refreshes never see a partial file."""

    destination_dir = output_root / "ops"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "paper-monitor.html"
    temporary = destination_dir / f".paper-monitor.{uuid4().hex}.tmp"
    try:
        temporary.write_text(
            render_paper_monitor(dashboard, runtime, realtime, decision, universe),
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
