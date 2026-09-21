#!/usr/bin/env python3
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USERNAME = os.getenv("GITHUB_FEED_USERNAME", "sedatyildiznet")
GH_TOKEN = os.getenv("GH_TOKEN", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATE_FILE = Path(os.getenv("STATE_FILE", ".github-public-feed-state.json"))
MAX_SEEN = 250


def github_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-public-feed",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send_telegram(message: str) -> bool:
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": message[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        return bool(result.get("ok"))
    except Exception as exc:
        print(f"Telegram error: {exc}", file=sys.stderr)
        return False


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{esc(label)}</a>'


def short(value: Any, limit: int = 170) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_event(event: dict[str, Any]) -> str:
    etype = event.get("type", "GitHubEvent")
    repo = event.get("repo", {}).get("name", "unknown/repository")
    payload = event.get("payload") or {}
    actor = event.get("actor", {}).get("login", USERNAME)
    base = f"https://github.com/{repo}"

    if etype == "PushEvent":
        ref = str(payload.get("ref", "")).removeprefix("refs/heads/")
        commits = payload.get("commits") or []
        count = payload.get("size", len(commits))
        lines = [
            "🟢 <b>New Push</b>", "",
            f"📦 {link(repo, base)}",
            f"🌿 <code>{esc(ref)}</code>",
            f"📝 {count} commit{'s' if count != 1 else ''}",
        ]
        for commit in commits[:5]:
            sha_full = str(commit.get("sha", ""))
            sha = sha_full[:7]
            msg = short(str(commit.get("message", "")).splitlines()[0], 120)
            lines.append(f"• {link(sha, f'{base}/commit/{sha_full}')} — {esc(msg)}")
        return "\n".join(lines)

    if etype == "ReleaseEvent":
        release = payload.get("release") or {}
        tag = release.get("tag_name") or ""
        name = release.get("name") or tag or "Release"
        url = release.get("html_url") or f"{base}/releases"
        return "\n".join([
            "🚀 <b>Release</b>", "",
            f"<b>{esc(name)}</b>",
            f"📦 {link(repo, base)}",
            f"🏷 <code>{esc(tag)}</code>",
            f"⚡ {esc(payload.get('action', 'published'))}", "",
            link("View release →", url),
        ])

    if etype == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        action = payload.get("action", "updated")
        if action == "closed" and pr.get("merged"):
            action = "merged"
        url = pr.get("html_url") or f"{base}/pulls"
        return "\n".join([
            f"🔀 <b>Pull Request {esc(str(action).title())}</b>", "",
            f"<b>#{esc(pr.get('number') or payload.get('number'))} {esc(short(pr.get('title')))}</b>",
            f"📦 {link(repo, base)}", "",
            link("View pull request →", url),
        ])

    if etype == "IssuesEvent":
        issue = payload.get("issue") or {}
        return "\n".join([
            f"🎫 <b>Issue {esc(str(payload.get('action', 'updated')).title())}</b>", "",
            f"<b>#{esc(issue.get('number'))} {esc(short(issue.get('title')))}</b>",
            f"📦 {link(repo, base)}", "",
            link("View issue →", issue.get("html_url") or f"{base}/issues"),
        ])

    if etype == "IssueCommentEvent":
        issue = payload.get("issue") or {}
        comment = payload.get("comment") or {}
        return "\n".join([
            "💬 <b>Issue Comment</b>", "",
            f"<b>#{esc(issue.get('number'))} {esc(short(issue.get('title'), 150))}</b>",
            f"📦 {link(repo, base)}", "",
            link("View comment →", comment.get("html_url") or issue.get("html_url") or base),
        ])

    if etype == "PullRequestReviewEvent":
        pr = payload.get("pull_request") or {}
        review = payload.get("review") or {}
        state = review.get("state") or payload.get("action", "reviewed")
        return "\n".join([
            f"✅ <b>Pull Request Review: {esc(str(state).title())}</b>", "",
            f"<b>#{esc(pr.get('number'))} {esc(short(pr.get('title'), 150))}</b>",
            f"📦 {link(repo, base)}", "",
            link("View review →", review.get("html_url") or pr.get("html_url") or base),
        ])

    if etype == "PullRequestReviewCommentEvent":
        pr = payload.get("pull_request") or {}
        comment = payload.get("comment") or {}
        return "\n".join([
            "💬 <b>Pull Request Review Comment</b>", "",
            f"<b>#{esc(pr.get('number'))} {esc(short(pr.get('title'), 150))}</b>",
            f"📦 {link(repo, base)}", "",
            link("View comment →", comment.get("html_url") or pr.get("html_url") or base),
        ])

    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "repository")
        if ref_type == "repository":
            return "\n".join(["✨ <b>New Repository</b>", "", f"📦 {link(repo, base)}"])
        return "\n".join([
            f"✨ <b>New {esc(str(ref_type).title())}</b>", "",
            f"📦 {link(repo, base)}",
            f"🔖 <code>{esc(payload.get('ref'))}</code>",
        ])

    if etype == "DeleteEvent":
        return "\n".join([
            f"🗑 <b>{esc(str(payload.get('ref_type', 'ref')).title())} Deleted</b>", "",
            f"📦 {link(repo, base)}",
            f"🔖 <code>{esc(payload.get('ref'))}</code>",
        ])

    if etype == "WatchEvent":
        return "\n".join(["⭐ <b>Repository Starred</b>", "", f"📦 {link(repo, base)}"])

    if etype == "ForkEvent":
        forkee = payload.get("forkee") or {}
        fork_name = forkee.get("full_name") or "fork"
        fork_url = forkee.get("html_url") or f"https://github.com/{fork_name}"
        return "\n".join([
            "🍴 <b>Repository Forked</b>", "",
            f"📦 {link(repo, base)}",
            f"↳ {link(fork_name, fork_url)}",
        ])

    if etype == "PublicEvent":
        return "\n".join(["🌍 <b>Repository Made Public</b>", "", f"📦 {link(repo, base)}"])

    if etype == "MemberEvent":
        member = (payload.get("member") or {}).get("login", "")
        return "\n".join([
            f"👥 <b>Collaborator {esc(str(payload.get('action', 'updated')).title())}</b>", "",
            f"📦 {link(repo, base)}",
            f"👤 {esc(member)}",
        ])

    if etype == "CommitCommentEvent":
        comment = payload.get("comment") or {}
        return "\n".join([
            "💬 <b>Commit Comment</b>", "",
            f"📦 {link(repo, base)}", "",
            link("View comment →", comment.get("html_url") or base),
        ])

    if etype == "GollumEvent":
        return "\n".join(["📚 <b>Wiki Updated</b>", "", f"📦 {link(repo, base)}"])

    label = etype[:-5] if etype.endswith("Event") else etype
    return "\n".join([
        f"🔔 <b>{esc(label)}</b>", "",
        f"📦 {link(repo, base)}",
        f"👤 {esc(actor)}",
    ])


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"initialized": False, "seen": []}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError
        state.setdefault("initialized", False)
        state.setdefault("seen", [])
        return state
    except Exception:
        return {"initialized": False, "seen": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> int:
    state = load_state()

    if not TG_TOKEN or not TG_CHAT_ID:
        save_state(state)
        print("Telegram secrets are not configured; skipping.")
        return 0

    events = github_json(f"https://api.github.com/users/{USERNAME}/events/public?per_page=100")
    current_ids = [str(event.get("id")) for event in events if event.get("id")]

    if not state["initialized"]:
        state["initialized"] = True
        state["seen"] = current_ids[:MAX_SEEN]
        save_state(state)
        print(f"Initialized with {len(current_ids)} current events; historical events were not posted.")
        return 0

    seen = set(map(str, state.get("seen", [])))
    new_events = [event for event in events if str(event.get("id")) not in seen]
    sent_ids: list[str] = []
    failures = 0

    for event in reversed(new_events):
        event_id = str(event.get("id"))
        if send_telegram(format_event(event)):
            sent_ids.append(event_id)
            print(f"Sent {event.get('type')} {event_id}")
        else:
            failures += 1

    known = seen | set(sent_ids)
    ordered: list[str] = []
    for event_id in current_ids + list(state.get("seen", [])):
        if event_id in known and event_id not in ordered:
            ordered.append(event_id)
    state["seen"] = ordered[:MAX_SEEN]
    save_state(state)

    if failures:
        print(f"{failures} event(s) failed and will be retried.", file=sys.stderr)
        return 1

    print(f"{len(sent_ids)} new event(s) sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
