# -*- coding: utf-8 -*-
# Author: 无聊
# 网站: chaturbate.com
# CMS: API
# 日期: 2026-09-15
import json, re, sys, urllib3, traceback
from urllib.parse import quote, unquote, urljoin
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        pass
try:
    import requests as _req
except Exception:
    _req = None

SITE = "https://chaturbate.com"
NAME = "Chaturbate 直播"

_CATS = [
    ("女性", "female-cams"), ("男性", "male-cams"),
    ("情侣", "couple-cams"), ("变性", "trans-cams"), ("新人", "new-cams"),
    ("游戏", "gaming-cams"), ("熟女", "mature-cams"),
    ("北美", "north-american-cams"), ("南美", "south-american-cams"),
    ("亚洲", "asian-cams"), ("欧洲/俄罗斯", "euro-russian-cams"),
]

CAT_PARAMS = {
    "female-cams": "&genders=f",
    "male-cams": "&genders=m",
    "couple-cams": "&genders=c",
    "trans-cams": "&genders=t",
    "new-cams": "&new_cams=true",
    "gaming-cams": "&gaming=true",
    "mature-cams": "&from_age=50&to_age=100",
    "north-american-cams": "&regions=NA",
    "south-american-cams": "&regions=SA",
    "asian-cams": "&regions=AS",
    "euro-russian-cams": "&regions=ER",
}

