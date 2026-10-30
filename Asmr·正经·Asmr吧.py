# -*- coding: utf-8 -*-
# ASMR吧 (ufov8.com) TVBox 爬虫（修复播放直链过期问题）
# 融合遮天法·前字秘（预知） + 者字秘（兜底）
# 适配站点：https://www.ufov8.com

import sys
import re
import json
import html
import time
from urllib.parse import quote, urljoin

try:
    import requests
except ImportError:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return "Base"
        def homeContent(self, filter): return {'class': [], 'filters': {}}
        def homeVideoContent(self): return {'list': []}
        def categoryContent(self, tid, pg, filter, extend):
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0}
        def detailContent(self, ids): return {'list': []}
        def playerContent(self, flag, id, vipFlags=None):
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': {}}
        def searchContent(self, key, quick, pg='1'):
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0}
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def localProxy(self, param): return [404, 'text/plain', b'']
        def destroy(self): pass


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE_URL = "https://www.ufov8.com"
WP_API = "/wp-json/wp/v2"

CATEGORY_MAP = {
    "2": {"name": "🎬 全部视频", "slug": "asmrsp"},
    "18": {"name": "🇨🇳 国内ASMR", "slug": "gnasmr"},
    "12": {"name": "🌍 国外ASMR", "slug": "omasmr"},
    "11": {"name": "🇰🇷 韩国ASMR", "slug": "rhsp"},
    "14": {"name": "💕 女性向", "slug": "nxxasmr"},
    "56": {"name": "🌊 白噪音", "slug": "bzy"},
    "37": {"name": "✂️ 精剪合集", "slug": "jinjianspheji"},
}

DEFAULT_CATEGORY = "2"


