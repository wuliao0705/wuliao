# -*- coding: utf-8 -*-
# 番茄动漫 (fqdm.cc) - TVBox/影视仓/PeekPro Python 爬虫
# CMS: MacCMS (觅知模板)
# 注意: 播放页 JS 混淆严重，建议返回播放页让 App 解析

import sys
import re
import json
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HOST = "http://www.fqdm.cc"

class Spider:
    def __init__(self):
        self.host = HOST
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": HOST + "/",
        })
        self.session.trust_env = False
        
        self.class_map = {
            "1": "🇯🇵 日韩动漫",
            "2": "🇨🇳 国产动漫",
            "3": "🇭🇰 港台动漫",
            "4": "🇺🇸 欧美动漫",
            "5": "🌍 动漫综合",
        }
    
    def getName(self):
        return "番茄动漫"
    
    def init(self, extend=""):
        pass
    
    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except:
            pass
        self.session = None
    
    def _fetch(self, url, timeout=15, retry=2):
        for i in range(retry + 1):
            try:
                r = self.session.get(url, timeout=timeout)
                if r.status_code == 200:
                    r.encoding = 'utf-8'
                    return r.text
                if i < retry:
                    import time
                    time.sleep(1)
            except:
                if i < retry:
                    import time
                    time.sleep(1)
        return ""
    
    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "http:" + url
        if url.startswith("/"):
            return self.host + url
        return url
    
    def homeContent(self, filter=False):
        result = {"class": []}
        for tid, tname in self.class_map.items():
            result["class"].append({
                "type_id": tid,
                "type_name": tname,
            })
        return result
    
    def homeVideoContent(self):
        try:
            html = self._fetch(self.host)
            if not html:
                return {"list": []}
            videos = self._parse_list(html)
            return {"list": videos[:20]}
        except Exception as e:
            print(f"[fqdm] homeVideoContent error: {e}")
            return {"list": []}
    
    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1
        url = f"{self.host}/index.php/vod/type/id/{tid}.html"
        if pg > 1:
            url = f"{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html"
        
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        
        videos = self._parse_list(html)
        pagecount = self._extract_pagecount(html, pg)
        
        # 智能判断分页
        if pagecount <= 1 and len(videos) >= 18:
            pagecount = pg + 1
        if pagecount < pg:
            pagecount = pg
        
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        }
    
    def _parse_list(self, html):
        videos = []
        seen = set()
        soup = BeautifulSoup(html, "html.parser")
        
        for a in soup.find_all('a', href=re.compile(r'/vod/detail/')):
            href = a.get('href', '')
            m = re.search(r'/id/(\d+)', href)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            
            title = a.get('title', '') or a.get_text(strip=True)
            title_el = a.find('div', class_=re.compile('title|name'))
            if title_el:
                title = title_el.get_text(strip=True)
            if not title:
                title = f"视频{vid}"
            
            pic = ''
            img = a.find('img')
            if img:
                pic = self._fix_url(img.get('data-original', '') or img.get('src', ''))
            
            remark = ''
            remark_el = a.find('span', class_=re.compile('remark|indexx|score'))
            if remark_el:
                remark = remark_el.get_text(strip=True)
            
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })
        
        return videos
    
    def _extract_pagecount(self, html, current):
        soup = BeautifulSoup(html, "html.parser")
        max_page = current
        for a in soup.find_all('a'):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            m = re.search(r'page/(\d+)', href)
            if m:
                try:
                    p = int(m.group(1))
                    if p > max_page:
                        max_page = p
                except:
                    pass
            if ("下一页" in text or "下页" in text) and href and not href.startswith('javascript'):
                max_page = current + 1
        return max_page
    
    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if pg else 1
        enc_key = quote(key)
        url = f"{self.host}/index.php/vod/search/wd/{enc_key}.html"
        if pg > 1:
            url += f"/page/{pg}.html"
        
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        
        videos = self._parse_list(html)
        pagecount = self._extract_pagecount(html, pg)
        
        if pagecount <= 1 and len(videos) >= 18:
            pagecount = pg + 1
        
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        }
    
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]
        
        url = f"{self.host}/index.php/vod/detail/id/{vid}.html"
        html = self._fetch(url)
        if not html:
            return {"list": []}
        
        soup = BeautifulSoup(html, "html.parser")
        
        # 标题
        title = ""
        h1 = soup.find('h1') or soup.find('h2')
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            meta = soup.find('meta', property='og:title')
            if meta:
                title = meta.get('content', '')
        
        # 简介
        desc = ""
        desc_el = soup.find('span', string=re.compile('简介'))
        if desc_el:
            next_span = desc_el.find_next('span')
            if next_span:
                desc = next_span.get_text(strip=True)
        
        # 演员/导演/年份/地区
        actor = director = year = area = ""
        for span in soup.find_all('span'):
            text = span.get_text(strip=True)
            if text.startswith('演员'):
                next_span = span.find_next('span')
                if next_span:
                    actor = next_span.get_text(strip=True)
            elif text.startswith('导演'):
                next_span = span.find_next('span')
                if next_span:
                    director = next_span.get_text(strip=True)
            elif text.startswith('年份'):
                next_span = span.find_next('span')
                if next_span:
                    year = next_span.get_text(strip=True)
            elif text.startswith('地区'):
                next_span = span.find_next('span')
                if next_span:
                    area = next_span.get_text(strip=True)
        
        # 封面
        pic = ""
        img = soup.find('img', class_='lazy') or soup.find('img', attrs={'data-original': True})
        if img:
            pic = self._fix_url(img.get('data-original', '') or img.get('src', ''))
        
        # 播放线路
        play_froms = []
        play_urls = []
        
        play_links = soup.select('a[href*="/vod/play/"]')
        lines = {}
        for a in play_links:
            href = a.get('href', '')
            m = re.search(r'/sid/(\d+)/nid/(\d+)', href)
            if m:
                sid = m.group(1)
                nid = m.group(2)
                name = a.get('title', '') or a.get_text(strip=True)
                ep_name = re.sub(r'^播放', '', name) or f"第{nid}集"
                play_url = self._fix_url(href)
                
                if sid not in lines:
                    lines[sid] = f"线路{len(play_froms)+1}"
                    play_froms.append(lines[sid])
                    play_urls.append("")
                
                if play_urls[-1]:
                    play_urls[-1] += "#"
                play_urls[-1] += f"{ep_name}${play_url}"
        
        vod = {
            "vod_id": vid,
            "vod_name": title or "未知",
            "vod_pic": pic,
            "vod_content": desc,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_play_from": "$$$".join(play_froms) if play_froms else "在线播放",
            "vod_play_url": "$$$".join(play_urls) if play_urls else "暂缺",
        }
        
        return {"list": [vod]}
    
    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = self._fix_url(id)
            if not url:
                return {"parse": 0, "url": "", "header": {}}
            
            # 直链
            if ".m3u8" in url or ".mp4" in url:
                return {
                    "parse": 0,
                    "url": url,
                    "header": {"Referer": self.host + "/", "User-Agent": UA}
                }
            
            # 播放页 - 由于 JS 混淆，直接返回播放页让 App 解析
            return {
                "parse": 1,
                "url": url,
                "header": {"Referer": self.host + "/"}
            }
        except Exception as e:
            print(f"[fqdm] playerContent error: {e}")
            return {"parse": 0, "url": id, "header": {"Referer": self.host + "/"}}
    
    def localProxy(self, param):
        return None
    
    def isVideoFormat(self, url):
        return url and (".m3u8" in url or re.search(r"\.(mp4|mkv|avi|flv)", url, re.I))
    
    def manualVideoCheck(self):
        return False

# ==================== 测试代码 ====================
if __name__ == "__main__":
    spider = Spider()
    
    print("=== 测试首页 ===")
    home = spider.homeContent()
    print(f"分类: {len(home['class'])}个")
    for c in home['class']:
        print(f"  {c['type_id']}: {c['type_name']}")
    
    print("\n=== 测试分类页 ===")
    cat = spider.categoryContent("1", "1")
    print(f"列表: {len(cat['list'])}个, 页码: {cat['pagecount']}")
    for v in cat['list'][:3]:
        print(f"  {v['vod_id']}: {v['vod_name'][:20]}")
    
    print("\n=== 测试详情页 ===")
    det = spider.detailContent(["129"])
    if det.get('list'):
        v = det['list'][0]
        print(f"标题: {v['vod_name']}")
        print(f"简介: {v.get('vod_content', '')[:50]}...")
        print(f"线路: {v['vod_play_from']}")
        eps = v['vod_play_url'].split('#')
        print(f"集数: {len(eps)}集")
    
    print("\n=== 测试搜索 ===")
    result = spider.searchContent("海贼", 1)
    print(f"结果: {len(result['list'])}个")
    
    spider.destroy()
    print("\n✅ 测试完成")
