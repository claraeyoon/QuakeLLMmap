from __future__ import annotations
import os
import json
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional

from quake_agent.config import EventConfig, Settings
from quake_agent.core.models import RawContentItem

class WebHarvester:
    """
    Constructs multilingual, event-grounded search queries and harvests
    content from Reddit, YouTube, and the Web (Tavily/DuckDuckGo).
    """

    def __init__(self, event_config: EventConfig, settings: Optional[Settings] = None):
        self.event = event_config
        self.settings = settings or Settings()

    def generate_search_queries(self) -> List[str]:
        """Generates multilingual queries tailored to the event parameters."""
        queries = []
        name = self.event.name
        mag = self.event.magnitude

        # English queries
        queries.append(f"earthquake {name} building damage photo")
        queries.append(f"earthquake {name} surface rupture fault scarp")
        queries.append(f"earthquake {name} shaking video CCTV")

        # Regional township / landmark queries
        for township in self.event.townships[:4]:
            queries.append(f"earthquake damage {township}")
            queries.append(f"earthquake shaking {township} video")

        # Local language queries (e.g., Burmese, Turkish, etc.)
        for term in self.event.local_lexicon[:3]:
            for township in self.event.townships[:2]:
                queries.append(f"{township} {term}")

        return queries

    def search_web_tavily(self, query: str, max_results: int = 5) -> List[RawContentItem]:
        api_key = self.settings.tavily_api_key or os.getenv("TAVILY_API_KEY")
        if not api_key:
            return []

        items: List[RawContentItem] = []
        try:
            import urllib.request
            req_data = json.dumps({
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_images": True
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for res in data.get("results", []):
                items.append(RawContentItem(
                    event_id=self.event.event_id,
                    source_platform="web",
                    content_type="text",
                    source_url=res.get("url"),
                    title=res.get("title"),
                    text_content=res.get("content"),
                    raw_metadata={"score": res.get("score"), "query": query}
                ))

            # Also capture image results
            for img_url in data.get("images", []):
                items.append(RawContentItem(
                    event_id=self.event.event_id,
                    source_platform="web",
                    content_type="image",
                    source_url=img_url if isinstance(img_url, str) else img_url.get("url"),
                    title=f"Web image: {query}",
                    raw_metadata={"query": query}
                ))
        except Exception as e:
            print(f"Notice: Tavily web search error: {e}")

        return items

    def search_reddit_public(self, query: str, limit: int = 5) -> List[RawContentItem]:
        """Harvests public Reddit posts using Reddit's JSON search endpoint."""
        items: List[RawContentItem] = []
        try:
            import urllib.request
            encoded = urllib.parse.quote(query)
            url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit={limit}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) QuakeAgent/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                created_utc = post.get("created_utc")
                pub_dt = datetime.utcfromtimestamp(created_utc) if created_utc else None

                media_url = post.get("url_overridden_by_dest") or post.get("url")
                content_type = "text"
                if media_url and any(media_url.endswith(ext) for ext in [".jpg", ".png", ".jpeg"]):
                    content_type = "image"
                elif media_url and any(kw in media_url for kw in ["v.redd.it", "youtube.com", "youtu.be"]):
                    content_type = "video"

                items.append(RawContentItem(
                    event_id=self.event.event_id,
                    source_platform="reddit",
                    content_type=content_type,
                    source_url=f"https://reddit.com{post.get('permalink')}",
                    published_at=pub_dt,
                    title=post.get("title"),
                    text_content=post.get("selftext"),
                    raw_metadata={"subreddit": post.get("subreddit"), "media_url": media_url}
                ))
        except Exception as e:
            print(f"Notice: Reddit search notice: {e}")

        return items
