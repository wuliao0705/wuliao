# -*- coding: utf-8 -*-
"""
Hentai Cosplay (hentai-cosplay-xxx.com) - COS·涩涩 Spider
站点: 自研 PHP，无 CF 挑战；注意 curl_cffi 对该站握手会断，必须用标准 requests
列表: /search/            (最新，分页 /search/page/N/)
      /search/tag/SLUG/   (标签，分页 .../page/N/)
      /ranking-{like,download,bookmark}/type/{day,week,month,year}/  (分页同上)
详情: /image/SLUG/
图片: https://staticNN.hentai-cosplay-xxx.com/upload/YYYYMMDD/DIR/ID/p=700/N.webp
      去掉 p=NNN/ 段即原图(体积最大)；p=160x200 为列表缩略
"""
import re, json, time, requests
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

BASE = "https://hentai-cosplay-xxx.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/",
}

# 一级分类（带图标）
CATS = [
    ("search", "🆕 最新"),
    ("ranking-like/type/day", "❤️ 日榜·喜欢"),
    ("ranking-like/type/week", "❤️ 周榜·喜欢"),
    ("ranking-download/type/week", "⬇️ 周榜·下载"),
    ("ranking-bookmark/type/week", "🔖 周榜·收藏"),
    ("ranking-like/type/month", "🏆 月榜·喜欢"),
    ("search/tag/cosplay", "🎭 Cosplay"),
    ("search/tag/lesbian", "👭 Lesbian"),
]

# 二级：标签
TAGS = [
    ("cosplay", "🎭 Cosplay"),
    ("lesbian", "👭 Lesbian"),
    ("beautiful-breasts", "🍒 Beautiful Breasts"),
    ("fgo", "🗡️ Fate/GO"),
    ("rom", "📀 ROM"),
    ("swimsuit", "🏖️ Swimsuit"),
    ("uniform", "👔 Uniform"),
    ("nude", "🔞 Nude"),
]

# 榜单周期
PERIODS = [("day", "日"), ("week", "周"), ("month", "月"), ("year", "年")]


def _get(url, referer=None, timeout=25):
    """该站 TLS 对 curl_cffi 会 SSL_ERROR_SYSCALL，仅用标准 requests；静态图床偶发 EOF → 重试"""
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    for i in range(3):
        try:
            return requests.get(url, headers=h, timeout=timeout)
        except Exception:
            time.sleep(0.5 * (i + 1))
    return None


def _full_size(u):
    """p=700/1.webp 或 p=160x200/1.webp → 去掉尺寸段取原图"""
    return re.sub(r"/p=[^/]+/", "/", u) if u else ""


