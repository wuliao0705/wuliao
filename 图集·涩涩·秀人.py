# -*- coding: utf-8 -*-
"""
秀人网 (xiurenai.com) - 图集·涩涩 Spider
站点: 帝国CMS(modown 皮肤)，无 CF 挑战
列表: /{jigou|other|overseas}/{slug}/     分页 /{...}/index_N.html
      /girls/  /aigirl/                    分页 /aigirl/index_N.html
      卡片 div.post.grid → h2/h3 标题 + a[href$=".html"] + img
详情: /{分类路径}/{ID}.html  (ID 唯一，可用任意分类前缀访问)
图片: https://xr.afxfl.com/uploads/YYYY/MM/DD/HASH-NN.jpg
      列表封面走 /x/YYYY/MM/DD/NNNNN.jpg
搜索: POST /e/search/index.php  (帝国CMS 表单)
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

BASE = "https://www.xiurenai.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE + "/",
}

# 一级分类（带图标）
CATS = [
    ("jigou/xiuren", "🌟 秀人网"),
    ("jigou/xrng", "💎 秀人内购"),
    ("jigou/xingyan", "✨ 星颜社"),
    ("jigou/youmi", "🍯 尤蜜荟"),
    ("jigou/imiss", "💕 爱蜜社"),
    ("jigou/xiaoyu", "🎨 语画界"),
    ("other/rosi", "👠 ROSI写真"),
    ("other/ugirls", "🎀 爱尤物"),
    ("other/beautyleg", "🦵 Beautyleg"),
    ("overseas/djawa", "🇰🇷 DJAWA"),
    ("overseas/artgravia", "📸 ARTGRAVIA"),
    ("girls", "🌐 网络美女"),
    ("aigirl", "🤖 AiGirl"),
]

# 二级筛选：机构
JIGOU_SUB = [
    ("jigou/xingyan", "星颜社"), ("jigou/youmi", "尤蜜荟"), ("jigou/huayang", "花漾"),
    ("jigou/imiss", "爱蜜社"), ("jigou/kelagirls", "克拉女神"), ("jigou/mygirl", "美媛馆"),
    ("jigou/mistar", "魅妍社"), ("jigou/mitao", "蜜桃社"), ("jigou/mfstar", "模范学院"),
    ("jigou/xiaoyu", "语画界"), ("jigou/feilin", "嗲囡囡"), ("jigou/xiuren", "秀人网"),
    ("jigou/xrng", "秀人内购"),
]
OTHER_SUB = [
    ("other/rosi", "ROSI写真"), ("other/iess", "异思趣向"), ("other/mzsock", "爱美足"),
    ("other/wlcm", "物恋传媒"), ("other/bobosocks", "袜啵啵"), ("other/ligui", "丽柜"),
    ("other/ishow", "爱秀"), ("other/beautyleg", "Beautyleg"), ("other/toutiao", "头条女神"),
    ("other/twmm", "台湾正妹"), ("other/ugirls", "爱尤物"), ("other/llct", "森萝财团"),
    ("other/fzly", "风之领域"), ("other/qmsy", "绮梦摄影"), ("other/cxnv", "初夏女神"),
    ("other/yituyu", "艺图语"), ("other/tysy", "甜予摄影"), ("other/zyx", "足愉心"),
]
OVERSEAS_SUB = [
    ("overseas/digi", "Digi-Gra"), ("overseas/djawa", "DJAWA"), ("overseas/cosdoki", "Cosdoki"),
    ("overseas/artgravia", "ARTGRAVIA"), ("overseas/onlytease", "OnlyTease"),
    ("overseas/bejean-on-line", "Bejean"), ("overseas/misty", "@misty"),
    ("overseas/bomb", "Bomb.TV"), ("overseas/x-city", "X-City"),
    ("overseas/the-black-alley", "Black Alley"), ("overseas/lovepop", "LOVEPOP"),
    ("overseas/minisuka-tv", "Minisuka.tv"), ("overseas/puremedia", "PURE MEDIA"),
    ("overseas/leehee", "LEEHEE"), ("overseas/graphis", "Graphis"),
]


def _get(url, referer=None, timeout=25):
    """站点响应头无 charset，requests 会猜成 ISO-8859-1 导致中文乱码 → 强制 utf-8"""
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    last = None
    if cffi_req is not None:
        for imp in ("chrome120", "chrome124"):
            try:
                r = cffi_req.get(url, headers=h, impersonate=imp, timeout=timeout)
                last = r
                if r.status_code == 200:
                    r.encoding = "utf-8"
                    return r
            except Exception:
                continue
    try:
        r = requests.get(url, headers=h, timeout=timeout)
        r.encoding = "utf-8"
        return r
    except Exception:
        if last is not None:
            try:
                last.encoding = "utf-8"
            except Exception:
                pass
        return last


def _norm(u):
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE + u
    return u


class Spider(BaseSpider):
    def getName(self):
        return "秀人网"

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

    # 关键：声明非视频，宿主才会走图片相册而不是流嗅探
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
            f = {}
            for t, _ in CATS:
                if t.startswith("jigou/"):
                    vals = JIGOU_SUB
                elif t.startswith("other/"):
                    vals = OTHER_SUB
                elif t.startswith("overseas/"):
                    vals = OVERSEAS_SUB
                else:
                    continue
                f[t] = [{
                    "key": "sub",
                    "name": "🏢 机构",
                    "value": [{"n": "本栏目", "v": ""}] + [{"n": n, "v": v} for v, n in vals],
                }]
            result["filters"] = f
        return result

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None):
        return self.categoryContent("jigou/xiuren", "1")

    def _parse_grid(self, soup, tid="", remark=""):
        out, seen = [], set()
        grids = soup.find_all("div", class_="post grid") or soup.find_all("div", class_="grid")
        for d in grids:
            a = d.find("a", href=re.compile(r"/\d{5,}\.html"))
            if not a:
                continue
            m = re.search(r"/(\d{5,})\.html", a["href"])
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            h = d.find(["h2", "h3", "h4"])
            title = (h.get_text(strip=True) if h else "") or a.get("title", "") or a.get_text(strip=True)
            if not title:
                img_alt = d.find("img", alt=True)
                title = img_alt["alt"] if img_alt else vid
            pic = ""
            img = d.find("img")
            if img is not None:
                pic = _norm(img.get("data-src") or img.get("data-original") or img.get("src", ""))
            # 路径前缀保留，详情页可直接用
            path = a["href"].lstrip("/")
            out.append({
                "vod_id": path,
                "vod_name": title[:90],
                "vod_pic": pic,
                "vod_remarks": remark or "🖼️ 图集",
                "type_name": tid.split("/")[-1] if tid else "秀人",
            })
        return out

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        result = {"list": [], "page": str(pg), "pagecount": 9999, "limit": 30, "total": 999999}
        pg_int = int(pg) if str(pg).isdigit() else 1
        if extend and isinstance(extend, dict) and extend.get("sub"):
            tid = extend["sub"]
        try:
            seg = tid.strip("/")
            # 分页走 index_N.html
            url = f"{BASE}/{seg}/" if pg_int <= 1 else f"{BASE}/{seg}/index_{pg_int}.html"
            r = _get(url, referer=BASE + "/")
            if r is None or r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")
            result["list"] = self._parse_grid(soup, tid)
        except Exception as e:
            print(f"[xiuren] categoryContent error: {e}")
        return result

    def detailContent(self, ids, filter=False):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid).strip().strip("[]'\"")
        try:
            if vid.startswith("http"):
                url = vid
            elif vid.endswith(".html"):
                url = f"{BASE}/{vid.lstrip('/')}"
            else:
                # 只给了纯 ID → 用 aigirl 前缀兜底（ID 唯一，站点会正确渲染）
                num = re.search(r"\d{5,}", vid)
                url = f"{BASE}/aigirl/{num.group()}.html" if num else f"{BASE}/{vid}.html"
            r = _get(url, referer=BASE + "/")
            if r is None or r.status_code != 200:
                return {"list": []}
            soup = BeautifulSoup(r.text, "html.parser")

            vod_name = ""
            h1 = soup.find("h1")
            if h1:
                vod_name = h1.get_text(strip=True)
            if not vod_name and soup.title:
                vod_name = soup.title.get_text(strip=True)
            vod_name = re.sub(r"[-_]\s*秀人(网|爱)\s*$", "", vod_name).strip()

            # 正文图：uploads 路径
            images = []
            for img in soup.find_all("img"):
                for attr in ("data-src", "data-original", "src"):
                    v = img.get(attr, "")
                    if v and "afxfl.com/uploads/" in v and re.search(r"\.(jpg|jpeg|png|webp)$", v, re.I):
                        v = _norm(v)
                        if v not in images:
                            images.append(v)
                        break
            if not images:
                for v in re.findall(r"https://xr\.afxfl\.com/uploads/[^\s\"'<>]+?\.(?:jpg|jpeg|png|webp)", r.text):
                    if v not in images:
                        images.append(v)

            # 按末尾序号排序：xxx-5b168-010.jpg → 10
            def _k(u):
                m = re.search(r"-(\d+)\.\w+$", u)
                return int(m.group(1)) if m else 0
            images.sort(key=_k)

            desc = ""
            md = soup.find("meta", attrs={"name": "description"})
            if md:
                desc = md.get("content", "")[:300]

            # 标签
            tags = [a.get_text(strip=True) for a in soup.find_all("a", href=re.compile(r"/tags?[-/]"))]
            tags = list(dict.fromkeys([t for t in tags if t and len(t) < 20]))[:6]

            play_url = self._album_eps(vid, len(images))
            self._cache[vid] = images
            return {"list": [{
                "vod_id": vid,
                "vod_name": vod_name or vid,
                "vod_pic": images[0] if images else "",
                "vod_remarks": f"{len(images)}张",
                "type_name": "秀人网",
                "vod_actor": " / ".join(tags),
                "vod_content": desc,
                "vod_play_from": "图集",
            "vod_content_type": "image",
                "vod_play_url": play_url,
            }]}
        except Exception as e:
            print(f"[xiuren] detailContent error: {e}")
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        result = {"list": [], "page": str(pg)}
        if str(pg) not in ("1", 1):
            return result
        try:
            data = {
                "keyboard": str(key),
                "tbname": "news",
                "tempid": "1",
                "show": "title,smalltext",
                "andor": "or",
            }
            h = dict(HEADERS)
            h["Content-Type"] = "application/x-www-form-urlencoded"
            r = None
            if cffi_req is not None:
                try:
                    r = cffi_req.post(f"{BASE}/e/search/index.php", headers=h, data=data,
                                      impersonate="chrome120", timeout=25)
                except Exception:
                    r = None
            if r is None or r.status_code != 200:
                r = requests.post(f"{BASE}/e/search/index.php", headers=h, data=data, timeout=25)
            soup = BeautifulSoup(r.text, "html.parser")
            items = self._parse_grid(soup, remark="🔍")
            if not items:
                # 帝国CMS 有时重定向到 result 页，直接扫链接
                seen = set()
                for a in soup.find_all("a", href=re.compile(r"/\d{5,}\.html")):
                    m = re.search(r"/(\d{5,})\.html", a["href"])
                    if not m or m.group(1) in seen:
                        continue
                    seen.add(m.group(1))
                    t = a.get_text(strip=True) or a.get("title", "")
                    if not t:
                        continue
                    items.append({
                        "vod_id": a["href"].lstrip("/"),
                        "vod_name": t[:90],
                        "vod_pic": "",
                        "vod_remarks": "🔍",
                        "type_name": "秀人",
                    })
            result["list"] = items
        except Exception as e:
            print(f"[xiuren] searchContent error: {e}")
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
