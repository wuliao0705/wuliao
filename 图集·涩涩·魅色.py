#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MMRGB 魅色MM — TVBox / PeekPro / CatVod / 影视仓 图集爬虫
Site : https://mmrgb.com/
Type : Discuz! X3.5 (template iscwo_u8) 图集论坛
Play : pics://  图片相册协议

侦察结论（2026-08-26 实测）：
  · 列表页  forum-{fid}-{page}.html      → card 结构 ui8-image + card-permalink
  · 排序    filter=lastpost|heat|reply & orderby=lastpost|heats|views [&dateline]
  · 详情页  thread-{tid}-1-1.html        → zoomfile / file 属性取原图
  · 图片    attachment.mmrgb.com         → 无防盗链，可直连
  · 搜索    search.php?mod=forum&srchtxt=..&searchsubmit=yes
            翻页需先取 searchid 再带 kw 请求
  · 站点偶发 522（Cloudflare origin timeout）→ 内置退避重试
"""

import re
import sys
import json
import time

from urllib.parse import quote, unquote, urljoin

try:
    import requests
    try:
        requests.packages.urllib3.disable_warnings()
    except Exception:
        pass
except Exception:
    requests = None

import gzip
import io
import urllib.request
import urllib.error

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def init(self, extend=""):
            pass


class Spider(BaseSpider):

    HOST = "https://mmrgb.com"

    # fid -> 版块名（首页抓取失败时的兜底静态表）
    FORUMS = [
        ("2", "秀人网"),
        ("3", "模范学院"),
        ("4", "魅妍社"),
        ("5", "美媛馆"),
        ("6", "爱蜜社"),
        ("7", "波萝社"),
        ("8", "尤物馆"),
        ("9", "优星馆"),
        ("10", "蜜桃社"),
        ("11", "嗲囡囡"),
        ("12", "影私荟"),
        ("13", "顽味生活"),
        ("14", "星乐园"),
        ("15", "花の颜"),
        ("16", "御女郎"),
        ("17", "薄荷叶"),
        ("18", "尤蜜荟"),
        ("19", "糖果画报"),
        ("20", "模特联盟"),
        ("21", "猫萌榜"),
        ("22", "花漾show"),
        ("23", "星颜社"),
        ("24", "语画界"),
    ]

    # 排序：value -> (filter, orderby, dateline)
    SORTS = [
        ("lastpost", "最新"),
        ("heats", "推荐"),
        ("month", "月榜"),
        ("year", "年榜"),
        ("views", "总榜"),
    ]

    SORT_MAP = {
        "lastpost": ("lastpost", "lastpost", ""),
        "heats": ("heat", "heats", ""),
        "month": ("reply", "views", "2592000"),
        "year": ("reply", "views", "31536000"),
        "views": ("reply", "views", ""),
    }

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # ── 生命周期 ────────────────────────────────────────────────
    def init(self, extend=""):
        self.host = self.HOST
        self.proxy_pic = False
        self.headers = {
            "User-Agent": self.UA,
            "Referer": self.HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self._searchid = {}
        self._cache = {}

        try:
            if extend:
                cfg = extend if isinstance(extend, dict) else json.loads(extend)
                host = cfg.get("host") or cfg.get("HOST")
                if host:
                    self.host = str(host).rstrip("/")
                    self.headers["Referer"] = self.host + "/"
                ua = cfg.get("ua") or cfg.get("UA")
                if ua:
                    self.headers["User-Agent"] = ua
                ck = cfg.get("cookie") or cfg.get("Cookie")
                if ck:
                    self.headers["Cookie"] = ck
                if cfg.get("proxy_pic") or cfg.get("proxy"):
                    self.proxy_pic = True
        except Exception:
            pass

        self.session = None
        if requests:
            try:
                self.session = requests.Session()
                self.session.headers.update(self.headers)
                self.session.verify = False
            except Exception:
                self.session = None
        return self

    def getName(self):
        return "MMRGB 魅色MM"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    # ── HTTP ────────────────────────────────────────────────────
    def _fetch(self, url, tries=4, referer=None):
        """站点偶发 522/503，做指数退避重试。返回 html 文本，失败返回 ''。"""
        hdr = dict(self.headers)
        if referer:
            hdr["Referer"] = referer
        last = ""
        for i in range(tries):
            try:
                if self.session is not None:
                    r = self.session.get(url, headers=hdr, timeout=20,
                                         allow_redirects=True)
                    if r.status_code == 200 and len(r.text) > 500:
                        return r.text
                    last = "http %s" % r.status_code
                else:
                    req = urllib.request.Request(url, headers=dict(
                        hdr, **{"Accept-Encoding": "gzip, deflate"}))
                    resp = urllib.request.urlopen(req, timeout=20)
                    data = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                    txt = data.decode("utf-8", "ignore")
                    if len(txt) > 500:
                        return txt
                    last = "short body"
            except Exception as e:
                last = str(e)
            time.sleep(0.6 * (i + 1))
        return ""

    def _bytes(self, url, referer=None):
        hdr = dict(self.headers)
        hdr["Referer"] = referer or (self.host + "/")
        for i in range(3):
            try:
                if self.session is not None:
                    r = self.session.get(url, headers=hdr, timeout=25)
                    if r.status_code == 200:
                        return (r.content,
                                r.headers.get("Content-Type", "image/jpeg"))
                else:
                    req = urllib.request.Request(url, headers=hdr)
                    resp = urllib.request.urlopen(req, timeout=25)
                    return (resp.read(),
                            resp.headers.get("Content-Type", "image/jpeg"))
            except Exception:
                time.sleep(0.5 * (i + 1))
        return (b"", "image/jpeg")

    # ── 工具 ────────────────────────────────────────────────────
    @staticmethod
    def _page(pg):
        try:
            p = int(str(pg))
        except Exception:
            p = 1
        return p if p > 0 else 1

    @staticmethod
    def _unesc(s):
        if not s:
            return ""
        for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#039;", "'"),
                     ("&apos;", "'"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&nbsp;", " ")):
            s = s.replace(a, b)
        return s

    # 搜索结果里关键词被 <strong><font> 包裹，直接删标签（不补空格）
    INLINE_TAG_RE = re.compile(
        r"</?(?:strong|font|b|em|i|u|span|mark|ins)\b[^>]*>", re.I)

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
        s = self.INLINE_TAG_RE.sub("", s)
        s = re.sub(r"<[^>]+>", " ", s)
        s = self._unesc(s)
        s = re.sub(r"\s+", " ", s).strip()
        # 修正 "[XiaoYu 语画界 ]" 这类括号内多余空格
        s = re.sub(r"\[\s+", "[", s)
        s = re.sub(r"\s+\]", "]", s)
        return s

    def _abs(self, u):
        if not u:
            return ""
        u = self._unesc(u.strip())
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        return urljoin(self.host + "/", u.lstrip("/"))

    def _pic(self, u):
        u = self._abs(u)
        if u and self.proxy_pic:
            return self._proxy_base() + "&url=" + quote(u)
        return u

    def _proxy_base(self):
        """优先用宿主提供的代理地址，取不到时退回 TVBox 默认端口。"""
        try:
            base = self.getProxyUrl()
            if base:
                return base if "?" in base else base + "?do=py"
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    @staticmethod
    def _tidy_title(s):
        return re.sub(r"[\s\-_—·,，、.。]+$", "", s or "").strip()

    # ── 列表解析 ────────────────────────────────────────────────
    CARD_RE = re.compile(
        r'ui8-image="(?P<cover>[^"]*)"'          # 封面
        r'.*?<p>(?P<meta>.*?)</p>'               # 浏览/收藏/标题
        r'.*?href="(?P<href>thread-(?P<tid>\d+)-[^"]*\.html)"',
        re.S)

    def _parse_list(self, html):
        out = []
        seen = set()
        for m in self.CARD_RE.finditer(html or ""):
            tid = m.group("tid")
            if tid in seen:
                continue
            seen.add(tid)

            raw = re.sub(r"<!--.*?-->", " ", m.group("meta"), flags=re.S)
            # <br /> 之后是标题，之前是数字统计
            parts = re.split(r"<br\s*/?>", raw, maxsplit=1)
            stat = self._clean(parts[0]) if parts else ""
            title = self._clean(parts[1]) if len(parts) > 1 else ""
            if not title:
                title = self._clean(raw)

            nums = re.findall(r"\d+", stat)
            remark = ""
            if nums:
                views = nums[0]
                try:
                    v = int(views)
                    views = "%.1fw" % (v / 10000.0) if v >= 10000 else str(v)
                except Exception:
                    pass
                remark = "👁 " + views
                if len(nums) > 1:
                    remark += "  ★ " + nums[-1]

            # 标题里带 [XiuRen秀人网] 2026.02.04 No.11319 杨晨晨
            name = title
            date = ""
            dm = re.search(r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})", title)
            if dm:
                date = dm.group(1)
            if date and remark:
                remark = date + "  " + remark
            elif date:
                remark = date

            cover = m.group("cover")
            if not cover:
                cover = "%s/forum/threadcover/%s.jpg" % (
                    "https://attachment.mmrgb.com", tid)

            out.append({
                "vod_id": tid,
                "vod_name": self._tidy_title(name) or ("图集 " + tid),
                "vod_pic": self._pic(cover),
                "vod_remarks": remark,
            })
        return out

    @staticmethod
    def _pagecount(html):
        if not html:
            return 1
        m = re.search(r'class="last"[^>]*>[^0-9<]{0,20}(\d+)', html)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
        nums = [int(x) for x in re.findall(r'page=(\d+)', html)] or [1]
        nums += [int(x) for x in re.findall(r'forum-\d+-(\d+)\.html', html)]
        return max(1, max(nums))

    # ── URL 构造 ────────────────────────────────────────────────
    def _cat_url(self, tid, pg=1, sort=""):
        tid = str(tid or "").strip()
        pg = self._page(pg)

        if tid.startswith("portal:"):
            order = tid.split(":", 1)[1] or "new"
            return "%s/portal.php?order=%s&page=%d" % (self.host, order, pg)

        fid = re.sub(r"\D", "", tid) or "2"
        if not sort or sort == "lastpost":
            return "%s/forum-%s-%d.html" % (self.host, fid, pg)

        f, o, dl = self.SORT_MAP.get(sort, self.SORT_MAP["lastpost"])
        u = "%s/forum.php?mod=forumdisplay&fid=%s&filter=%s&orderby=%s" % (
            self.host, fid, f, o)
        if dl:
            u += "&dateline=" + dl
        return u + "&page=%d" % pg

    def _thread_url(self, tid, page=1):
        tid = re.sub(r"\D", "", str(tid)) or "0"
        return "%s/thread-%s-%d-1.html" % (self.host, tid, self._page(page))

    # ── 首页 ────────────────────────────────────────────────────
    def homeContent(self, filter=True):
        classes = []
        html = self._fetch(self.host + "/")

        got = []
        if html:
            for m in re.finditer(
                    r'href="forum-(\d+)-1\.html"[^>]*>\s*([^<]{1,48})', html):
                fid, name = m.group(1), self._clean(m.group(2))
                if not name or any(c["type_id"] == fid for c in got):
                    continue
                # "XiuRen 秀人网" → 取中文部分更适合手机显示
                cn = re.sub(r"^[A-Za-z0-9 &]+", "", name).strip()
                got.append({"type_id": fid, "type_name": cn or name})
        if len(got) >= 5:
            classes = got
        else:
            classes = [{"type_id": f, "type_name": n} for f, n in self.FORUMS]

        classes.insert(0, {"type_id": "portal:hot", "type_name": "🔥 热门"})
        classes.insert(1, {"type_id": "portal:new", "type_name": "🆕 最新"})

        result = {"class": classes}
        if filter:
            sorts = [{"n": n, "v": v} for v, n in self.SORTS]
            filters = {}
            for c in classes:
                if c["type_id"].startswith("portal:"):
                    continue
                filters[c["type_id"]] = [
                    {"key": "sort", "name": "排序", "value": sorts}]
            result["filters"] = filters

        if html:
            vods = self._parse_list(html)
            if vods:
                self._cache["home"] = vods[:30]
        return result

    def homeVideoContent(self):
        vods = self._cache.get("home")
        if not vods:
            html = self._fetch(self.host + "/portal.php?order=new")
            vods = self._parse_list(html)[:30]
        return {"list": vods}

    # ── 分类 ────────────────────────────────────────────────────
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        pg = self._page(pg)
        sort = ""
        try:
            if extend:
                ex = extend if isinstance(extend, dict) else json.loads(extend)
                sort = ex.get("sort") or ""
        except Exception:
            sort = ""

        html = self._fetch(self._cat_url(tid, pg, sort))
        vods = self._parse_list(html)
        pc = self._pagecount(html) if vods else pg
        return {
            "list": vods,
            "page": pg,
            "pagecount": pc,
            "limit": max(len(vods), 20),
            "total": pc * max(len(vods), 20),
        }

    # ── 详情 ────────────────────────────────────────────────────
    IMG_RE = re.compile(
        r'(?:zoomfile|file|data-original|src)="'
        r'(https?://[^"]*?/forum/\d{6}/[^"]+?\.(?:jpg|jpeg|png|webp|gif))"',
        re.I)

    def _parse_thread(self, html, tid=""):
        """返回 (标题, 图片列表, 简介, 本帖总页数)"""
        title = ""
        m = re.search(r"<title>(.*?)</title>", html or "", re.S)
        if m:
            title = self._clean(m.group(1))
            title = re.sub(r"\s*-\s*[^-]*-\s*MMRGB\s*$", "", title)
            title = re.sub(r"\s*-\s*MMRGB\s*$", "", title).strip()
            title = self._tidy_title(title)

        # 优先只在帖子正文里取图，避免侧栏/推荐位混入
        scope = html or ""
        bodies = re.findall(
            r'id="postmessage_\d+"[^>]*>(.*?)</td>', scope, re.S)
        if bodies:
            joined = "\n".join(bodies)
            if self.IMG_RE.search(joined):
                scope = joined

        imgs = []
        seen = set()
        for mm in self.IMG_RE.finditer(scope):
            u = self._unesc(mm.group(1))
            if u in seen:
                continue
            seen.add(u)
            imgs.append(u)

        # 帖内分页只认本帖 tid，防止误取推荐帖链接
        pages = 1
        fid = re.sub(r"\D", "", str(tid)) if tid else r"\d+"
        pm = re.findall(r'thread-%s-(\d+)-1\.html' % fid, html or "")
        if pm:
            try:
                pages = max(1, max(int(x) for x in pm))
            except Exception:
                pages = 1

        desc = ""
        dm = re.search(r'name="description"[^>]*content="([^"]*)"', html or "")
        if dm:
            desc = self._clean(dm.group(1))
        return title, imgs, desc, pages

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        tid = str(ids[0])
        url = self._thread_url(tid, 1)
        html = self._fetch(url, referer=self.host + "/")
        if not html:
            return {"list": []}

        title, imgs, desc, pages = self._parse_thread(html, tid)

        # 标题拆解：[XiuRen秀人网] 2026.02.04 No.11319 杨晨晨
        series = model = date = ""
        sm = re.match(r"\s*\[([^\]]+)\]\s*(.*)$", title)
        rest = title
        if sm:
            series, rest = sm.group(1).strip(), sm.group(2).strip()
        dm = re.search(r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})", rest)
        if dm:
            date = dm.group(1)
        nm = re.search(r"(?:No|Vol)\.?\s*[\d.]+\s*(.+)$", rest)
        if nm:
            model = nm.group(1).strip()

        # 选集：单页帖 → 1 集全图；多页帖 → 每页一集
        eps = []
        if pages > 1:
            for p in range(1, pages + 1):
                eps.append("第%d页$%s|%d" % (p, tid, p))
        else:
            eps.append("查看图集(%d张)$%s|1" % (len(imgs), tid))

        cover = imgs[0] if imgs else (
            "https://attachment.mmrgb.com/forum/threadcover/%s.jpg" % tid)

        vod = {
            "vod_id": tid,
            "vod_name": title or ("图集 " + tid),
            "vod_pic": self._pic(cover),
            "vod_year": date,
            "vod_area": series,
            "vod_actor": model,
            "vod_director": series,
            "vod_tag": series,
            "vod_remarks": "%d 张" % len(imgs) if imgs else "",
            "vod_content": desc or title,
            "vod_play_from": "图集",
            "vod_play_url": "#".join(eps),
        }
        return {"list": [vod]}

    # ── 搜索 ────────────────────────────────────────────────────
    # 关键词 → 版块 fid 兜底（站内搜索对版块名/系列名常返回空）
    SERIES_ALIAS = {
        "秀人": "2", "秀人网": "2", "xiuren": "2",
        "模范学院": "3", "mfstar": "3",
        "魅妍社": "4", "mistar": "4",
        "美媛馆": "5", "mygirl": "5",
        "爱蜜社": "6", "imiss": "6",
        "波萝社": "7", "bololi": "7", "兔几盟": "7", "tukmo": "7",
        "尤物馆": "8", "youwu": "8",
        "优星馆": "9", "uxing": "9",
        "蜜桃社": "10", "miitao": "10",
        "嗲囡囡": "11", "feilin": "11",
        "影私荟": "12", "wings": "12",
        "顽味生活": "13", "taste": "13",
        "星乐园": "14", "leyuan": "14",
        "花の颜": "15", "花的颜": "15", "huayan": "15",
        "御女郎": "16", "dkgirl": "16",
        "薄荷叶": "17", "mintye": "17",
        "尤蜜荟": "18", "youmi": "18",
        "糖果画报": "19", "网红馆": "19", "candy": "19",
        "模特联盟": "20", "mtmeng": "20",
        "猫萌榜": "21", "瑞丝馆": "21", "micat": "21", "ruisg": "21",
        "花漾show": "22", "花漾": "22", "huayang": "22",
        "星颜社": "23", "xingyan": "23",
        "语画界": "24", "xiaoyu": "24",
    }

    # 站点限制：游客 5 秒内只能搜一次
    THROTTLE_MARK = "只能进行一次搜索"

    def _fetch_search(self, url, tries=3):
        """搜索专用抓取：命中频率限制则等待后重试。"""
        for i in range(tries):
            html = self._fetch(url, tries=2)
            if html and self.THROTTLE_MARK not in html:
                return html
            if html and self.THROTTLE_MARK in html:
                time.sleep(5.5)
                continue
            time.sleep(1.0)
        return ""

    def _search_html(self, key, pg=1):
        pg = self._page(pg)
        kw = quote(str(key).strip())
        first = ("%s/search.php?mod=forum&srchtxt=%s&searchsubmit=yes"
                 % (self.host, kw))
        if pg <= 1:
            html = self._fetch_search(first)
            sid = re.search(r"searchid=(\d+)", html or "")
            if sid:
                self._searchid[key] = sid.group(1)
            return html

        sid = self._searchid.get(key)
        if not sid:
            h0 = self._fetch_search(first)
            m = re.search(r"searchid=(\d+)", h0 or "")
            if not m:
                return h0
            sid = m.group(1)
            self._searchid[key] = sid

        u = ("%s/search.php?mod=forum&searchid=%s&orderby=lastpost"
             "&ascdesc=desc&searchsubmit=yes&kw=%s&page=%d"
             % (self.host, sid, kw, pg))
        html = self._fetch_search(u)
        if not html:
            self._searchid.pop(key, None)
        return html

    def searchContent(self, key, quick=False, pg=1):
        pg = self._page(pg)
        html = self._search_html(key, pg)
        vods = self._parse_list(html)

        # 搜不到时：关键词若命中系列名，退回该版块列表
        if not vods:
            k = re.sub(r"[\s\[\]【】]", "", str(key or "")).lower()
            fid = self.SERIES_ALIAS.get(k)
            if not fid:
                for name, f in self.SERIES_ALIAS.items():
                    if name and name in k:
                        fid = f
                        break
            if fid:
                return self.categoryContent(fid, pg)

        pc = self._pagecount(html) if vods else pg
        return {
            "list": vods,
            "page": pg,
            "pagecount": pc,
            "limit": max(len(vods), 20),
            "total": pc * max(len(vods), 20),
        }

    def searchContentPage(self, key, quick=False, pg=1):
        return self.searchContent(key, quick, pg)

    # ── 播放（pics:// 相册）─────────────────────────────────────
    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        tid, _, page = raw.partition("|")
        page = self._page(page or 1)

        html = self._fetch(self._thread_url(tid, page),
                           referer=self._thread_url(tid, 1))
        _, imgs, _, _ = self._parse_thread(html, tid)

        if not imgs:
            return {"parse": 1, "playUrl": "", "url": self._thread_url(tid, page),
                    "header": json.dumps({"User-Agent": self.UA,
                                          "Referer": self.host + "/"})}

        urls = [self._pic(u) for u in imgs]
        return {
            "parse": 0,
            "playUrl": "",
            "url": "pics://" + "&&".join(urls),
            "header": json.dumps({"User-Agent": self.UA,
                                  "Referer": self.host + "/"}),
            "contentType": "image",
            "format": "",
        }

    # ── 本地代理（可选，init 传 proxy_pic 时启用）───────────────
    def localProxy(self, param):
        try:
            url = unquote((param or {}).get("url", ""))
            if not url.startswith("http"):
                return [404, "text/plain", b"bad url"]
            data, ctype = self._bytes(url)
            if not data:
                return [502, "text/plain", b"upstream error"]
            return [200, ctype, data]
        except Exception as e:
            return [500, "text/plain", str(e).encode("utf-8", "ignore")]
