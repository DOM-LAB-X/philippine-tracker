"""
Discord webhook notifications.
All alerts (flight updates, new deals, price drops) go through here.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 10

# Embed colour constants (Discord decimal values)
COLOUR_FLIGHT  = 0x0038A8   # Philippine blue
COLOUR_DEAL    = 0xFCD116   # Philippine gold (promo alert)
COLOUR_PRICE   = 0x2ECC71   # Green (price drop)
COLOUR_ERROR   = 0xE74C3C   # Red
COLOUR_STATUS  = 0x7C3AED   # Midnight purple


def _build_embed(
    title: str,
    description: str,
    colour: int,
    fields: Optional[list] = None,
    url: str = "",
) -> dict:
    embed: dict = {
        "title": title,
        "description": description,
        "color": colour,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "PhilFlight Tracker"},
    }
    if url:
        embed["url"] = url
    if fields:
        embed["fields"] = [
            {"name": f["name"], "value": f["value"], "inline": f.get("inline", True)}
            for f in fields
        ]
    return embed


def send(webhook_url: str, embed: dict) -> bool:
    """POST a single embed to the webhook.  Returns True on success."""
    if not webhook_url:
        return False
    try:
        resp = requests.post(
            webhook_url,
            json={"embeds": [embed]},
            timeout=TIMEOUT,
        )
        # 204 = No Content (success), 200 = OK
        if resp.status_code in (200, 204):
            return True
        logger.warning("Discord returned HTTP %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("Discord notification failed: %s", exc)
        return False


# ------------------------------------------------------------------ #
# Convenience senders                                                  #
# ------------------------------------------------------------------ #

def notify_flight_update(webhook_url: str, flights: list, dep: str, arr: str) -> bool:
    count = len(flights)
    if count == 0:
        return True  # nothing to say

    sample = flights[:5]
    lines = []
    for f in sample:
        cs   = f.get("callsign") or "—"
        src  = f.get("departure_airport") or dep or "—"
        dst  = f.get("arrival_airport") or arr or "—"
        lines.append(f"✈ **{cs}**  {src} → {dst}")
    if count > 5:
        lines.append(f"_…and {count - 5} more_")

    embed = _build_embed(
        title=f"✈ {count} flight{'s' if count != 1 else ''} — {dep or 'PH'} → {arr or 'any'}",
        description="\n".join(lines),
        colour=COLOUR_FLIGHT,
    )
    return send(webhook_url, embed)


def notify_deal(webhook_url: str, deal: dict) -> bool:
    source = deal.get("source", "Unknown source")
    title  = deal.get("title", "New deal found")[:256]
    url    = deal.get("url", "")
    score  = deal.get("score")

    desc = f"**{title}**"
    if score is not None:
        desc += f"\n🔼 Reddit score: {score}"

    embed = _build_embed(
        title=f"🎫 Promo alert — {source}",
        description=desc,
        colour=COLOUR_DEAL,
        url=url,
    )
    return send(webhook_url, embed)


def notify_price_drop(
    webhook_url: str,
    route: str,
    old_price: float,
    new_price: float,
    airline: str,
    url: str = "",
) -> bool:
    drop_pct = ((old_price - new_price) / old_price) * 100
    embed = _build_embed(
        title=f"💸 Price drop — {route}",
        description=f"**{airline}** dropped by {drop_pct:.0f}%",
        colour=COLOUR_PRICE,
        fields=[
            {"name": "Was",  "value": f"₱{old_price:,.0f}", "inline": True},
            {"name": "Now",  "value": f"₱{new_price:,.0f}", "inline": True},
            {"name": "Route","value": route,                 "inline": True},
        ],
        url=url,
    )
    return send(webhook_url, embed)


def notify_status(
    webhook_url: str,
    window_hours: int,
    searches_in_window: int,
    total_searches: int,
    routes_count: int,
    next_check: str = "",
) -> bool:
    """12-hour heartbeat: how many searches ran and tracker health."""
    ran = searches_in_window > 0
    status_line = (
        f"✅ Ran — **{searches_in_window}** search{'es' if searches_in_window != 1 else ''}"
        if ran else "⚠️ No searches ran in this window"
    )
    fields = [
        {"name": f"Last {window_hours}h",  "value": status_line,                  "inline": False},
        {"name": "Routes watched",          "value": str(routes_count),            "inline": True},
        {"name": "Total since launch",      "value": str(total_searches),          "inline": True},
    ]
    if next_check:
        fields.append({"name": "Next check", "value": next_check, "inline": True})
    embed = _build_embed(
        title="📊 PhilFlight — 12-hour status report",
        description="Automated status from your tracker.",
        colour=COLOUR_STATUS,
        fields=fields,
    )
    return send(webhook_url, embed)


def test_webhook(webhook_url: str) -> bool:
    """Send a test message. Used by the Settings dialog."""
    embed = _build_embed(
        title="✅ PhilFlight Tracker — webhook test",
        description="If you see this, Discord notifications are working!",
        colour=COLOUR_FLIGHT,
    )
    return send(webhook_url, embed)
