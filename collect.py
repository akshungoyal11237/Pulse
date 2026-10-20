#!/usr/bin/env python3
"""
Collector: news (RSS) + markets (yfinance) + mutual funds (mfapi.in) -> data/data.json

Memory files (committed back to the repo by the GitHub Action):
  data/stories.json         ongoing storylines with a "story so far" and a timeline
  data/analysis_cache.json  per-article AI output, so we never pay twice for the same article

Set ANTHROPIC_API_KEY to enable summaries, storylines and "explain". Without it the
site still works: headlines + prices only.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CONFIG = json.loads((ROOT / "config.json").read_text())

IST =dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(dt.timezone.utc)


def load(name, default):
    p = DATA / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- news
def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3}


def fetch_segment(seg_key, seg):
    items = []
    for url in seg["feeds"]:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0 news-tracker"})
        except Exception as e:
            log("feed failed", url, e)
            continue
        source = clean(feed.feed.get("title", "")) or url.split("/")[2]
        for e in feed.entries[:40]:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            when = dt.datetime(*ts[:6], tzinfo=dt.timezone.utc) if ts else NOW
            age_h = (NOW - when).total_seconds() / 3600
            if age_h > CONFIG["max_age_hours"] or not e.get("link") or not e.get("title"):
                continue
            items.append({
                "id": hashlib.md5(e["link"].encode()).hexdigest()[:12],
                "title": clean(e["title"]),
                "link": e["link"],
                "source": source[:40],
                "published": when.isoformat(),
                "snippet": clean(e.get("summary", ""))[:400],
                "age_h": age_h,
            })
    return items


def rank_and_dedupe(items, n):
    """Score = how many different sources cover the same story (weighted) + freshness."""
    for it in items:
        it["_tok"] = tokens(it["title"])
    for it in items:
        same = [o for o in items if o is not it and o["source"] != it["source"]
                and it["_tok"] and len(it["_tok"] & o["_tok"]) / max(1, len(it["_tok"] | o["_tok"])) > 0.35]
        it["_score"] = 3 * len({o["source"] for o in same}) + max(0, 48 - it["age_h"]) / 12
    items.sort(key=lambda x: -x["_score"])
    out, seen = [], []
    for it in items:
        if any(it["_tok"] and len(it["_tok"] & t) / max(1, len(it["_tok"] | t)) > 0.5 for t in seen):
            continue  # near-duplicate of something already chosen
        seen.append(it["_tok"])
        out.append(it)
        if len(out) == n:
            break
    return out


# --------------------------------------------------------------------------- AI layer
class LLM:
    """Tiny wrapper so the rest of the script doesn't care which AI is used.
    kind = "gemini" (free tier, no card) or "anthropic" (paid, optional)."""

    def __init__(self, kind, key, model):
        self.kind, self.key, self.model, self.calls, self.dead = kind, key, model, 0, False

    def text(self, system, user, max_tokens=4000, json_mode=False):
        if self.dead:
            raise RuntimeError("AI switched off for the rest of this run after repeated errors")
        if self.calls:
            time.sleep(6)  # stay well under free-tier per-minute limits
        self.calls += 1
        last = None
        for attempt in range(3):
            try:
                return self._once(system, user, max_tokens, json_mode)
            except Exception as e:
                last = e
                log("AI call failed (try %d): %s" % (attempt + 1, str(e)[:200]))
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (400, 401, 403, 404):
                    break  # retrying will not help (bad key / bad model name)
                time.sleep(20 * (attempt + 1))
        self.dead = True
        raise last

    def _once(self, system, user, max_tokens, json_mode):
        if self.kind == "gemini":
            cfg = {"maxOutputTokens": max_tokens}
            if json_mode:
                cfg["responseMimeType"] = "application/json"
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": cfg},
                timeout=120)
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        import anthropic
        r = anthropic.Anthropic(api_key=self.key).messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if b.type == "text")


def get_client():
    gem = os.environ.get("GEMINI_API_KEY", "").strip()
    ant = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    custom = os.environ.get("TRACKER_MODEL", "").strip()
    if gem:
        return LLM("gemini", gem, custom or "gemini-3.1-flash-lite")
    if ant:
        return LLM("anthropic", ant, custom or "claude-haiku-5-5")
    return None


def ask_json(client, system, user, max_tokens=8000):
    text = client.text(system, user, max_tokens, json_mode=True)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [0])
    return json.loads(text[start:])


ANALYSIS_SYSTEM = """You help a reader who is NOT up to date with the news understand each story in context.
You get EXISTING_STORIES (ongoing storylines already tracked) and NEW_ARTICLES. For every article return an object:
- idx: the article's idx
- summary: 1-2 plain sentences, no hype
- story_id: id of the matching existing story, or null if it is a genuinely new storyline
- story_title: short title (3-7 words) for the storyline (reuse the existing title if matched)
- story_update: one sentence: what is new in this article within the storyline
- story_so_far: 2-4 sentences of background so a newcomer can follow (include key dates, actors, numbers).
  Required if story_id is null. If matched, write an improved version only if something material changed, else null.
