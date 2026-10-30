# -*- coding: utf-8 -*-
# EcoHub TVBox 爬虫（修复版）
# 站点：https://eco.fe-spark.cn
# 修正分类 ID 映射，对齐实际 API 返回的 class 字段

import sys
import re
import json
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
BASE_URL = "https://eco.fe-spark.cn"
API_BASE = "/api/provide/vod"

# ============================================================
# 修复点：分类 ID 映射（来自实际 API 返回的 class 字段）
# ============================================================
CATEGORY_MAP = {
    "1": "电视剧",
    "9": "电影",
    "19": "伦理片",
    "20": "动漫",
    "24": "综艺",
    "29": "体育赛事",
    "34": "短剧",
    "44": "预告片",
}
# 一级分类（用于首页显示）
MAIN_CATEGORIES = ["1", "9", "20", "24", "29", "34", "44", "19"]

# 筛选器配置（针对主要分类）
FILTER_CONFIG = {
    "1": [  # 电视剧
        {"key": "area", "name": "地区", "value": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "日本", "v": "日本"},
            {"n": "韩国", "v": "韩国"},
        ]},
        {"key": "year", "name": "年份", "value": [
            {"n": "全部", "v": ""},
            {"n": "2026", "v": "2026"},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
        ]},
        {"key": "sort", "name": "排序", "value": [
            {"n": "最近更新", "v": "update_stamp"},
            {"n": "人气", "v": "hits"},
            {"n": "评分", "v": "score"},
        ]},
    ],
    "9": [  # 电影
        {"key": "area", "name": "地区", "value": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "美国", "v": "美国"},
            {"n": "日本", "v": "日本"},
            {"n": "韩国", "v": "韩国"},
        ]},
        {"key": "year", "name": "年份", "value": [
            {"n": "全部", "v": ""},
            {"n": "2026", "v": "2026"},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
        ]},
        {"key": "sort", "name": "排序", "value": [
            {"n": "最近更新", "v": "update_stamp"},
            {"n": "人气", "v": "hits"},
            {"n": "评分", "v": "score"},
        ]},
    ],
}


class Spider(BaseSpider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = BASE_URL
        self.session = None
        self._init_urllib_fallback()

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

    def _request(self, url, params=None, headers=None):
        try:
            if self.session:
                h = self.session.headers.copy()
                if headers:
                    h.update(headers)
                h.setdefault("User-Agent", UA)
                h.setdefault("Accept", "application/json")
                h.setdefault("Referer", self.host + "/")

                r = self.session.get(url, params=params, headers=h, timeout=20)
                if r.status_code == 200:
                    return r.json()
                print(f"[EcoHub] HTTP {r.status_code}: {r.text[:200]}")
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
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[EcoHub] request error: {e}")
        return None

    def getDependence(self):
        return []

    def getName(self):
        return "EcoHub"

    def init(self, extend=""):
        self.setExtendInfo(extend)
        if requests:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": UA,
                "Accept": "application/json",
                "Referer": self.host + "/",
            })

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

    # ==================== 首页分类 ====================
    def homeContent(self, filter=False):
        classes = []
        for cid in MAIN_CATEGORIES:
            classes.append({
                "type_id": cid,
                "type_name": CATEGORY_MAP.get(cid, f"分类{cid}")
            })

        # 筛选器：只对已配置的分类添加
        filters = {}
        for cid in FILTER_CONFIG:
            if cid in MAIN_CATEGORIES:
                filters[cid] = FILTER_CONFIG[cid]

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 默认显示电视剧（tid=1）
        return self.categoryContent("1", "1")

    # ==================== 分类列表 ====================
    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = self._safe_int(pg, 1)
        page_size = 20

        params = {
            "ac": "videolist",
            "t": tid,
            "pg": page,
        }

        if isinstance(extend, dict):
            for k in ["area", "year", "sort"]:
                if k in extend:
                    params[k] = extend[k]

        url = f"{self.host}{API_BASE}"
        data = self._request(url, params=params)

        if not data or data.get("code") != 1:
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        items = []
        for item in data.get("list", []):
            vid = str(item.get("vod_id", ""))
            name = item.get("vod_name", "")
            pic = item.get("vod_pic", "")
            remarks = item.get("vod_remarks", "")
            area = item.get("vod_area", "")
            year = item.get("vod_year", "")

            if not vid or not name:
                continue

            remark_parts = [p for p in (area, year, remarks) if p]
            remark_text = " | ".join(remark_parts)

            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark_text,
            })

        total = data.get("total", 0) or len(items) + (page - 1) * page_size
        pagecount = data.get("pagecount", 0) or (total + page_size - 1) // page_size if total > 0 else page

        return {
            "list": items,
            "page": page,
            "pagecount": pagecount if pagecount >= page else page,
            "limit": page_size,
            "total": total,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]

        params = {"ac": "detail", "ids": vid}
        url = f"{self.host}{API_BASE}"
        data = self._request(url, params=params)

        if not data or data.get("code") != 1:
            return {"list": []}

        item = data.get("list", [{}])[0] if data.get("list") else {}
        if not item:
            return {"list": []}

        content = re.sub(r'<[^>]+>', '', item.get("vod_content", ""))

        vod = {
            "vod_id": vid,
            "vod_name": item.get("vod_name", ""),
            "vod_pic": item.get("vod_pic", ""),
            "vod_actor": item.get("vod_actor", ""),
            "vod_director": item.get("vod_director", ""),
            "vod_area": item.get("vod_area", ""),
            "vod_year": item.get("vod_year", ""),
            "vod_remarks": item.get("vod_remarks", ""),
            "vod_content": content,
            "vod_play_from": item.get("vod_play_from", "EcoHub"),
            "vod_play_url": item.get("vod_play_url", ""),
        }
        return {"list": [vod]}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags=None):
        if id.startswith("http") and self.isVideoFormat(id):
            return {
                "parse": 0,
                "url": id,
                "header": {"User-Agent": UA, "Referer": self.host + "/"},
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

        params = {"ac": "videolist", "wd": key, "pg": page}
        url = f"{self.host}{API_BASE}"
        data = self._request(url, params=params)

        if not data or data.get("code") != 1:
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        items = []
        for item in data.get("list", []):
            vid = str(item.get("vod_id", ""))
            name = item.get("vod_name", "")
            pic = item.get("vod_pic", "")
            remarks = item.get("vod_remarks", "")
            if not vid or not name:
                continue
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })

        total = data.get("total", 0) or len(items) + (page - 1) * page_size
        pagecount = data.get("pagecount", 0) or (total + page_size - 1) // page_size if total > 0 else page
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount if pagecount >= page else page,
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

    print("\n--- 测试加载列表（电视剧 tid=1） ---")
    result = spider.categoryContent("1", "1")
    print(f"列表数: {len(result.get('list', []))}, 总页数: {result.get('pagecount', 1)}")
    for item in result.get('list', [])[:3]:
        print(f"  {item['vod_name']} ({item['vod_id']})")
