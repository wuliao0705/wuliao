# -*- coding: utf-8 -*-
"""
Danryoku (danryoku.com) - 图集·涩涩 Spider
站点: WordPress(GenerateBlocks) + Cloudflare
列表: /category/{cosplay,nsfw,ai}/ 与 /category/country/{japan,china,korea,taiwan,western}/
      分页 /page/N/  (cosplay 实测 735 页)
详情: /SLUG/  正文图 https://img.danryoku.com/YYYY/MM/xxxx.webp
      列表封面在 img[data-lazy-src]
"""
import re, json, requests
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

BASE = "https://danryoku.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": BASE + "/",
}

CATS = [
    ("category/cosplay", "🎭 COSPLAY"),
    ("category/nsfw", "🔞 NSFW"),
    ("category/ai", "🤖 AI"),
    ("video/video", "🎥 VIDEO"),
    ("random-photobook", "🎲 随机"),
]

COUNTRY = [
    ("category/country/japan", "🇯🇵 日本"),
    ("category/country/china", "🇨🇳 中国"),
    ("category/country/korea", "🇰🇷 韩国"),
    ("category/country/taiwan", "🇹🇼 台湾"),
    ("category/country/western", "🇪🇺 欧美"),
]

# 站内导航之外的功能页，列表解析时需排除
_SKIP_SEG = ("category", "tag", "page", "video", "random-photobook", "author", "wp-content",
             "wp-json", "cdn-cgi", "feed")


def _get(url, referer=None, timeout=25):
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    last = None
    if cffi_req is not None:
        for imp in ("chrome120", "chrome124", "safari17_0"):
            try:
                r = cffi_req.get(url, headers=h, impersonate=imp, timeout=timeout)
                last = r
                if r.status_code == 200:
                    return r
            except Exception:
                continue
    try:
        return requests.get(url, headers=h, timeout=timeout)
    except Exception:
        return last


def _pic_of(node):
    """封面在 img[data-lazy-src]；src 常是 svg 占位"""
    if node is None:
        return ""
    for img in node.find_all("img"):
        for attr in ("data-lazy-src", "data-src", "data-original", "src"):
            v = img.get(attr, "")
            if not v or v.startswith("data:"):
                continue
            if re.search(r"\.(webp|jpg|jpeg|png)", v, re.I):
                return "https:" + v if v.startswith("//") else v
    return ""


def _parse_articles(soup, remark="🖼️ 图集"):
    out, seen = [], set()
    for art in soup.find_all("article"):
        h = None
        for tag in ("h2", "h3", "h1", "h4"):
            h = art.find(tag)
            if h:
                break
        a = (h.find("a", href=True) if h else None) or art.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = BASE + href
        m = re.search(r"danryoku\.com/([^?#]+?)/?$", href)
        if not m:
            continue
        slug = m.group(1)
        if slug.split("/")[0] in _SKIP_SEG or slug in seen:
            continue
        seen.add(slug)
        title = (h.get_text(strip=True) if h else "") or a.get("title", "") or a.get_text(strip=True)
        if not title:
            img = art.find("img", alt=True)
            title = img["alt"] if img else slug
        out.append({
            "vod_id": slug,
            "vod_name": title[:90],
            "vod_pic": _pic_of(art),
            "vod_remarks": remark,
            "type_name": "写真",
        })
    return out