- explain: 2-4 plain sentences for a beginner: what happened, why it matters, and define any jargon used.
Group several articles about the same event into the SAME storyline (use the same story_title when story_id is null).
Use only facts present in the articles or well-established background. If unsure of background, say so briefly.
Return ONLY a JSON array."""


def analyse(client, seg_key, items, stories, cache):
    todo = [it for it in items if it["id"] not in cache]
    if not todo:
        return
    existing = [{"id": s["id"], "title": s["title"], "so_far": s["so_far"]}
                for s in stories.values() if s["segment"] == seg_key][:40]
    payload = {"EXISTING_STORIES": existing,
               "NEW_ARTICLES": [{"idx": i, "title": it["title"], "source": it["source"],
                                 "published": it["published"][:10], "snippet": it["snippet"]}
                                for i, it in enumerate(todo)]}
    try:
        result = ask_json(client, ANALYSIS_SYSTEM, json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        log("analysis failed for", seg_key, e)
        return
    for r in result:
        try:
            it = todo[r["idx"]]
        except Exception:
            continue
        sid = r.get("story_id")
        if sid not in stories:
            title = (r.get("story_title") or it["title"])[:80]
            # reuse a story created earlier in this same run with same title
            sid = next((s["id"] for s in stories.values()
                        if s["segment"] == seg_key and s["title"].lower() == title.lower()), None)
            if not sid:
                sid = f"{seg_key}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:40]}"
                stories[sid] = {"id": sid, "segment": seg_key, "title": title,
                                "so_far": r.get("story_so_far") or r.get("summary", ""),
                                "timeline": [], "updated": NOW.isoformat()}
        s = stories[sid]
        if r.get("story_so_far"):
            s["so_far"] = r["story_so_far"]
        if not any(t["link"] == it["link"] for t in s["timeline"]):
            s["timeline"].append({"date": it["published"][:10], "text": r.get("story_update") or r.get("summary", ""),
                                  "link": it["link"], "source": it["source"]})
        s["updated"] = NOW.isoformat()
        cache[it["id"]] = {"summary": r.get("summary", ""), "story_id": sid,
                           "explain": r.get("explain", ""), "cached_at": NOW.isoformat()}


PULSE_SYSTEM = """You write a 3-4 sentence 'Why are markets moving today?' note for a beginner.
Given today's price moves and top headlines, connect the moves to likely causes. Be careful: say 'likely' or
'possibly' when linking cause and effect. Mention India first, then US, then crypto/commodities/forex if notable.
Plain text only."""


# --------------------------------------------------------------------------- markets
def fetch_markets():
    import yfinance as yf
    all_syms = {}
    for grp in CONFIG["market_groups"].values():
        for sym, name in grp:
            all_syms[sym] = name
    for sym, name in CONFIG["watchlist"]:
        all_syms[sym] = name
    syms = list(all_syms)
    quotes = {}
    try:
        hist = yf.download(syms, period="1mo", interval="1d", group_by="ticker",
                           auto_adjust=True, progress=False, threads=True)
    except Exception as e:
        log("yfinance failed:", e)
        return quotes
    for sym in syms:
        try:
            closes = hist[sym]["Close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            first = float(closes.iloc[0])
            quotes[sym] = {
                "symbol": sym, "name": all_syms[sym], "price": round(last, 4),
                "change": round(last - prev, 4), "pct": round((last / prev - 1) * 100, 2),
                "pct_1m": round((last / first - 1) * 100, 2),
                "spark": [round(float(x), 4) for x in closes.tolist()],
                "asof": closes.index[-1].strftime("%Y-%m-%d"),
            }
        except Exception:
            continue
    return quotes


def fetch_mf():
    out = []
    for code, name in CONFIG["mutual_funds"]:
        try:
            j = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=20).json()
            navs = j["data"][:31]  # newest first
            last, prev, oldest = float(navs[0]["nav"]), float(navs[1]["nav"]), float(navs[-1]["nav"])
            out.append({"code": code, "name": name or j["meta"]["scheme_name"],
                        "nav": last, "pct": round((last / prev - 1) * 100, 2),
                        "pct_1m": round((last / oldest - 1) * 100, 2), "date": navs[0]["date"],
                        "spark": [float(x["nav"]) for x in reversed(navs)]})
        except Exception as e:
            log("mf failed", code, e)
    return out


# --------------------------------------------------------------------------- earlier coverage (works with no AI)
def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def attach_related(segments, archive):
    """For each article, find older headlines we've stored that look like the same ongoing story."""
    for key, seg in segments.items():
        past = [(a, tokens(a["title"])) for a in archive if a["segment"] == key]
        for it in seg["articles"]:
            tok = it["_tok"]
            hits = []
            for a, t in past:
                if a["id"] == it["id"] or a["published"][:10] >= it["published"][:10]:
                    continue
                if len(tok & t) >= 2 and jaccard(tok, t) >= 0.25:
                    hits.append((a, t))
            hits.sort(key=lambda x: x[0]["published"], reverse=True)
            chosen = []
            for a, t in hits:                       # skip near-identical repeats of the same headline
                if all(jaccard(t, c[1]) < 0.8 for c in chosen):
                    chosen.append((a, t))
                if len(chosen) == 6:
                    break
            it["related"] = [{"date": a["published"][:10], "title": a["title"], "link": a["link"], "source": a["source"]}
                             for a, _ in reversed(chosen)]


