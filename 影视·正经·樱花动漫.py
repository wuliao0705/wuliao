# -*- coding: utf-8 -*-
"""樱花动漫 yinghua228.com — MacCMS(v8) 动漫站 TVBox Spider
分类: /index.php/vod/type/id/{tid}[/page/{pg}].html
详情: /index.php/vod/detail/id/{vid}.html  (多线路 block: 线路N -> /vod/play/id/x/sid/y/nid/z)
播放: play 页 var player_aaaa={"url":"https://...m3u8","encrypt":0}  → 直链
搜索: /index.php/vod/search.html?wd={key}
注意: 首页响应有时缺 charset 头, 需强制 utf-8; 站点偶发 TLS EOF, 备用域名 + curl_cffi 兜底。
"""
import re, json, time, requests
from urllib.parse import quote

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


class Spider(_BaseSpider):

    def getName(self):
        return "YingHua"

    def getDependence(self):
        return []

    def init(self, extend="", *args, **kwargs):
        self.domains = ["https://www.yinghua228.com", "https://www.yinghua3333.com"]
        self.base_url = self.domains[0]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        try:
            self.session.verify = False
        except Exception:
            pass
        self.types = {"20": "日本动漫", "21": "国产动漫", "22": "欧美动漫", "23": "动漫电影", "24": "其他动漫"}
        self._last_search = 0.0
        self._search_gap = 3.5
        return True

    def destroy(self, *args, **kwargs):
        if getattr(self, "session", None):
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None
        return True

    def manualVideoCheck(self):
        return False

    def action(self, action="", *args, **kwargs):
        return {}

    # ---------------- 网络 ----------------
    @staticmethod
    def _decode(r):
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "charset" not in ctype or (r.encoding or "").upper() in ("", "ISO-8859-1"):
            r.encoding = "utf-8"
        return r.text or ""

    def _candidates(self, url):
        out = [url]
        for d in getattr(self, "domains", []):
            if url.startswith(d):
                for alt in self.domains:
                    if alt != d:
                        out.append(alt + url[len(d):])
                break
        return out

    def _fetch(self, url, h):
        try:
            r = self.session.get(url, headers=h, timeout=20, verify=False)
            if r.status_code == 200 and r.content:
                return self._decode(r)
        except Exception:
            pass
        try:
            from curl_cffi import requests as cr
            rc = cr.get(url, headers=h, impersonate="chrome120", timeout=20, verify=False)
            if rc.status_code == 200 and rc.content:
                return rc.text or ""
        except Exception:
            pass
        return ""

    def _req(self, url, referer=None, retry=2):
        h = dict(self.headers)
        if referer:
            h["Referer"] = referer
        cands = self._candidates(url)
        for _ in range(max(1, retry)):
            for u in cands:
                txt = self._fetch(u, h)
                if txt:
                    return txt
        return ""

    # ---------------- 列表解析 ----------------
    def _main_block(self, html):
        i = html.find("stui-vodlist clearfix")
        if i < 0:
            return html
        j = html.find("stui-page", i)
        return html[i:j if j > i else len(html)]

    def _parse_list(self, html):
        scope = self._main_block(html) or html
        out, seen = [], set()
        for m in re.finditer(r"<a\b[^>]*>(?:(?!</a>).)*?</a>", scope, re.S):
            tag = m.group(0)
            if "stui-vodlist__thumb" not in tag:
                continue
            mv = re.search(r"/index\.php/vod/detail/id/(\d+)\.html", tag)
            if not mv or mv.group(1) in seen:
                continue
            seen.add(mv.group(1))
            mt = re.search(r'title="([^"]*)"', tag)
            mp = re.search(r'data-original="([^"]+)"', tag) or re.search(r'src="([^"]+\.(?:jpg|jpeg|png|webp))"', tag, re.I)
            tail = tag + scope[m.end():m.end() + 200]
            note = re.search(r"pic-text[^>]*>([^<]+)<", tail)
            pic = mp.group(1).strip() if mp else ""
            if pic and not pic.startswith("http"):
                pic = self.base_url + pic
            out.append({
                "vod_id": mv.group(1),
                "vod_name": (mt.group(1).strip() if mt else ""),
                "vod_pic": pic,
                "vod_remarks": note.group(1).strip() if note else "",
            })
        return out

    def _pagecount(self, html):
        m = re.search(r'<span class="num">\d+/(\d+)</span>', html)
        if m:
            return max(1, int(m.group(1)))
        nums = re.findall(r"/page/(\d+)\.html", html)
        return max([int(x) for x in nums], default=1)

    # ---------------- 首页 / 分类 ----------------
    def homeContent(self, filter=False, *args, **kwargs):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.types.items()]
        areas = ["全部", "日本", "韩国", "美国", "大陆", "其他"]
        years = ["全部"] + [str(y) for y in range(2026, 2009, -1)]
        filters = {tid: [{
            "key": "class", "name": "状态",
            "value": [{"n": a, "v": a} for a in areas],
        }, {
            "key": "year", "name": "年份",
            "value": [{"n": y, "v": y} for y in years],
        }] for tid in self.types}
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None, *args, **kwargs):
        html = self._req(self.base_url + "/")
        return {"list": self._parse_list(html)[:40]}

    def categoryContent(self, tid, pg="1", filter=False, extend=None, *args, **kwargs):
        tid = re.sub(r"\D", "", str(tid or "")) or "20"
        p = int(pg) if str(pg).isdigit() else 1
        ext = extend if isinstance(extend, dict) else {}
        url = "%s/index.php/vod/type/id/%s%s" % (self.base_url, tid, ("/page/%d.html" % p) if p > 1 else ".html")
        if ext.get("year") and ext["year"] != "全部":
            url = "%s/index.php/vod/show/id/%s/year/%s/page/%d.html" % (self.base_url, tid, quote(str(ext["year"])), p)
        html = self._req(url)
        items = self._parse_list(html)
        return {"list": items, "page": str(p), "pagecount": self._pagecount(html) or 999, "limit": len(items), "total": 99999}

    # ---------------- 详情 ----------------
    def detailContent(self, ids, *args, **kwargs):
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        vid = re.sub(r"\D", "", str(ids))
        url = "%s/index.php/vod/detail/id/%s.html" % (self.base_url, vid)
        html = self._req(url, referer=self.base_url + "/")
        if not html:
            return {"list": []}
        name = ""
        mh = re.search(r"<h1[^>]*>\s*([^<]+)", html)
        if mh:
            name = mh.group(1).strip()
        thumb = re.search(r"stui-content__thumb(.*?)</div>", html, re.S)
        pic, note = "", ""
        if thumb:
            mp = re.search(r'data-original="([^"]+)"', thumb.group(1)) or re.search(r'src="(/upload/[^"]+)"', thumb.group(1))
            mn = re.search(r"pic-text[^>]*>([^<]+)<", thumb.group(1))
            pic = mp.group(1).strip() if mp else ""
            if pic and not pic.startswith("http"):
                pic = self.base_url + pic
            note = mn.group(1).strip() if mn else ""
        desc = ""
        md = re.search(r"剧情简介.*?<p class=\"col-pd\">\s*(.*?)\s*</p>", html, re.S)
        if md:
            desc = re.sub(r"<[^>]+>", "", md.group(1)).strip()
        meta = {}
        for label, key in (("类型", "type_name"), ("主演", "vod_actor"), ("导演", "vod_director"),
                           ("地区", "vod_area"), ("年份", "vod_year")):
            start = html.find("%s：</span>" % label)
            if start < 0:
                continue
            body = html[start + len("%s：</span>" % label):start + 4000]
            cut = re.search(r'<span class="(?:split-line|text-muted)[^"]*">|更新：|</div>|<h3|剧情简介', body)
            if cut:
                body = body[:cut.start()]
            val = re.sub(r"&nbsp;", ",", body)
            val = re.sub(r"<[^>]+>", ",", val)
            val = re.sub(r"\s+", ",", val)
            val = re.sub(r",{2,}", ",", val).strip(", \t")
            if val:
                meta[key] = val
        lines = []
        for blk in re.finditer(r"线路(\d+).*?<ul class=\"stui-content__playlist clearfix\">(.*?)</ul>", html, re.S):
            eps = re.findall(r'href="/index\.php/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>\s*([^<]{1,40}?)\s*<', blk.group(2))
            plist = ["%s$%s|%s|%s" % (e[3].strip() or ("第%d集" % (i + 1)), e[0], e[1], e[2]) for i, e in enumerate(eps)]
            if plist:
                lines.append(("线路" + blk.group(1), plist))
        vod = {
            "vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": note,
            "type_name": meta.get("type_name", "动漫"), "vod_actor": meta.get("vod_actor", ""),
            "vod_director": meta.get("vod_director", ""), "vod_content": desc,
            "vod_area": meta.get("vod_area", ""), "vod_year": meta.get("vod_year", ""),
            "vod_play_from": "$$$".join(l[0] for l in lines),
            "vod_play_url": "$$$".join("#".join(l[1]) for l in lines),
        }
        return {"list": [vod]}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, ids, vipFlags=None, *args, **kwargs):
        idv = ids if isinstance(ids, str) else str(ids)
        parts = re.findall(r"\d+", idv)
        if len(parts) >= 3:
            vid, sid, nid = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            vid, sid, nid = parts[0], parts[1], "1"
        elif len(parts) == 1:
            vid, sid, nid = parts[0], "1", "1"
        else:
            return {"parse": 0, "url": idv, "header": {"User-Agent": self.headers["User-Agent"]}, "jx": 0}
        play_url = "%s/index.php/vod/play/id/%s/sid/%s/nid/%s.html" % (self.base_url, vid, sid, nid)
        html = self._req(play_url, referer="%s/index.php/vod/detail/id/%s.html" % (self.base_url, vid))
        raw = ""
        m = re.search(r"var player_aaaa\s*=\s*(\{[\s\S]{0,4000}?\})\s*;?\s*</script>", html)
        if m:
            raw = m.group(1)
        else:
            m2 = re.search(r'player_aaaa=(\{[\s\S]{0,4000}?\})</script>', html)
            raw = m2.group(1) if m2 else ""
        real = ""
        mu = re.search(r'"url"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        if mu:
            real = mu.group(1).replace("\\/", "/")
        if not real:
            try:
                real = json.loads(raw).get("url", "")
            except Exception:
                real = ""
        header = {"User-Agent": self.headers["User-Agent"], "Referer": self.base_url + "/"}
        if re.match(r"^https?://", real or ""):
            if ".m3u8" in real or ".mp4" in real or ".mkv" in real:
                return {"parse": 0, "url": real, "header": header, "jx": 0, "msg": ""}
            return {"parse": 1, "url": real, "header": header, "jx": 0, "msg": ""}
        return {"parse": 1, "url": play_url, "header": header, "jx": 0, "msg": ""}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=0, pg="1", *args, **kwargs):
        wd = quote(str(key))
        items = []
        gap = getattr(self, "_search_gap", 3.5)
        wait = getattr(self, "_last_search", 0.0) + gap - time.time()
        if wait > 0:
            time.sleep(min(wait, 6))
        for _ in range(3):
            for path in ("/index.php/vod/search/wd/%s.html" % wd, "/index.php/vod/search.html?wd=%s" % wd):
                html = self._req(self.base_url + path)
                if html and "频繁操作" in html:
                    time.sleep(gap + 1)
                    continue
                items = self._parse_list(html)
                if items:
                    break
            if items:
                break
        self._last_search = time.time()
        return {"list": items, "page": str(pg or 1), "pagecount": 1, "limit": len(items), "total": len(items)}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|avi)([?#]|$)", str(url), re.I)) or str(url).startswith("http")

    def localProxy(self, param=None, *args, **kwargs):
        return []
