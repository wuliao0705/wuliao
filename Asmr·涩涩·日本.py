# -*- coding: utf-8 -*-
"""
japaneseasmr.com TVBox 爬虫（封面修复 + CDN 防盗链代理）
站点: https://japaneseasmr.com/
类型: WordPress 博客 (ASMR 音频)
修复:
  1. 封面提取：优先 og:image，其次 lazy 图片 data-src
  2. 图片代理：localProxy 携带 Referer 绕过 Cloudflare 403
"""
import re
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
from urllib.parse import quote, unquote, urlparse, parse_qs

HOST = "https://japaneseasmr.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": HOST + "/",
}


class Spider:
    def __init__(self):
        self.host = HOST
        self.name = "JapaneseASMR"
        self._categories = None

    # ── 工具方法 ──
    def _fetch(self, url):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            print("[JASMR] fetch error: %s" % e)
            return ""

    def _parse_posts(self, html):
        """解析文章列表（首页、分类、搜索）"""
        posts = []
        # 列表页封面：img.lazy 的 data-src
        pattern = re.compile(
            r'<li[^>]*class="[^"]*site-archive-post[^"]*"[^>]*>'
            r'.*?<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>'
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
            r'.*?<div[^>]*class="[^"]*op-square[^"]*"[^>]*>'
            r'.*?<img[^>]*class="[^"]*lazy[^"]*"[^>]*data-src="([^"]+)"[^>]*>'
            r'.*?<p[^>]*class="[^"]*entry-excerpt[^"]*"[^>]*>(.*?)</p>',
            re.DOTALL
        )
        for m in pattern.finditer(html):
            url, title, img, excerpt = m.groups()
            # 使用代理协议，由 localProxy 处理防盗链
            pic_proxy = f"proxy://img?url={quote(img)}" if img else ""
            posts.append({
                "vod_id": url,
                "vod_name": title.strip(),
                "vod_pic": pic_proxy,
                "vod_remarks": re.sub(r"<[^>]+>", "", excerpt).strip()[:50],
            })

        # 备用匹配（万一结构有变）
        if not posts:
            pattern2 = re.compile(
                r'<a[^>]*href="([^"]+)"[^>]*>.*?<h2[^>]*>([^<]+)</h2>'
                r'.*?<img[^>]*class="[^"]*lazy[^"]*"[^>]*data-src="([^"]+)"',
                re.DOTALL
            )
            for m in pattern2.finditer(html):
                url, title, img = m.groups()
                pic_proxy = f"proxy://img?url={quote(img)}" if img else ""
                posts.append({
                    "vod_id": url,
                    "vod_name": title.strip(),
                    "vod_pic": pic_proxy,
                    "vod_remarks": "",
                })
        return posts

    def _extract_page_count(self, html):
        """提取总页数"""
        m = re.search(r'<a[^>]*class="page-numbers"[^>]*>(\d+)</a>.*?</nav>', html, re.DOTALL)
        if m:
            nums = re.findall(r'>(\d+)</a>', m.group(0))
            if nums:
                return max(int(n) for n in nums)
        if re.search(r'<a[^>]*class="next page-numbers"', html):
            return 2
        return 1

    def _get_categories(self):
        """从导航菜单提取分类"""
        if self._categories is not None:
            return self._categories
        html = self._fetch(self.host + "/")
        cats = []
        pattern = re.compile(
            r'<li[^>]*class="[^"]*menu-item[^"]*"[^>]*>'
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            re.DOTALL
        )
        for m in pattern.finditer(html):
            link, name = m.groups()
            if link.startswith(self.host + "/category/") or link.startswith(self.host + "/tag/"):
                slug = link.replace(self.host + "/category/", "").replace(self.host + "/tag/", "").strip("/")
                cats.append({"type_id": slug, "type_name": name.strip()})
        if not cats:
            cats = [
                {"type_id": "rating/sfw", "type_name": "SFW"},
                {"type_id": "rating/maniax", "type_name": "NSFW"},
                {"type_id": "rating/r-15", "type_name": "R-15"},
            ]
        self._categories = cats
        return cats

    # ── 详情页解析（封面优先 og:image，其次 lazy 图片 data-src） ──
    def _parse_detail(self, html):
        """从详情页提取信息"""
        result = {"title": "", "cover": "", "desc": "", "audio": ""}

        # 标题
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            result["title"] = m.group(1).strip()
        if not result["title"]:
            m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
            if m:
                result["title"] = m.group(1).strip()

        # 封面：优先 og:image
        m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
        if m:
            cover = m.group(1)
        else:
            # 备用：lazy 图片的 data-src
            m = re.search(r'<img[^>]*class="[^"]*lazy[^"]*"[^>]*data-src="([^"]+)"', html)
            if m:
                cover = m.group(1)
            else:
                # 再备用：video 标签的 poster
                m = re.search(r'<video[^>]*poster="([^"]+)"', html)
                if m:
                    cover = m.group(1)
                else:
                    cover = ""
        # 通过代理协议
        result["cover"] = f"proxy://img?url={quote(cover)}" if cover else ""

        # 简介
        m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html)
        if m:
            result["desc"] = m.group(1)
        if not result["desc"]:
            m = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                text = re.sub(r"<[^>]+>", "", m.group(1))
                result["desc"] = text[:200].strip()

        # 音频URL
        m = re.search(r'<audio[^>]*src="([^"]+)"', html)
        if m:
            result["audio"] = m.group(1)
        if not result["audio"]:
            m = re.search(r'<source[^>]*src="([^"]+\.mp3)"', html)
            if m:
                result["audio"] = m.group(1)
        if not result["audio"]:
            m = re.search(r'data-mp3="([^"]+\.mp3)"', html)
            if m:
                result["audio"] = m.group(1)
        if not result["audio"]:
            m = re.search(r'(https?://[^\s"\']+\.mp3)', html)
            if m:
                result["audio"] = m.group(1)
        if result["audio"] and not result["audio"].startswith("http"):
            result["audio"] = self.host + result["audio"]
        return result

    # ── TVBox API ──
    def homeContent(self, filter=None):
        cats = self._get_categories()
        return {"class": cats}

    def homeVideoContent(self):
        html = self._fetch(self.host + "/")
        posts = self._parse_posts(html)
        return {"list": posts[:20]}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        pg = int(pg or 1)
        if tid.startswith("rating/") or "/" in tid:
            base = "/category/" + tid + "/"
        elif tid.startswith("tag/"):
            base = "/tag/" + tid.replace("tag/", "") + "/"
        else:
            base = "/category/" + tid + "/"
        url = self.host + base + ("page/" + str(pg) + "/" if pg > 1 else "")
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "total": 0}
        posts = self._parse_posts(html)
        pagecount = self._extract_page_count(html)
        return {"list": posts, "page": pg, "pagecount": pagecount, "total": pagecount * 24}

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        url = ids[0] if ids[0].startswith("http") else self.host + ids[0]
        html = self._fetch(url)
        if not html:
            return {"list": []}
        info = self._parse_detail(html)
        play_url = f"正片${info['audio']}" if info["audio"] else ""
        vod = {
            "vod_id": url,
            "vod_name": info["title"] or url,
            "vod_pic": info["cover"],
            "vod_remarks": "",
            "vod_content": info["desc"],
            "vod_play_from": "音频",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg=1):
        pg = int(pg or 1)
        url = self.host + "/?s=" + quote(key) + ("&paged=" + str(pg) if pg > 1 else "")
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "total": 0}
        posts = self._parse_posts(html)
        pagecount = self._extract_page_count(html)
        return {"list": posts, "page": pg, "pagecount": pagecount, "total": pagecount * 24}

    def playerContent(self, flag, id, vipFlags=None):
        if not id:
            return {"parse": 0, "url": "", "header": {}}
        if "$" in id:
            real_url = id.split("$", 1)[-1]
        else:
            real_url = id
        if not real_url.startswith("http"):
            real_url = self.host + real_url
        if real_url.endswith((".mp3", ".m4a", ".wav", ".ogg")):
            return {
                "parse": 0,
                "url": real_url,
                "header": {"Referer": self.host + "/", "User-Agent": HEADERS["User-Agent"]},
            }
        else:
            html = self._fetch(real_url)
            if html:
                info = self._parse_detail(html)
                if info["audio"]:
                    return {
                        "parse": 0,
                        "url": info["audio"],
                        "header": {"Referer": self.host + "/", "User-Agent": HEADERS["User-Agent"]},
                    }
            return {"parse": 1, "url": real_url, "header": {"Referer": self.host + "/"}}

    # ════════════════════════════════════════════════════════════
    # 🔧 图片代理 (解决 Cloudflare 403)
    # ════════════════════════════════════════════════════════════
    def localProxy(self, param):
        """
        TVBox 调用 localProxy 处理 proxy:// 协议
        param 可能包含:
          - {"url": "proxy://img?url=encoded_url"}
          - {"url": "http://...", "referer": "..."}  (直接代理)
        """
        url = param.get("url", "")
        if not url:
            return [404, "text/plain", b""]

        # 解析真实 URL
        if url.startswith("proxy://"):
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            real_url = qs.get("url", [""])[0]
            if not real_url:
                return [404, "text/plain", b""]
        else:
            real_url = url

        # 强制使用站点首页作为 Referer
        referer = param.get("referer", self.host + "/")
        headers = {
            "Referer": referer,
            "User-Agent": HEADERS["User-Agent"],
        }

        try:
            req = urllib.request.Request(real_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
                ctype = resp.headers.get("Content-Type", "")
                if not ctype or "text/html" in ctype:
                    # 根据扩展名补充 MIME
                    if real_url.lower().endswith((".png", ".webp")):
                        ctype = "image/png" if "png" in real_url else "image/webp"
                    elif real_url.lower().endswith((".jpg", ".jpeg")):
                        ctype = "image/jpeg"
                    elif real_url.lower().endswith(".gif"):
                        ctype = "image/gif"
                    else:
                        ctype = "image/jpeg"
                return [200, ctype, content]
        except Exception as e:
            print("[JASMR] proxy error: %s" % e)
            # 透明 1x1 GIF 占位图
            gif = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
            return [200, "image/gif", gif]

    # ── 其他必须方法 ──
    def getName(self):
        return self.name

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(mp3|m4a|wav|ogg|m3u8|mp4)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def getHomeContent(self, filter=True):
        return self.homeContent(filter)

    def getDependence(self):
        return []


# ── 实例化 ──
spider = Spider()