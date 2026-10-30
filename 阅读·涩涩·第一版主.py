# -*- coding: utf-8 -*-
# 第一版主网 TVBox 小说爬虫（精选 + 全部书库 + 章节正序 + 全部分页合并）
# 适配站点：https://m.diyibanzhu5.online

import sys
import re
import json
import time
import urllib.parse
from urllib.parse import urljoin, quote

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ---------- 兼容基类 ----------
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


# ---------- 常量 ----------
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE_URL = "https://m.diyibanzhu5.online"


class Spider(BaseSpider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = BASE_URL
        self.session = None
        self._init_urllib_fallback()
        self._cache = {}
        self._cache_time = {}
        self._page_prefix_cache = {}

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

    def _fetch_html(self, url, data=None, method="GET"):
        try:
            if self.session:
                if method.upper() == "POST":
                    resp = self.session.post(url, data=data, timeout=15)
                else:
                    resp = self.session.get(url, timeout=15)
                if resp.status_code == 200:
                    if 'charset=gbk' in resp.text.lower() or 'charset=gb2312' in resp.text.lower():
                        resp.encoding = 'gbk'
                    else:
                        resp.encoding = 'utf-8'
                    return resp.text
            elif self._urllib:
                if method.upper() == "POST":
                    data_bytes = urllib.parse.urlencode(data).encode('utf-8')
                    req = self._urllib.Request(url, data=data_bytes, headers={"User-Agent": UA, "Referer": self.host + "/"})
                else:
                    req = self._urllib.Request(url, headers={"User-Agent": UA, "Referer": self.host + "/"})
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=15) as resp:
                    raw = resp.read()
                    for enc in ('utf-8', 'gbk', 'gb2312'):
                        try:
                            return raw.decode(enc)
                        except:
                            continue
                    return raw.decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"[第一版主] fetch error: {e}")
        return ""

    def getDependence(self):
        return []

    def getName(self):
        return "第一版主网"

    def init(self, extend=""):
        self.setExtendInfo(extend)
        if requests:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
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
        return False

    def manualVideoCheck(self):
        return False

    # ==================== 首页分类 ====================
    def homeContent(self, filter=False):
        classes = [
            {"type_id": "book", "type_name": "📚 全部书库"},
        ]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        """首页推荐 = 全部书库第一页（最新更新）"""
        html = self._fetch_html(self.host + "/book/index.html")
        if not html:
            return {"list": []}
        items = self._parse_book_list(html)
        return {"list": items[:20]}

    # ==================== 分类列表（带筛选） ====================
    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = self._safe_int(pg, 1)
        page_size = 20

        if tid == "book":
            # 获取排序参数
            sort = extend.get("sort", "latest") if isinstance(extend, dict) else "latest"
            # 获取完结筛选（网站目前没有明确的完结/连载字段，暂时保留）
            status = extend.get("status", "all") if isinstance(extend, dict) else "all"

            return self._load_book_list(sort, page)

        return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

    # ==================== 加载书籍列表 ====================
    def _load_book_list(self, sort, page):
        """加载指定排序的书籍列表"""
        page = self._safe_int(page, 1)
        page_size = 20

        # 排序 URL 映射
        sort_map = {
            "latest": {"first": "/book/index.html", "prefix_key": "latest"},
            "hot": {"first": "/book/rate_1.html", "prefix_key": "hot"},
            "month": {"first": "/book/rate_2.html", "prefix_key": "month"},
            "new": {"first": "/book/rate_3.html", "prefix_key": "new"},
            "word": {"first": "/book/rate_4.html", "prefix_key": "word"},
        }

        if sort not in sort_map:
            sort = "latest"

        sort_info = sort_map[sort]
        if page == 1:
            url = f"{self.host}{sort_info['first']}"
        else:
            prefix = self._get_page_prefix(sort_info['prefix_key'])
            url = f"{self.host}/book/{prefix}_{page}.html"

        html = self._fetch_html(url)
        if not html:
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        items = self._parse_book_list(html)
        pagecount = self._extract_pagecount(html)
        if pagecount < page:
            pagecount = page

        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": pagecount * page_size,
        }

    def _get_page_prefix(self, key):
        """获取分页URL前缀"""
        if key in self._page_prefix_cache:
            return self._page_prefix_cache[key]

        url_map = {
            "latest": "/book/index.html",
            "hot": "/book/rate_1.html",
            "month": "/book/rate_2.html",
            "new": "/book/rate_3.html",
            "word": "/book/rate_4.html",
        }

        url = f"{self.host}{url_map.get(key, '/book/index.html')}"
        html = self._fetch_html(url)
        if not html:
            return "17111"

        # 从分页链接中提取前缀
        # 格式: /book/1_17116_2.html 或 /book/17111_2.html
        m = re.search(r'/book/([^_]+_\d+)_\d+\.html', html)
        if m:
            prefix = m.group(1)
        else:
            m = re.search(r'/book/(\d+)_\d+\.html', html)
            if m:
                prefix = m.group(1)
            else:
                prefix = "17111"

        self._page_prefix_cache[key] = prefix
        return prefix

    # ==================== 详情（章节正序） ====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        book_id = ids[0]
        m = re.search(r"(\d+)", book_id)
        if m:
            book_id = m.group(1)
        else:
            return {"list": []}

        detail_url = f"{self.host}/list/{book_id}.html"
        html = self._fetch_html(detail_url)
        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
        if not soup:
            return self._parse_detail_with_regex(html, book_id)

        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        pic = ""
        img_el = soup.select_one(".detail .left img")
        if not img_el:
            img_el = soup.select_one(".bookcover img")
        if img_el:
            pic = img_el.get("src", "")
            if pic and not pic.startswith("http"):
                pic = urljoin(self.host, pic)

        info_el = soup.select_one(".detail .right .info")
        author = ""
        kind = ""
        word_count = ""
        if info_el:
            info_text = info_el.get_text(strip=True)
            m = re.search(r"作者[：:]\s*([^\s，,、]+)", info_text)
            if m:
                author = m.group(1)
            m = re.search(r"类型[：:]\s*([^\s，,、]+)", info_text)
            if m:
                kind = m.group(1)
            m = re.search(r"字数[：:]\s*([0-9,]+)", info_text)
            if m:
                word_count = m.group(1)

        intro_el = soup.select_one(".book-intro .bd")
        intro = intro_el.get_text(strip=True) if intro_el else ""

        # ---------- 提取完整章节列表 ----------
        chapters = []
        seen_urls = set()

        chapter_divs = soup.select("div.chapter-list")
        target_div = chapter_divs[-1] if chapter_divs else None
        if not target_div:
            target_div = soup.select_one("div.chapter-list")
        if target_div:
            uls = target_div.select("ul.list")
            for ul in uls:
                for li in ul.find_all("li"):
                    a = li.find("a", href=re.compile(r"/view/\d+\.html"))
                    if not a:
                        continue
                    href = a.get("href", "")
                    full_url = urljoin(self.host, href)
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    name = a.get_text(strip=True)
                    if not name:
                        m = re.search(r"(\d+)", href)
                        if m:
                            name = f"第{m.group(1)}章"
                        else:
                            name = "章节"
                    chapters.append(f"{name}${full_url}")

        if not chapters:
            for a in soup.find_all("a", href=re.compile(r"/view/\d+\.html")):
                href = a.get("href", "")
                full_url = urljoin(self.host, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                name = a.get_text(strip=True)
                if not name:
                    m = re.search(r"(\d+)", href)
                    if m:
                        name = f"第{m.group(1)}章"
                    else:
                        name = "章节"
                chapters.append(f"{name}${full_url}")

        if not chapters:
            chapters = [f"{title}暂无章节$"]

        play_url = "#".join(chapters)

        vod = {
            "vod_id": book_id,
            "vod_name": title or "未命名",
            "vod_pic": pic,
            "vod_actor": author,
            "vod_remarks": f"{kind} | {word_count}字" if kind and word_count else kind or word_count or "",
            "vod_content": intro,
            "vod_play_from": "章节列表",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def _parse_detail_with_regex(self, html, book_id):
        title = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
        title = title.group(1).strip() if title else ""

        pic = re.search(r'<div[^>]*class="detail"[^>]*>.*?<div[^>]*class="left"[^>]*>.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
        pic = pic.group(1) if pic else ""
        if pic and not pic.startswith("http"):
            pic = urljoin(self.host, pic)

        author = re.search(r"作者[：:]\s*([^\s，,、]+)", html)
        author = author.group(1) if author else ""

        kind = re.search(r"类型[：:]\s*([^\s，,、]+)", html)
        kind = kind.group(1) if kind else ""

        word_count = re.search(r"字数[：:]\s*([0-9,]+)", html)
        word_count = word_count.group(1) if word_count else ""

        intro = re.search(r'<div[^>]*class="book-intro"[^>]*>.*?<div[^>]*class="bd"[^>]*>([\s\S]*?)</div>', html, re.DOTALL)
        intro = re.sub(r'<[^>]+>', '', intro.group(1)).strip() if intro else ""

        chapters = []
        seen = set()
        for href, name in re.findall(r'<a[^>]+href="(/view/\d+\.html)"[^>]*>([^<]+)</a>', html):
            full_url = urljoin(self.host, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            name = name.strip()
            if not name:
                m = re.search(r"(\d+)", href)
                if m:
                    name = f"第{m.group(1)}章"
                else:
                    name = "章节"
            chapters.append(f"{name}${full_url}")

        play_url = "#".join(chapters) if chapters else ""

        vod = {
            "vod_id": book_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": author,
            "vod_remarks": f"{kind} | {word_count}字" if kind and word_count else kind or word_count or "",
            "vod_content": intro,
            "vod_play_from": "章节列表",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ==================== 解析书库 ====================
    def _parse_book_list(self, html):
        if BeautifulSoup is None:
            return self._parse_book_list_regex(html)

        soup = BeautifulSoup(html, "html.parser")
        books = []
        seen = set()

        for li in soup.select("li.column-2"):
            name_a = li.select_one(".right .name")
            if not name_a:
                name_a = li.find("a", href=re.compile(r"/list/\d+\.html"))
            if not name_a:
                continue

            href = name_a.get("href", "")
            m = re.search(r"/list/(\d+)\.html", href)
            if not m:
                continue
            book_id = m.group(1)
            if book_id in seen:
                continue
            seen.add(book_id)

            name = name_a.get_text(strip=True)
            if not name:
                continue

            author = ""
            info_p = li.select_one(".info")
            if info_p:
                author_match = re.search(r"作者[：:]\s*([^\s，,、]+)", info_p.get_text(strip=True))
                if author_match:
                    author = author_match.group(1)

            update = ""
            update_a = li.select_one(".update a")
            if update_a:
                update = update_a.get_text(strip=True)

            date = ""
            date_span = li.select_one("span[style*='float:right']")
            if date_span:
                date = date_span.get_text(strip=True)

            remarks = ""
            if author:
                remarks = author
            if update:
                remarks = f"{remarks} | {update}" if remarks else update
            if date and not remarks:
                remarks = date

            books.append({
                "vod_id": book_id,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": remarks[:80],
            })

        if not books:
            books = self._parse_book_list_regex(html)

        return books

    def _parse_book_list_regex(self, html):
        books = []
        seen = set()
        pattern = r'<a[^>]+class="name"[^>]+href="(/list/(\d+)\.html)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html)
        for href, book_id, name in matches:
            if book_id in seen:
                continue
            seen.add(book_id)
            name = name.strip()
            if not name:
                continue
            author = ""
            author_match = re.search(r'作者[：:]\s*([^\s，,、]+)', html)
            if author_match:
                author = author_match.group(1)
            books.append({
                "vod_id": book_id,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": author,
            })
        return books

    def _extract_pagecount(self, html):
        end_match = re.search(r'<a[^>]+class="endPage"[^>]+href="[^"]*_(\d+)\.html"', html)
        if end_match:
            return int(end_match.group(1))
        nums = re.findall(r'href="[^"]*_(\d+)\.html"', html)
        if nums:
            return max(int(n) for n in nums)
        select_match = re.search(r'<select[^>]*>(.*?)</select>', html, re.DOTALL)
        if select_match:
            nums = re.findall(r'value="[^"]*_(\d+)\.html"', select_match.group(1))
            if nums:
                return max(int(n) for n in nums)
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            return int(m.group(1))
        return 1

    # ==================== 章节内容（合并所有分页） ====================
    def _fetch_full_chapter(self, first_page_url):
        full_content = ""
        chapter_title = ""
        visited = set()
        page_urls = set()
        page_urls.add(first_page_url)

        html = self._fetch_html(first_page_url)
        if not html:
            return "章节加载失败", ""

        soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None

        if not chapter_title:
            if soup:
                title_tag = soup.find("h1", class_="page-title")
                if title_tag:
                    chapter_title = title_tag.get_text(strip=True)
            if not chapter_title:
                title_match = re.search(r"<title>(.*?)</title>", html)
                if title_match:
                    chapter_title = title_match.group(1).strip()
            if not chapter_title:
                chapter_title = "章节正文"

        if soup:
            for a in soup.select("center.chapterPages a, .chapterPages a"):
                href = a.get("href", "")
                if href:
                    full_url = urljoin(first_page_url, href)
                    page_urls.add(full_url)

            for a in soup.select("#nr1 a"):
                href = a.get("href", "")
                if href and "view" in href and "_" in href:
                    full_url = urljoin(first_page_url, href)
                    page_urls.add(full_url)

        if len(page_urls) == 1:
            pattern = r'href="(.*?_(\d+)\.html)"'
            matches = re.findall(pattern, html)
            for href, page_num in matches:
                if href:
                    full_url = urljoin(first_page_url, href)
                    page_urls.add(full_url)

        def get_page_num(url):
            m = re.search(r"_(\d+)\.html$", url)
            if m:
                return int(m.group(1))
            return 0

        sorted_urls = sorted(list(page_urls), key=get_page_num)

        content = self._extract_content_from_html(html, soup)
        if content:
            full_content += content + "\n\n"

        for url in sorted_urls:
            if url == first_page_url:
                continue
            if url in visited:
                continue
            visited.add(url)

            page_html = self._fetch_html(url)
            if not page_html:
                continue
            page_soup = BeautifulSoup(page_html, "html.parser") if BeautifulSoup else None
            page_content = self._extract_content_from_html(page_html, page_soup)
            if page_content:
                full_content += page_content + "\n\n"

        full_content = self._clean_content(full_content)
        return chapter_title, full_content.strip()

    def _extract_content_from_html(self, html, soup=None):
        if soup is None:
            soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None

        if not soup:
            return self._extract_content_regex(html)

        nr1 = soup.select_one("#nr1")
        if nr1:
            for tag in nr1.select("center.chapterPages, .chapterPages, font[color='blue']"):
                tag.decompose()
            content = nr1.get_text("\n", strip=True)
            content = re.sub(r'最新章节请访问.*', '', content)
            if len(content) > 50:
                return content

        for selector in ["#content", ".content", ".chapter-content", ".novel-content", ".txt", ".text"]:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text("\n", strip=True)
                content = re.sub(r'最新章节请访问.*', '', content)
                if len(content) > 50:
                    return content

        body = soup.find("body")
        if body:
            for tag in body.find_all(["script", "style"]):
                tag.decompose()
            content = body.get_text("\n", strip=True)
            content = re.sub(r'最新章节请访问.*', '', content)
            if len(content) > 50:
                return content

        return ""

    def _extract_content_regex(self, html):
        match = re.search(r'<div[^>]*id="nr1"[^>]*>([\s\S]*?)</div>', html)
        if match:
            content = re.sub(r'<[^>]+>', '', match.group(1))
            content = re.sub(r'<br\s*/?>', '\n', content)
            content = self._clean_content(content)
            return content
        return ""

    def _clean_content(self, content):
        if not content:
            return ""
        patterns = [
            r'最新章节请访问.*',
            r'<center>.*?</center>',
            r'<br ?/?>\s*<br ?/?>',
            r'支持正版.*',
            r'如喜欢.*请支持正版',
            r'飞鸟VPN.*',
            r'DarkVPN.*',
            r'免费试用.*',
            r'立即体验.*',
            r'下载.*APP.*',
        ]
        for pat in patterns:
            content = re.sub(pat, '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'\n\s*\n', '\n', content)
        return content.strip()

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = id if id.startswith("http") else urljoin(self.host, id)
            if not url:
                result = {"title": "错误", "content": "无效的URL"}
                return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

            cache_key = f"chapter_{url}"
            if cache_key in self._cache:
                cache_time = self._cache_time.get(cache_key, 0)
                if time.time() - cache_time < 3600:
                    content = self._cache[cache_key]
                    result = {"title": "缓存章节", "content": content}
                    return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

            title, content = self._fetch_full_chapter(url)

            if not content or len(content) < 20:
                result = {"title": title or "章节", "content": "未找到章节内容，请检查网络"}
                return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

            self._cache[cache_key] = content
            self._cache_time[cache_key] = time.time()

            result = {"title": title or "章节", "content": content}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}
        except Exception as e:
            print(f"playerContent error: {e}")
            result = {"title": "错误", "content": f"异常: {str(e)}"}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick=False, pg="1"):
        page = self._safe_int(pg, 1)
        page_size = 20

        if not key or not key.strip():
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        search_url = f"{self.host}/wap.php?action=search"
        data = {
            "objectType": "2",
            "wd": key,
        }
        if page > 1:
            data["page"] = str(page)

        html = self._fetch_html(search_url, data=data, method="POST")
        if not html:
            url = f"{self.host}/wap.php?action=search&wd={quote(key)}&objectType=2"
            if page > 1:
                url += f"&page={page}"
            html = self._fetch_html(url)
            if not html:
                return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        items = self._parse_book_list(html)
        pagecount = self._extract_pagecount(html)
        if pagecount <= 1 and len(items) >= page_size:
            pagecount = page + 1
        if pagecount < page:
            pagecount = page

        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": page_size,
            "total": pagecount * page_size,
        }

    @staticmethod
    def _safe_int(val, default=1):
        try:
            v = int(str(val or "").strip())
            return v if v > 0 else default
        except:
            return default

    def action(self, action_str):
        return None

    def localProxy(self, param):
        return [404, "text/plain", b""]


# ---------- 测试 ----------
if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("爬虫名称:", spider.getName())

    print("\n--- 首页分类 ---")
    home = spider.homeContent()
    for c in home.get("class", []):
        print(f"  {c['type_id']}: {c['type_name']}")