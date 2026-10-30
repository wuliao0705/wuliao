# -*- coding: utf-8 -*-
"""袋鼠影视 dsystv.com — 自研模板影视站 TVBox Spider
分类: /frim/index{tid}.html (1电影 2电视剧 3综艺 4动漫 44短剧)
列表/筛选/搜索: /search.php?searchtype=5&tid={tid}&area=&year=&letter=&page={pg}
                /search.php?searchword={key}&page={pg}
详情: /movie/index{vid}.html —— JSON-LD VideoObject 提供 名称/海报/类型/简介；
      播放线路为 <div class="panel" data-playlist-name="蓝光专线N"> + /play/{vid}-{line}-{ep}.html
播放: play 页 var now="https://....m3u8" 直链（var pn 为线路播放器名）
注意: 海报托管在 community.codewave.163.com（无防盗链）；站点在 CF 后，偶发需 curl_cffi 兜底。
"""
import re, json, requests
from urllib.parse import quote

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


class Spider(_BaseSpider):

    def getName(self):
        return "DaiShu"

    def getDependence(self):
        return []

    def init(self, extend="", *args, **kwargs):
        self.base_url = "https://dsystv.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.base_url + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        try:
            self.session.verify = False
        except Exception:
            pass
        self.types = {"1": "电影", "2": "电视剧", "3": "综艺", "4": "动漫", "44": "短剧"}
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
        for _ in range(max(1, retry)):
            txt = self._fetch(url, h)
            if txt:
                return txt
        return ""

    # ---------------- 列表 ----------------
    def _parse_list(self, html):
        out, seen = [], set()
        for m in re.finditer(r"<a\b[^>]*>(?:(?!</a>).)*?</a>", html, re.S):
            tag = m.group(0)
            if "videopic" not in tag:
                continue
            mv = re.search(r"/movie/index(\d+)\.html", tag)
            if not mv or mv.group(1) in seen:
                continue
            seen.add(mv.group(1))
            mt = re.search(r'title="([^"]*)"', tag)
            mp = re.search(r'data-original="([^"]+)"', tag) or re.search(r'<img[^>]*\bsrc="(https?://[^"]+)"', tag)
            note = re.search(r'class="note[^"]*"[^>]*>([^<]+)<', tag + html[m.end():m.end() + 260])
            out.append({
                "vod_id": mv.group(1),
                "vod_name": (mt.group(1).strip() if mt else ""),
                "vod_pic": mp.group(1).strip() if mp else "",
                "vod_remarks": note.group(1).strip() if note else "",
            })
        return out

    def _pagecount(self, html):
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", html) if x.isdigit()]
        if nums:
            return max(1, max(nums))
        m = re.search(r"共\s*(\d+)\s*页", html)
        return max(1, int(m.group(1))) if m else 20

    def homeContent(self, filter=False, *args, **kwargs):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.types.items()]
        v = lambda items: [{"n": x or "不限", "v": x} for x in items]
        filters = {tid: [
            {"key": "area", "name": "地区", "value": v(["", "大陆", "香港", "台湾", "美国", "韩国", "日本", "英国", "法国", "德国", "泰国", "印度", "其他"])},
            {"key": "year", "name": "年份", "value": v([""] + [str(y) for y in range(2026, 2009, -1)])},
            {"key": "letter", "name": "字母", "value": v([""] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))},
            {"key": "order", "name": "排序", "value": [{"n": "按推荐", "v": ""}, {"n": "按时间", "v": "time"}, {"n": "按热度", "v": "weekhit"}, {"n": "按评分", "v": "douban"}]},
        ] for tid in self.types}
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self, tid="", pg="1", filter=False, extend=None, *args, **kwargs):
        html = self._req("%s/frim/index1.html" % self.base_url)
        return {"list": self._parse_list(html)[:40]}

    def categoryContent(self, tid, pg="1", filter=False, extend=None, *args, **kwargs):
        tid = re.sub(r"\D", "", str(tid or "")) or "1"
        if tid not in self.types:
            tid = "1"
        p = int(pg) if str(pg).isdigit() else 1
        ext = extend if isinstance(extend, dict) else {}
        parts = ["searchtype=5", "tid=%s" % tid]
        for k in ("area", "year", "letter", "order", "yuyan", "state", "jq"):
            val = ext.get(k) or ""
            if val:
                parts.append("%s=%s" % (k, quote(str(val))))
        parts.append("page=%d" % p)
        html = self._req(self.base_url + "/search.php?" + "&".join(parts))
        items = self._parse_list(html)
        pc = self._pagecount(html)
        if not items:
            html2 = self._req("%s/frim/index%s.html" % (self.base_url, tid))
            items = self._parse_list(html2)
        return {"list": items, "page": str(p), "pagecount": pc, "limit": len(items), "total": 99999}

    # ---------------- 详情 ----------------
    def detailContent(self, ids, *args, **kwargs):
        if isinstance(ids, (list, tuple)):
            ids = ids[0] if ids else ""
        vid = re.sub(r"\D", "", str(ids))
        url = "%s/movie/index%s.html" % (self.base_url, vid)
        html = self._req(url, referer=url)
        if not html:
            return {"list": []}
        meta, name, pic, intro = {}, "", "", ""
        ld = re.search(r'"@type":\s*"VideoObject"\s*,([\s\S]*?)\n\s*\}\s*</script>', html)
        if ld:
            blob = ld.group(1)
            for field, key in (("name", "vod_name"), ("thumbnailUrl", "vod_pic"), ("genre", "type_name"), ("description", "vod_content")):
                mm = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % field, blob)
                if mm:
                    try:
                        meta[key] = json.loads('"%s"' % mm.group(1)).strip()
                    except Exception:
                        meta[key] = mm.group(1).strip()
        name = meta.get("vod_name", "")
        pic = meta.get("vod_pic", "")
        intro = meta.get("vod_content", "")
        if not name:
            mh = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html)
            name = re.sub(r"<[^>]+>", "", mh.group(1)).strip() if mh else ""
        if not pic:
            mp = re.search(r'class="videopic"[\s\S]{0,600}?src="([^"]+)"', html) or re.search(r'property="og:image" content="([^"]+)"', html)
            pic = mp.group(1).strip() if mp else ""
        if not intro:
            mi = re.search(r'name="description" content="([^"]+)"', html)
            intro = mi.group(1).strip() if mi else ""
        labels = (("主演", "vod_actor"), ("导演", "vod_director"), ("地区", "vod_area"),
                  ("年份", "vod_year"), ("语言", "vod_lang"), ("状态", "vod_remarks"), ("豆瓣", "vod_douban_score"))
        for li in re.finditer(r'<li[^>]*data-video-meta="([^"]*)">[\s\S]{0,60}?<span class="text-muted">([^<]{1,6})：</span>([\s\S]*?)</li>', html):
            val, label, body = li.group(1).strip(), li.group(2).strip(), li.group(3)
            if not val:
                val = re.sub(r"\s+", " ", re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", "", body))).strip()
            for lb, key in labels:
                if label == lb and val:
                    meta[key] = val
                    break
        intro = re.sub(r"&nbsp;", " ", intro).strip()
        cleaned = re.sub(r"^《[^》]*》是[^，,]{0,14}，免费在线观看全集及最新播放线路。", "", intro).strip()
        intro = cleaned or intro
        lines = []
        blocks = re.split(r'data-playlist-name="([^"]*)"', html)
        for i in range(1, len(blocks), 2):
            lname = (blocks[i] or "").strip() or ("线路%d" % (len(lines) + 1))
            eps = re.findall(r'href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>\s*([^<]{1,40}?)\s*<', blocks[i + 1][:200000])
            plist = ["%s$%s|%s|%s" % (e[3].strip() or ("第%d集" % (j + 1)), e[0], e[1], e[2]) for j, e in enumerate(eps)]
            if plist:
                lines.append((lname, plist))
        if not lines:
            eps = re.findall(r'href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>\s*([^<]{1,40}?)\s*<', html)
            plist = ["%s$%s|%s|%s" % (e[3].strip() or ("第%d集" % (j + 1)), e[0], e[1], e[2]) for j, e in enumerate(eps)]
            if plist:
                lines = [("默认线路", plist)]
        vod = {
            "vod_id": vid, "vod_name": name, "vod_pic": pic,
            "vod_remarks": meta.get("vod_remarks", "") or "",
            "type_name": meta.get("type_name") or "影视",
            "vod_actor": meta.get("vod_actor", ""), "vod_director": meta.get("vod_director", ""),
            "vod_area": meta.get("vod_area", ""), "vod_year": meta.get("vod_year", ""),
            "vod_content": intro,
            "vod_play_from": "$$$".join(l[0] for l in lines),
            "vod_play_url": "$$$".join("#".join(l[1]) for l in lines),
        }
        return {"list": [vod]}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, ids, vipFlags=None, *args, **kwargs):
        idv = ids if isinstance(ids, str) else str(ids)
        parts = re.findall(r"\d+", idv)
        if len(parts) >= 3:
            vid, line, ep = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            vid, line, ep = parts[0], parts[1], "0"
        elif len(parts) == 1:
            vid, line, ep = parts[0], "0", "0"
        else:
            return {"parse": 0, "url": idv, "header": {"User-Agent": self.headers["User-Agent"]}, "jx": 0}
        play_url = "%s/play/%s-%s-%s.html" % (self.base_url, vid, line, ep)
        html = self._req(play_url, referer="%s/movie/index%s.html" % (self.base_url, vid))
        m = re.search(r'var now="([^"]+)"', html)
        real = (m.group(1).strip() if m else "")
        pn = re.search(r'var pn="([^"]*)"', html)
        if not real:
            m2 = re.search(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", html)
            real = m2.group(0) if m2 else ""
        header = {"User-Agent": self.headers["User-Agent"], "Referer": play_url}
        if real.startswith("http"):
            return {"parse": 0, "url": real, "header": header, "jx": 0, "msg": (pn.group(1) if pn else "")}
        return {"parse": 1, "url": play_url, "header": header, "jx": 0, "msg": ""}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=0, pg="1", *args, **kwargs):
        wd = quote(str(key))
        p = int(pg) if str(pg).isdigit() else 1
        html = ""
        items = []
        for path in ("/search.php?searchword=%s&page=%d" % (wd, p), "/search.php?q=%s&page=%d" % (wd, p)):
            html = self._req(self.base_url + path)
            items = self._parse_list(html)
            if items:
                break
        return {"list": items, "page": str(p), "pagecount": self._pagecount(html) if items else 1, "limit": len(items), "total": len(items)}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|avi)([?#]|$)", str(url), re.I)) or str(url).startswith("http")

    def localProxy(self, param=None, *args, **kwargs):
        return []
