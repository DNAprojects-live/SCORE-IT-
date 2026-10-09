import asyncio
import logging
import time

import aiohttp

log = logging.getLogger("rfl.roblox")
CACHE_SECONDS = 3600


class Roblox:
    def __init__(self, session):
        self.s = session
        self.cache = {}

    async def _json(self, method, url, **kw):
        try:
            async with self.s.request(method, url, timeout=aiohttp.ClientTimeout(total=10), **kw) as r:
                if r.status != 200:
                    log.warning("roblox %s %s -> %s", method, url, r.status)
                    return None
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("roblox request failed: %s", e)
            return None

    async def lookup_username(self, name):
        data = await self._json("POST", "https://users.roblox.com/v1/usernames/users",
                                json={"usernames": [name], "excludeBannedUsers": False})
        rows = (data or {}).get("data") or []
        return rows[0] if rows else None

    async def get_user(self, user_id):
        return await self._json("GET", f"https://users.roblox.com/v1/users/{user_id}")

    async def thumb_urls(self, ids, kind, size):
        out = {}
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            data = await self._json("GET", f"https://thumbnails.roblox.com/v1/users/{kind}", params={
                "userIds": ",".join(str(x) for x in chunk), "size": size,
                "format": "Png", "isCircular": "false"})
            for row in (data or {}).get("data", []):
                if row.get("state") == "Completed" and row.get("imageUrl"):
                    out[row["targetId"]] = row["imageUrl"]
        return out

    async def avatar_url(self, user_id, kind="avatar", size="420x420"):
        return (await self.thumb_urls([user_id], kind, size)).get(user_id)

    async def _download(self, url):
        if not url:
            return None
        try:
            async with self.s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.read() if r.status == 200 else None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    async def images(self, ids, kind="avatar-headshot", size="150x150"):
        now = time.time()
        ids = list(dict.fromkeys(i for i in ids if i))
        out, todo = {}, []
        for uid in ids:
            hit = self.cache.get((uid, kind, size))
            if hit and hit[0] > now:
                out[uid] = hit[1]
            else:
                todo.append(uid)
        if todo:
            urls = await self.thumb_urls(todo, kind, size)
            blobs = await asyncio.gather(*(self._download(urls.get(u)) for u in todo))
            for uid, blob in zip(todo, blobs):
                out[uid] = blob
                self.cache[(uid, kind, size)] = (now + (CACHE_SECONDS if blob else 60), blob)
        return out