class Spider(BaseSpider):
    def getName(self):
        return "Danryoku"

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

    CHUNK = 150

    def _album_eps(self, token, n):
        if n <= self.CHUNK:
            return "查看图集(%d张)$%s|1" % (n, token)
        eps = []
        for i in range(0, n, self.CHUNK):
            g = i // self.CHUNK + 1
            eps.append("第%d组(%d-%d)$%s|%d" % (g, i + 1, min(i + self.CHUNK, n), token, g))
        return "#".join(eps)

    def homeContent(self, filter=False):
        result = {"class": [{"type_id": t, "type_name": n} for t, n in CATS + COUNTRY]}
        if filter:
            country_filter = [{
                "key": "country",
                "name": "🌏 地区",
                "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": t} for t, n in COUNTRY],
            }]
            result["filters"] = {t: country_filter for t, _ in CATS}
        return result

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
        return self.categoryContent("category/cosplay", "1")

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        result = {"list": [], "page": str(pg), "pagecount": 9999, "limit": 30, "total": 999999}
        pg_int = int(pg) if str(pg).isdigit() else 1
        if extend and isinstance(extend, dict) and extend.get("country"):
            tid = extend["country"]
        try:
            url = f"{BASE}/{tid.strip('/')}/"
            if pg_int > 1 and tid != "random-photobook":
                url += f"page/{pg_int}/"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = _parse_articles(soup)
        except Exception as e:
            print(f"[danryoku] categoryContent error: {e}")
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
            vod_name = re.sub(r"\s*[-–|]\s*Danryoku(\.com)?\s*$", "", vod_name).strip()

            # 正文图：img.danryoku.com 下的 webp/jpg，含 data-lazy-src
            images = []
            for img in soup.find_all("img"):
                for attr in ("data-lazy-src", "data-src", "src"):
                    v = img.get(attr, "")
                    if v and "img.danryoku.com" in v and re.search(r"\.(webp|jpg|jpeg|png)$", v, re.I):
                        v = "https:" + v if v.startswith("//") else v
                        if v not in images:
                            images.append(v)
                        break
            if not images:
                for v in re.findall(r"https://img\.danryoku\.com/[^\s\"'<>]+?\.(?:webp|jpg|jpeg|png)", r.text):
                    if v not in images:
                        images.append(v)

            # 视频
            videos = list(dict.fromkeys(
                re.findall(r"https?://[^\s\"'<>]+\.(?:mp4|m3u8)", r.text)))

            # 标签 → 备注
            tags = [a.get_text(strip=True) for a in soup.find_all("a", href=re.compile(r"/tag/"))]
            tags = list(dict.fromkeys([t for t in tags if t]))[:4]

            desc = ""
            md = soup.find("meta", attrs={"name": "description"})
            if md:
                desc = md.get("content", "")[:300]

            self._cache[vid] = images
            play_from = "图集"
            play_url = self._album_eps(vid, len(images))
            if videos:
                play_from += "$$$视频"
                play_url += "$$$" + "#".join(f"视频{i+1}${u}" for i, u in enumerate(videos))

            return {"list": [{
                "vod_id": vid,
                "vod_name": vod_name,
                "vod_pic": images[0] if images else "",
                "vod_remarks": f"{len(images)}张",
                "type_name": "写真",
                "vod_actor": " / ".join(tags),
                "vod_content": desc,
                "vod_play_from": play_from,
                "vod_content_type": "image",
                "vod_play_url": play_url,
            }]}
        except Exception as e:
            print(f"[danryoku] detailContent error: {e}")
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        result = {"list": [], "page": str(pg)}
        try:
            pg_int = int(pg) if str(pg).isdigit() else 1
            kw = requests.utils.quote(str(key))
            # ?s= 会被 Cloudflare 挡(403)，/search/KW/ 正常
            url = f"{BASE}/search/{kw}/"
            if pg_int > 1:
                url += f"page/{pg_int}/"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = _parse_articles(soup, remark="🔍")
        except Exception as e:
            print(f"[danryoku] searchContent error: {e}")
        return result

    def playerContent(self, flag, id, vipFlags=None):
        """pics:// 相册协议 —— 漫画式连续看图，不走视频流"""
        raw = str(id or "")
        token, _, grp = raw.partition("|")
        try:
            grp = int(grp or 1)
        except Exception:
            grp = 1
        images = self._cache.get(token)
        if not images:
            self.detailContent([token])
            images = self._cache.get(token) or []
        hdr = json.dumps({"User-Agent": HEADERS["User-Agent"], "Referer": BASE + "/"})
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
