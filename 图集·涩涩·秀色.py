# -*- coding: utf-8 -*-
"""
秀色女神 (xsnvshen.com) — 图集 Spider
Play : pics://  图片相册协议（漫画式连续看图）

侦察结论：
  · 列表 /album/tN/ /girl/tN/   分页只认 ?p=N（?page= / index_N 均无效）
  · 详情 /album/ID             标题取 h1（title 会把标签串在后面）
  · 图片 //img.xsnvshen.com/album/DIR/ID/000.jpg  三位补零、从 000 起
  · **防盗链**：原图必须带 Referer = 该图集详情页
        Referer=https://www.xsnvshen.com/        → 403
        Referer=https://www.xsnvshen.com/album/ID → 200
    缩略图 thumb_205x308/ 无 Referer 也能取 → 列表封面直接用，不代理
    原图默认走 localProxy 代理（proxy_pic=True），由本地补正确 Referer
  · 张数 span.num，页面图不全时按序号构造全量
  · 女神大全 /girl/ID 是二级目录 → g_ID，detail 里每套图集一条线路
"""
import re
import json
import time

try:
    import requests
except Exception:
    requests = None
try:
    from curl_cffi import requests as cffi_req
except Exception:
    cffi_req = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None): return {}
        def localProxy(self, params): return []

from bs4 import BeautifulSoup

BASE = "https://www.xsnvshen.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE + "/",
}

CATS = [
    ("album", "📷 女神图集"),
    ("album/t147", "🌟 秀人网"),
    ("album/t2", "🔥 性感"),
    ("album/t183", "🧦 黑丝"),
    ("album/t138", "👙 比基尼"),
    ("album/t178", "🔞 大尺度"),
    ("album/t176", "🏠 私房照"),
    ("album/t108", "🇯🇵 日本"),
    ("album/t180", "🇰🇷 韩国"),
    ("girl", "🌸 女神大全"),
    ("girl/t79", "🇨🇳 内地女神"),
    ("girl/t72", "🇹🇼 台湾正妹"),
]

ALBUM_TAGS = [
    ("t167", "丁字裤"), ("t138", "比基尼"), ("t183", "黑丝"), ("t175", "内衣"),
    ("t189", "湿身"), ("t140", "旗袍"), ("t146", "肚兜"), ("t151", "空姐"),
    ("t168", "护士"), ("t173", "和服"), ("t93", "制服"), ("t97", "校服"),
    ("t115", "女仆"), ("t195", "瑜伽服"), ("t196", "婚纱"), ("t187", "角色扮演"),
    ("t2", "性感"), ("t96", "诱惑"), ("t104", "气质"), ("t107", "清纯"),
    ("t123", "冷艳"), ("t141", "野性"), ("t114", "萌系"), ("t128", "极品"),
    ("t171", "萝莉"), ("t100", "童颜巨乳"), ("t178", "大尺度"),
    ("t88", "骨感"), ("t95", "美臀"), ("t185", "肉感"), ("t166", "美腿"),
    ("t137", "清新"), ("t130", "白嫩"), ("t149", "尤物"), ("t101", "小麦色"),
    ("t131", "波涛胸涌"), ("t143", "人间胸器"),
    ("t160", "街拍"), ("t116", "浴室"), ("t126", "户外"), ("t169", "沙滩"),
    ("t190", "泳池"), ("t161", "家居"), ("t176", "私房照"),
    ("t92", "中国内地"), ("t155", "香港"), ("t165", "台湾"), ("t108", "日本"),
    ("t180", "韩国"), ("t90", "马来西亚"), ("t156", "泰国"), ("t150", "欧美"),
    ("t191", "混血"),
    ("t1", "爱蜜社"), ("t133", "尤蜜荟"), ("t110", "蜜桃社"), ("t91", "尤物馆"),
    ("t102", "美媛馆"), ("t119", "波萝社"), ("t120", "推女郎"), ("t121", "兔几盟"),
    ("t127", "爱尤物"), ("t162", "尤果网"), ("t192", "推女神"), ("t122", "魅妍社"),
    ("t89", "头条女神"), ("t94", "克拉女神"), ("t113", "嗲囡囡"), ("t193", "语画界"),
    ("t147", "秀人网"), ("t154", "模范学院"),
]

