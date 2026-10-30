# -*- coding: utf-8 -*-
"""
123AV TVBox Spider
站点: https://123av.com/cn
分类: 类型 + 趋势 + 系列 + 制作商 + 女演员 + 类别 (均含二级子分类) + 搜索
播放: javplayer.cc → stream API → m3u8
"""
import re
import json
from html import unescape
from urllib.parse import quote
from base.spider import Spider


class Spider(Spider):
    name = "123av"
    host = "https://123av.com"
    lang = "cn"

    # ══════════════════════════════════════════════════════
    def init(self, *args, **kwargs):
        pass

    # ── 内部缓存 ────────────────────────────────────────
    _genre_cache   = None   # 类别 (动态 ~483)
    _series_cache  = None   # 系列列表
    _maker_cache   = None   # 制作商列表
    _actress_cache = None   # 女演员列表

    # ══════════════════════════════════════════════════════
    #  请求工具
    # ══════════════════════════════════════════════════════

    def _url(self, path, **kw):
        if path.startswith("http"):
            return path
        base = f"{self.host}/{self.lang}"
        if not path.startswith("/"):
            path = "/" + path
        if kw:
            qs = "&".join(
                f"{k}={v}" for k, v in kw.items() if v not in (None, "")
            )
            sep = "&" if "?" in path else "?"
            return f"{base}{path}{sep}{qs}"
        return f"{base}{path}"

    def _get(self, url, **kw):
        return self.fetch(url, headers=self._headers(url), timeout=15)

    def _headers(self, url=""):
        h = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if url and "javplayer.cc" in url:
            h["Referer"] = f"{self.host}/{self.lang}/"
        return h

    # ══════════════════════════════════════════════════════
    #  分类解析 (懒加载 + 缓存)
    # ══════════════════════════════════════════════════════

    def _get_genres(self):
        """获取所有类别"""
        if Spider._genre_cache is not None:
            return Spider._genre_cache
        genres = {}
        try:
            resp = self._get(self._url("genres"))
            for m in re.finditer(
                r'href="/cn/genres/([^"]+)"\s+data-name="([^"]+)"',
                self._text(resp),
            ):
                genres[m.group(1)] = unescape(m.group(2))
        except Exception:
            pass
        Spider._genre_cache = sorted(genres.items(), key=lambda x: x[1])
        return Spider._genre_cache

    def _get_series(self):
        """获取系列列表 (分页获取前 5 页 ≈ 240 条)"""
        if Spider._series_cache is not None:
            return Spider._series_cache
        items = []
        try:
            for pg in range(1, 6):
                resp = self._get(self._url(f"series?page={pg}"))
                html = self._text(resp)
                for m in re.finditer(
                    r'class="srow"[^>]*href="/cn/series/([^"]+)"',
                    html,
                ):
                    slug = m.group(1)
                    if slug not in {x[0] for x in items}:
                        items.append((slug, slug.replace("-", " ").title()))
        except Exception:
            pass
        Spider._series_cache = items
        return items

    def _get_makers(self):
        """获取制作商列表 (首页 + /cn/makers 第一页)"""
        if Spider._maker_cache is not None:
            return Spider._maker_cache
        items = {}
        # 从首页导航提取
        for slug, name in [
            ("fc2", "FC2"), ("heyzo", "HEYZO"), ("1pondo", "1Pondo"),
            ("caribbeancom", "Caribbeancom"), ("10musume", "10Musume"),
            ("pacopacomama", "Pacopacomama"), ("tokyo-hot", "Tokyo Hot"),
            ("xxx-av", "XXX-AV"), ("s-cute", "S-CUTE"),
        ]:
            items[slug] = name
        # 从 /cn/makers 获取全部
        try:
            for pg in range(1, 4):
                resp = self._get(self._url(f"makers?page={pg}"))
                html = self._text(resp)
                for m in re.finditer(
                    r'<a[^>]*href="/cn/makers/([^"]+)"[^>]*>([^<]+)<', html
                ):
                    slug, name = m.group(1), unescape(m.group(2).strip())
                    if slug and name and slug not in items:
                        items[slug] = name
        except Exception:
            pass
        Spider._maker_cache = sorted(items.items(), key=lambda x: x[1])
        return Spider._maker_cache

    def _get_actresses(self):
        """获取女演员列表 (前 5 页 ≈ 150 位)"""
        if Spider._actress_cache is not None:
            return Spider._actress_cache
        items = []
        seen = set()
        try:
            for pg in range(1, 6):
                resp = self._get(self._url(f"actresses?page={pg}"))
                html = self._text(resp)
                for m in re.finditer(
                    r'<a[^>]*class="actress__name"[^>]*href="/cn/actresses/([^"]+)"[^>]*>([^<]+)<',
                    html,
                ):
                    slug, name = m.group(1), m.group(2).strip()
                    if slug and name and slug not in seen:
                        seen.add(slug)
                        items.append((slug, name))
        except Exception:
            pass
        Spider._actress_cache = items
        return items

    # ══════════════════════════════════════════════════════
    #  homeContent
    # ══════════════════════════════════════════════════════

    def homeContent(self, filter={}):
        classes = []
        filters = {}

        # ── 基础分类 ──
        basic = [
            ("new",      "🏠 主页推荐", True),
            ("hot",      "🔥 热门",       True),
            ("recent",   "⏱ 最近",       True),
            ("today",    "📈 今日热门",   True),
            ("week",     "📈 本周热门",   True),
            ("month",    "📈 本月热门",   True),
            ("censored", "🎬 有码",       True),
            ("uncensored", "🎬 无码",     True),
            ("uncensored-leaked", "🎬 无码泄露", True),
        ]
        for tid, name, has_filter in basic:
            classes.append({"type_id": tid, "type_name": name})
            if has_filter:
                filters[tid] = [{"key": "year", "name": "年份",
                    "value": [{"n": y, "v": y} for y in ["", "2026","2025","2024","2023","2022","2021","2020"]]}]

        # ── 系列 (二级分类) ──
        series_list = self._get_series()
        classes.append({"type_id": "series", "type_name": "🎞 系列"})
        filters["series"] = [
            {"key": "sid", "name": "系列",
             "value": [{"n": n, "v": s} for s, n in series_list[:300]]}
        ]

        # ── 制作商 (二级分类) ──
        makers_list = self._get_makers()
        classes.append({"type_id": "makers", "type_name": "🏭 制作商"})
        filters["makers"] = [
            {"key": "mid", "name": "制作商",
             "value": [{"n": n, "v": s} for s, n in makers_list]}
        ]

        # ── 女演员 (二级分类) ──
        actress_list = self._get_actresses()
        classes.append({"type_id": "actresses", "type_name": "👩 女演员"})
        filters["actresses"] = [
            {"key": "aid", "name": "女演员",
             "value": [{"n": n, "v": s} for s, n in actress_list]}
        ]

        # ── 类别 (二级分类) ──
        genres_list = self._get_genres()
        classes.append({"type_id": "genres", "type_name": "📂 类别"})
        filters["genres"] = [
            {"key": "gid", "name": "类别",
             "value": [{"n": n, "v": s} for s, n in genres_list]}
        ]

        return {"class": classes, "filters": filters}

    # ══════════════════════════════════════════════════════
    #  homeVideoContent
    # ══════════════════════════════════════════════════════

    def homeVideoContent(self):
        return self._list(self._url("new?page=1"))

    # ══════════════════════════════════════════════════════
    #  categoryContent
    # ══════════════════════════════════════════════════════

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._page(pg)
        year = (extend or {}).get("year", "")
        kw = {"page": str(pg)}
        if year:
            kw["year"] = year

        # ── 基础分类 ──
        if tid in ("new", "hot", "recent"):
            return self._list(self._url(tid, **kw))
        if tid in ("today", "week", "month"):
            return self._list(self._url(f"all?sort={tid}", **kw))
        if tid in ("censored", "uncensored", "uncensored-leaked"):
            return self._list(self._url(tid, **kw))

        # ── 系列 (tid=series, extend.sid=slug) ──
        if tid == "series":
            sid = (extend or {}).get("sid", "")
            if sid:
                return self._list(self._url(f"series/{sid}", **kw))
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        # ── 制作商 (tid=makers, extend.mid=slug) ──
        if tid == "makers":
            mid = (extend or {}).get("mid", "")
            if mid:
                return self._list(self._url(f"makers/{mid}", **kw))
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        # ── 女演员 (tid=actresses, extend.aid=slug) ──
        if tid == "actresses":
            aid = (extend or {}).get("aid", "")
            if aid:
                return self._list(self._url(f"actresses/{aid}", **kw))
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        # ── 类别 (tid=genres, extend.gid=slug) ──
        if tid == "genres":
            gid = (extend or {}).get("gid", "")
            if gid:
                return self._list(self._url(f"genres/{gid}", **kw))
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

    # ══════════════════════════════════════════════════════
    #  detailContent
    # ══════════════════════════════════════════════════════

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        slug = (ids[0] if isinstance(ids, list) else ids).strip("/").split("/")[-1]
        url = self._url(f"v/{slug}")
        try:
            resp = self._get(url)
            html = self._text(resp)
            vod = self._parse_detail(html, slug)
            return {"list": [vod]} if vod else {"list": []}
        except Exception:
            pass
        return {"list": []}

    def _parse_detail(self, html, slug):
        vod = {
            "vod_id": slug,
            "vod_name": "",
            "vod_pic": "",
            "vod_year": "",
            "vod_remarks": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_area": "日本",
            "vod_content": "",
            "vod_play_from": "123AV",
            "vod_play_url": "",
            "type_name": "",
        }
        # 标题
        m = re.search(r'class="watch__title"[^>]*>([^<]+)', html)
        if m:
            vod["vod_name"] = unescape(m.group(1)).strip()
        # 封面 (优先 s500)
        m = re.search(r'cdn\.123av\.me/img2/s500/[^"\'?]+\.jpg', html)
        if m:
            vod["vod_pic"] = f"https://{m.group(0)}"
        else:
            m = re.search(r'cdn\.123av\.me/img2/s360/[^"\'?]+\.jpg', html)
            if m:
                vod["vod_pic"] = f"https://{m.group(0)}"
        # 元数据
        meta = self._extract_meta(html)
        vod["vod_year"] = meta.get("发布日期", "")[:4]
        vod["vod_remarks"] = meta.get("类型", "")
        vod["vod_actor"]   = meta.get("演员", "")
        vod["vod_director"] = meta.get("制作商", "")
        code = meta.get("代码", slug.upper())
        # 播放 URL
        hash_id = self._extract_hash_id(html)
        vod["vod_play_url"] = f"{code}${hash_id}" if hash_id else f"{code}${slug}"
        return vod

    def _extract_meta(self, html):
        meta = {}
        m = re.search(r'class="watch__info">(.*?)</section>', html, re.S)
        if not m:
            return meta
        for row in re.finditer(
            r'<dt>([^<]+)</dt>\s*<dd[^>]*>(.*?)</dd>', m.group(0), re.S
        ):
            key = row.group(1).strip()
            val = re.sub(r'<[^>]+>', ', ', row.group(2))
            val = re.sub(r',\s*,', ',', val).strip().strip(",").strip()
            val = unescape(val)
            if val:
                meta[key] = val
        return meta

    def _extract_hash_id(self, html):
        m = re.search(r"player\(JSON\.parse\('([^']+)'\)", html)
        if not m:
            return None
        try:
            raw = m.group(1).encode().decode('unicode_escape')
            eps = json.loads(raw)
            if eps and eps[0].get("url"):
                url = eps[0]["url"].replace('\\/', '/')
                hm = re.search(r'/e/([A-Za-z0-9]+)', url)
                if hm:
                    return hm.group(1)
        except Exception:
            pass
        return None

    # ══════════════════════════════════════════════════════
    #  searchContent
    # ══════════════════════════════════════════════════════

    def searchContent(self, key, quick, pg="1"):
        url = self._url("search", keyword=quote(key), page=self._page(pg))
        return self._list(url)

    # ══════════════════════════════════════════════════════
    #  playerContent
    # ══════════════════════════════════════════════════════

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 1, "url": "", "header": self._headers()}
        try:
            stream_url = f"https://javplayer.cc/stream?id={quote(str(id))}"
            resp = self.fetch(stream_url, headers={
                "User-Agent": self._headers()["User-Agent"],
                "Referer": f"{self.host}/{self.lang}/",
            }, timeout=15)
            data = resp.json()
            m3u8 = data.get("media", {}).get("stream", "")
            if m3u8:
                return {
                    "parse": 0,
                    "url": m3u8,
                    "header": {
                        "User-Agent": self._headers()["User-Agent"],
                        "Referer": f"{self.host}/{self.lang}/",
                    },
                }
        except Exception:
            pass
        return {
            "parse": 1,
            "url": f"https://javplayer.cc/e/{quote(str(id))}",
            "header": self._headers(),
        }

    # ══════════════════════════════════════════════════════
    #  工具方法
    # ══════════════════════════════════════════════════════

    def _list(self, url):
        videos, pagecount = [], 1
        try:
            resp = self._get(url)
            html = self._text(resp)
            # 卡片解析
            for m in re.finditer(
                r'<div class="card"[^>]*>.*?</div>\s*</div>\s*</div>',
                html, re.S,
            ):
                card = m.group(0)
                pic  = ""
                pm   = re.search(r'class="card__img" src="([^"]+)"', card)
                if pm:
                    pic = pm.group(1)
                name, vod_id = "", ""
                nm = re.search(
                    r'class="card__link" href="(/cn/v/([^"]+))">([^<]+)', card
                )
                if nm:
                    vod_id = nm.group(2)
                    name   = unescape(nm.group(3)).strip()
                    if " — " in name:
                        name = name.split(" — ", 1)[1]
                if vod_id:
                    videos.append({
                        "vod_id":    vod_id,
                        "vod_name":  name,
                        "vod_pic":   pic,
                        "vod_remarks": "",
                    })
            pm = re.search(r'pager__total">/\s*(\d+)', html)
            if pm:
                pagecount = int(pm.group(1))
        except Exception:
            pass
        return {
            "list":       videos,
            "page":       self._page(url),
            "pagecount":  pagecount,
            "limit":      24,
            "total":      pagecount * 24,
        }

    @staticmethod
    def _page(val):
        try:
            v = int(val)
            return v if v >= 1 else 1
        except (ValueError, TypeError):
            return 1

    @staticmethod
    def _text(resp):
        if resp is None:
            return ""
        if hasattr(resp, "text"):
            return resp.text or ""
        if hasattr(resp, "content"):
            return (resp.content or b"").decode("utf-8", errors="ignore")
        return ""

    def destroy(self):
        pass