class Spider(BaseSpider):
    def getName(self):
        return "HentaiCosplay"

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
        result = {"class": [{"type_id": t, "type_name": n} for t, n in CATS]}
        if filter:
            tag_filter = [{
                "key": "tag",
                "name": "🏷️ 标签",
                "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": "search/tag/" + s} for s, n in TAGS],
            }]
            period_filter = [{
                "key": "period",
                "name": "📅 周期",
                "value": [{"n": n, "v": p} for p, n in PERIODS],
            }]
            f = {}
            for t, _ in CATS:
                f[t] = period_filter if t.startswith("ranking-") else tag_filter
            result["filters"] = f
        return result

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
        return self.categoryContent("search", "1")

    def _parse_list(self, soup, remark="🖼️"):
        """<a href="/image/SLUG/"><img alt="标题" src=".../p=160x200/N.webp"></a>
        同一 slug 出现两次：一次图(带 alt)，一次文字标题"""
        pics, titles, order = {}, {}, []
        for a in soup.find_all("a", href=re.compile(r"^/image/")):
            slug = a["href"].strip("/").split("/")[-1]
            if slug not in order:
                order.append(slug)
            img = a.find("img")
            if img is not None:
                src = img.get("data-src") or img.get("src", "")
                if src and slug not in pics:
                    pics[slug] = src
                alt = (img.get("alt") or "").strip()
                if alt and slug not in titles:
                    titles[slug] = alt
            else:
                t = a.get_text(strip=True)
                if t and slug not in titles:
                    titles[slug] = t

        out = []
        for slug in order:
            name = titles.get(slug) or slug.replace("-", " ")
            # 标题尾部常带 (93P) → 提炼成备注
            cm = re.search(r"\((\d+)\s*(?:P|photos?)\)", name, re.I)
            out.append({
                "vod_id": slug,
                "vod_name": name[:90],
                "vod_pic": pics.get(slug, ""),
                "vod_remarks": (cm.group(1) + "P") if cm else remark,
                "type_name": "COS",
            })
        return out

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        result = {"list": [], "page": str(pg), "pagecount": 9999, "limit": 32, "total": 999999}
        pg_int = int(pg) if str(pg).isdigit() else 1
        if extend and isinstance(extend, dict):
            if extend.get("tag"):
                tid = extend["tag"]
            elif extend.get("period") and tid.startswith("ranking-"):
                tid = re.sub(r"/type/\w+$", "/type/" + extend["period"], tid)
        try:
            url = f"{BASE}/{tid.strip('/')}/"
            if pg_int > 1:
                url += f"page/{pg_int}/"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = self._parse_list(soup)
        except Exception as e:
            print(f"[hentai-cosplay] categoryContent error: {e}")
        return result

    def detailContent(self, ids, filter=False):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid).strip().strip("[]'\"")
        slug = vid.strip("/").split("/")[-1]
        try:
            r = _get(f"{BASE}/image/{slug}/", referer=BASE)
            if r is None or r.status_code != 200:
                return {"list": []}
            soup = BeautifulSoup(r.text, "html.parser")

            vod_name = soup.title.get_text(strip=True) if soup.title else slug
            vod_name = re.sub(r"\s*-\s*Hentai Cosplay\s*$", "", vod_name).strip()

            # 正文图：本图集的 upload 目录 = 出现次数最多的那个前缀
            raw = re.findall(
                r"https://static\d+\.hentai-cosplay-xxx\.com/upload/\d+/\d+/\d+/p=[^/]+/(\d+)\.(?:webp|jpg|png)",
                r.text)
            prefixes = re.findall(
                r"(https://static\d+\.hentai-cosplay-xxx\.com/upload/\d+/\d+/\d+)/p=[^/]+/\d+\.(?:webp|jpg|png)",
                r.text)
            images = []
            if prefixes:
                # 主目录取众数（页面还有推荐位缩略图，前缀不同）
                main = max(set(prefixes), key=prefixes.count)
                nums = sorted({int(n) for p, n in zip(prefixes, raw) if p == main})
                ext_m = re.search(re.escape(main) + r"/p=[^/]+/\d+\.(webp|jpg|png)", r.text)
                ext = ext_m.group(1) if ext_m else "webp"
                # 页面只渲染部分图 → 按最大序号补齐全量（实测 1..max 全部 200）
                mx = max(nums) if nums else 0
                if mx and len(nums) < mx:
                    nums = list(range(1, mx + 1))
                images = [f"{main}/{n}.{ext}" for n in nums]

            # 兜底：直接从 img 标签取并去掉尺寸段
            if not images:
                for img in soup.find_all("img"):
                    src = img.get("data-src") or img.get("src", "")
                    if "hentai-cosplay-xxx.com/upload/" in src:
                        u = _full_size(src)
                        if u not in images:
                            images.append(u)

            # 标签
            tags = [a.get_text(strip=True) for a in soup.find_all("a", href=re.compile(r"/search/tag/"))]
            tags = list(dict.fromkeys([t for t in tags if t]))[:6]

            self._cache[slug] = images
            play_url = self._album_eps(slug, len(images))
            return {"list": [{
                "vod_id": slug,
                "vod_name": vod_name,
                "vod_pic": images[0] if images else "",
                "vod_remarks": f"{len(images)}张",
                "type_name": "COS",
                "vod_actor": " / ".join(tags),
                "vod_content": "",
                "vod_play_from": "图集",
            "vod_content_type": "image",
                "vod_play_url": play_url,
            }]}
        except Exception as e:
            print(f"[hentai-cosplay] detailContent error: {e}")
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        result = {"list": [], "page": str(pg)}
        try:
            pg_int = int(pg) if str(pg).isdigit() else 1
            kw = requests.utils.quote(str(key))
            url = f"{BASE}/search/keyword/{kw}/"
            if pg_int > 1:
                url += f"page/{pg_int}/"
            r = _get(url, referer=BASE)
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = self._parse_list(soup, remark="🔍")
        except Exception as e:
            print(f"[hentai-cosplay] searchContent error: {e}")
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