GIRL_TAGS = [
    ("t79", "内地女神"), ("t68", "香港女神"), ("t72", "台湾正妹"), ("t28", "澳门美女"),
    ("t84", "韩国美女"), ("t36", "日本美女"), ("t55", "大马美女"), ("t58", "新加坡"),
    ("t16", "泰国美女"), ("t13", "混血女神"),
    ("t45", "气质女神"), ("t76", "萝莉"), ("t66", "美少女"), ("t59", "熟女"),
    ("t12", "美腿"), ("t49", "清纯美女"), ("t86", "美臀"), ("t27", "童颜巨乳"),
    ("t65", "波涛汹涌"), ("t78", "G奶女神"),
    ("t80", "演员"), ("t47", "歌手"), ("t25", "主播主持"), ("t24", "模特麻豆"),
    ("t15", "学生"), ("t42", "OL"), ("t35", "舞蹈家"), ("t77", "空姐"),
    ("t85", "体坛美女"), ("t75", "足球宝贝"),
]

_TAG_NAME = {}
for _t, _n in ALBUM_TAGS + GIRL_TAGS:
    _TAG_NAME[_t] = _n


def _norm(u):
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE + u
    return u


def _to_thumb(u, size="thumb_205x308"):
    """任意图 → 指定缩略图规格（无 Referer 也能取，适合列表封面）"""
    u = _norm(u)
    if not u:
        return ""
    if re.search(r"/thumb_[0-9x]+/", u):
        return re.sub(r"/thumb_[0-9x]+/", "/%s/" % size, u)
    return u.replace("/album/", "/%s/album/" % size, 1)


def _to_full(u):
    """缩略图 → 原图（需要正确 Referer，走代理）"""
    return re.sub(r"/thumb_[0-9x]+/", "/", _norm(u))


