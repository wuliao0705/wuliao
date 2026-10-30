# -*- coding: utf-8 -*-
# ---------------------------------------------------------------
# 一二五影视 (125la.com)  TVBox / 影视仓 / CatVod  Python 爬虫源
# CMS      : MacCMS10 + plex 自定义模板（路由被改名混淆）
#   分类   : /wagon4v/{slug}.html          分页 /wagon4v/{slug}-{N}.html
#   详情   : /trayedgea6/{id}.html
#   播放   : /filmcanlite/{id}-{sid}-{nid}.html  → player_aaaa.url (m3u8 直链)
#   搜索   : /isthmusk.html?wd={key}&page={N}
# 播放     : 暴风源 m3u8 直链, parse=0 直连
# ---------------------------------------------------------------
import json
import re
import sys

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
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
            return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)", url or ""))

        def manualVideoCheck(self):
            return False


class Spider(BaseSpider):
    HOST = "https://125la.com"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 混淆后的路由前缀
    P_CAT = "/wagon4v/"
    P_DETAIL = "/trayedgea6/"
    P_PLAY = "/filmcanlite/"
    P_SEARCH = "/isthmusk.html"

    # (slug, 显示名) —— 全部实测有内容
    CATEGORIES = [
        ("short-drama", "短剧大全"), ("ai-short-drama", "AI短剧"),
        ("comeback-drama", "逆袭爽剧"), ("ceo-romance", "霸总甜宠"),
        ("urban-comeback", "都市逆袭"), ("modern-urban", "现代都市"),
        ("xianxia-cultivation", "仙侠修仙"), ("modern-time-travel", "现代穿越"),
        ("republican-rebirth", "民国重生"),
        ("movie", "必看电影"), ("action", "动作大片"), ("comedy", "爆笑喜剧"),
        ("horror", "惊悚恐怖"), ("sci-fi", "科幻AI"), ("romance", "催泪爱情"),
        ("war", "战争史诗"), ("drama", "高分剧情"),
        ("tv", "热播剧集"), ("chinese-drama", "国产好剧"), ("hk-drama", "TVB港剧"),
        ("korean-drama", "口碑韩剧"), ("japanese-drama", "日剧必看"),
        ("taiwan-drama", "台剧偶像"), ("us-uk-drama", "烧脑欧美"),
        ("thai-drama", "泰剧推荐"), ("overseas-drama", "小众海外"),
        ("family-drama", "治愈家庭"),
        ("anime", "新番动漫"), ("chinese-anime", "国漫巅峰"),
        ("japanese-anime", "热血日漫"), ("us-animation", "迪士尼动画"),
        ("overseas-anime", "全球动漫"), ("hk-tw-anime", "怀旧动漫"),
        ("variety", "热门综艺"), ("china-variety", "内地综艺"),
        ("hk-tw-variety", "港台综艺"), ("jp-kr-variety", "搞笑韩综"),
        ("us-uk-variety", "欧美综艺"),
    ]

    # ---------------- 正则 ----------------
    RE_CARD = re.compile(r'<article[^>]*class="[^"]*px-card[^"]*"[^>]*>(.*?)</article>', re.S)
    RE_VID = re.compile(r'href="/trayedgea6/(\d+)\.html"')
    RE_IMG = re.compile(r'data-src="([^"]*)"')
    RE_NAME = re.compile(r"<strong>(.*?)</strong>", re.S)
    RE_EM = re.compile(r"<em>(.*?)</em>", re.S)
    RE_B = re.compile(r"<b>(.*?)</b>", re.S)
    RE_MAXPAGE = re.compile(r'/wagon4v/[a-z-]+-(\d+)\.html')
    RE_FACT = re.compile(r'data-field="([a-z]+)"><dt>[^<]*</dt><dd>(.*?)</dd>', re.S)
    RE_TAB = re.compile(r'data-tab="([^"]+)"[^>]*>([^<]+)</button>')
    RE_PANEL = re.compile(r'data-panel="([^"]+)"[^>]*>(.*?)</div>', re.S)
    RE_EP = re.compile(r'href="(/filmcanlite/[^"]+)"[^>]*>([^<]+)</a>')
    RE_PLAYER = re.compile(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', re.S)
    RE_DESC = re.compile(r'class="[^"]*px-prose__raw"[^>]*>(.*?)</div>', re.S)
    RE_JSON_NAME = re.compile(r'"@type":"(?:TVSeries|Movie|VideoObject)","@id":"[^"]*","name":"([^"]*)"')
    RE_JSON_PIC = re.compile(r'"@type":"ImageObject"[^}]*?"url":"([^"]*)"')

    # ------------------------------------------------------------------
    def getName(self):
        return "一二五影视"

    def init(self, extend=""):
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.HOST + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        # 站点用 js_on cookie 区分真人/爬虫，直接补上
        try:
            self.session.cookies.set("js_on", "1", domain="125la.com", path="/")
        except Exception:
            pass
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
    # 请求：requests 优先，curl_cffi 兜底
    # ------------------------------------------------------------------
    def _fetch(self, path, params=None, retry=2):
        url = path if path.startswith("http") else self.HOST + path
        for i in range(retry + 1):
            try:
                r = self.session.get(url, params=params, timeout=15)
                if r.status_code == 200 and len(r.text) > 500:
                    r.encoding = r.apparent_encoding or "utf-8"
                    return r.text
            except Exception as e:
                self._log("req %d fail: %s" % (i, e))
            try:
                from curl_cffi import requests as cr
                full = url
                if params:
                    import urllib.parse
                    full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
                r = cr.get(full, headers=self.headers, impersonate="chrome120", timeout=15)
                if r.status_code == 200:
                    return r.text
            except Exception as e:
                self._log("cffi %d fail: %s" % (i, e))
        return ""

    def _log(self, msg):
        try:
            print("[125la] %s" % msg)
            sys.stdout.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _strip(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", str(s))
        for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                     ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'")):
            s = s.replace(a, b)
        return re.sub(r"\s+", " ", s).strip()

    def _abs(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.HOST + u
        return u

    @staticmethod
    def _norm_id(ids):
        """兼容 list / str / int / 完整 url / 带 .html 后缀 / 混淆路由前缀"""
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        v = str(ids).strip().split("#")[0].split("?")[0]
        # 优先取路由段里的 id（trayedgea6 / filmcanlite 前缀本身带数字，不能直接 search）
        m = re.search(r"/(?:trayedgea6|filmcanlite)/(\d+)", v)
        if m:
            return m.group(1)
        m = re.search(r"(\d+)(?:-\d+-\d+)?\.html$", v)
        if m:
            return m.group(1)
        m = re.search(r"^\D*(\d+)", v)
        return m.group(1) if m else ""

    # ------------------------------------------------------------------
    # 列表解析（分类页 / 搜索页 / 首页通用）
    # ------------------------------------------------------------------
    def _parse_list(self, html):
        if not html:
            return []
        end = html.find("px-pager")
        main = html[:end] if end > 0 else html
        out, seen = [], set()
        for block in self.RE_CARD.findall(main):
            m = self.RE_VID.search(block)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            name = self.RE_NAME.search(block)
            em = self.RE_EM.search(block)
            b = self.RE_B.search(block)
            img = self.RE_IMG.search(block)
            remark = self._strip(em.group(1)) if em else ""
            score = self._strip(b.group(1)) if b else ""
            if score and score not in ("0.0分", "0分"):
                remark = ("%s %s" % (remark, score)).strip()
            out.append({
                "vod_id": vid,
                "vod_name": self._strip(name.group(1)) if name else "",
                "vod_pic": self._abs(img.group(1)) if img else "",
                "vod_remarks": remark,
            })
        return out

    def _max_page(self, html, slug):
        try:
            nums = [int(x) for x in re.findall(r'/wagon4v/%s-(\d+)\.html' % re.escape(slug), html or "")]
            return max(nums) if nums else 1
        except Exception:
            return 1

    # ------------------------------------------------------------------
    # 首页
    # ------------------------------------------------------------------
    def homeContent(self, filter=False):
        classes = [{"type_id": s, "type_name": n} for s, n in self.CATEGORIES]
        result = {"class": classes, "filters": {}}
        try:
            result["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {"list": self._parse_list(self._fetch("/"))[:60]}

    # ------------------------------------------------------------------
    # 分类
    # ------------------------------------------------------------------
    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        slug = str(tid).strip()
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        path = "%s%s.html" % (self.P_CAT, slug) if page <= 1 else \
               "%s%s-%d.html" % (self.P_CAT, slug, page)
        html = self._fetch(path)
        vods = self._parse_list(html)
        return {
            "list": vods,
            "page": page,
            "pagecount": self._max_page(html, slug),
            "limit": len(vods) or 36,
            "total": 999999,
        }

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def detailContent(self, ids):
        vid = self._norm_id(ids)
        if not vid:
            return {"list": []}
        html = self._fetch("%s%s.html" % (self.P_DETAIL, vid))
        if not html:
            return {"list": []}

        facts = {k: self._strip(v) for k, v in self.RE_FACT.findall(html)}

        def f(key):
            v = facts.get(key, "")
            return "" if v in ("暂无", "未知", "-") else v

        name = self.RE_JSON_NAME.search(html)
        name = self._strip(name.group(1)) if name else ""
        if not name:
            t = re.search(r"<title>《?([^《》_|<]+)", html)
            name = self._strip(t.group(1)) if t else vid

        pic = self.RE_JSON_PIC.search(html)
        pic = self._abs(pic.group(1)) if pic else ""
        if not pic:
            m = re.search(r'class="[^"]*px-ledger__cover".*?<img[^>]*src="([^"]*)"', html, re.S)
            pic = self._abs(m.group(1)) if m else ""

        desc = self.RE_DESC.search(html)
        desc = self._strip(desc.group(1)) if desc else ""
        if desc in ("暂无简介，敬请期待", "暂无剧情介绍"):
            desc = ""

        froms, urls = self._playlists(html, vid)
        rating = f("rating").split("/")[0].strip()
        remarks = f("status") or f("update")
        if rating:
            remarks = ("%s %s分" % (remarks, rating)).strip()

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": f("genre"),
            "vod_year": f("year"),
            "vod_area": f("country"),
            "vod_lang": f("language"),
            "vod_remarks": remarks,
            "vod_actor": f("actors").replace("、", ","),
            "vod_director": f("director"),
            "vod_content": desc or "暂无简介",
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod]}

    def _playlists(self, html, vid):
        """解析多线路 tab + 各线路集数；tab 缺失时回退全页扫描"""
        tabs = dict(self.RE_TAB.findall(html))
        panels = self.RE_PANEL.findall(html)
        froms, urls = [], []
        for pid, body in panels:
            eps = []
            for href, title in self.RE_EP.findall(body):
                title = self._strip(title)
                if not title or title in ("下一集", "上一集"):
                    continue
                eps.append("%s$%s" % (title, href))
            if eps:
                froms.append(self._strip(tabs.get(pid, "")) or "线路%d" % (len(froms) + 1))
                urls.append("#".join(eps))
        if froms:
            return froms, urls

        # 兜底：整页找 /filmcanlite/{vid}-*
        eps, seen = [], set()
        for href, title in self.RE_EP.findall(html):
            if not href.startswith("%s%s-" % (self.P_PLAY, vid)) or href in seen:
                continue
            title = self._strip(title)
            if not title or title in ("下一集", "上一集", "立即播放"):
                continue
            seen.add(href)
            eps.append("%s$%s" % (title, href))
        if eps:
            return ["暴风播放"], ["#".join(eps)]
        return ["暴风播放"], ["播放$%s%s-1-1.html" % (self.P_PLAY, vid)]

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        html = self._fetch(self.P_SEARCH, {"wd": key, "page": page})
        vods = self._parse_list(html)
        return {"list": vods, "page": page, "pagecount": 99 if vods else page,
                "limit": len(vods) or 24, "total": 999999}

    # ------------------------------------------------------------------
    # 播放：实时抓 player_aaaa 取 m3u8
    # ------------------------------------------------------------------
    def playerContent(self, flag, id, vipFlags=None):
        path = id
        if isinstance(path, (list, tuple)):
            path = path[0] if path else ""
        path = str(path).strip()

        if self.isVideoFormat(path) and path.startswith("http"):
            return self._play(path)

        html = self._fetch(path if path.startswith("/") or path.startswith("http")
                           else "%s%s.html" % (self.P_PLAY, path))
        m = self.RE_PLAYER.search(html or "")
        if m:
            try:
                data = json.loads(m.group(1))
                url = (data.get("url") or "").replace("\\/", "/")
                if url:
                    if not url.startswith("http"):
                        url = self._abs(url)
                    return self._play(url)
            except Exception as e:
                self._log("player_aaaa parse fail: %s" % e)
        # 兜底：页内直接找 m3u8/mp4
        m2 = re.search(r'(https?:[^\s"\'<>\\]+\.(?:m3u8|mp4)[^\s"\'<>\\]*)',
                       (html or "").replace("\\/", "/"))
        if m2:
            return self._play(m2.group(1))
        return {"parse": 1, "playUrl": "", "url": self._abs(path),
                "header": json.dumps({"User-Agent": self.UA})}

    def _play(self, url):
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": json.dumps({"User-Agent": self.UA, "Referer": self.HOST + "/"}),
        }

    def localProxy(self, params):
        return [200, "text/plain", ""]