class Spider(BaseSpider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = BASE_URL
        self.session = None
        self._init_urllib_fallback()
        self._categories = []
        self._bili_cid_cache = {}
        self._bili_status_cache = {}      # 新增：缓存稿件状态

    def _init_urllib_fallback(self):
        if requests is None:
            import urllib.request
            import ssl
            self._urllib = urllib.request
            self._ssl_ctx = ssl.create_default_context()
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE
        else:
            self._urllib = None

    def _fetch_json(self, url, params=None, headers=None):
        try:
            if self.session:
                h = self.session.headers.copy()
                if headers:
                    h.update(headers)
                h.setdefault("User-Agent", UA)
                h.setdefault("Accept", "application/json")
                h.setdefault("Referer", self.host + "/")
                r = self.session.get(url, params=params, headers=h, timeout=15)
                if r.status_code == 200:
                    return r.json()
                print(f"[ASMR吧] HTTP {r.status_code}: {r.text[:200]}")
            elif self._urllib:
                import urllib.parse as _up
                if params:
                    url = url + "?" + _up.urlencode(params)
                h = {
                    "User-Agent": UA,
                    "Accept": "application/json",
                    "Referer": self.host + "/",
                }
                if headers:
                    h.update(headers)
                req = self._urllib.Request(url, headers=h)
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[ASMR吧] fetch json error: {e}")
        return None

    def _fetch_html(self, url):
        try:
            if self.session:
                h = self.session.headers.copy()
                h.setdefault("User-Agent", UA)
                h.setdefault("Accept", "text/html,application/xhtml+xml")
                h.setdefault("Referer", self.host + "/")
                r = self.session.get(url, headers=h, timeout=15)
                if r.status_code == 200:
                    return r.text
            elif self._urllib:
                req = self._urllib.Request(url, headers={"User-Agent": UA, "Referer": self.host + "/"})
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=15) as resp:
                    return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[ASMR吧] fetch html error: {e}")
        return ""

    def getDependence(self):
        return []

    def getName(self):
        return "ASMR吧"

    def init(self, extend=""):
        self.setExtendInfo(extend)
        if requests:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": UA,
                "Accept": "application/json",
                "Referer": self.host + "/",
            })
        self._load_categories()

    def setExtendInfo(self, extend=""):
        if isinstance(extend, dict):
            cfg = extend
        elif isinstance(extend, str):
            try:
                cfg = json.loads(extend) if extend else {}
            except:
                cfg = {}
        else:
            cfg = {}
        self.host = str(cfg.get("host") or self.host).rstrip("/")

    def destroy(self):
        if self.session:
            try:
                self.session.close()
            except:
                pass

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|webm|flv)(\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    # ==================== 加载分类 ====================
    def _load_categories(self):
        if self._categories:
            return
        url = f"{self.host}{WP_API}/categories"
        data = self._fetch_json(url)
        if data and isinstance(data, list):
            self._categories = data
            return
        for cid, info in CATEGORY_MAP.items():
            self._categories.append({
                "id": int(cid),
                "name": info["name"],
                "slug": info["slug"],
                "count": 0,
            })

    # ==================== 首页分类 ====================
    def homeContent(self, filter=False):
        classes = []
        for cat in self._categories:
            if isinstance(cat, dict):
                cid = str(cat.get("id", ""))
                cname = cat.get("name", "")
                if cid and cname:
                    classes.append({"type_id": cid, "type_name": cname})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent(DEFAULT_CATEGORY, "1")

    # ==================== 分类列表 ====================
    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = self._safe_int(pg, 1)
        page_size = 20

        url = f"{self.host}{WP_API}/posts"
        params = {
            "per_page": page_size,
            "page": page,
            "orderby": "date",
            "order": "desc",
            "_embed": "1",
        }
        if tid and tid != "0" and tid != "all":
            params["categories"] = tid

        data = self._fetch_json(url, params=params)
        if not data or not isinstance(data, list):
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        items = []
        for post in data:
            vid = str(post.get("id", ""))
            if not vid:
                continue
            title = post.get("title", {}).get("rendered", "")
            title = re.sub(r"<[^>]+>", "", html.unescape(title)).strip()
            if not title:
                title = f"视频 {vid}"

            pic = self._extract_featured_image(post)
            if not pic:
                content = post.get("content", {}).get("rendered", "")
                img_match = re.search(r'<img[^>]+src="([^"]+)"', content)
                if img_match:
                    pic = img_match.group(1)

            cats = post.get("categories", [])
            cat_name = ""
            for c in self._categories:
                if isinstance(c, dict) and c.get("id") in cats:
                    cat_name = c.get("name", "")
                    break
            date = post.get("date", "")[:10] if post.get("date") else ""
            remarks = f"{cat_name} | {date}" if cat_name and date else cat_name or date

            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })

        total = len(items)
        pagecount = page + 1 if len(items) >= page_size else page

        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": total,
        }

    def _extract_featured_image(self, post):
        embedded = post.get("_embedded", {})
        featured = embedded.get("wp:featuredmedia", [])
        if featured and isinstance(featured[0], dict):
            src = featured[0].get("source_url")
            if src:
                return src
            sizes = featured[0].get("media_details", {}).get("sizes", {})
            for size in ["large", "medium_large", "medium"]:
                if size in sizes:
                    src = sizes[size].get("source_url")
                    if src:
                        return src
        return ""

    # ==================== 详情（含预检测） ====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        post_id = ids[0]

        url = f"{self.host}{WP_API}/posts/{post_id}"
        params = {"_embed": "1"}
        post = self._fetch_json(url, params=params)
        if not post:
            return {"list": []}

        title = post.get("title", {}).get("rendered", "")
        title = re.sub(r"<[^>]+>", "", html.unescape(title)).strip()

        pic = self._extract_featured_image(post)
        if not pic:
            content_raw = post.get("content", {}).get("rendered", "")
            img_match = re.search(r'<img[^>]+src="([^"]+)"', content_raw)
            if img_match:
                pic = img_match.group(1)

        content_raw = post.get("content", {}).get("rendered", "")
        desc = re.sub(r"<[^>]+>", "", html.unescape(content_raw)).strip()
        desc = desc[:300] + "..." if len(desc) > 300 else desc

        cats = post.get("categories", [])
        cat_name = ""
        for c in self._categories:
            if isinstance(c, dict) and c.get("id") in cats:
                cat_name = c.get("name", "")
                break

        date = post.get("date", "")[:10] if post.get("date") else ""

        # 提取 BVID
        bvid = self._extract_bvid_from_content(content_raw)
        if not bvid:
            detail_html = self._fetch_html(f"{self.host}/{post_id}.html")
            if detail_html:
                bvid = self._extract_bvid_from_html(detail_html)

        # ---------- 新增：预检测 B 站视频状态 ----------
        play_from = "ASMR吧"
        play_url = ""
        remarks = date
        if bvid:
            status = self._check_bilibili_status(bvid)
            if status["valid"]:
                play_url = f"bili://{bvid}"
            else:
                # 失效标记，播放时显示错误
                play_url = f"invalid://{bvid}?reason={quote(status['reason'])}"
                remarks = f"{date} ⚠️ 失效（{status['reason']}）"
                print(f"[ASMR吧] 稿件 {bvid} 失效: {status['reason']}")
        else:
            # 无 BVID，无法播放
            play_url = "invalid://无BVID"
            remarks = f"{date} ⚠️ 无视频源"

        vod = {
            "vod_id": post_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": "",
            "vod_director": "",
            "vod_area": cat_name,
            "vod_year": date[:4] if date else "",
            "vod_remarks": remarks,
            "vod_content": desc,
            "vod_play_from": play_from,
            "vod_play_url": f"播放${play_url}" if play_url else "",
        }
        return {"list": [vod]}

    # ==================== B站状态检测 ====================
    def _check_bilibili_status(self, bvid):
        """检测 B 站稿件有效性，返回 {'valid': bool, 'reason': str, 'cid': int or None}"""
        if bvid in self._bili_status_cache:
            return self._bili_status_cache[bvid]

        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
        data = self._fetch_json(url, headers=headers)
        status = {"valid": False, "reason": "未知", "cid": None}

        if data and data.get("code") == 0:
            cid = data.get("data", {}).get("cid")
            if cid:
                status = {"valid": True, "reason": "有效", "cid": cid}
            else:
                status["reason"] = "无 cid 数据"
        else:
            code = data.get("code") if data else "无响应"
            msg = data.get("message", "") if data else "请求失败"
            if code == -404:
                status["reason"] = "视频已被删除"
            elif code == 62002:
                status["reason"] = "稿件不可见（私密/隐藏）"
            else:
                status["reason"] = f"B站返回 {code}: {msg}"

        self._bili_status_cache[bvid] = status
        return status

    # ==================== 提取 BVID ====================
    def _extract_bvid_from_content(self, content):
        if not content:
            return None
        patterns = [
            r'<iframe[^>]+src="[^"]*bvid=([A-Za-z0-9]+)"',
            r'player\.bilibili\.com/player\.html\?[^"]*bvid=([A-Za-z0-9]+)',
            r'bvid=([A-Za-z0-9]+)',
        ]
        for pat in patterns:
            m = re.search(pat, content, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _extract_bvid_from_html(self, html):
        if not html:
            return None
        patterns = [
            r'<iframe[^>]+src="[^"]*bvid=([A-Za-z0-9]+)"',
            r'player\.bilibili\.com/player\.html\?[^"]*bvid=([A-Za-z0-9]+)',
            r'bvid=([A-Za-z0-9]+)',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    # ==================== B站播放直链获取 ====================
    def _get_bilibili_cid(self, bvid):
        if not bvid:
            return None
        if bvid in self._bili_cid_cache:
            return self._bili_cid_cache[bvid]
        # 优先从缓存中取
        status = self._bili_status_cache.get(bvid)
        if status and status["valid"]:
            cid = status.get("cid")
            if cid:
                self._bili_cid_cache[bvid] = cid
                return cid
        # 否则实时请求
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
            headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
            data = self._fetch_json(url, headers=headers)
            if data and data.get("code") == 0:
                cid = data.get("data", {}).get("cid")
                if cid:
                    self._bili_cid_cache[bvid] = cid
                    return cid
        except Exception as e:
            print(f"[ASMR吧] B站 CID 获取失败: {e}")
        return None

    def _get_bilibili_play_url(self, bvid, cid=None):
        if not bvid:
            return None
        if not cid:
            cid = self._get_bilibili_cid(bvid)
            if not cid:
                return None
        try:
            url = "https://api.bilibili.com/x/player/playurl"
            params = {
                "bvid": bvid,
                "cid": cid,
                "qn": 64,
                "fnval": 0,
                "platform": "html5",
            }
            headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
            data = self._fetch_json(url, params=params, headers=headers)
            if data and data.get("code") == 0:
                play_data = data.get("data", {})
                durl = play_data.get("durl", [])
                if durl and isinstance(durl, list) and len(durl) > 0:
                    return durl[0].get("url")
                dash = play_data.get("dash")
                if dash:
                    videos = dash.get("video", [])
                    if videos:
                        videos_sorted = sorted(videos, key=lambda x: x.get("id", 0), reverse=True)
                        for v in videos_sorted:
                            base_url = v.get("baseUrl") or v.get("base_url")
                            if base_url:
                                return base_url
        except Exception as e:
            print(f"[ASMR吧] B站播放地址获取失败: {e}")
        return None

    # ==================== 播放（含失效处理） ====================
    def playerContent(self, flag, id, vipFlags=None):
        # 处理失效标记
        if id.startswith("invalid://"):
            # 提取原因
            reason = "视频已失效"
            if "?reason=" in id:
                reason = id.split("?reason=", 1)[-1]
                try:
                    reason = quote(reason)  # 安全显示
                except:
                    pass
            error_html = f"<html><body><h2>⚠️ 视频失效</h2><p>原因：{reason}</p><p>可能已被 UP 主删除或设为私密</p></body></html>"
            return {
                "parse": 1,
                "url": f"data:text/html,{quote(error_html)}",
                "header": {},
            }

        if id.startswith("bili://"):
            bvid = id.replace("bili://", "")
            play_url = self._get_bilibili_play_url(bvid)
            if play_url:
                return {
                    "parse": 0,
                    "url": play_url,
                    "header": {
                        "User-Agent": UA,
                        "Referer": "https://www.bilibili.com/",
                        "Origin": "https://www.bilibili.com",
                    },
                }
            else:
                # 获取直链失败，回退到 iframe
                return {
                    "parse": 1,
                    "url": f"https://player.bilibili.com/player.html?bvid={bvid}&page=1",
                    "header": {
                        "User-Agent": UA,
                        "Referer": "https://www.bilibili.com/",
                    },
                }

        if id.startswith("http") and self.isVideoFormat(id):
            return {
                "parse": 0,
                "url": id,
                "header": {
                    "User-Agent": UA,
                    "Referer": "https://www.bilibili.com/",
                    "Origin": "https://www.bilibili.com",
                },
            }

        return {
            "parse": 1,
            "url": id,
            "header": {"User-Agent": UA, "Referer": self.host + "/"},
        }

    # ==================== 搜索 ====================
    def searchContent(self, key, quick=False, pg="1"):
        page = self._safe_int(pg, 1)
        page_size = 20

        url = f"{self.host}{WP_API}/posts"
        params = {
            "search": key,
            "per_page": page_size,
            "page": page,
            "orderby": "relevance",
            "order": "desc",
            "_embed": "1",
        }

        data = self._fetch_json(url, params=params)
        if not data or not isinstance(data, list):
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        items = []
        for post in data:
            vid = str(post.get("id", ""))
            if not vid:
                continue
            title = post.get("title", {}).get("rendered", "")
            title = re.sub(r"<[^>]+>", "", html.unescape(title)).strip()
            if not title:
                title = f"视频 {vid}"

            pic = self._extract_featured_image(post)
            if not pic:
                content = post.get("content", {}).get("rendered", "")
                img_match = re.search(r'<img[^>]+src="([^"]+)"', content)
                if img_match:
                    pic = img_match.group(1)

            date = post.get("date", "")[:10] if post.get("date") else ""
            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": date,
            })

        total = len(items)
        pagecount = page + 1 if len(items) >= page_size else page

        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": total,
        }

    @staticmethod
    def _safe_int(val, default=1):
        try:
            v = int(str(val or "").strip())
            return v if v > 0 else default
        except:
            return default

    def localProxy(self, param):
        return [404, "text/plain", b""]

    def action(self, action_str):
        return None


# ---------- 测试 ----------
if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("爬虫名称:", spider.getName())
    print("\n--- 首页分类 ---")
    home = spider.homeContent()
    for c in home.get("class", []):
        print(f"  {c['type_id']}: {c['type_name']}")
    print("\n--- 测试加载列表 ---")
    result = spider.categoryContent("18", "1")
    print(f"列表数: {len(result.get('list', []))}, 总页数: {result.get('pagecount', 1)}")
    for item in result.get('list', [])[:3]:
        print(f"  {item['vod_name']} ({item['vod_id']})")