class _Spider(Spider):
    _sess = None
    _m3u8_cache = {}

    def __init__(self, *args, **kwargs):
        super(_Spider, self).__init__(*args, **kwargs)
        self._sess = None
        t4_api = kwargs.get('t4_api', '')
        if t4_api:
            try:
                from urllib.parse import urlparse as _up
                self.proxy_url = t4_api
                self.py_proxy_base = f"{_up(t4_api).scheme}://{_up(t4_api).netloc}{_up(t4_api).path.replace('/api/', '/proxy/')}"
            except:
                self.proxy_url = ""
                self.py_proxy_base = ""
        else:
            self.proxy_url = ""
            self.py_proxy_base = ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Referer": SITE + "/",
        }

    def getName(self): return NAME

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url): return url.endswith(".m3u8") or "/m3u8/" in url

    def manualVideoCheck(self): return False

    def destroy(self):
        if self._sess:
            try: self._sess.close()
            except: pass
        self._sess = None

    def homeContent(self, filter=False):
        return {"class": [{"type_id": c[1], "type_name": c[0]} for c in _CATS]}

    def homeVideoContent(self): return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        pg = int(pg) if pg else 0
        params = CAT_PARAMS.get(tid, "&genders=f")
        offset = pg * 60
        url = f"{SITE}/api/ts/roomlist/room-list/?enable_recommendations=false&limit=60&offset={offset}{params}"
        html = self._get(url)
        if not html: return {"list": [], "page": pg, "pagecount": 1, "limit": 60, "total": 0}
        try:
            j = json.loads(html)
        except:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 60, "total": 0}
        rooms = j.get("rooms", [])
        videos = []
        for r in rooms:
            username = r.get("username", "")
            if not username: continue
            img = r.get("img", "") or f"https://thumb.live.mmcdn.com/ri/{username}.jpg"
            viewers = r.get("num_users", "")
            if viewers is not None and viewers > 0:
                remarks = f"{viewers:,} 人"
            else:
                remarks = ""
            videos.append({
                "vod_id": username,
                "vod_name": username,
                "vod_pic": img,
                "vod_remarks": remarks,
            })
        total = j.get("total_count", len(videos))
        pagecount = (total + 59) // 60 if total > 0 else 1
        return {"list": videos, "page": pg + 1, "pagecount": pagecount, "limit": 60, "total": total}

    def detailContent(self, ids):
        username = str(ids[0]).strip()
        qualities = [
            ("1080P", "4"),
            ("720P", "3"),
            ("480P", "2"),
            ("360P", "1"),
            ("自动", "all"),
        ]
        plays = []
        for q, qi in qualities:
            plays.append(f"{q}${username}___{qi}")
        vod_play_url = "#".join(plays)
        return {
            "list": [{
                "vod_id": username,
                "vod_name": username,
                "vod_play_from": "Chaturbate",
                "vod_play_url": vod_play_url,
            }]
        }

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = id.split("___")
            username = parts[0].strip()
            q_idx = parts[1] if len(parts) > 1 else "all"
            api_url = f"{SITE}/api/chatvideocontext/{username}/"
            html = self._get(api_url)
            if not html: return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}
            j = json.loads(html)
            play_url = j.get("hls_source", "")
            if not play_url: return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}
            if self.py_proxy_base and play_url:
                play_url = self._make_proxy(play_url, q_idx)
            return {"parse": 0, "jx": 0, "playUrl": "", "url": play_url, "header": self.headers}
        except:
            return {"parse": 0, "jx": 0, "playUrl": "", "url": id, "header": {}}

    def searchContent(self, key, quick=False, pg=1):
        pg = int(pg) if pg else 0
        offset = pg * 60
        url = f"{SITE}/api/ts/roomlist/room-list/?limit=60&query={key}&offset={offset}"
        html = self._get(url)
        if not html: return {"list": [], "page": pg, "pagecount": 1, "limit": 60, "total": 0}
        try:
            j = json.loads(html)
        except:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 60, "total": 0}
        rooms = j.get("rooms", [])
        videos = []
        for r in rooms:
            username = r.get("username", "")
            if not username: continue
            img = r.get("img", "") or f"https://thumb.live.mmcdn.com/ri/{username}.jpg"
            videos.append({
                "vod_id": username,
                "vod_name": username,
                "vod_pic": img,
                "vod_remarks": "",
            })
        return {"list": videos, "page": pg, "pagecount": 1, "limit": 60, "total": len(videos)}

    def _get(self, url):
        try:
            if _req:
                r = _req.get(url, headers=self.headers, timeout=10, verify=False)
                return r.text
            import urllib.request as _ur
            req = _ur.Request(url, headers=self.headers)
            with _ur.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", "replace")
        except:
            return ""

    def _make_proxy(self, raw_url, q_idx):
        prefix = self.py_proxy_base if self.py_proxy_base else self.proxy_url
        if not prefix:
            return raw_url
        safe_url = quote(raw_url, safe="")
        return f"{prefix}?do=py&ptype=m3u8&url={safe_url}&q={q_idx}&ext=.m3u8"

    def localProxy(self, params):
        import time
        ptype = params.get("ptype", "")
        url = unquote(params.get("url", ""))
        q_idx = params.get("q", "all")
        if not url:
            return [400, "text/plain", b"no url"]
        curr_time = time.time()
        cache_key = f"{url.split('?')[0]}_{q_idx}"
        if cache_key in self._m3u8_cache:
            c_data, c_expire = self._m3u8_cache[cache_key]
            if curr_time < c_expire:
                return [200, "application/vnd.apple.mpegurl", c_data.encode("utf-8")]
        try:
            if _req:
                res = _req.get(url, headers=self.headers, timeout=10, verify=False)
                content = res.text
            else:
                import urllib.request as _ur
                req = _ur.Request(url, headers=self.headers)
                with _ur.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8", "replace")
            base_url = url[:url.rfind("/") + 1]
            lines = content.splitlines()
            # Master M3U8
            if "#EXT-X-STREAM-INF" in content:
                audio_tags = {}
                for line in lines:
                    if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                        gm = re.search(r'GROUP-ID="([^"]+)"', line)
                        if gm:
                            line = re.sub(r'URI="([^"]+)"', lambda m: f'URI="{urljoin(base_url, m.group(1))}"', line)
                            audio_tags[gm.group(1)] = line
                streams = []
                for i in range(len(lines)):
                    if lines[i].startswith("#EXT-X-STREAM-INF"):
                        bw_match = re.search(r"BANDWIDTH=(\d+)", lines[i])
                        bw = int(bw_match.group(1)) if bw_match else 0
                        uri = lines[i + 1].strip() if i + 1 < len(lines) else ""
                        streams.append({"bw": bw, "inf": lines[i], "uri": uri})
                streams.sort(key=lambda x: x["bw"], reverse=True)
                selected = None
                if q_idx != "all":
                    for s in streams:
                        if f"chunklist_{q_idx}_video" in s["uri"]:
                            selected = s
                            break
                if not selected and streams:
                    selected = streams[0]
                new_lines = ["#EXTM3U", "#EXT-X-VERSION:6", "#EXT-X-INDEPENDENT-SEGMENTS"]
                am = re.search(r'AUDIO="([^"]+)"', selected["inf"]) if selected else None
                audio_group = am.group(1) if am else None
                if audio_group and audio_group in audio_tags:
                    new_lines.append(audio_tags[audio_group])
                inf_line = selected["inf"] if selected else ""
                inf_line = re.sub(r",CODECS=\"[^\"]*\"", "", inf_line)
                inf_line = re.sub(r",mp4a[^\",]*", "", inf_line)
                new_lines.append(inf_line)
                if selected:
                    new_lines.append(urljoin(base_url, selected["uri"]))
                final_content = "\n".join(new_lines)
                self._m3u8_cache[cache_key] = (final_content, curr_time + 15)
                return [200, "application/vnd.apple.mpegurl", final_content.encode("utf-8")]
            # 子 chunklist
            new_chunklist = []
            for line in lines:
                if line.startswith("#"):
                    if "URI=" in line:
                        line = re.sub(r'URI="([^"]+)"', lambda m: f'URI="{urljoin(base_url, m.group(1))}"', line)
                    new_chunklist.append(line)
                elif line.strip():
                    new_chunklist.append(urljoin(base_url, line))
            final_content = "\n".join(new_chunklist)
            self._m3u8_cache[cache_key] = (final_content, curr_time + 15)
            return [200, "application/vnd.apple.mpegurl", final_content.encode("utf-8")]
        except Exception as e:
            return [500, "text/plain", traceback.format_exc().encode("utf-8")]

Spider = _Spider

