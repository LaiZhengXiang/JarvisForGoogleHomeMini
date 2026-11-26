"""
Sources - where the yapper gets real facts. All free, no API keys, and 0 AI tokens:
plain code fetches the data, and only a tiny summary is handed to the AI later.

  weather()  Open-Meteo forecast for Penang
  news()     Google News Malaysia headlines (RSS)
  market()   hot stock news: big moves worldwide (Nvidia, Tesla...) and on Bursa Malaysia
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

CITY = "Penang"
LAT, LON = 5.4141, 100.3288  # George Town
TIMEOUT = 15
HEADERS = {"User-Agent": "JARVIS-home-assistant/1.0"}

_cache: dict[str, tuple[float, object]] = {}  # name -> (time fetched, data)


def _cached(name: str, max_age: int, fetch):
    """Fetch at most once every max_age seconds - saves time and is polite to the websites."""
    hit = _cache.get(name)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    data = fetch()
    _cache[name] = (time.time(), data)
    return data


# ---------- weather ----------
WEATHER_WORDS = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 80: "light showers", 81: "showers", 82: "heavy showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def weather_data() -> dict:
    """Penang weather as numbers (for the dashboard). Cached 30 minutes."""
    def fetch():
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON, "timezone": "Asia/Kuala_Lumpur", "forecast_days": 2,
            "current": "temperature_2m,apparent_temperature,weather_code,relative_humidity_2m,wind_speed_10m",
            "hourly": "precipitation_probability,weather_code,temperature_2m",
        }, timeout=TIMEOUT, headers=HEADERS)
        r.raise_for_status()
        return r.json()

    d = _cached("weather", 30 * 60, fetch)
    now = d["current"]
    this_hour = datetime.now().strftime("%Y-%m-%dT%H:00")
    today = datetime.now().strftime("%Y-%m-%d")
    hours = [
        {"date": t[:10], "time": t[11:16], "temp": temp, "rain": rain, "desc": WEATHER_WORDS.get(code, "rain")}
        for t, temp, rain, code in zip(d["hourly"]["time"], d["hourly"]["temperature_2m"],
                                       d["hourly"]["precipitation_probability"], d["hourly"]["weather_code"])
        if t > this_hour
    ]
    return {
        "city": CITY,
        "temp": round(now["temperature_2m"]),
        "feels": round(now["apparent_temperature"]),
        "humidity": now["relative_humidity_2m"],
        "wind": round(now["wind_speed_10m"]),
        "desc": WEATHER_WORDS.get(now["weather_code"], "unknown"),
        "next_hours": hours[:6],
        "rain_later_today": [h for h in hours if (h["rain"] or 0) >= 40 and h["date"] == today][:4],
    }


def weather() -> str:
    """Penang weather as one sentence (for the yapper's AI prompt)."""
    w = weather_data()
    today_rain = w["rain_later_today"]
    summary = (f"{w['city']} now: {w['temp']}°C, feels like {w['feels']}°C, {w['desc']}, humidity {w['humidity']}%.")
    if today_rain:
        summary += " Rain likely in the next hours: " + "; ".join(f"{h['time']} {h['rain']}% chance ({h['desc']})" for h in today_rain) + "."
    else:
        summary += " No rain expected in the next hours."
    return summary


# ---------- news ----------
def _google_news(query: str | None, region: str = "MY") -> list[dict]:
    url = "https://news.google.com/rss" + (f"/search?q={requests.utils.quote(query)}" if query else "")
    url += ("&" if query else "?") + f"hl=en-{region}&gl={region}&ceid={region}:en"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    items = []
    for item in ET.fromstring(r.content).iter("item"):
        title = item.findtext("title") or ""
        source = item.findtext("source") or ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        items.append({"title": title.strip(), "source": source, "link": item.findtext("link") or ""})
    return items


def news() -> list[dict]:
    """Top Malaysia headlines right now (cached 1 hour)."""
    return _cached("news", 60 * 60, lambda: _google_news(None))


BIG_MOVE = re.compile(r"\d+(\.\d+)?\s?%|soar|surge|plunge|tumble|jump|sink|slump|rall(y|ies)|crash|skyrocket|record high|sell-?off", re.I)


CLICKBAIT = re.compile(r"buy,? sell,? or hold|should you buy|top \d+ stocks|stocks? to buy|price prediction", re.I)


def _movers(query: str, region: str) -> list[dict]:
    """Headlines about stocks that moved a lot - the ones with a % or a big-move word first."""
    items = _google_news(query, region)
    for it in items:
        it["region"] = "Malaysia" if region == "MY" else "Global"
        it["score"] = (2 if re.search(r"\d+(\.\d+)?\s?%", it["title"]) else 0) + (1 if BIG_MOVE.search(it["title"]) else 0)
    return [it for it in items if it["score"] > 0 and not CLICKBAIT.search(it["title"])]


def market() -> list[dict]:
    """Hot stock news from the last day: global (Nvidia, Tesla...) + Malaysia (Bursa). Cached 1 hour."""
    def fetch():
        found = (_movers("stock shares soar OR plunge OR surge OR tumble OR jumps when:1d", "US")[:12]
                 + _movers("Bursa Malaysia shares soar OR plunge OR surge OR jump when:1d", "MY")[:6])
        return sorted(found, key=lambda it: -it["score"])

    return _cached("market", 60 * 60, fetch)


if __name__ == "__main__":
    print(weather())
    for n in news()[:5]:
        print("-", n["title"], "|", n["source"])
    for n in market()[:8]:
        print("-", n["region"], n["score"], n["title"], "|", n["source"])
