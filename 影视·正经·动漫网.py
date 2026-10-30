# -*- coding: utf-8 -*-
# Anime7 (anime7.top) TVBox 爬虫（翻页修复版）
# 基于苹果 CMS 风格 SSR HTML 解析
# 功能：首页、分类列表（翻页）、详情、播放、搜索

import sys
import re
import json
import base64
from urllib.parse import urljoin, quote, unquote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
BASE_URL = "https://anime7.top"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE_URL + "/",
}

# 分类映射（从导航提取）
CATEGORY_MAP = {
    "4": "动漫",
    "29": "日韩动漫",
    "38": "剧场版",
    "37": "僧侣番",
    "28": "国产动漫",
    "31": "欧美动漫",
    "30": "港台动漫",
}
MAIN_TIDS = list(CATEGORY_MAP.keys())


class Spider(BaseSpider):
    def __init__(self):
        self.host = BASE_URL
        self.session = None
        self._init_session()

    def _init_session(self):
        if requests:
            self.session = requests.Session()
            self.session.headers.update(HEADERS)
        else:
            self.session = None

    def _fetch(self, url, params=None):
        if not self.session:
            return ""
        try:
            r = self.session.get(url, params=params, timeout=20)
            r.encoding = "utf-8"
            return r.text if r.status_code == 200 else ""
        except Exception as e:
            print(f"[anime7] 请求失败: {e}")
            return ""

    def _clean(self, text):
        return re.sub(r'\s+', ' ', text).strip() if text else ""

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return urljoin(self.host, url)
        if url.startswith("http"):
            return url
        return urljoin(self.host, "/" + url)

    def getName(self):
        return "Anime7动漫"

    def init(self, extend=""):
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(cfg, dict) and cfg.get("host"):
                    self.host = cfg["host"].rstrip("/")
                    self.session.headers["Referer"] = self.host + "/"
            except:
                pass

    def destroy(self):
        if self.session:
            try:
                self.session.close()
            except:
                pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|webm|flv)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    # ========== 首页分类 ==========
    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name} for tid, name in CATEGORY_MAP.items()]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        # 获取首页“本月热播”列表
        html = self._fetch(self.host + "/")
        if not html:
            return {"list": []}
        items = []
        if BeautifulSoup:
            soup = BeautifulSoup(html, "html.parser")
            for section in soup.find_all("div", class_="hl-rb-vod"):
                title_elem = section.find("h2", class_="hl-rb-title")
                if title_elem and "本月热播" in title_elem.get_text():
                    ul = section.find("ul", class_="hl-vod-list")
                    if ul:
                        for li in ul.find_all("li", class_="hl-list-item"):
                            a = li.find("a", class_="hl-item-thumb")
                            if not a:
                                continue
                            href = a.get("href")
                            pic = a.get("data-original") or a.get("src") or ""
                            title_el = li.find("div", class_="hl-item-title")
                            if title_el:
                                a_title = title_el.find("a")
                                title = a_title.text.strip() if a_title else ""
                            else:
                                title = ""
                            remarks_el = li.find("span", class_="remarks")
                            remarks = remarks_el.text.strip() if remarks_el else ""
                            if href and title:
                                items.append({
                                    "vod_id": href,
                                    "vod_name": self._clean(title),
                                    "vod_pic": self._fix_url(pic),
                                    "vod_remarks": self._clean(remarks)
                                })
                            if len(items) >= 20:
                                break
        else:
            pattern = r'<h2 class="hl-rb-title">.*?本月热播.*?</h2>.*?<ul class="hl-vod-list.*?>(.*?)</ul>'
            m = re.search(pattern, html, re.S)
            if m:
                list_html = m.group(1)
                li_pattern = r'<li class="hl-list-item.*?">.*?<a class="hl-item-thumb" href="([^"]+)" data-original="([^"]+)".*?<div class="hl-item-title">.*?<a[^>]*>([^<]+)</a>.*?<span class="remarks">([^<]+)</span>'
                for m2 in re.finditer(li_pattern, list_html, re.S):
                    href, pic, title, remarks = m2.groups()
                    items.append({
                        "vod_id": href,
                        "vod_name": self._clean(title),
                        "vod_pic": self._fix_url(pic),
                        "vod_remarks": self._clean(remarks)
                    })
        return {"list": items}

    # ========== 分类列表（分页修复版） ==========
    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = int(pg) if str(pg).isdigit() else 1
        # 分页 URL: /vod-type/{tid}-{page}/  (第1页为 /vod-type/{tid}/)
        if page == 1:
            url = f"{self.host}/vod-type/{tid}/"
        else:
            url = f"{self.host}/vod-type/{tid}-{page}/"
        print(f"[anime7] 请求分类页: {url}")
        html = self._fetch(url)
        if not html:
            print(f"[anime7] 获取页面失败: {url}")
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

        items = []
        if BeautifulSoup:
            soup = BeautifulSoup(html, "html.parser")
            ul = soup.find("ul", class_="hl-vod-list")
            if ul:
                for li in ul.find_all("li", class_="hl-list-item"):
                    a = li.find("a", class_="hl-item-thumb")
                    if not a:
                        continue
                    href = a.get("href")
                    pic = a.get("data-original") or a.get("src") or ""
                    title_el = li.find("div", class_="hl-item-title")
                    if title_el:
                        a_title = title_el.find("a")
                        title = a_title.text.strip() if a_title else ""
                    else:
                        title = ""
                    remarks_el = li.find("span", class_="remarks")
                    remarks = remarks_el.text.strip() if remarks_el else ""
                    if href and title:
                        items.append({
                            "vod_id": href,
                            "vod_name": self._clean(title),
                            "vod_pic": self._fix_url(pic),
                            "vod_remarks": self._clean(remarks)
                        })
                print(f"[anime7] 解析到 {len(items)} 条数据")
            else:
                print("[anime7] 未找到列表容器，尝试正则备用")
                li_pattern = r'<li class="hl-list-item.*?">.*?<a class="hl-item-thumb" href="([^"]+)" data-original="([^"]+)".*?<div class="hl-item-title">.*?<a[^>]*>([^<]+)</a>.*?<span class="remarks">([^<]+)</span>'
                for m in re.finditer(li_pattern, html, re.S):
                    href, pic, title, remarks = m.groups()
                    items.append({
                        "vod_id": href,
                        "vod_name": self._clean(title),
                        "vod_pic": self._fix_url(pic),
                        "vod_remarks": self._clean(remarks)
                    })
                print(f"[anime7] 正则解析到 {len(items)} 条数据")

            # 提取总页数
            pagecount = page
            pagination = soup.find("div", class_="hl-page-wrap")
            if pagination:
                max_page = page
                for a in pagination.find_all("a"):
                    try:
                        num = int(a.text.strip())
                        if num > max_page:
                            max_page = num
                    except:
                        pass
                # 检查“尾页”链接
                last_link = pagination.find("a", href=lambda x: x and "vod-type" in x and "-" in x and x.split("-")[-1].isdigit())
                if last_link:
                    try:
                        last_page = int(last_link.get("href").split("-")[-1])
                        if last_page > max_page:
                            max_page = last_page
                    except:
                        pass
                if max_page > page:
                    pagecount = max_page
                else:
                    # 从 hl-total 提取总条数
                    total_el = soup.find("script", string=re.compile(r"\$\.\(\.hl-total\)\.html\('(\d+)'\)"))
                    if total_el:
                        total_match = re.search(r"\$\.\(\.hl-total\)\.html\('(\d+)'\)", total_el.string)
                        if total_match:
                            total = int(total_match.group(1))
                            pagecount = (total + 19) // 20
                            print(f"[anime7] 从 hl-total 提取总条数: {total}, 总页数: {pagecount}")
                    else:
                        pagecount = page + 1 if len(items) >= 20 else page
            else:
                pagecount = page + 1 if len(items) >= 20 else page
            print(f"[anime7] 当前页: {page}, 总页数: {pagecount}")
        else:
            # 无 BeautifulSoup 降级
            li_pattern = r'<li class="hl-list-item.*?">.*?<a class="hl-item-thumb" href="([^"]+)" data-original="([^"]+)".*?<div class="hl-item-title">.*?<a[^>]*>([^<]+)</a>.*?<span class="remarks">([^<]+)</span>'
            for m in re.finditer(li_pattern, html, re.S):
                href, pic, title, remarks = m.groups()
                items.append({
                    "vod_id": href,
                    "vod_name": self._clean(title),
                    "vod_pic": self._fix_url(pic),
                    "vod_remarks": self._clean(remarks)
                })
            pagecount = page + 1 if len(items) >= 20 else page

        total = len(items) + (page - 1) * 20
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": total,
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        if not vod_id.startswith("/"):
            vod_id = "/" + vod_id
        if not vod_id.startswith("/vod-detail/"):
            vod_id = "/vod-detail/" + vod_id.lstrip("/")
        detail_url = self._fix_url(vod_id)
        html = self._fetch(detail_url)
        if not html:
            return {"list": []}

        if BeautifulSoup:
            soup = BeautifulSoup(html, "html.parser")
            title = ""
            h1 = soup.find("h1")
            if h1:
                title = self._clean(h1.text)
            if not title:
                og_title = soup.find("meta", property="og:title")
                if og_title:
                    title = self._clean(og_title.get("content", ""))
            pic = ""
            og_img = soup.find("meta", property="og:image")
            if og_img:
                pic = og_img.get("content", "")
            if not pic:
                img = soup.select_one(".hl-item-thumb img, .video-cover img")
                if img:
                    pic = img.get("src") or img.get("data-src") or ""
            pic = self._fix_url(pic)
            desc = ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                desc = meta_desc.get("content", "")
            if not desc:
                desc_el = soup.select_one(".hl-vod-content, .video-info-content")
                if desc_el:
                    desc = self._clean(desc_el.text)
            episodes = []
            play_list = soup.select_one(".hl-plays-list, .hl-play-source .hl-plays-list")
            if play_list:
                for a in play_list.find_all("a"):
                    ep_url = a.get("href")
                    ep_title = a.text.strip() or f"第{len(episodes)+1}集"
                    if ep_url:
                        episodes.append(f"{ep_title}${ep_url}")
            if not episodes:
                for a in soup.select(".hl-play-source a"):
                    ep_url = a.get("href")
                    ep_title = a.text.strip() or f"第{len(episodes)+1}集"
                    if ep_url:
                        episodes.append(f"{ep_title}${ep_url}")
        else:
            title = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            title = self._clean(title.group(1)) if title else ""
            pic = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            pic = self._fix_url(pic.group(1)) if pic else ""
            desc = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
            desc = self._clean(desc.group(1)) if desc else ""
            episodes = []
            for m in re.finditer(r'<a[^>]+href="(/vod-play/[^"]+)"[^>]*>([^<]*)</a>', html):
                ep_url, ep_title = m.groups()
                ep_title = ep_title.strip() or f"第{len(episodes)+1}集"
                episodes.append(f"{ep_title}${ep_url}")

        play_url = "#".join(episodes) if episodes else ""

        vod = {
            "vod_id": vod_id,
            "vod_name": title or "未知动漫",
            "vod_pic": pic,
            "vod_actor": "",
            "vod_director": "",
            "vod_area": "",
            "vod_year": "",
            "vod_remarks": "",
            "vod_content": desc,
            "vod_play_from": "Anime7",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags=None):
        headers = {"User-Agent": UA, "Referer": self.host + "/"}
        if not id:
            return {"parse": 0, "url": "", "header": headers}
        url = self._fix_url(str(id))
        if self.isVideoFormat(url):
            return {"parse": 0, "url": url, "header": headers}
        page_html = self._fetch(url)
        if not page_html:
            return {"parse": 0, "url": "", "header": headers}

        player = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*;?\s*</script>', page_html, re.S)
        if not player:
            player = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', page_html, re.S)
        if player:
            try:
                data = json.loads(player.group(1))
                media_url = data.get("url", "")
                encrypt = int(data.get("encrypt", 0) or 0)
                if encrypt == 1:
                    media_url = unquote(media_url)
                elif encrypt == 2:
                    media_url = unquote(base64.b64decode(media_url).decode("utf-8", "replace"))
                media_url = self._fix_url(media_url)
                if self.isVideoFormat(media_url):
                    return {"parse": 0, "url": media_url, "header": headers}
            except Exception:
                pass

        for pattern in (
            r'<video[^>]+src=["\']([^"\']+)',
            r'<source[^>]+src=["\']([^"\']+)',
            r'(https?://[^\s"\']+\.(?:m3u8|mp4)(?:\?[^\s"\']*)?)',
        ):
            match = re.search(pattern, page_html, re.I)
            if match:
                media_url = self._fix_url(match.group(1))
                if self.isVideoFormat(media_url):
                    return {"parse": 0, "url": media_url, "header": headers}
        iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)', page_html, re.I)
        if iframe:
            return {"parse": 1, "url": self._fix_url(iframe.group(1)), "header": headers}
        return {"parse": 1, "url": url, "header": headers}

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        url = self.host + "/vod-search/"
        params = {"wd": key, "page": page}
        html = self._fetch(url, params=params)
        if not html:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

        items = []
        if BeautifulSoup:
            soup = BeautifulSoup(html, "html.parser")
            ul = soup.find("ul", class_="hl-vod-list")
            if ul:
                for li in ul.find_all("li", class_="hl-list-item"):
                    a = li.find("a", class_="hl-item-thumb")
                    if not a:
                        continue
                    href = a.get("href")
                    pic = a.get("data-original") or a.get("src") or ""
                    title_el = li.find("div", class_="hl-item-title")
                    if title_el:
                        a_title = title_el.find("a")
                        title = a_title.text.strip() if a_title else ""
                    else:
                        title = ""
                    remarks_el = li.find("span", class_="remarks")
                    remarks = remarks_el.text.strip() if remarks_el else ""
                    if href and title:
                        items.append({
                            "vod_id": href,
                            "vod_name": self._clean(title),
                            "vod_pic": self._fix_url(pic),
                            "vod_remarks": self._clean(remarks)
                        })
        else:
            li_pattern = r'<li class="hl-list-item.*?">.*?<a class="hl-item-thumb" href="([^"]+)" data-original="([^"]+)".*?<div class="hl-item-title">.*?<a[^>]*>([^<]+)</a>.*?<span class="remarks">([^<]+)</span>'
            for m in re.finditer(li_pattern, html, re.S):
                href, pic, title, remarks = m.groups()
                items.append({
                    "vod_id": href,
                    "vod_name": self._clean(title),
                    "vod_pic": self._fix_url(pic),
                    "vod_remarks": self._clean(remarks)
                })

        pagecount = page + 1 if len(items) >= 20 else page
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": len(items) + (page - 1) * 20,
        }

    def localProxy(self, param):
        return [404, "text/plain", b""]

    def action(self, action_str):
        return None


