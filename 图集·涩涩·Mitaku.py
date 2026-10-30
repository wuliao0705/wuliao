# -*- coding: utf-8 -*-
"""
Mitaku (mitaku.net) - COS·涩涩 Spider
Play : pics://  图片相册协议（漫画式连续看图）

侦察结论：
  · Cloudflare，impersonate=chrome124 可过
  · 列表 /category/{ero-cosplay,sexy-set,nude,online-video}/  分页 /page/N/
    卡片 <article class="post-ID ..."> → h2/h3 a 标题 + img.wp-post-image
  · 详情 /{seg}/SLUG/  正文图在 img[data-lazy]，src 是插件 spacer.gif
  · **图片 URL 含日文/中文**（Neppu-ネップ-Label-NIKKE-1.jpg）
    → 必须 percent-encode 路径段，否则播放器请求失败
  · 列表封面去掉 -300x134 之类尺寸后缀取原图
"""
import re
import json
import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self, tid="", pg="1", filter=False, extend=None): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None): return {"parse": 1, "url": "", "header": {}, "content": ""}
        def localProxy(self, params): return []

from bs4 import BeautifulSoup
try:
    from curl_cffi import requests as cffi_req
except ImportError:
    cffi_req = None

BASE = "https://mitaku.net"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/",
}

CATS = [
    ("category/ero-cosplay", "🔥 Ero Cosplay"),
    ("category/sexy-set", "💋 Sexy Set"),
    ("category/nude", "🔞 Nude"),
    ("category/online-video", "🎥 Online Video"),
]

TAGS = [
    ("tag/nikke", "🎯 NIKKE"),
    ("tag/blue-archive", "📘 Blue Archive"),
    ("tag/honkai-star-rail", "🚄 Honkai Star Rail"),
    ("tag/genshin-impact", "⚔️ Genshin Impact"),
    ("tag/nier-automata", "🤖 Nier Automata"),
    ("tag/marvel", "🦸 Marvel"),
    ("tag/azur-lane", "⚓ Azur Lane"),
    ("tag/fate-grand-order", "🗡️ Fate/GO"),
]

POST_SEG = ("ero-cosplay", "sexy-set", "nude", "online-video")


def _enc(u):
    """图片路径含非 ASCII（日文假名）→ 逐段 percent-encode，避免播放器请求失败"""
    if not u:
        return ""
    try:
        from urllib.parse import quote, urlsplit, urlunsplit
        parts = urlsplit(u)
        if not parts.path:
            return u
        path = quote(parts.path, safe="/%")
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    except Exception:
        return u


def _get(url, referer=None, timeout=25):
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    last = None
    if cffi_req is not None:
        for imp in ("chrome124", "chrome120", "safari17_0"):
            try:
                r = cffi_req.get(url, headers=h, impersonate=imp, timeout=timeout)
                if r.status_code == 200:
                    return r
                last = r
            except Exception:
                continue
    try:
        return requests.get(url, headers=h, timeout=timeout)
    except Exception:
        return last


def _pic_of(node):
    """封面：优先 wp-post-image，跳过 spacer.gif 占位；去掉 WP 尺寸后缀"""
    if node is None:
        return ""
    imgs = node.find_all("img", class_="wp-post-image") or node.find_all("img")
    for img in imgs:
        for attr in ("data-lazy", "data-src", "data-original", "src"):
            v = img.get(attr, "")
            if not v or "spacer.gif" in v or v.startswith("data:"):
                continue
            if re.search(r"\.(jpg|jpeg|png|webp)", v, re.I):
                if v.startswith("//"):
                    v = "https:" + v
                elif v.startswith("/"):
                    v = BASE + v
                return _enc(re.sub(r"-\d+x\d+(\.\w+)$", r"\1", v))
    return ""


def _parse_articles(soup):
    """列表每篇是 <article class="post-ID ...">，标题在 h2/h3 内的 a"""
    out, seen = [], set()
    for art in soup.find_all("article"):
        a = None
        for h in art.find_all(["h2", "h3", "h4"]):
            cand = h.find("a", href=True)
            if cand:
                a = cand
                break
        if a is None:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = BASE + href
        m = re.search(r"mitaku\.net/([^?#]+?)/?$", href)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen or slug.split("/")[0] not in POST_SEG:
            continue
        seen.add(slug)
        title = a.get_text(strip=True)
        if not title:
            continue
        cls = " ".join(art.get("class", []))
        tags = []
        if "category-nude" in cls:
            tags.append("🔞")
        if "category-online-video" in cls:
            tags.append("🎥")
        remark = "".join(tags) + " 图集" if tags else "🖼️ 图集"
        out.append({
            "vod_id": slug,
            "vod_name": title,
            "vod_pic": _pic_of(art),
            "vod_remarks": remark,
            "type_name": "COS",
        })
    return out


