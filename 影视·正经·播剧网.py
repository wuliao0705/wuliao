# -*- coding: utf-8 -*-
# ---------------------------------------------------------------
# 播剧网 (ysxq.cc)  TVBox / 影视仓 / CatVod  Python 爬虫源
# CMS      : MacCMS10 (开放 provide/vod 接口)
# 接口     : https://ysxq.cc/api.php/provide/vod/
# 播放     : 多线 m3u8 直链, parse=0 直连
# ---------------------------------------------------------------
import json
import re
import sys
import urllib.parse

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:  # 本地调试用的空壳
    class BaseSpider(object):
        def init(self, extend=""):
            pass

        def destroy(self):
            pass

        def getName(self):
            return ""

        def homeContent(self, filter=False):
            return {"class": []}

        def homeVideoContent(self):
            return {"list": []}

        def categoryContent(self, tid, pg="1", filter=False, extend=None):
            return {"list": []}

        def detailContent(self, ids):
            return {"list": []}

        def searchContent(self, key, quick=False, pg="1"):
            return {"list": []}

        def playerContent(self, flag, id, vipFlags=None):
            return {"parse": 0, "url": "", "header": {}}

        def localProxy(self, params):
            return []

        def isVideoFormat(self, url):
            return bool(re.search(r"\.(m3u8|mp4|flv|avi|mkv|ts)", url or ""))

        def manualVideoCheck(self):
            return False