# ---------- 测试 ----------
if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("爬虫名称:", spider.getName())

    print("\n--- 首页分类 ---")
    home = spider.homeContent()
    for c in home.get("class", []):
        print(f"  {c['type_id']}: {c['type_name']}")

    print("\n--- 首页推荐（本月热播） ---")
    rec = spider.homeVideoContent()
    print(f"推荐数: {len(rec.get('list', []))}")
    for item in rec.get('list', [])[:3]:
        print(f"  {item['vod_name']} ({item['vod_id']})")

    print("\n--- 分类列表（剧场版 第1页） ---")
    cat = spider.categoryContent("38", "1")
    print(f"列表数: {len(cat.get('list', []))}, 总页数: {cat.get('pagecount', 1)}")
    for item in cat.get('list', [])[:3]:
        print(f"  {item['vod_name']} ({item['vod_id']})")

    if cat.get('list'):
        vid = cat['list'][0]['vod_id']
        print(f"\n--- 详情 ID: {vid} ---")
        detail = spider.detailContent([vid])
        if detail.get('list'):
            vod = detail['list'][0]
            print(f"标题: {vod['vod_name']}")
            print(f"简介: {vod['vod_content'][:80]}...")
            play_url = vod['vod_play_url']
            if play_url:
                parts = play_url.split('#')
                print(f"剧集数: {len(parts)}")
                if parts:
                    first_ep = parts[0]
                    ep_url = first_ep.split('$')[1] if '$' in first_ep else first_ep
                    print(f"首集: {ep_url}")
                    player = spider.playerContent("", ep_url)
                    print(f"播放返回: parse={player.get('parse')}, url={player.get('url', '')[:80]}...")
