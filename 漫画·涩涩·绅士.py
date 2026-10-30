# -*- coding: utf-8 -*-
# 绅士漫画 (wnacg.com) TVBox Spider - 修复版
# 目标：https://www.wnacg.com/

import sys
import re
import json
import requests
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "绅士漫画"

    def init(self, extend=""):
        self.host = "https://www.wnacg.com"
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
        })
        # 分类映射（从站点导航提取）
        self.classes = [
            {"type_id": "index",      "type_name": "推荐"},
            {"type_id": "albums",     "type_name": "更新"},
            {"type_id": "ranking",    "type_name": "排行"},
            {"type_id": "cate_5",     "type_name": "同人志"},
            {"type_id": "cate_6",     "type_name": "单行本"},
            {"type_id": "cate_7",     "type_name": "杂志短篇"},
            {"type_id": "cate_19",    "type_name": "韩漫"},
            {"type_id": "cate_3",     "type_name": "Cosplay"},
            {"type_id": "cate_2",     "type_name": "CG画集"},
            {"type_id": "cate_37",    "type_name": "AI图集"},
            {"type_id": "cate_22",    "type_name": "3D漫画"},
            {"type_id": "cate_1",     "type_name": "汉化"},
            {"type_id": "cate_12",    "type_name": "日语"},
            {"type_id": "cate_16",    "type_name": "English"},
        ]

    def _fetch(self, url, headers=None):
        try:
            h = headers or self.session.headers
            resp = self.session.get(url, headers=h, timeout=15)
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            print(f"[请求] 失败: {e}")
            return ""

    def _fix_url(self, url):
        """修复URL格式：////host → https://host, //host → https://host"""
        if not url:
            return ""
        url = str(url).strip()
        if url.startswith("////"):
            return "https://" + url.lstrip("/")
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return url

    def _parse_comic_list(self, html):
        """解析列表页 - 兼容多种结构"""
        videos = []
        if not html:
            return videos
        soup = BeautifulSoup(html, "html.parser")

        # 策略1：.pic_box div（首页/分类页主要结构）
        items = []
        pic_boxes = soup.select(".pic_box")
        if pic_boxes:
            items = pic_boxes
            print(f"[解析] 策略1 (.pic_box): 找到 {len(items)} 个")
        else:
            # 策略2：ul.col_2 > li（搜索页/分类页结构）
            col_items = soup.select("ul.col_2 li, ul[class*='col'] li")
            if col_items:
                items = col_items
                print(f"[解析] 策略2 (ul li): 找到 {len(items)} 个")
            else:
                # 策略3：直接查找 a 标签含 photos-index-aid
                anchors = soup.select('a[href*="photos-index-aid-"]')
                if anchors:
                    # 包装成类似 pic_box 的结构
                    for a in anchors:
                        div = soup.new_tag("div")
                        div.attrs["class"] = ["pic_box"]
                        div.append(a)
                        items.append(div)
                    print(f"[解析] 策略3 (a标签): 找到 {len(items)} 个")

        for item in items:
            try:
                # 提取链接
                a_tag = item.find("a", href=re.compile(r"photos-index-aid-\d+\.html"))
                if not a_tag:
                    # 如果 item 本身就是 a 标签
                    if item.name == "a" and "photos-index-aid-" in item.get("href", ""):
                        a_tag = item
                    else:
                        continue
                href = a_tag.get("href", "")
                if not href:
                    continue

                # 封面图
                img = a_tag.find("img")
                pic = ""
                if img:
                    pic = img.get("src") or img.get("data-src") or ""
                    pic = self._fix_url(pic)

                # 标题
                title = a_tag.get("title", "")
                if not title:
                    # 从 li 的文本中提取
                    title = item.get_text(strip=True)
                    # 去掉已有的标题部分（如果 a 标签文本和父级重复）
                    a_text = a_tag.get_text(strip=True)
                    if a_text and len(a_text) < len(title):
                        title = a_text
                if not title:
                    title = href.replace("/photos-index-aid-", "").replace(".html", "")

                # 信息（图片数量、日期等）
                remark = ""
                info_div = item.find("div", class_="info")
                if info_div:
                    remark = info_div.get_text(strip=True)

                videos.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                })
            except Exception as e:
                print(f"[解析] 卡片失败: {e}")

        print(f"[解析] 共解析到 {len(videos)} 个漫画")
        return videos

    def _get_pagination(self, html):
        """提取分页信息"""
        soup = BeautifulSoup(html, "html.parser")
        max_page = 1
        for a in soup.select("a[href*='page']"):
            href = a.get("href", "")
            # 匹配 ?page=N 或 /page-N.html 或 -page-N. 格式
            m = re.search(r"page[-_]?(\d+)", href)
            if m:
                num = int(m.group(1))
                if num > max_page:
                    max_page = num
        return max_page

    def homeContent(self, filter=False):
        return {"class": self.classes}

    def homeVideoContent(self):
        """首页推荐 - 取最新更新部分"""
        html = self._fetch(self.host + "/")
        if not html:
            return {"list": []}
        videos = self._parse_comic_list(html)
        return {"list": videos[:20]}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        """分类列表"""
        try:
            pg = int(pg)
        except:
            pg = 1

        if tid == "index":
            url = self.host + "/"
        elif tid == "albums":
            url = self.host + "/albums.html"
        elif tid == "ranking":
            url = self.host + "/albums-favorite_ranking.html"
        elif tid.startswith("cate_"):
            cate_id = tid.replace("cate_", "")
            url = self.host + f"/albums-index-cate-{cate_id}.html"
        else:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        # 修复分页URL格式：/albums-index-page-{n}.html
        if tid == "albums":
            url = self.host + f"/albums-index-page-{pg}.html"
        elif pg > 1:
            if "?" in url:
                url += f"&page={pg}"
            else:
                url += f"?page={pg}"

        print(f"[分类] {tid} page={pg} -> {url}")
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

        videos = self._parse_comic_list(html)
        pagecount = self._get_pagination(html) or (pg + 1 if len(videos) >= 20 else pg)

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": pagecount * 20,
        }

    def detailContent(self, ids):
        """详情页 - 提取所有图片URL"""
        vid = ids[0] if isinstance(ids, list) else ids

        # 构建详情URL
        if not vid.startswith("http"):
            if not vid.startswith("/photos-index-aid-"):
                aid = vid.replace(".html", "")
                vid = f"/photos-index-aid-{aid}.html"
            url = self.host + vid
        else:
            url = vid

        print(f"[详情] 请求: {url}")
        html = self._fetch(url)
        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        # 标题：从<title>提取
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string
            # 去掉网站名后缀
            title = re.sub(r'\s*[-—|｜]\s*紳士漫畫.*$', '', title).strip()
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title.get("content", "")
        if not title:
            title = vid.split("/")[-1].replace(".html", "")

        # 封面：从详情页的第一张图片或og:image获取
        pic = ""
        og_img = soup.find("meta", property="og:image")
        if og_img:
            pic = self._fix_url(og_img.get("content", ""))
        if not pic:
            # 取gallary第一项
            first_img = soup.select_one(".gallary_item img")
            if first_img:
                pic = self._fix_url(first_img.get("src", ""))

        # 提取阅读分页链接
        # 格式: /photos-index-page-{n}-aid-{aid}.html
        aid_match = re.search(r"photos-index-aid-(\d+)", url)
        aid = aid_match.group(1) if aid_match else ""

        # 找所有分页链接
        page_links = []
        for a in soup.select('a[href*="photos-index-page-"]'):
            href = a.get("href", "")
            m = re.search(r"photos-index-page-(\d+)-aid-" + re.escape(aid) + r"\.html", href)
            if m:
                page_no = int(m.group(1))
                full_url = self._fix_url(href)
                page_links.append((page_no, full_url))

        # 去重并排序
        page_links = sorted(set(page_links), key=lambda x: x[0])
        max_page = page_links[-1][0] if page_links else 1

        print(f"[详情] 标题: {title[:40]}, 阅读页: {max_page} 页")

        # 获取第1页图片作为默认
        first_images = []
        self._extract_reader_images(html, first_images)

        # 构建集数
        episodes = []
        # 第1集 = 详情页本身
        if first_images:
            episodes.append(f"第1话$pics://{ '&&'.join(first_images)}")

        # 其他阅读页
        for page_no, page_url in page_links:
            if page_no == 1:
                continue
            page_html = self._fetch(page_url)
            if page_html:
                images = []
                self._extract_reader_images(page_html, images)
                if images:
                    episodes.append(f"第{page_no}话$pics://{ '&&'.join(images)}")

        print(f"[详情] 提取到 {len(first_images)} 张图片，共 {len(episodes)} 集")

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": "",
            "vod_play_from": "绅士漫画",
            "vod_play_url": "#".join(episodes) if episodes else f"全集$pics://{pic}",
        }
        return {"list": [vod]}

    def _extract_reader_images(self, html, output):
        """从reader页面提取图片URL"""
        if not html or "Attention Required" in html:
            return
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.select(".gallary_item img, .gallary_wrap img"):
            src = img.get("src") or ""
            if not src:
                continue
            src = self._fix_url(src)
            # 过滤掉非图片资源
            low = src.lower()
            if any(x in low for x in ("logo", "loading", "icon", "avatar", "banner", ".gif", "watch")):
                continue
            # 只保留qy0.ru的图片
            if "qy0.ru" not in low and "t4." not in low:
                continue
            if src not in output:
                output.append(src)

    def playerContent(self, flag, id, vipFlags=None):
        """播放"""
        headers = {
            "Referer": self.host + "/",
            "User-Agent": self.session.headers.get("User-Agent", "Mozilla/5.0"),
        }
        if not id:
            return {"parse": 0, "playUrl": "", "url": "", "header": headers}
        # id 格式: "第N话$pics://url1&&url2&&..." 或直接是 pics://...
        if "$" in id:
            url = id.split("$", 1)[1]
        else:
            url = id
        if url.startswith("pics://"):
            return {"parse": 0, "playUrl": "", "url": url, "header": headers}
        if re.search(r"\.(jpg|jpeg|png|webp|avif)", url, re.I):
            return {"parse": 0, "playUrl": "", "url": f"pics://{url}", "header": headers}
        return {"parse": 1, "url": url, "header": headers}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if pg else 1
        enc_key = quote(key)
        url = self.host + f"/q/?q={enc_key}&page={pg}"
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}
        videos = self._parse_comic_list(html)
        pagecount = self._get_pagination(html) or (pg + 1 if len(videos) >= 20 else pg)
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(videos),
            "total": pagecount * 20,
        }

    def isVideoFormat(self, url):
        return url and (url.startswith("pics://") or re.search(r"\.(jpg|png|webp)", url, re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        if self.session:
            self.session.close()

    def localProxy(self, param):
        return None