def update_archive(segments, archive):
    have = {a["id"] for a in archive}
    for key, seg in segments.items():
        for it in seg["articles"]:
            if it["id"] not in have:
                archive.append({"id": it["id"], "segment": key, "title": it["title"], "link": it["link"],
                                "source": it["source"], "published": it["published"]})
    cutoff = (NOW - dt.timedelta(days=60)).isoformat()
    return [a for a in archive if a["published"] > cutoff]


# --------------------------------------------------------------------------- main
def refresh_prices_only():
    """Free, no-AI refresh: updates prices and fund NAVs inside the existing data.json."""
    payload = load("data.json", None)
    if not payload:
        log("no data.json yet - run the full news update first")
        return
    quotes = fetch_markets()
    mf = fetch_mf()
    if not quotes and not mf:
        log("nothing fetched; leaving data.json untouched")
        return
    payload.setdefault("quotes", {}).update(quotes)      # keep old value for any symbol that failed
    if mf:
        payload["mutual_funds"] = mf
    payload["prices_generated"] = NOW.isoformat()
    payload.pop("sample", None)
    save("data.json", payload)
    log("prices refreshed:", len(quotes), "quotes,", len(mf), "funds")


def main():
    if "--prices-only" in sys.argv:
        return refresh_prices_only()
    stories = load("stories.json", {})
    cache = load("analysis_cache.json", {})
    client = get_client()
    log("AI enabled:", bool(client))

    segments = {}
    for key, seg in CONFIG["segments"].items():
        items = rank_and_dedupe(fetch_segment(key, seg), CONFIG["top_n"])
        log(key, "->", len(items), "articles")
        if client:
            analyse(client, key, items, stories, cache)
        segments[key] = {"label": seg["label"], "articles": items}

    archive = load("archive.json", [])
    attach_related(segments, archive)

    quotes = fetch_markets()
    mf = fetch_mf()
    old = load("data.json", {})
    if not old.get("sample"):          # if a price source is down, keep the last good numbers
        quotes = quotes or old.get("quotes", {})
        mf = mf or old.get("mutual_funds", [])

    # Build page payload
    for key, seg in segments.items():
        arts = []
        for it in seg["articles"]:
            c = cache.get(it["id"], {})
            s = stories.get(c.get("story_id"))
            arts.append({
                "id": it["id"], "title": it["title"], "link": it["link"], "source": it["source"],
                "published": it["published"], "summary": c.get("summary") or it["snippet"][:220],
                "explain": c.get("explain"),
                "related": it.get("related", []),
                "story": ({"id": s["id"], "title": s["title"], "so_far": s["so_far"],
                           "timeline": sorted(s["timeline"], key=lambda t: t["date"])[-12:]} if s else None),
            })
        seg["articles"] = arts

    pulse = None
    if client and quotes:
        try:
            group_syms = {x[0] for g in CONFIG["market_groups"].values() for x in g}
            moves = {q["name"]: f'{q["pct"]:+.2f}%' for q in quotes.values() if q["symbol"] in group_syms}
            heads = [a["title"] for k in ("business", "markets") for a in segments[k]["articles"][:6]]
            pulse = client.text(PULSE_SYSTEM, json.dumps({"moves": moves, "headlines": heads}), 800).strip()
        except Exception as e:
            log("pulse failed", e)

    payload = {
        "generated": NOW.isoformat(),
        "prices_generated": NOW.isoformat(),
        "ai": client.kind if client else None,
        "pulse": pulse,
        "ticker_strip": CONFIG["ticker_strip"],
        "market_groups": {g: [s for s, _ in lst] for g, lst in CONFIG["market_groups"].items()},
        "watchlist": [s for s, _ in CONFIG["watchlist"]],
        "quotes": quotes,
        "mutual_funds": mf,
        "segments": segments,
    }
    save("data.json", payload)

    # Prune memory: stories idle >120 days, cache older than 4 days
    cutoff_s = (NOW - dt.timedelta(days=120)).isoformat()
    stories = {k: v for k, v in stories.items() if v["updated"] > cutoff_s}
    cutoff_c = (NOW - dt.timedelta(days=4)).isoformat()
    cache = {k: v for k, v in cache.items() if v["cached_at"] > cutoff_c}
    save("stories.json", stories)
    save("analysis_cache.json", cache)
    save("archive.json", update_archive(segments, archive))
    log("done:", len(quotes), "quotes,", len(mf), "funds,", len(stories), "stories")


if __name__ == "__main__":
    main()
