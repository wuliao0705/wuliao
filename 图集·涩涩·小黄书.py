# -*- coding: utf-8 -*-
"""
小黄书 xChina (xchina.co) - 聚合·涩涩 Spider
站点: 自研 PHP + Cloudflare(需 TLS 指纹伪装, 多指纹重试)
列表: /photos.html?page=N          → div.item.photo 内 /photo/id-XXX.html
标签: /photos/tag/SLUG?page=N      (37 个标签, 二级目录)
详情: /photo/id-HASH.html          → div.item.text 里 "499P" 给出总张数
图片: https://img.xchina.io/photos/HASH/00001.jpg  (5 位补零, 无防盗链)
      缩略: .../00001_600x0.webp
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
try:
    from curl_cffi import requests as cffi_req
except ImportError:
    cffi_req = None

BASE = "https://xchina.co"
IMGBASE = "https://img.xchina.io/photos"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE + "/photos.html",
}

# 一级分类（带图标）
CATS = [
    ("photos", "🔥 最新套图"),
    ("tag/stockings", "🧦 丝袜"),
    ("tag/lingerie", "👙 情趣内衣"),
    ("tag/cosplay", "🎭 Cosplay"),
    ("tag/jk", "🎒 JK"),
    ("tag/ol", "💼 OL"),
    ("tag/maid", "🎀 女仆"),
    ("tag/bunny-girl", "🐰 兔女郎"),
]

# 二级：全部 37 个标签
TAGS = [
    ("stockings", "🧦 丝袜"), ("lingerie", "👙 情趣内衣"), ("cosplay", "🎭 Cosplay"),
    ("jk", "🎒 JK"), ("ol", "💼 OL"), ("maid", "🎀 女仆"), ("nurse", "💉 护士"),
    ("bunny-girl", "🐰 兔女郎"), ("air-hostess", "✈️ 空姐"), ("teacher", "📚 教师"),
    ("police", "👮 警察"), ("ancient", "🏯 古装"), ("bondage", "⛓️ 捆绑"),
    ("props", "🪄 道具"), ("shaved", "🐯 白虎"), ("lesbian", "👭 女同"),
    ("pussy-visible", "🍑 露底"), ("interaction", "🤝 互动"), ("sex", "💞 性爱"),
    ("exposure", "🌤️ 露出"),
]


def _get(url, referer=None, timeout=25):
    """xchina 图片域和页面域都要 TLS 指纹，标准 requests 一律 403"""
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    last = None
    if cffi_req is not None:
        for imp in ("chrome120", "chrome124", "chrome110", "safari17_0"):
            for _ in range(2):
                try:
                    r = cffi_req.get(url, headers=h, impersonate=imp, timeout=timeout)
                    last = r
                    if r.status_code == 200 and "Just a moment" not in r.text[:600]:
                        return r
                except Exception:
                    pass
                time.sleep(0.4)
    try:
        return requests.get(url, headers=h, timeout=timeout)
    except Exception:
        return last


def _img_bytes(url, referer=None, timeout=25):
    """取图专用：必须走 curl_cffi 指纹，否则 403"""
    h = dict(HEADERS)
    h["Referer"] = referer or (BASE + "/")
    h["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
    for i in range(3):
        if cffi_req is not None:
            try:
                r = cffi_req.get(url, headers=h, impersonate="chrome120", timeout=timeout)
                if r.status_code == 200 and "image" in (r.headers.get("Content-Type") or ""):
                    return (r.content, r.headers.get("Content-Type", "image/jpeg"))
            except Exception:
                pass
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            if r.status_code == 200 and "image" in (r.headers.get("Content-Type") or ""):
                return (r.content, r.headers.get("Content-Type", "image/jpeg"))
        except Exception:
            pass
        time.sleep(0.4 * (i + 1))
    return (b"", "image/jpeg")


def _norm_url(u):
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE + u
    return u


class Spider(BaseSpider):
    def getName(self):
        return "小黄书"

    CHUNK = 150          # 单集最多张数，超出自动分组

    def init(self, extend=""):
        self.base_url = BASE
        self._cache = {}
        # 图片域 img.xchina.io 需要 TLS 指纹，播放器直连会 403 → 默认走本地代理
        self.proxy_pic = True
        try:
            if extend:
                cfg = extend if isinstance(extend, dict) else json.loads(extend)
                if cfg.get("proxy_pic") is False:
                    self.proxy_pic = False
        except Exception:
            pass
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.trust_env = False

    def _proxy_base(self):
        try:
            base = self.getProxyUrl()
            if base:
                return base if "?" in base else base + "?do=py"
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def _pic(self, u):
        """图片经本地代理，由代理侧用 curl_cffi 指纹取回"""
        if not u:
            return ""
        if not self.proxy_pic:
            return u
        try:
            from urllib.parse import quote
            return "%s&url=%s" % (self._proxy_base(), quote(u, safe=""))
        except Exception:
            return u

    def destroy(self):
        if self.session:
            self.session.close()
            self.session = None

    # 关键：声明非视频，宿主才会走图片相册而不是流嗅探
    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return True

    def _album_eps(self, token, n):
        """≤CHUNK 张 → 单集看全本；超出按组分集"""
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
                "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": "tag/" + s} for s, n in TAGS],
            }]
            result["filters"] = {t: tag_filter for t, _ in CATS}
        return result

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
        return self.categoryContent("photos", "1")

    def _parse_list(self, soup, remark=""):
        out, seen = [], set()
        for div in soup.find_all("div", class_="item"):
            cls = " ".join(div.get("class", []))
            if "photo" not in cls:
                continue
            a = div.find("a", href=re.compile(r"/photo/id-"))
            if not a:
                continue
            m = re.search(r"/photo/(id-\w+)\.html", a["href"])
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)

            # 标题：容器文本首段（尾部会带 "1502P 4" 之类统计，剥掉）
            raw = div.get_text(" ", strip=True)
            title = re.sub(r"\s*\d+P(\s*\+\s*\d+V)?\s*\d*\s*$", "", raw).strip()
            if not title:
                title = a.get("title", "") or pid
            cm = re.search(r"(\d+)\s*P", raw)
            remarks = f"{cm.group(1)}P" if cm else (remark or "🖼️")

            # 封面：优先容器内真实 img，否则按 hash 构造第一张 webp
            pic = ""
            for img in div.find_all("img"):
                v = img.get("src") or img.get("data-src") or img.get("data-original") or ""
                if v and "icon" not in v and re.search(r"\.(jpg|jpeg|png|webp)", v, re.I):
                    pic = _norm_url(v)
                    break
            if not pic:
                pic = f"{IMGBASE}/{pid[3:]}/00001_600x0.webp"

            out.append({
                "vod_id": pid,
                "vod_name": title[:80],
                "vod_pic": self._pic(pic),
                "vod_remarks": remarks,
                "type_name": "套图",
            })
        return out

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        result = {"list": [], "page": str(pg), "pagecount": 9999, "limit": 20, "total": 999999}
        pg_int = int(pg) if str(pg).isdigit() else 1
        if extend and isinstance(extend, dict) and extend.get("tag"):
            tid = extend["tag"]
        try:
            if tid.startswith("tag/"):
                url = f"{BASE}/photos/{tid}"
                if pg_int > 1:
                    url += f"?page={pg_int}"
            else:
                url = f"{BASE}/photos.html"
                if pg_int > 1:
                    url += f"?page={pg_int}"
            r = _get(url, referer=BASE + "/photos.html")
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = self._parse_list(soup)
        except Exception as e:
            print(f"[xchina] categoryContent error: {e}")
        return result

    def detailContent(self, ids, filter=False):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid).strip().strip("[]'\"")
        if not vid.startswith("id-"):
            vid = "id-" + vid
        pid = vid[3:]
        try:
            url = f"{BASE}/photo/{vid}.html"
            r = _get(url, referer=BASE + "/photos.html")
            if r is None or r.status_code != 200:
                return {"list": []}
            soup = BeautifulSoup(r.text, "html.parser")

            vod_name = soup.title.get_text(strip=True) if soup.title else vid
            vod_name = re.sub(r"\s*-\s*小黄书 xChina\s*$", "", vod_name).strip()

            # 总张数：div.item.text 里的 "499P"
            total = 0
            for div in soup.find_all("div", class_="item"):
                t = div.get_text(" ", strip=True)
                m = re.fullmatch(r"(\d+)P", t)
                if m:
                    total = int(m.group(1))
                    break
            if not total:
                m = re.search(r"\b(\d{2,5})\s*P\b", soup.get_text(" ", strip=True))
                if m:
                    total = int(m.group(1))

            # 页面里已出现的真实图 URL（顺带确认 hash 正确）
            found = []
            for u in re.findall(rf"https://img\.xchina\.io/photos/{re.escape(pid)}/\d+\.jpg", r.text):
                if u not in found:
                    found.append(u)

            # 图片按 5 位补零序号构造（实测 00001.jpg ... N.jpg 全部 200，无防盗链）
            if total:
                images = [f"{IMGBASE}/{pid}/{i:05d}.jpg" for i in range(1, total + 1)]
            else:
                images = found or [f"{IMGBASE}/{pid}/00001.jpg"]

            # 演员/系列
            actor, series = "", ""
            for a in soup.find_all("a", href=True):
                if "/model/" in a["href"] and not actor:
                    actor = a.get_text(strip=True)
                if "/photos/series-" in a["href"] and not series:
                    series = a.get_text(strip=True)

            desc = ""
            md = soup.find("meta", attrs={"name": "description"})
            if md:
                desc = md.get("content", "")[:300]

            self._cache[pid] = images
            return {"list": [{
                "vod_id": vid,
                "vod_name": vod_name,
                "vod_pic": self._pic(f"{IMGBASE}/{pid}/00001_600x0.webp"),
                "vod_remarks": f"{len(images)}张",
                "type_name": series or "套图",
                "vod_actor": actor,
                "vod_content": desc,
                "vod_play_from": "图集",
            "vod_content_type": "image",
                "vod_play_url": self._album_eps(pid, len(images)),
            }]}
        except Exception as e:
            print(f"[xchina] detailContent error: {e}")
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        result = {"list": [], "page": str(pg)}
        try:
            pg_int = int(pg) if str(pg).isdigit() else 1
            kw = requests.utils.quote(str(key))
            url = f"{BASE}/search.html?keyword={kw}"
            if pg_int > 1:
                url += f"&page={pg_int}"
            r = _get(url, referer=BASE + "/photos.html")
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = self._parse_list(soup, remark="🔍")
        except Exception as e:
            print(f"[xchina] searchContent error: {e}")
        return result

    def playerContent(self, flag, id, vipFlags=None):
        """pics:// 相册协议 —— 漫画式连续看图，不走视频流"""
        raw = str(id or "")
        pid, _, grp = raw.partition("|")
        pid = pid.strip()
        if pid.startswith("id-"):
            pid = pid[3:]
        try:
            grp = int(grp or 1)
        except Exception:
            grp = 1

        images = self._cache.get(pid)
        if not images:
            self.detailContent(["id-" + pid])
            images = self._cache.get(pid) or []
        if not images:
            return {"parse": 0, "playUrl": "", "url": "",
                    "header": json.dumps({"User-Agent": HEADERS["User-Agent"],
                                          "Referer": BASE + "/"})}

        if len(images) > self.CHUNK:
            images = images[(grp - 1) * self.CHUNK: grp * self.CHUNK]
        urls = [self._pic(u) for u in images]
        return {
            "parse": 0,
            "playUrl": "",
            "url": "pics://" + "&&".join(urls),
            "header": json.dumps({"User-Agent": HEADERS["User-Agent"],
                                  "Referer": BASE + "/"}),
            "contentType": "image",
            "format": "",
        }

    # ── 本地代理：用 curl_cffi 指纹取图（播放器直连会 403）──────
    def localProxy(self, param):
        try:
            from urllib.parse import unquote
            url = unquote((param or {}).get("url", ""))
            if not url.startswith("http"):
                return [404, "text/plain", b"bad url"]
            data, ctype = _img_bytes(url, referer=BASE + "/")
            if not data:
                return [502, "text/plain", b"upstream error"]
            return [200, ctype, data]
        except Exception as e:
            return [500, "text/plain", str(e).encode("utf-8", "ignore")]