class Spider(BaseSpider):

    CHUNK = 150          # 单集最多张数，超出自动分组

    # ── 生命周期 ────────────────────────────────────────────────
    def getName(self):
        return "秀色女神"

    def init(self, extend=""):
        self.host = BASE
        self.headers = dict(HEADERS)
        # 原图有精确 Referer 防盗链 → 默认走本地代理；传 {"proxy_pic": false} 可关
        self.proxy_pic = True
        self._cache = {}
        try:
            if extend:
                cfg = extend if isinstance(extend, dict) else json.loads(extend)
                if cfg.get("cookie"):
                    self.headers["Cookie"] = cfg["cookie"]
                if cfg.get("proxy_pic") is False:
                    self.proxy_pic = False
                if cfg.get("ua"):
                    self.headers["User-Agent"] = cfg["ua"]
        except Exception:
            pass
        self.session = None
        if requests is not None:
            try:
                self.session = requests.Session()
                self.session.headers.update(self.headers)
                self.session.trust_env = False
            except Exception:
                self.session = None
        return self

    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass
        self.session = None

    # 走相册阅读器
    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return True

    # ── HTTP ────────────────────────────────────────────────────
    def _get(self, url, referer=None, timeout=25):
        """站点对标准 requests 偶发 SSL EOF → 优先 curl_cffi 指纹"""
        h = dict(self.headers)
        if referer:
            h["Referer"] = referer
        if cffi_req is not None:
            for imp in ("chrome120", "chrome124"):
                try:
                    r = cffi_req.get(url, headers=h, impersonate=imp, timeout=timeout)
                    if r.status_code == 200:
                        r.encoding = "utf-8"
                        return r.text
                except Exception:
                    continue
        try:
            r = (self.session or requests).get(url, headers=h, timeout=timeout)
            if r.status_code == 200:
                r.encoding = "utf-8"          # 站点无 charset meta，必须强制
                return r.text
        except Exception:
            pass
        return ""

    def _bytes(self, url, referer=None):
        """取图：原图必须带该图集详情页做 Referer"""
        h = dict(self.headers)
        h["Referer"] = referer or (self.host + "/")
        h["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
        for i in range(3):
            if cffi_req is not None:
                try:
                    r = cffi_req.get(url, headers=h, impersonate="chrome120", timeout=25)
                    if r.status_code == 200 and "image" in (r.headers.get("Content-Type") or ""):
                        return (r.content, r.headers.get("Content-Type", "image/jpeg"))
                except Exception:
                    pass
            try:
                r = (self.session or requests).get(url, headers=h, timeout=25)
                if r.status_code == 200 and "image" in (r.headers.get("Content-Type") or ""):
                    return (r.content, r.headers.get("Content-Type", "image/jpeg"))
            except Exception:
                pass
            time.sleep(0.4 * (i + 1))
        return (b"", "image/jpeg")

    # ── 图片地址 ────────────────────────────────────────────────
    def _proxy_base(self):
        try:
            base = self.getProxyUrl()
            if base:
                return base if "?" in base else base + "?do=py"
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def _pic_cover(self, u):
        """列表封面：用 thumb_205x308，任何 Referer 都能取，无需代理"""
        return _to_thumb(u)

    def _pic_full(self, u, aid=""):
        """正文原图：默认经本地代理补 Referer"""
        u = _to_full(u)
        if not u:
            return ""
        if not self.proxy_pic:
            return u
        try:
            from urllib.parse import quote
            ref = "%s/album/%s" % (self.host, aid) if aid else (self.host + "/")
            return "%s&url=%s&ref=%s" % (self._proxy_base(), quote(u, safe=""),
                                         quote(ref, safe=""))
        except Exception:
            return u

    # ── 首页 ────────────────────────────────────────────────────
    def homeContent(self, filter=True):
        result = {"class": [{"type_id": t, "type_name": n} for t, n in CATS]}
        if filter:
            album_f = [{
                "key": "tag", "name": "🏷️ 标签",
                "value": [{"n": "全部", "v": "album"}] +
                         [{"n": n, "v": "album/" + t} for t, n in ALBUM_TAGS],
            }]
            girl_f = [{
                "key": "tag", "name": "🏷️ 分类",
                "value": [{"n": "全部", "v": "girl"}] +
                         [{"n": n, "v": "girl/" + t} for t, n in GIRL_TAGS],
            }]
            result["filters"] = {t: (girl_f if t.startswith("girl") else album_f)
                                 for t, _ in CATS}
        return result

    def homeVideoContent(self):
        return {"list": self.categoryContent("album", "1").get("list", [])}

    # ── 列表 ────────────────────────────────────────────────────
    def _parse_list(self, soup, tid=""):
        out, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"/album/\d+")):
            m = re.search(r"/album/(\d+)", a["href"])
            if not m:
                continue
            aid = m.group(1)
            # 分类页标题在 title 属性；搜索页无 title、标题在文本里
            title = (a.get("title") or "").strip()
            if not title:
                txt = a.get_text(strip=True)
                if not txt or re.fullmatch(r"\d+张", txt):
                    continue
                title = txt
            if aid in seen:
                continue
            seen.add(aid)

            raw = ""
            img = a.find("img")
            if img is not None:
                raw = img.get("src") or img.get("data-src") or ""
            if not raw:
                box = a.find_parent("li") or a.find_parent("div")
                if box is not None:
                    for im in box.find_all("img"):
                        v = im.get("src") or im.get("data-src") or ""
                        if "xsnvshen.com" in v and re.search(r"\.(jpg|jpeg|png|webp)", v, re.I):
                            raw = v
                            break

            remarks = "🖼️ 图集"
            box = a.find_parent("li") or a.find_parent("div")
            if box is not None:
                num = box.find("span", class_="num")
                if num is not None and num.get_text(strip=True).isdigit():
                    remarks = num.get_text(strip=True) + "张"

            slug = tid.split("/")[-1] if "/" in tid else ""
            out.append({
                "vod_id": aid,
                "vod_name": title[:90],
                "vod_pic": self._pic_cover(raw),
                "vod_remarks": remarks,
                "type_name": _TAG_NAME.get(slug, "图集"),
            })
        return out

    def _parse_models(self, soup):
        """女神大全：<a href="/girl/ID" title="艺名"><img></a> → g_ID"""
        out, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"/girl/\d+")):
            m = re.search(r"/girl/(\d+)", a["href"])
            if not m:
                continue
            gid = m.group(1)
            title = (a.get("title") or "").strip()
            img = a.find("img")
            if img is None or not title or gid in seen:
                continue
            seen.add(gid)
            out.append({
                "vod_id": "g_" + gid,
                "vod_name": title[:60],
                "vod_pic": self._pic_cover(img.get("src") or img.get("data-src", "")),
                "vod_remarks": "👩 女神",
                "type_name": "女神",
            })
        return out

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        result = {"list": [], "page": str(pg), "pagecount": 9999, "limit": 25, "total": 999999}
        try:
            pg_int = int(str(pg))
        except Exception:
            pg_int = 1
        if extend:
            try:
                ex = extend if isinstance(extend, dict) else json.loads(extend)
                if ex.get("tag"):
                    tid = ex["tag"]
            except Exception:
                pass
        try:
            url = "%s/%s/" % (self.host, str(tid).strip("/"))
            if pg_int > 1:
                url += "?p=%d" % pg_int          # 唯一有效的分页参数
            html = self._get(url, referer=self.host + "/")
            if not html:
                return result
            soup = BeautifulSoup(html, "html.parser")
            if str(tid) == "girl" or str(tid).startswith("girl/"):
                result["list"] = self._parse_models(soup)
            else:
                result["list"] = self._parse_list(soup, tid)
        except Exception as e:
            print("[xsnvshen] category error: %s" % e)
        return result

    # ── 取图 ────────────────────────────────────────────────────
    def _album_images(self, aid):
        """返回 (标题, 原图列表(未代理), 简介, 标签)"""
        html = self._get("%s/album/%s" % (self.host, aid), referer=self.host + "/")
        if not html:
            return "", [], "", []
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        h1 = soup.find("h1")
        if h1 is not None:
            title = h1.get_text(strip=True)
        if not title and soup.title:
            title = re.sub(r"[_\-]\s*秀色女神\s*$", "", soup.title.get_text(strip=True)).strip()
            title = re.split(r"\s{2,}", title)[0].strip()

        imgs = []
        for img in soup.find_all("img"):
            v = img.get("src") or img.get("data-src") or ""
            if re.search(r"/album/\d+/\d+/\d+\.jpg", v):
                u = _to_full(v)
                if u not in imgs:
                    imgs.append(u)
        if not imgs:
            for v in re.findall(r"//img\.xsnvshen\.com/[^\s\"'<>]*?/album/\d+/\d+/\d+\.jpg", html):
                u = _to_full(v)
                if u not in imgs:
                    imgs.append(u)

        total = 0
        num = soup.find("span", class_="num")
        if num is not None and num.get_text(strip=True).isdigit():
            total = int(num.get_text(strip=True))
        if not total:
            tm = re.search(r"(\d+)\s*张", soup.get_text(" ", strip=True))
            if tm:
                total = int(tm.group(1))
        # 页面图不全 → 按 DIR/ID/NNN.jpg 序号补齐（三位补零，从 000 起）
        if imgs and total and len(imgs) < total:
            bm = re.match(r"(.+/album/\d+/\d+)/\d+\.jpg", imgs[0])
            if bm:
                imgs = ["%s/%03d.jpg" % (bm.group(1), i) for i in range(total)]

        desc = ""
        md = soup.find("meta", attrs={"name": "description"})
        if md:
            desc = (md.get("content") or "")[:300]

        tags = []
        for a in soup.find_all("a", href=re.compile(r"/(album|girl)/t\d+/")):
            t = a.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)
        return title, imgs, desc, tags[:6]

    def _model_albums(self, gid):
        """女神页 → (模特名, 封面, [(album_id, 标题)])"""
        html = self._get("%s/girl/%s" % (self.host, gid), referer=self.host + "/")
        if not html:
            return "", "", []
        soup = BeautifulSoup(html, "html.parser")
        name = soup.title.get_text(strip=True) if soup.title else str(gid)
        name = re.sub(r"[_\-]\s*秀色女神\s*$", "", name).strip()
        name = re.split(r"人?个?资料|写真集", name)[0].strip() or name

        cover = ""
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            cover = self._pic_cover(og["content"])

        albums, seen = [], set()
        for a in soup.find_all("a", href=re.compile(r"/album/\d+")):
            m = re.search(r"/album/(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            t = (a.get("title") or "").strip()
            if not t:
                continue
            seen.add(m.group(1))
            albums.append((m.group(1), t))
            if not cover:
                img = a.find("img")
                if img is not None:
                    cover = self._pic_cover(img.get("src", ""))
        return name, cover, albums[:20]

    # ── 选集 ────────────────────────────────────────────────────
    def _album_eps(self, token, n):
        if n <= self.CHUNK:
            return "查看图集(%d张)$%s|1" % (n, token)
        eps = []
        for i in range(0, n, self.CHUNK):
            g = i // self.CHUNK + 1
            eps.append("第%d组(%d-%d)$%s|%d" % (g, i + 1, min(i + self.CHUNK, n), token, g))
        return "#".join(eps)

    # ── 详情 ────────────────────────────────────────────────────
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        vid = str(vid).strip().strip("[]'\"")

        # 女神二级目录：每套图集一条线路
        if vid.startswith("g_"):
            gm = re.search(r"g_(\d+)", vid)
            gid = gm.group(1) if gm else vid[2:]
            name, cover, albums = self._model_albums(gid)
            if not albums:
                return {"list": []}
            froms, urls = [], []
            for aid, t in albums:
                froms.append(re.sub(r"[$#]", " ", t)[:26])
                urls.append("查看图集$%s|1" % aid)
            return {"list": [{
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": cover,
                "vod_remarks": "%d 套图集" % len(albums),
                "type_name": "女神",
                "vod_actor": name,
                "vod_content": "共 %d 套，切换线路看不同图集" % len(albums),
                "vod_play_from": "$$$".join(froms),
                "vod_play_url": "$$$".join(urls),
            }]}

        m = re.search(r"(\d+)", vid)
        aid = m.group(1) if m else vid
        title, imgs, desc, tags = self._album_images(aid)
        if not imgs:
            return {"list": []}
        self._cache[aid] = imgs

        return {"list": [{
            "vod_id": aid,
            "vod_name": title or ("图集 " + aid),
            "vod_pic": self._pic_cover(imgs[0]),
            "vod_remarks": "%d 张" % len(imgs),
            "type_name": "秀色女神",
            "vod_actor": " / ".join(tags),
            "vod_content": desc or title,
            "vod_play_from": "图集",
            "vod_content_type": "image",
            "vod_play_url": self._album_eps(aid, len(imgs)),
        }]}

    # ── 播放（pics:// 相册）─────────────────────────────────────
    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        aid, _, grp = raw.partition("|")
        aid = re.sub(r"\D", "", aid) or aid
        try:
            grp = int(grp or 1)
        except Exception:
            grp = 1

        imgs = self._cache.get(aid)
        if not imgs:
            _, imgs, _, _ = self._album_images(aid)
            if imgs:
                self._cache[aid] = imgs
        # 直连时 Referer 必须是该图集详情页，否则 403
        hdr = json.dumps({"User-Agent": self.headers["User-Agent"],
                          "Referer": "%s/album/%s" % (self.host, aid)})
        if not imgs:
            return {"parse": 0, "playUrl": "", "url": "", "header": hdr}

        if len(imgs) > self.CHUNK:
            imgs = imgs[(grp - 1) * self.CHUNK: grp * self.CHUNK]
        urls = [self._pic_full(u, aid) for u in imgs]
        return {
            "parse": 0,
            "playUrl": "",
            "url": "pics://" + "&&".join(urls),
            "header": hdr,
            "contentType": "image",
            "format": "",
        }

    # ── 搜索 ────────────────────────────────────────────────────
    def searchContent(self, key, quick=False, pg="1"):
        result = {"list": [], "page": str(pg)}
        try:
            if str(pg) not in ("1", 1):
                return result          # /search 不支持翻页
            from urllib.parse import quote
            html = self._get("%s/search?w=%s" % (self.host, quote(str(key))),
                             referer=self.host + "/")
            if not html:
                return result
            soup = BeautifulSoup(html, "html.parser")
            items = self._parse_list(soup)
            for it in items:
                if not it["vod_remarks"].endswith("张"):
                    it["vod_remarks"] = "🔍"
            result["list"] = items
        except Exception as e:
            print("[xsnvshen] search error: %s" % e)
        return result

    def searchContentPage(self, key, quick=False, pg="1"):
        return self.searchContent(key, quick, pg)

    # ── 本地代理：补 Referer 取原图 ─────────────────────────────
    def localProxy(self, param):
        try:
            from urllib.parse import unquote
            p = param or {}
            url = unquote(p.get("url", ""))
            ref = unquote(p.get("ref", "")) or (self.host + "/")
            if not url.startswith("http"):
                return [404, "text/plain", b"bad url"]
            data, ctype = self._bytes(url, referer=ref)
            if not data:
                # 原图取不到时退回缩略图，别让播放器空白
                data, ctype = self._bytes(_to_thumb(url, "thumb_600x900"), referer=ref)
            if not data:
                return [502, "text/plain", b"upstream error"]
            return [200, ctype, data]
        except Exception as e:
            return [500, "text/plain", str(e).encode("utf-8", "ignore")]
