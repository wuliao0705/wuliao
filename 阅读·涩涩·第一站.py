# -*- coding: utf-8 -*-
# 第一站小说 (diyizhan.cc) - TVBox 爬虫
# 完全模仿夜读/速读谷的结构，适配 PeekPro 自动归类到小说

import sys
import re
import json
import urllib.parse
from base.spider import Spider
from bs4 import BeautifulSoup
import requests
import time


class Spider(Spider):
    def getName(self):
        return "第一站小说"

    def init(self, extend=""):
        self.host = "https://www.diyizhan.cc"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        })
        self.class_map = {
            "all": "📚 全部书库",
            "allvisit": "🔥 总点击榜",
            "monthvisit": "📅 月点击榜",
            "weekvisit": "📈 周点击榜",
            "allvote": "⭐ 总推荐榜",
            "goodnum": "📖 收藏排行",
            "lastupdate": "🆕 最近更新",
            "postdate": "📚 新书上架",
            "size": "📏 字数排行",
            "xuanhuan": "👨‍👩‍👧‍👦 家庭乱伦",
            "xianxia": "💑 人妻女友",
            "dushi": "🏯 古典玄幻",
            "junshi": "🏙️ 都市生活",
            "wangyou": "🎓 学生校园",
            "kehuan": "⚔️ 强暴性虐",
            "lingyi": "👥 多人群交",
            "yanqing": "💚 绿帽主题",
            "qita": "📦 其他小说",
        }

    def _fix_url(self, url, base=None):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        if base:
            return urllib.parse.urljoin(base, url)
        return self.host + "/" + url

    def _fetch(self, url, timeout=30, retry=2):
        for attempt in range(retry):
            try:
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 200:
                    resp.encoding = "gbk"
                    return resp.text
                if resp.status_code in [403, 503, 429]:
                    time.sleep(2)
                    continue
            except Exception as e:
                time.sleep(2)
                continue
        return ""

    def _post_search(self, url, data, timeout=30):
        try:
            resp = self.session.post(url, data=data, timeout=timeout)
            if resp.status_code == 200:
                resp.encoding = "gbk"
                return resp.text
        except Exception:
            pass
        return ""

    # ==================== 首页分类 ====================

    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.class_map.items()]
        return {"class": classes}

    # ==================== 首页推荐（模仿夜读/速读谷，不包含 vod_play_url） ====================

    def homeVideoContent(self):
        try:
            html = self._fetch(self.host)
            if not html:
                return {"list": []}
            videos = self._extract_books(html)
            return {"list": videos[:30]}
        except Exception as e:
            print(f"首页异常: {e}")
            return {"list": []}

    def _extract_books(self, html):
        """从首页提取书籍（热门推荐 + 最近更新）"""
        soup = BeautifulSoup(html, "html.parser")
        videos = []
        seen = set()

        # 1. 从 #fengtui 提取热门推荐
        for item in soup.select("#fengtui .item"):
            a = item.find("a")
            if not a:
                continue
            href = a.get("href", "")
            id_match = re.search(r"/zhan/(\d+)/", href)
            vod_id = id_match.group(1) if id_match else ""
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)

            img = item.find("img")
            pic = img.get("src", "") if img else ""
            pic = self._fix_url(pic)

            dt = item.find("dt")
            name = dt.get_text(strip=True) if dt else f"书籍{vod_id}"

            dd = item.find("dd")
            intro = dd.get_text(strip=True) if dd else ""

            videos.append({
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "🔥 热门推荐",
                "vod_content": intro,
                # 故意不添加 vod_play_url
            })

        # 2. 从 #gengxin 提取最近更新（补充）
        for li in soup.select("#gengxin li"):
            a = li.find("a", href=re.compile(r"/zhan/\d+/"))
            if not a:
                continue
            href = a.get("href", "")
            id_match = re.search(r"/zhan/(\d+)/", href)
            vod_id = id_match.group(1) if id_match else ""
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)

            name = a.get_text(strip=True)
            s4 = li.find("span", class_="s4")
            author = s4.get_text(strip=True) if s4 else ""
            s3 = li.find("span", class_="s3")
            chapter = s3.get_text(strip=True) if s3 else ""

            remarks = f"{author} | {chapter}" if author and chapter else author or chapter or "最近更新"

            videos.append({
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": remarks,
                "vod_content": "",
                # 不添加 vod_play_url
            })

        return videos

    # ==================== 分类列表 ====================

    def _extract_books_from_list(self, html):
        soup = BeautifulSoup(html, "html.parser")
        videos = []
        seen = set()

        for book in soup.select(".bookbox"):
            h4 = book.select_one("h4.bookname a")
            if not h4:
                continue
            href = h4.get("href", "")
            id_match = re.search(r"/zhan/(\d+)/", href)
            vod_id = id_match.group(1) if id_match else ""
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)
            name = h4.get_text(strip=True)
            if not name:
                name = f"书籍{vod_id}"

            author_el = book.select_one(".author:first-child")
            author = author_el.get_text(strip=True).replace("作者：", "") if author_el else ""

            intro_el = book.select_one(".update")
            intro = intro_el.get_text(strip=True).replace("简介：", "") if intro_el else ""

            img_el = book.find("img")
            pic = img_el.get("src", "") if img_el else ""

            videos.append({
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": author,
                "vod_content": intro,
            })

        if not videos:
            for li in soup.select("#gengxin li, #zuixin li"):
                a = li.find("a", href=re.compile(r"/zhan/\d+/"))
                if not a:
                    continue
                href = a.get("href", "")
                id_match = re.search(r"/zhan/(\d+)/", href)
                vod_id = id_match.group(1) if id_match else ""
                if not vod_id or vod_id in seen:
                    continue
                seen.add(vod_id)
                name = a.get_text(strip=True)
                s4 = li.find("span", class_="s4")
                author = s4.get_text(strip=True) if s4 else ""
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": name,
                    "vod_pic": "",
                    "vod_remarks": author,
                    "vod_content": "",
                })

        return videos

    def _extract_pagecount(self, html):
        soup = BeautifulSoup(html, "html.parser")
        max_page = 1
        for a in soup.select("a"):
            href = a.get("href", "")
            if "尾页" in a.get_text():
                m = re.search(r"[-_](\d+)\.html$", href)
                if m:
                    try:
                        return int(m.group(1))
                    except:
                        pass
            m = re.search(r"[-_](\d+)\.html", href)
            if m:
                try:
                    num = int(m.group(1))
                    if num > max_page:
                        max_page = num
                except:
                    pass
        m = re.search(r"共\s*(\d+)\s*页", html)
        if m:
            try:
                return int(m.group(1))
            except:
                pass
        return max_page

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1

        if tid == "all":
            url = f"{self.host}/all-{pg}.html" if pg > 1 else f"{self.host}/all.html"
        elif tid in ["allvisit", "monthvisit", "weekvisit", "allvote", "goodnum", "lastupdate", "postdate", "size"]:
            if pg > 1:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
            url = f"{self.host}/{tid}.html"
        elif tid in ["xuanhuan", "xianxia", "dushi", "junshi", "wangyou", "kehuan", "lingyi", "yanqing", "qita"]:
            url = f"{self.host}/{tid}.html" if pg <= 1 else f"{self.host}/{tid}-{pg}.html"
        else:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_books_from_list(html)
        pagecount = self._extract_pagecount(html)
        if pagecount <= 1 and len(videos) >= 15:
            pagecount = pg + 1
        if pagecount < pg:
            pagecount = pg

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    # ==================== 详情页 ====================

    def detailContent(self, ids):
        vod_id = ids[0]
        if "/zhan/" in vod_id:
            id_match = re.search(r"/zhan/(\d+)/", vod_id)
            if id_match:
                vod_id = id_match.group(1)

        url = f"{self.host}/zhan/{vod_id}/"
        html = self._fetch(url)
        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.select_one("h1.booktitle")
        title = title_el.get_text(strip=True) if title_el else ""

        img_el = soup.select_one(".bookcover img")
        pic = img_el.get("src", "") if img_el else ""
        pic = self._fix_url(pic)
        if not pic:
            img_el = soup.select_one(".bookintro img")
            pic = img_el.get("src", "") if img_el else ""
            pic = self._fix_url(pic)

        author_el = soup.select_one(".booktag a.red")
        author = author_el.get_text(strip=True) if author_el else ""

        intro_el = soup.select_one(".bookintro")
        intro = intro_el.get_text(strip=True) if intro_el else ""

        base_url = f"{self.host}/zhan/{vod_id}/"
        chapters = []
        seen = set()

        for a in soup.select("dl.book.chapterlist dd a"):
            href = a.get("href", "")
            name = a.get_text(strip=True)
            if not name:
                name = href.split("/")[-1].replace(".html", "")
            if any(kw in name for kw in ["上一章", "下一章", "返回", "目录", "首页", "查看全部章节", "展开", "收起"]):
                continue
            full_url = self._fix_url(href, base=base_url)
            if full_url and full_url not in seen:
                seen.add(full_url)
                chapters.append(f"{name}${full_url}")

        if not chapters:
            for a in soup.select(".chapterlist dd a"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if not name or any(kw in name for kw in ["上一章", "下一章", "返回", "目录", "首页", "查看全部章节", "展开", "收起"]):
                    continue
                full_url = self._fix_url(href, base=base_url)
                if full_url and full_url not in seen:
                    seen.add(full_url)
                    chapters.append(f"{name}${full_url}")

        chapters.reverse()

        play_url = "#".join(chapters) if chapters else f"阅读全文$/{vod_id}/"

        content = ""
        if author:
            content += f"作者: {author}\n"
        if intro:
            content += intro

        return {
            "list": [{
                "vod_id": vod_id,
                "vod_name": title or "未命名",
                "vod_pic": pic,
                "vod_content": content,
                "vod_play_from": "第一站",
                "vod_play_url": play_url
            }]
        }

    # ==================== 正文提取 ====================

    def _extract_content(self, soup):
        for selector in [".readcontent", "#content", ".content", "#nr", "#nr1", ".txt", ".chapter-content", ".novel-content"]:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text("\n", strip=True)
                if len(content) > 50:
                    return content
        body = soup.find("body")
        if body:
            for tag in body.find_all(["script", "style"]):
                tag.decompose()
            content = body.get_text("\n", strip=True)
            if len(content) > 50:
                return content
        return ""

    def _fetch_full_chapter(self, first_page_url):
        full_content = ""
        chapter_title = ""
        current_url = first_page_url
        visited = set()
        max_pages = 500

        while current_url and len(visited) < max_pages:
            if current_url in visited:
                break
            visited.add(current_url)

            html = self._fetch(current_url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")

            if not chapter_title:
                title_tag = soup.find("h1") or soup.find("h2") or soup.find("h3")
                if title_tag:
                    chapter_title = title_tag.get_text(strip=True)
                if not chapter_title:
                    title_match = re.search(r"<title>(.*?)</title>", html)
                    if title_match:
                        chapter_title = title_match.group(1).strip()
                if not chapter_title:
                    chapter_title = "章节正文"

            content = self._extract_content(soup)
            if content:
                full_content += content + "\n\n"

            next_url = None
            link_next = soup.select_one("#linkNext")
            if link_next:
                href = link_next.get("href", "")
                if href and href != "#":
                    next_url = self._fix_url(href, base=current_url)

            if not next_url:
                for a in soup.find_all("a"):
                    text = a.get_text(strip=True)
                    if "下一页" in text or "下页" in text:
                        href = a.get("href", "")
                        if href and href != "#":
                            next_url = self._fix_url(href, base=current_url)
                            break

            if not next_url:
                break

            cur_filename = current_url.split("/")[-1]
            next_filename = next_url.split("/")[-1]
            m_cur = re.search(r'(\d+)', cur_filename)
            m_next = re.search(r'(\d+)', next_filename)
            if m_cur and m_next:
                cur_num = int(m_cur.group(1))
                next_num = int(m_next.group(1))
                if next_num > cur_num + 1 or (next_num > cur_num and '-' not in next_filename):
                    break

            current_url = next_url

        full_content = re.sub(r'\n\s*\n', '\n\n', full_content)
        return chapter_title, full_content.strip()

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = id if id.startswith("http") else self._fix_url(id)
            if not url:
                result = {"title": "错误", "content": "无效的URL"}
                return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

            title, content = self._fetch_full_chapter(url)

            if not content or len(content) < 20:
                result = {"title": title or "章节", "content": "未找到章节内容，请检查网络"}
                return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

            result = {"title": title or "章节", "content": content}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}
        except Exception as e:
            result = {"title": "错误", "content": f"异常: {str(e)}"}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if pg else 1
        search_url = f"{self.host}/modules/article/search.php"
        data = {"searchkey": key}
        html = self._post_search(search_url, data)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_books_from_list(html)
        pagecount = self._extract_pagecount(html)
        if pagecount <= 1 and len(videos) >= 15:
            pagecount = pg + 1
        if pagecount < pg:
            pagecount = pg

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        if self.session:
            self.session.close()

    def localProxy(self, param):
        return None