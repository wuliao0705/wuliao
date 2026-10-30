#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
211dm (Omofun动漫) TVBox 爬虫 - 终极兼容版
Site: https://www.211dm.com/
特性：自动探测分类URL、封面直链、多级播放提取
"""
import re
import json
import base64
from urllib.parse import quote, unquote, urljoin

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class Spider:
    def __init__(self):
        self.host = "https://www.211dm.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update(self.headers)
            self.session.verify = False

    # ── helpers ────────────────────────────────────────────────
    def _get(self, url, **kwargs):
        if not self.session:
            raise RuntimeError("requests not available")
        r = self.session.get(url, timeout=15, **kwargs)
        r.raise_for_status()
        return r

    def _text(self, url):
        return self._get(url).text

    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", s)
        s = s.replace("&nbsp;", " ")
        return s.strip()

    @staticmethod
    def _abs(src, base):
        if not src:
            return ""
        src = src.strip()
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return urljoin(base, src)
        if src.startswith("http"):
            return src
        return urljoin(base, src)

    @staticmethod
    def _page(pg):
        try:
            p = int(pg)
        except Exception:
            p = 1
        return max(p, 1)

    # ── 分类页 URL（自动探测） ──────────────────────────────
    def _cat_url_candidates(self, tid, page=1):
        """生成可能的分类页 URL 列表，按优先级排列"""
        tid = str(tid).strip()
        if tid.startswith("type/"):
            tid = tid.split("/")[-1]
        m = re.search(r"(\d+)", tid)
        if m:
            tid = m.group(1)
        else:
            tid = "1"
        candidates = []
        # 格式1（修复版）：/type/{tid}.html  /type/{tid}-{page}.html
        if page == 1:
            candidates.append(f"{self.host}/type/{tid}.html")
        else:
            candidates.append(f"{self.host}/type/{tid}-{page}.html")
        # 格式2（最初版）：/show/{tid}-----------.html  /show/{tid}----------{page}.html
        if page == 1:
            candidates.append(f"{self.host}/show/{tid}-----------.html")
        else:
            candidates.append(f"{self.host}/show/{tid}----------{page}.html")
        # 格式3（备用）：/vodtype/{tid}.html
        if page == 1:
            candidates.append(f"{self.host}/vodtype/{tid}.html")
        else:
            candidates.append(f"{self.host}/vodtype/{tid}-{page}.html")
        return candidates

    def _fetch_category(self, tid, page=1):
        """尝试多个URL，返回第一个成功的HTML"""
        for url in self._cat_url_candidates(tid, page):
            try:
                html = self._text(url)
                if html and len(html) > 500:
                    print(f"[211dm] 分类页成功: {url}")
                    return html
            except Exception:
                continue
        return None

    def _search_url(self, keyword, page=1):
        k = quote(keyword)
        u = f"{self.host}/search/-------------.html?wd={k}"
        if page > 1:
            u += f"&page={page}"
        return u

    # ── 解析列表（封面直链） ──────────────────────────────────
    def _parse_list(self, html):
        if not BeautifulSoup:
            return self._parse_list_regex(html)
        soup = BeautifulSoup(html, "html.parser")
        items = []
        # 尝试多种容器选择器
        containers = soup.select("li.daFJ_dJJfFHa__gEI, li:has(.daFJ_dJJfFHa__gEI), .daFJ_dJJfFHa__gEI, .module-item, .vodlist-item")
        if not containers:
            containers = soup.select(".module-items .module-poster-item")
        for container in containers:
            a = container.select_one("a.daFJ_dJJfFHa__aAICe.lazyload[href]")
            if not a:
                a = container.select_one("a[href*='/anime/']")
            if not a:
                continue
            href = a.get("href", "").strip()
            if not href or not href.startswith("/anime/"):
                continue
            # 标题
            title_el = container.select_one("h4.title a, h4 a, .title a, .module-poster-item-title")
            title = ""
            if title_el:
                title = self._clean(title_el.get_text(" ", strip=True))
            if not title:
                title = a.get("title", "").strip()
            # 封面
            img = a.select_one("img")
            pic = (a.get("data-original") or a.get("data-src") or
                   a.get("data-lazy-src") or "")
            if not pic and img:
                pic = (img.get("data-original") or img.get("data-src") or
                       img.get("data-lazy-src") or img.get("src") or "")
            if not pic:
                style = a.get("style", "")
                bg = re.search(r"url\((?:['\"]?)([^'\")]+)", style, re.I)
                pic = bg.group(1) if bg else ""
            pic_abs = self._abs(pic, self.host) if pic else ""
            # 备注
            remark = ""
            for b in a.select("b"):
                t = self._clean(b.get_text(" ", strip=True))
                if t:
                    remark = t
                    break
            if not remark:
                note = container.select_one(".aaE_EaDE, .module-item-note, .vodlist-remarks")
                if note:
                    remark = self._clean(note.get_text(" ", strip=True))
            if href and title:
                items.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic_abs,
                    "vod_remarks": remark,
                })
        return items

    def _parse_list_regex(self, html):
        # 兼容两种模式的混合正则
        patterns = [
            r'<a[^>]+href="(/anime/[^"]+)"[^>]*>\s*<img[^>]+data-original="([^"]+)"[^>]*>.*?<h4[^>]*>.*?<a[^>]*>([^<]+)</a>.*?<span[^>]*>([^<]+)</span>',
            r'<a[^>]+href="(/anime/[^"]+)"[^>]*>\s*<img[^>]+data-original="([^"]+)"[^>]*>.*?<div class="title">([^<]+)</div>.*?<span class="remark">([^<]+)</span>',
        ]
        items = []
        for pattern in patterns:
            for m in re.finditer(pattern, html, re.S):
                if len(m.groups()) >= 3:
                    href, pic, title, *rest = m.groups()
                    remark = rest[0] if rest else ""
                    pic_abs = self._abs(pic, self.host)
                    items.append({
                        "vod_id": href,
                        "vod_name": self._clean(title),
                        "vod_pic": pic_abs,
                        "vod_remarks": self._clean(remark),
                    })
            if items:
                break
        return items

    # ── 提取总页数 ──────────────────────────────────────────────
    def _pagecount_from_html(self, html):
        if BeautifulSoup:
            soup = BeautifulSoup(html, "html.parser")
            pagination = soup.select_one(".daFJ_aFJe__aEge, .stui-page, .pagination")
            if pagination:
                num_el = pagination.select_one(".active.num a")
                if num_el:
                    txt = num_el.get_text(" ", strip=True)
                    m = re.search(r"(\d+)\s*/\s*(\d+)", txt)
                    if m:
                        return int(m.group(2))
                last = pagination.select_one("a:last-child")
                if last:
                    href = last.get("href", "")
                    m = re.search(r"/(\d+)---?\.html$", href)
                    if m:
                        return int(m.group(1))
        m = re.search(r"1\s*/\s*(\d+)", html)
        if m:
            return int(m.group(1))
        m = re.search(r"尾页.*?/(\d+)---?\.html", html)
        if m:
            return int(m.group(1))
        return 1

    # ── 解析详情（封面直链） ──────────────────────────────────
    def _parse_detail(self, html):
        if not BeautifulSoup:
            return self._parse_detail_regex(html)
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        title_el = soup.select_one("h1.h1_title, h1.title, .h1_title")
        if title_el:
            title = self._clean(title_el.get_text(" ", strip=True))
        cover = ""
        cover_el = soup.select_one(".daFJ_iJEdJHa__aAICe img, .video-cover img, .poster img")
        if cover_el:
            cover = cover_el.get("data-original") or cover_el.get("data-src") or cover_el.get("src") or ""
        if not cover:
            meta = soup.find("meta", property="og:image")
            if meta:
                cover = meta.get("content", "")
        cover_abs = self._abs(cover, self.host)
        desc = ""
        desc_el = soup.select_one(".detail-content, .desc.detail .detail-content, .desc.detail")
        if desc_el:
            desc = self._clean(desc_el.get_text("\n", strip=True))
        if not desc:
            meta = soup.find("meta", attrs={"name": "description"})
            if meta:
                desc = self._clean(meta.get("content", ""))
        director = ""
        actor = ""
        for item in soup.select(".data"):
            txt = self._clean(item.get_text(" ", strip=True))
            if txt.startswith("导演：") or txt.startswith("導演："):
                director = txt.split("：", 1)[-1].strip()
            elif txt.startswith("声优：") or txt.startswith("聲優："):
                actor = txt.split("：", 1)[-1].strip()
        tags = []
        for a in soup.select(".daFJ_dJJfFHa__cFAFeA a[href*='/search/'], .detail-tags a[href]"):
            t = self._clean(a.get_text(" ", strip=True))
            if t:
                tags.append(t)
        if not tags:
            for el in soup.select(".data"):
                txt = self._clean(el.get_text(" ", strip=True))
                if "类型：" in txt or "類型：" in txt:
                    parts = txt.split("：", 1)[-1]
                    for part in parts.split("/"):
                        part = part.strip()
                        if part:
                            tags.append(part)
                    break
        vod_from = []
        vod_url = []
        tabs = soup.select(".channel-tab li a")
        panes = soup.select(".tab-content .tab-pane")
        if tabs and panes:
            for idx, pane in enumerate(panes):
                ul = pane.select_one("ul.play-list-content")
                if not ul:
                    continue
                eps = []
                for li in ul.select("li.play-list-content-item a"):
                    href = li.get("href", "").strip()
                    name = self._clean(li.get_text(" ", strip=True))
                    if href and name:
                        eps.append(f"{name}${href}")
                if eps:
                    src_name = self._clean(tabs[idx].get_text(" ", strip=True)) if idx < len(tabs) else f"線路{idx+1}"
                    vod_from.append(src_name)
                    vod_url.append("#".join(eps))
        else:
            for ul in soup.select("ul.play-list-content"):
                eps = []
                for li in ul.select("li.play-list-content-item a"):
                    href = li.get("href", "").strip()
                    name = self._clean(li.get_text(" ", strip=True))
                    if href and name:
                        eps.append(f"{name}${href}")
                if eps:
                    vod_from.append("默认线路")
                    vod_url.append("#".join(eps))
        return {
            "title": title,
            "cover": cover_abs,
            "desc": desc,
            "director": director,
            "actor": actor,
            "tags": tags,
            "vod_from": vod_from,
            "vod_url": vod_url,
        }

    def _parse_detail_regex(self, html):
        title = ""
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            title = self._clean(m.group(1))
        cover = ""
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
        if m:
            cover = self._abs(m.group(1), self.host)
        desc = ""
        m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
        if m:
            desc = self._clean(m.group(1))
        director = ""
        actor = ""
        for m in re.finditer(r'<div class="data">([^<]+)</div>', html):
            txt = self._clean(m.group(1))
            if "导演：" in txt or "導演：" in txt:
                director = txt.split("：", 1)[-1].strip()
            elif "声优：" in txt or "聲優：" in txt:
                actor = txt.split("：", 1)[-1].strip()
        tags = []
        for m in re.finditer(r'<a[^>]+href="/search/[^"]+"[^>]*>([^<]+)</a>', html):
            t = self._clean(m.group(1))
            if t:
                tags.append(t)
        vod_from = []
        vod_url = []
        eps = []
        for m in re.finditer(r'<a[^>]+href="(/play/[^"]+)"[^>]*>([^<]*)</a>', html):
            href, name = m.groups()
            name = self._clean(name) or f"第{len(eps)+1}集"
            eps.append(f"{name}${href}")
        if eps:
            vod_from.append("默认线路")
            vod_url.append("#".join(eps))
        return {
            "title": title,
            "cover": cover,
            "desc": desc,
            "director": director,
            "actor": actor,
            "tags": tags,
            "vod_from": vod_from,
            "vod_url": vod_url,
        }

    # ── TVBox API ──────────────────────────────────────────────────
    def homeContent(self, filter=True):
        cats = [
            {"type_id": "1", "type_name": "日漫"},
            {"type_id": "2", "type_name": "国漫"},
            {"type_id": "5", "type_name": "动画"},
            {"type_id": "24", "type_name": "剧场"},
            {"type_id": "4", "type_name": "特摄"},
            {"type_id": "3", "type_name": "美漫"},
        ]
        filters = {c["type_id"]: [] for c in cats}
        return {"class": cats, "filters": filters}

    def homeVideoContent(self):
        try:
            html = self._text(self.host + "/")
            items = self._parse_list(html)
            pc = self._pagecount_from_html(html)
            return {"list": items[:30], "page": 1, "pagecount": pc, "limit": 24, "total": pc * 24}
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        pg = self._page(pg)
        html = self._fetch_category(tid, pg)
        if not html:
            print("[211dm] 所有分类页尝试失败")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        items = self._parse_list(html)
        pc = self._pagecount_from_html(html)
        return {"list": items, "page": pg, "pagecount": pc, "limit": 24, "total": pc * 24}

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        url = ids[0]
        if not url.startswith("http"):
            url = urljoin(self.host, url)
        try:
            html = self._text(url)
            d = self._parse_detail(html)
            vod = {
                "vod_id": url,
                "vod_name": d["title"] or url,
                "vod_pic": d["cover"],
                "vod_remarks": "",
                "vod_content": d["desc"],
                "vod_director": d["director"],
                "vod_actor": d["actor"],
                "vod_tags": "|".join(d["tags"]) if d["tags"] else "",
            }
            if d["vod_from"]:
                vod["vod_play_from"] = "$$$".join(d["vod_from"])
                vod["vod_play_url"] = "$$$".join(d["vod_url"])
            else:
                vod["vod_play_from"] = ""
                vod["vod_play_url"] = ""
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick=True, pg=1):
        pg = self._page(pg)
        try:
            url = self._search_url(key, page=pg)
            html = self._text(url)
            items = self._parse_list(html)
            pc = self._pagecount_from_html(html)
            return {"list": items, "page": pg, "pagecount": pc, "limit": 24, "total": pc * 24}
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}

    # ── 播放提取（增强） ──────────────────────────────────────
    def playerContent(self, flag, id, vipFlags=None):
        url = id if id.startswith("http") else urljoin(self.host, id)
        try:
            html = self._text(url)

            m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
            if not m:
                m = re.search(r'player_aaaa\s*=\s*(\{.*?\});', html, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    play_url = self._decrypt_player_url(data.get("url", ""), data.get("encrypt", 0))
                    if play_url and re.search(r"\.(m3u8|mp4)", play_url):
                        return {"parse": 0, "url": self._abs(play_url, self.host), "header": {}}
                except Exception:
                    pass

            m = re.search(r'var\s+now\s*=\s*["\']([^"\']+)["\']', html)
            if m:
                play_url = self._abs(m.group(1), self.host)
                if play_url and re.search(r'\.(m3u8|mp4)', play_url):
                    return {"parse": 0, "url": play_url, "header": {}}

            m = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', html, re.I)
            if m:
                play_url = self._abs(m.group(1), self.host)
                if play_url and re.search(r'\.(m3u8|mp4)', play_url):
                    return {"parse": 0, "url": play_url, "header": {}}
            m = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.I)
            if m:
                play_url = self._abs(m.group(1), self.host)
                if play_url and re.search(r'\.(m3u8|mp4)', play_url):
                    return {"parse": 0, "url": play_url, "header": {}}

            m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
            if m:
                iframe_url = self._abs(m.group(1), self.host)
                return self.playerContent(flag, iframe_url, vipFlags)

            m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
            if m:
                return {"parse": 0, "url": self._abs(m.group(1), self.host), "header": {}}
            m = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html)
            if m:
                return {"parse": 0, "url": self._abs(m.group(1), self.host), "header": {}}

            if re.search(r'\.(m3u8|mp4)', url):
                return {"parse": 0, "url": url, "header": {}}

            return {"parse": 1, "url": url, "header": {}}
        except Exception as e:
            print(f"[211dm] player error: {e}")
            return {"parse": 1, "url": url, "header": {}}

    def _decrypt_player_url(self, raw, encrypt=0):
        """MacCMS encrypt flag: 1 = percent-encoded, 2 = base64 + percent-encoded."""
        if not raw:
            return ""
        try:
            encrypt = int(encrypt or 0)
        except Exception:
            encrypt = 0
        try:
            if encrypt == 2:
                raw = base64.b64decode(raw).decode("utf-8", "replace")
            return unquote(raw)
        except Exception:
            return ""

    # ── localProxy（空实现） ──────────────────────────────────
    def localProxy(self, param):
        return [404, "text/plain", b""]

    # ── 其他方法 ──────────────────────────────────────────────────
    def getName(self):
        return "211dm"

    def init(self, extend=""):
        try:
            if extend:
                cfg = json.loads(extend)
                host = cfg.get("host") or cfg.get("Host") or cfg.get("HOST")
                ua = cfg.get("ua") or cfg.get("UA") or cfg.get("User-Agent")
                cookie = cfg.get("cookie") or cfg.get("Cookie")
                if host:
                    self.host = host.rstrip("/")
                if ua:
                    self.headers["User-Agent"] = ua
                if cookie:
                    self.headers["Cookie"] = cookie
                if self.session:
                    self.session.headers.update(self.headers)
                    self.session.verify = bool(cfg.get("verify", False))
        except Exception:
            pass

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def getHomeContent(self, filter=True):
        return self.homeContent(filter)

    def getDependence(self):
        return []


# ---------- 测试 ----------
if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("Spider name:", spider.getName())
    print("\n--- 首页分类 ---")
    home = spider.homeContent()
    for c in home["class"]:
        print(f"  {c['type_id']}: {c['type_name']}")
    print("\n--- 分类列表（日漫 第1页） ---")
    cat = spider.categoryContent("1", 1)
    print(f"列表数: {len(cat['list'])}, 总页数: {cat['pagecount']}")
    for item in cat['list'][:3]:
        print(f"  {item['vod_name']} ({item['vod_pic'][:50]}...)")
