#!/usr/bin/env python3
"""Tiny, dependency-free Codex reset watcher and LAN status page."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


FORECAST_URL = "https://codex-reset.com/api/forecast"
TIMELINE_URL = "https://codex-reset.com/api/timeline"
FEED_URL = "https://codex-reset.com/api/feed"
RADAR_SUMMARY_URL = "https://codexradar.com/current.json"
MODEL_INSIGHTS_URL = "https://codexradar.com/api/radar-insights?refresh=1"
MODEL_METRICS_URL = "https://codexradar.com/api/intelligence-efficiency-metrics?refresh=1"
FAST_HISTORY_URL = "https://codexradar.com/data/fast-radar-history.json"
POLL_SECONDS = max(120, int(os.environ.get("POLL_SECONDS", "600")))
PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
STATE_FILE = DATA_DIR / "state.json"
STATIC_FILE = Path(__file__).with_name("static") / "index.html"
USER_AGENT = "Dachun-Codex-Reset-Radar/0.1 (+LAN read-only watcher)"
FUTURE_RESET_PATTERN = re.compile(
    r"(?:\breset\b.{0,100}\b(?:tomorrow|monday|next\s+hour|soon|later\s+today|tonight)\b|"
    r"\b(?:tomorrow|monday|next\s+hour|soon|later\s+today|tonight)\b.{0,100}\breset\b)",
    re.IGNORECASE | re.DOTALL,
)
COMPLETED_RESET_PATTERN = re.compile(
    r"(?:\bbutton\b.{0,60}\balready\s+pressed\b|"
    r"\balready\s+(?:reset|resetted|completed)\b|"
    r"\breset\b.{0,60}\b(?:already\s+)?(?:done|completed)\b)",
    re.IGNORECASE | re.DOTALL,
)

state_lock = threading.Lock()
state: dict = {
    "service": "starting",
    "last_checked_at": None,
    "last_success_at": None,
    "next_check_at": None,
    "error": None,
    "forecast": None,
    "radar_summary": None,
    "model_radar": None,
    "fast_radar": None,
    "tibo_updates": [],
    "events": [],
    "new_event_ids": [],
    "seen_event_ids": [],
}

KNOWN_EVENT_ZH = {
    "2082317452755751098": "Tibo 已确认：ChatGPT Work 与 Codex 用户的用量限制已完成直接重置。",
    "2081940052154933696": "回到电脑后，Codex 与 ChatGPT Work 所有付费用户的用量限制已重置。",
    "2081899343091843463": "官方提前释放重置信号：用量重置将在几小时内到来。",
    "2081096447718723984": "在前一晚接近全球性的故障后，Codex 与 ChatGPT Work 用户获得用量重置。",
    "2079609157934886975": "达到 1000 万用户里程碑，付费用户获得新的用量重置，预计一小时内生效。",
    "2078320950488297917": "官方再次重置 Codex 与 ChatGPT Work 所有付费用户的用量限制。",
    "2077607697487188198": "达到 900 万活跃用户后再次重置，用量恢复至每周 100%。",
    "2077114635308986427": "达到 800 万活跃用户后全员重置，并继续暂停 5 小时限制。",
    "2076735790567338203": "达到 700 万活跃用户，每个账户新增一张可储备、可按需使用的重置卡。",
    "2076418567143408112": "50 万名用户新增可储备重置卡，并上线网页与移动端兑换功能。",
}

# The public feed is intentionally kept model-free.  These are the recent
# high-value Tibo posts that appear in the feed most often; keeping a small
# deterministic translation table lets the dashboard show useful Chinese
# content directly instead of making the user open X for every update.
TIBO_ZH_OVERRIDES = {
    "2102463847714247142": (
        "GPT-6 Sol 和 Luna 已经发布。它们在各方面都有显著提升，写作和整体"
        "“上手就知道”的体验质量也明显更好。我们还会永久下调 API 价格 50%，"
        "让更多新场景可用，也让订阅用户的额度更耐用。还有一件事：我们正在为"
        "所有 Plus、Pro 和 Business 用户账户加载一张可按需使用的储备重置卡。"
        "出发吧！"
    ),
    "2102254445082116335": (
        "女士们先生们……发动引擎！我们马上进入周二，我已经承诺周二会进行一次"
        "重置，还有其他事情。很快见。"
    ),
    "2101352781219258527": "好吧。但它仍然会在周二到来。",
    "2098685367058612394": "重置已全部传播。祝好梦。",
    "2098612714704891959": (
        "Astra 用户大家好。我们完成了一次重置，并针对近期反馈的质量问题做了"
        "快速更新；相关修复已经上线，今天午夜前还会有一次重置。"
    ),
    "2097752790177370535": (
        "今天早上，部分储备重置在 ChatGPT Work 和 Codex 中没有完全生效。"
        "所有在受影响时间窗口内使用过重置的人都会再获得一次，并收到道歉邮件。"
    ),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def event_to_chinese(event: dict) -> dict:
    event_id = str(event.get("id") or "")
    event_type = event.get("type") or "signal"
    if event_id in KNOWN_EVENT_ZH:
        summary_zh = KNOWN_EVENT_ZH[event_id]
    elif event_type == "credits":
        summary_zh = "发现可储备重置卡相关动态，具体适用范围请查看原帖。"
    elif event_type == "reset":
        summary_zh = "发现用量重置相关动态，中文摘要暂未收录，请查看原帖核对。"
    else:
        summary_zh = "发现新的 Codex 额度相关公开信号，请查看原帖核对。"
    return {
        "id": event_id,
        "date": event.get("date"),
        "type": event_type,
        "preview": bool(event.get("preview")),
        "url": event.get("url"),
        "summary_zh": summary_zh,
        "confidence": event.get("confidence"),
        "reason_tags": event.get("reason_tags") or [],
    }


def _fallback_tibo_content(signal: str, text: str) -> str:
    """Return a Chinese, model-free fallback for an unmapped feed item."""
    if signal == "已完成重置":
        return "Tibo 表示这次重置已经完成并已传播到账户。"
    if signal == "重置相关":
        return "Tibo 的这条动态与 Codex 用量重置有关，具体适用范围请以原帖和账户为准。"
    if signal == "Codex 相关":
        return "Tibo 的这条动态与 Codex 或模型有关，暂未形成新的明确重置承诺。"
    return "Tibo 的这条动态暂未发现新的明确重置承诺。"


def tweet_to_chinese(tweet: dict) -> dict:
    text = str(tweet.get("text") or "")
    lowered = text.lower()
    kind = tweet.get("kind") or "other"
    if COMPLETED_RESET_PATTERN.search(text):
        signal = "已完成重置"
        interpretation = "Tibo 表示重置今天已经执行；文中的明天指庆祝活动，不应重新开启未来重置窗口。"
    elif FUTURE_RESET_PATTERN.search(text):
        signal = "重置相关"
        interpretation = "Tibo 已明确预告即将重置，请打开原帖核对适用范围与具体生效时间。"
    elif "reset" in lowered and any(word in lowered for word in ("usage", "limit", "100%")):
        signal = "重置相关"
        interpretation = "这条动态提到用量或限制重置，建议打开原帖核对具体范围和生效时间。"
    elif kind in {"candidate", "signal", "banked", "limits"} or str(tweet.get("tibo_lane") or "") == "reset_related":
        signal = "重置相关"
        interpretation = "这条动态被上游标记为重置相关，建议打开原帖核对适用范围和生效时间。"
    elif kind == "codex":
        signal = "Codex 相关"
        interpretation = "这是 Codex 或模型相关动态，当前没有发现明确的用量重置承诺。"
    else:
        signal = "无重置信号"
        interpretation = "这是普通动态，当前没有发现明确的 Codex 重置、限额或用量承诺。"
    content_zh = (
        str(tweet.get("text_zh") or tweet.get("translation_zh") or "").strip()
        or TIBO_ZH_OVERRIDES.get(str(tweet.get("id") or ""))
        or _fallback_tibo_content(signal, text)
    )
    return {
        "id": str(tweet.get("id") or ""),
        "url": tweet.get("url"),
        "at": tweet.get("at"),
        "signal": signal,
        "interpretation_zh": interpretation,
        "content_zh": content_zh,
    }


def select_tibo_updates(tweets: list[dict], limit: int = 3) -> list[dict]:
    """Prefer reset-relevant posts while keeping the feed capped at three."""
    preferred_kinds = {"candidate", "signal", "banked", "codex", "limits"}
    preferred = [tweet for tweet in tweets if str(tweet.get("kind") or "") in preferred_kinds]
    if len(preferred) < limit:
        for tweet in tweets:
            if tweet in preferred or str(tweet.get("kind") or "") == "other":
                continue
            if str(tweet.get("tibo_lane") or "") == "reset_related":
                preferred.append(tweet)
            if len(preferred) >= limit:
                break
    pool = preferred or tweets
    return pool[:limit]


def adjudicate_forecast(payload: dict) -> dict:
    """Resolve obvious source-semantic conflicts before publishing status."""
    result = dict(payload)
    source_mode = str(payload.get("mode") or "")
    official = payload.get("official_signal") or {}
    summary = str(official.get("summary") or "")
    result["source_mode"] = source_mode

    if source_mode == "announced" and COMPLETED_RESET_PATTERN.search(summary):
        result["mode"] = "completed"
        result["adjudication"] = {
            "status": "completed",
            "trusted_announcement": False,
            "reason_zh": "动态说明重置今天已经执行；明天指庆祝活动，不能作为新的未来重置窗口。",
        }
    elif source_mode == "announced":
        result["adjudication"] = {
            "status": "announced",
            "trusted_announcement": True,
            "reason_zh": "上游检测到未来重置承诺，页面同时保留基础概率与信号置信度。",
        }
    else:
        result["adjudication"] = {
            "status": "model_only",
            "trusted_announcement": False,
            "reason_zh": "当前没有经过确认的未来重置承诺。",
        }
    return result


def prune_radar_summary(payload: dict) -> dict:
    model_iq = payload.get("model_iq") or {}
    return {
        "monitored_at": payload.get("monitored_at"),
        "prediction": payload.get("prediction") or {},
        "window": payload.get("window") or {},
        "tibo_presence": payload.get("tibo_presence") or {},
        "model_iq": {
            "updated_at": model_iq.get("updated_at"),
            "latest": model_iq.get("latest") or {},
            "quota_radar": model_iq.get("quota_radar") or {},
        },
        "source": "codexradar.com public summary",
    }


def _model_label(model: str) -> str:
    labels = {
        "gpt-6-astra": "GPT-6 Astra",
        "gpt-6-sol": "GPT-6 Sol",
        "gpt-6-luna": "GPT-6 Luna",
        "gpt-5.6-sol": "GPT-5.6 Sol",
        "gpt-5.6-terra": "GPT-5.6 Terra",
        "gpt-5.6-luna": "GPT-5.6 Luna",
        "gpt-5.5": "GPT-5.5",
    }
    if model in labels:
        return labels[model]
    cleaned = re.sub(r"^gpt-", "", model).replace("-", " ").strip()
    if model.lower().startswith("gpt-") and cleaned:
        parts = cleaned.split()
        return f"GPT-{parts[0]}" + (f" {' '.join(part.title() for part in parts[1:])}" if len(parts) > 1 else "")
    return cleaned.title() if cleaned else model


def _model_generation(model: str) -> tuple[int, int]:
    """Return the numeric GPT generation for display ordering."""
    match = re.match(r"^gpt-(\d+)(?:\.(\d+))?(?:-|$)", model.lower())
    if not match:
        return (-1, -1)
    return (int(match.group(1)), int(match.group(2) or -1))


def _is_stale(timestamp: str | None, hours: int = 6) -> bool:
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        return (utc_now() - parsed.astimezone(timezone.utc)).total_seconds() > hours * 3600
    except (TypeError, ValueError):
        return True


def build_model_radar(insights: dict, metrics: dict) -> dict:
    """Normalize public model feeds into the small /api/status contract."""
    metric_by_key = {
        (str(p.get("model")), str(p.get("effort"))): p
        for p in (metrics.get("points") or [])
    }
    source_model_order: dict[str, int] = {}
    rows = []
    for source_index, point in enumerate(insights.get("comprehensive_points") or []):
        model = str(point.get("model") or "")
        if not model:
            continue
        source_model_order.setdefault(model, len(source_model_order))
        effort = str(point.get("effort") or "")
        measured = metric_by_key.get((model, effort), {})
        rows.append((source_index, {
            "model": model,
            "model_label": _model_label(model),
            "effort": effort,
            "iq": point.get("iq"),
            "software_iq": point.get("software_iq"),
            "visual_iq": point.get("visual_iq"),
            "samples": point.get("samples"),
            "average_cost_usd": measured.get("average_price_usd"),
            "average_minutes": measured.get("average_minutes"),
            "runs_24h": measured.get("runs_24h"),
            "runs_48h": measured.get("runs_48h"),
        }))
    effort_order = {name: index for index, name in enumerate(("low", "medium", "high", "xhigh", "max", "ultra"))}
    rows.sort(key=lambda item: (
        -_model_generation(item[1]["model"])[0],
        -_model_generation(item[1]["model"])[1],
        source_model_order[item[1]["model"]],
        effort_order.get(item[1]["effort"], len(effort_order)),
        item[0],
    ))
    matrix = [row for _, row in rows]
    recommendations = []
    for group in insights.get("recommendations") or []:
        item = (group.get("items") or [{}])[0]
        if not item.get("model"):
            continue
        recommendations.append({
            "key": group.get("key"),
            "title": group.get("title"),
            "choice": f"{_model_label(str(item.get('model')))} · {item.get('effort')}",
            "iq": item.get("iq"),
        })
    samples = max([int(p.get("samples") or 0) for p in matrix] or [0])
    updated_at = insights.get("source_updated_at") or metrics.get("source_updated_at")
    return {
        "updated_at": updated_at,
        "matrix": matrix,
        "degradation_alerts": (insights.get("degradation_alerts") or {}).get("items") or [],
        "recommendations": recommendations,
        "health": {
            "source": "codexradar.com 公开众测接口",
            "updated_at": updated_at,
            "samples": samples,
            "runs_24h": metrics.get("runs_24h_total"),
            "runs_48h": metrics.get("runs_48h_total"),
            "stale": _is_stale(updated_at),
        },
    }


def build_fast_radar(payload: dict) -> dict:
    runs = payload.get("runs") or []
    latest_run = runs[-1] if runs else {}
    latest = []
    model_keys = []
    for run in runs[-76:]:
        for model in (run.get("models") or {}):
            if model not in model_keys:
                model_keys.append(model)
    history = {model: [] for model in model_keys}
    for run in runs[-76:]:
        for model in history:
            pair = (run.get("models") or {}).get(model) or {}
            standard, fast = pair.get("standard") or {}, pair.get("fast") or {}
            e2e, fast_e2e = standard.get("e2e_seconds"), fast.get("e2e_seconds")
            if e2e and fast_e2e:
                history[model].append({"at": run.get("measured_at"), "e2e_speedup": round(e2e / fast_e2e, 3)})
    for model, pair in (latest_run.get("models") or {}).items():
        standard, fast = pair.get("standard") or {}, pair.get("fast") or {}
        if not standard or not fast:
            continue
        e2e = standard.get("e2e_seconds") or 0
        fast_e2e = fast.get("e2e_seconds") or 0
        ttft = standard.get("ttft_seconds") or 0
        fast_ttft = fast.get("ttft_seconds") or 0
        tps = standard.get("tps") or 0
        fast_tps = fast.get("tps") or 0
        latest.append({
            "model": model,
            "model_label": _model_label(str(model)),
            "standard_e2e": e2e,
            "fast_e2e": fast_e2e,
            "e2e_speedup": round(e2e / fast_e2e, 3) if fast_e2e else None,
            "ttft_reduction_percent": round((ttft - fast_ttft) / ttft * 100, 1) if ttft else None,
            "tps_speedup": round(fast_tps / tps, 3) if tps else None,
        })
    return {
        "updated_at": payload.get("updated_at"),
        "sample_count": len(runs),
        "stale": _is_stale(payload.get("updated_at"), 48),
        "latest": latest,
        "history": history,
    }


def load_state() -> None:
    global state
    try:
        saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            state.update(saved)
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        state["error"] = "本地状态文件损坏，已重新建立。"


def save_state() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(STATE_FILE)


def refresh() -> None:
    checked_at = iso_now()
    try:
        forecast = adjudicate_forecast(fetch_json(FORECAST_URL))
        timeline = fetch_json(TIMELINE_URL)
        events = timeline.get("events", [])
        if not isinstance(events, list):
            raise ValueError("timeline.events is not a list")

        optional_errors = []
        radar_summary = None
        model_radar = None
        fast_radar = None
        tibo_updates = None
        try:
            radar_summary = prune_radar_summary(fetch_json(RADAR_SUMMARY_URL))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            optional_errors.append(f"原站公开摘要：{type(exc).__name__}")
        try:
            model_radar = build_model_radar(fetch_json(MODEL_INSIGHTS_URL), fetch_json(MODEL_METRICS_URL))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            optional_errors.append(f"模型众测：{type(exc).__name__}")
        try:
            fast_radar = build_fast_radar(fetch_json(FAST_HISTORY_URL))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            optional_errors.append(f"Fast 历史：{type(exc).__name__}")
        try:
            feed = fetch_json(FEED_URL)
            tibo_updates = [
                tweet_to_chinese(tweet)
                for tweet in select_tibo_updates(feed.get("tweets") or [], limit=3)
            ]
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            optional_errors.append(f"Tibo 公开动态：{type(exc).__name__}")

        current_ids = [str(event.get("id")) for event in events if event.get("id")]
        with state_lock:
            previous_ids = set(state.get("seen_event_ids") or [])
            # The first successful run establishes a baseline; it does not label
            # the entire historical timeline as newly discovered.
            new_ids = [] if not previous_ids else [
                event_id for event_id in current_ids if event_id not in previous_ids
            ]
            merged_ids = list(dict.fromkeys(current_ids + list(previous_ids)))[:500]
            state.update(
                {
                    "service": "ok",
                    "last_checked_at": checked_at,
                    "last_success_at": iso_now(),
                    "next_check_at": datetime.fromtimestamp(
                        time.time() + POLL_SECONDS, tz=timezone.utc
                    ).isoformat(timespec="seconds"),
                    "error": None,
                    "forecast": forecast,
                    "events": [event_to_chinese(event) for event in events[:400]],
                    "new_event_ids": new_ids,
                    "seen_event_ids": merged_ids,
                }
            )
            if radar_summary is not None:
                state["radar_summary"] = radar_summary
            if model_radar is not None:
                state["model_radar"] = model_radar
            if fast_radar is not None:
                state["fast_radar"] = fast_radar
            if tibo_updates is not None:
                state["tibo_updates"] = tibo_updates
            state["source_warnings"] = optional_errors
            save_state()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        with state_lock:
            state.update(
                {
                    "service": "degraded",
                    "last_checked_at": checked_at,
                    "next_check_at": datetime.fromtimestamp(
                        time.time() + POLL_SECONDS, tz=timezone.utc
                    ).isoformat(timespec="seconds"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            save_state()


def watcher() -> None:
    while True:
        refresh()
        time.sleep(POLL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            with state_lock:
                payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path in ("/", "/index.html"):
            payload = STATIC_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/healthz":
            payload = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(404)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_state()
    thread = threading.Thread(target=watcher, name="watcher", daemon=True)
    thread.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Codex reset radar listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