class Spider(BaseSpider):
    # ------------------------------------------------------------------
    # 常量（分类合并为6个大类）
    # ------------------------------------------------------------------
    HOST = "https://ysxq.cc"
    API = HOST + "/api.php/provide/vod/"

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 大类定义：(type_id, 显示名称)  注：type_id 为该大类下的一个代表ID
    # 实际请求时，如果筛选器中指定了子分类ID，则使用子分类ID
    MAIN_CATEGORIES = [
        ("13", "电视剧"),   # 默认国产剧
        ("60", "短剧"),     # 默认短剧
        ("33", "动漫"),     # 默认大陆动漫
        ("11", "电影"),     # 默认剧情片
        ("30", "综艺"),     # 默认国内综艺
        ("56", "体育"),     # 默认足球
    ]

    # 子分类映射（用于筛选器）
    SUB_CATEGORIES = {
        "电视剧": [
            ("13", "国产剧"), ("14", "港台剧"), ("15", "日韩剧"), ("16", "欧美剧"),
            ("29", "泰国剧"), ("59", "海外剧"), ("89", "Netflix剧"), ("50", "其他剧"),
        ],
        "短剧": [
            ("60", "短剧"), ("71", "现代都市"), ("75", "脑洞悬疑"), ("73", "女恋总裁"),
            ("72", "反转爽文"), ("76", "古装仙侠"), ("70", "穿越年代"), ("69", "重生民国"),
            ("74", "闪婚离婚"),
        ],
        "动漫": [
            ("33", "大陆动漫"), ("34", "日韩动漫"), ("35", "欧美动漫"),
            ("54", "港台动漫"), ("49", "其他动漫"), ("4", "动漫"), ("37", "B站"),
            ("92", "漫剧"), ("90", "有声动漫"),
        ],
        "电影": [
            ("11", "剧情片"), ("6", "动作片"), ("7", "喜剧片"), ("8", "爱情片"),
            ("9", "科幻片"), ("10", "恐怖片"), ("12", "战争片"), ("20", "惊悚片"),
            ("23", "悬疑片"), ("25", "犯罪片"), ("21", "奇幻片"), ("44", "冒险片"),
            ("26", "动画片"), ("24", "纪录片"), ("86", "4K电影"), ("87", "邵氏电影"),
            ("88", "网飞电影"), ("66", "电影解说"), ("28", "其他片"), ("27", "伦理片"),
        ],
        "综艺": [
            ("30", "国内综艺"), ("39", "港台综艺"), ("31", "日韩综艺"),
            ("32", "欧美综艺"), ("3", "综艺"),
        ],
        "体育": [
            ("56", "足球"), ("57", "篮球"), ("58", "网球"), ("63", "斯诺克"),
        ],
    }

    # 播放线路优先级（实测可直连的排前面）
    FLAG_ORDER = ["xiguam3u8", "bfzym3u8", "wsym3u8", "rym3u8",
                  "dyttm3u8", "ffm3u8", "1080zyk"]

    YEARS = ["2027", "2026", "2025", "2024", "2023", "2022", "2021", "2020",
             "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012",
             "2011", "2010", "2009", "2008", "2007", "2006", "2005"]

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def getName(self):
        return "播剧网"

    def init(self, extend=""):
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": self.HOST + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        return self

    def destroy(self):
        try:
            if getattr(self, "session", None):
                self.session.close()
        except Exception:
            pass
        self.session = None

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", url or ""))

    def manualVideoCheck(self):
        return False

    # ------------------------------------------------------------------
    # 底层请求：requests 优先，curl_cffi 兜底
    # ------------------------------------------------------------------
    def _get(self, params, retry=2):
        url = self.API + "?" + urllib.parse.urlencode(params)
        for i in range(retry + 1):
            try:
                r = self.session.get(url, timeout=15)
                if r.status_code == 200 and r.text.strip().startswith("{"):
                    return r.json()
            except Exception as e:
                self._log("requests fail %s: %s" % (i, e))
            # 兜底：TLS 指纹伪装
            try:
                from curl_cffi import requests as cr
                r = cr.get(url, headers=self.headers,
                           impersonate="chrome120", timeout=15)
                if r.status_code == 200:
                    return json.loads(r.text)
            except Exception as e:
                self._log("curl_cffi fail %s: %s" % (i, e))
        return {}

    def _log(self, msg):
        try:
            print("[播剧网] %s" % msg)
            sys.stdout.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _clean(text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _norm_id(ids):
        """把 TVBox 各种形态的 ids 统一成纯数字 vod_id"""
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        v = str(ids).strip()
        v = v.split("#")[0]
        m = re.search(r"(\d+)", v)
        return m.group(1) if m else v

    def _pic(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.HOST + url
        return url

    def _vod_item(self, v):
        remarks = self._clean(v.get("vod_remarks"))
        year = self._clean(v.get("vod_year"))
        if not remarks and year:
            remarks = year
        return {
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": self._clean(v.get("vod_name")),
            "vod_pic": self._pic(v.get("vod_pic")),
            "vod_remarks": remarks,
        }

    def _list_result(self, data, pg):
        vods, seen = [], set()
        for v in (data.get("list") or []):
            vid = str(v.get("vod_id", ""))
            if vid in seen:
                continue
            seen.add(vid)
            vods.append(self._vod_item(v))
        try:
            page = int(data.get("page") or pg)
        except Exception:
            page = int(pg)
        try:
            count = int(data.get("pagecount") or 1)
        except Exception:
            count = 1
        try:
            limit = int(data.get("limit") or 20)
        except Exception:
            limit = 20
        return {
            "list": vods,
            "page": page,
            "pagecount": count,
            "limit": limit,
            "total": int(data.get("total") or len(vods)),
        }

    # ------------------------------------------------------------------
    # 首页（分类合并）
    # ------------------------------------------------------------------
    def homeContent(self, filter=False):
        # 只显示6个大类
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.MAIN_CATEGORIES]

        # 构建筛选器：每个大类下都有子分类选择 + 年份筛选
        filters = {}
        for default_tid, main_name in self.MAIN_CATEGORIES:
            sub_list = self.SUB_CATEGORIES.get(main_name, [])
            # 子分类筛选器
            class_filter = {
                "key": "class",
                "name": "子分类",
                "value": [{"n": name, "v": tid} for tid, name in sub_list]
            }
            # 年份筛选器（复用）
            year_values = [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in self.YEARS]
            year_filter = {"key": "year", "name": "年份", "value": year_values}
            filters[default_tid] = [class_filter, year_filter]

        result = {"class": classes, "filters": filters}
        # 首页推荐直接带上最新入库
        try:
            result["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        data = self._get({"ac": "detail", "pg": 1})
        return {"list": [self._vod_item(v) for v in (data.get("list") or [])]}

    # ------------------------------------------------------------------
    # 分类（支持子分类筛选）
    # ------------------------------------------------------------------
    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        extend = extend or {}
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1

        # 如果有子分类筛选，使用子分类ID，否则使用大类默认ID
        sub_tid = (extend.get("class") or "").strip() if isinstance(extend, dict) else ""
        if sub_tid:
            cat_id = sub_tid
        else:
            cat_id = tid

        params = {"ac": "detail", "t": cat_id, "pg": page}
        year = (extend.get("year") or "").strip() if isinstance(extend, dict) else ""
        if year:
            params["year"] = year

        data = self._get(params)
        return self._list_result(data, page)

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def detailContent(self, ids):
        vid = self._norm_id(ids)
        if not vid:
            return {"list": []}
        data = self._get({"ac": "detail", "ids": vid})
        lst = data.get("list") or []
        if not lst:
            return {"list": []}
        v = lst[0]

        froms, urls = self._playlists(v)
        vod = {
            "vod_id": str(v.get("vod_id", vid)),
            "vod_name": self._clean(v.get("vod_name")),
            "vod_pic": self._pic(v.get("vod_pic")),
            "type_name": self._clean(v.get("vod_class")) or self._clean(v.get("type_name")),
            "vod_year": self._clean(v.get("vod_year")),
            "vod_area": self._clean(v.get("vod_area")),
            "vod_lang": self._clean(v.get("vod_lang")),
            "vod_remarks": self._clean(v.get("vod_remarks")),
            "vod_actor": self._clean(v.get("vod_actor")),
            "vod_director": self._clean(v.get("vod_director")),
            "vod_content": self._clean(v.get("vod_content")) or self._clean(v.get("vod_blurb")),
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod]}

    def _playlists(self, v):
        """整理 vod_play_from / vod_play_url，按线路优先级重排并剔除空线路"""
        raw_from = (v.get("vod_play_from") or "").split("$$$")
        raw_url = (v.get("vod_play_url") or "").split("$$$")
        groups = []
        for i, name in enumerate(raw_from):
            name = (name or "").strip()
            if i >= len(raw_url):
                break
            eps = []
            for seg in (raw_url[i] or "").split("#"):
                seg = seg.strip()
                if not seg:
                    continue
                if "$" in seg:
                    title, link = seg.split("$", 1)
                else:
                    title, link = "播放", seg
                link = link.strip()
                if not link.startswith("http"):
                    continue
                eps.append("%s$%s" % (self._clean(title) or "播放", link))
            if eps:
                groups.append((name or ("线路%d" % (i + 1)), eps))

        def rank(item):
            try:
                return self.FLAG_ORDER.index(item[0])
            except ValueError:
                return len(self.FLAG_ORDER)

        groups.sort(key=rank)
        used, froms, urls = {}, [], []
        for name, eps in groups:
            if name in used:
                used[name] += 1
                name = "%s%d" % (name, used[name])
            else:
                used[name] = 1
            froms.append(name)
            urls.append("#".join(eps))
        return froms, urls

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        data = self._get({"ac": "detail", "wd": key, "pg": page})
        return self._list_result(data, page)

    # ------------------------------------------------------------------
    # 播放
    # ------------------------------------------------------------------
    def playerContent(self, flag, id, vipFlags=None):
        url = id
        if isinstance(url, (list, tuple)):
            url = url[0] if url else ""
        url = str(url).strip()
        return {
            "parse": 0 if self.isVideoFormat(url) else 1,
            "playUrl": "",
            "url": url,
            "header": json.dumps({"User-Agent": self.UA}),
        }

    def localProxy(self, params):
        return [200, "text/plain", ""]