class Spider(BaseSpider):

    CHUNK = 150

    def getName(self):
        return "Mitaku"

    def init(self, extend=""):
        self.base_url = BASE
        self._cache = {}
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.trust_env = False

    def destroy(self):
        if self.session:
            self.session.close()
            self.session = None

    # 关键：声明非视频，宿主才走图片相册而不是流嗅探
    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return True

    def _album_eps(self, token, n):
        if n <= self.CHUNK:
            return "查看图集(%d张)$%s|1" % (n, token)
        eps = []
        for i in range(0, n, self.CHUNK):
            g = i // self.CHUNK + 1
            eps.append("第%d组(%d-%d)$%s|%d" % (g, i + 1, min(i + self.CHUNK, n), token, g))
        return "#".join(eps)

    def homeContent(self, filter=False):
        result = {"class": [{"type_id": t, "type_name": n} for t, n in CATS]}
        if filter:
            filters = {}
            for t, _ in CATS:
                filters[t] = [{
                    "key": "tag",
                    "name": "🏷️ 作品",
                    "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": tg} for tg, n in TAGS],
                }]
            result["filters"] = filters
        return result

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
        return self.categoryContent("category/ero-cosplay", "1")

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        result = {"list": [], "page": str(pg), "pagecount": 9999, "limit": 20, "total": 999999}
        pg_int = int(pg) if str(pg).isdigit() else 1
        if extend and isinstance(extend, dict) and extend.get("tag"):
            tid = extend["tag"]
        try:
            url = f"{BASE}/{tid.strip('/')}/"
            if pg_int > 1:
                url += f"page/{pg_int}/"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = _parse_articles(soup)
        except Exception as e:
            print(f"[mitaku] categoryContent error: {e}")
        return result

    def detailContent(self, ids, filter=False):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid).strip().strip("[]'\"")
        try:
            url = vid if vid.startswith("http") else f"{BASE}/{vid.strip('/')}/"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return {"list": []}
            soup = BeautifulSoup(r.text, "html.parser")

            vod_name = soup.title.get_text(strip=True) if soup.title else vid
            vod_name = re.sub(r"\s*[-–|]\s*Mitaku\s*$", "", vod_name).strip()

            # 正文图：data-lazy 是真图，src 是 spacer 占位
            images = []
            for img in soup.find_all("img"):
                for attr in ("data-lazy", "data-src", "data-original"):
                    v = img.get(attr, "")
                    if not v:
                        continue
                    if "/wp-content/uploads/" in v and re.search(r"\.(jpg|jpeg|png|webp)$", v, re.I):
                        if v.startswith("//"):
                            v = "https:" + v
                        elif v.startswith("/"):
                            v = BASE + v
                        if re.search(r"-\d+x\d+\.\w+$", v) or "Logo" in v:
                            break
                        v = _enc(v)
                        if v not in images:
                            images.append(v)
                    break

            if not images:
                for v in re.findall(r"https://mitaku\.net/wp-content/uploads/[^\s\"'<>]+?\.(?:jpg|jpeg|png|webp)", r.text):
                    if re.search(r"-\d+x\d+\.\w+$", v) or "Logo" in v:
                        continue
                    v = _enc(v)
                    if v not in images:
                        images.append(v)

            def _k(u):
                m = re.search(r"-(\d+)\.\w+$", u)
                return int(m.group(1)) if m else 0
            images.sort(key=_k)

            videos = [_enc(u) for u in dict.fromkeys(
                re.findall(r'https?://[^\s"\'<>]+\.(?:mp4|m3u8)', r.text))]

            self._cache[vid] = images
            play_from = "图集"
            play_url = self._album_eps(vid, len(images))
            if videos:
                play_from += "$$$视频"
                play_url += "$$$" + "#".join(f"视频{i+1}${u}" for i, u in enumerate(videos))

            desc = ""
            md = soup.find("meta", attrs={"name": "description"})
            if md:
                desc = md.get("content", "")

            return {"list": [{
                "vod_id": vid,
                "vod_name": vod_name,
                "vod_pic": images[0] if images else "",
                "vod_remarks": f"{len(images)}张",
                "type_name": "COS",
                "vod_actor": "",
                "vod_content": desc,
                "vod_play_from": play_from,
                "vod_content_type": "image",
                "vod_play_url": play_url,
            }]}
        except Exception as e:
            print(f"[mitaku] detailContent error: {e}")
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        result = {"list": [], "page": str(pg)}
        try:
            pg_int = int(pg) if str(pg).isdigit() else 1
            kw = requests.utils.quote(str(key))
            url = f"{BASE}/page/{pg_int}/?s={kw}" if pg_int > 1 else f"{BASE}/?s={kw}"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            items = _parse_articles(soup)
            for it in items:
                it["vod_remarks"] = "🔍"
            result["list"] = items
        except Exception as e:
            print(f"[mitaku] searchContent error: {e}")
        return result

    def playerContent(self, flag, id, vipFlags=None):
        """pics:// 相册协议 —— 漫画式连续看图，不走视频流"""
        raw = str(id or "")
        token, _, grp = raw.partition("|")
        hdr = json.dumps({"User-Agent": HEADERS["User-Agent"], "Referer": BASE + "/"})
        # 视频线路仍按流播放
        if raw.startswith("http") and re.search(r"\.(mp4|m3u8)", raw, re.I):
            return {"parse": 0, "playUrl": "", "url": raw, "header": hdr}
        try:
            grp = int(grp or 1)
        except Exception:
            grp = 1
        images = self._cache.get(token)
        if not images:
            self.detailContent([token])
            images = self._cache.get(token) or []
        if not images:
            return {"parse": 0, "playUrl": "", "url": "", "header": hdr}
        if len(images) > self.CHUNK:
            images = images[(grp - 1) * self.CHUNK: grp * self.CHUNK]
        return {
            "parse": 0,
            "playUrl": "",
            "url": "pics://" + "&&".join(images),
            "header": hdr,
            "contentType": "image",
            "format": "",
        }

    def localProxy(self, params):
        return []
