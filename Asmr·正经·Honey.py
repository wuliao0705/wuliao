# -*- coding: utf-8 -*-
"""
==================================================
@Spider Name : ASMRHoney Enhanced (修复缓存权限)
@Description : ASMRHoney - ASMR视频精选站 (增强版)
              自动适配缓存目录，权限失败则降级为内存缓存
==================================================
"""
import sys
import re
import json
import time
import os
import hashlib
import tempfile
from urllib.parse import quote, urljoin

try:
    import requests
except ImportError:
    requests = None

# ---------- 缓存目录自动适配 ----------
CANDIDATE_CACHE_DIRS = [
    "/sdcard/Android/data/com.example.peekpro/cache/asmrhoney",
    "/sdcard/asmrhoney_cache",
    os.path.join(os.getcwd(), "cache", "asmrhoney"),
    os.path.join(tempfile.gettempdir(), "asmrhoney_cache"),
]

CACHE_DIR = None
for path in CANDIDATE_CACHE_DIRS:
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".writetest")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        CACHE_DIR = path
        break
    except Exception:
        continue

if CACHE_DIR is None:
    print("[ASMRHoney] 警告：无法创建缓存目录，将仅使用内存缓存")
else:
    print(f"[ASMRHoney] 缓存目录: {CACHE_DIR}")

CACHE_TTL = 3600  # 秒

# ---------- 常量 ----------
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# 语言映射
LANG_MAP = {
    "zh": ("lang_zh", "中文ASMR"),
    "ja": ("lang_ja", "日语ASMR"),
    "ko": ("lang_ko", "韩语ASMR"),
    "en": ("lang_en", "英语ASMR"),
    "mixed": ("lang_mixed", "混合语言"),
}

# 标签分类
TAG_CATEGORIES = [
    ("tag_ear_licking", "舔耳", "ear_licking"),
    ("tag_mouth_sounds", "口腔音", "mouth_sounds"),
    ("tag_trigger_sounds", "触发音", "trigger_sounds"),
    ("tag_roleplay", "角色扮演", "roleplay"),
    ("tag_whisper", "耳语", "whisper"),
    ("tag_pantyhose", "丝袜", "pantyhose"),
    ("tag_scratching", "刮擦", "scratching"),
    ("tag_sexy", "性感", "sexy"),
    ("tag_sfw", "SFW全年龄", "sfw"),
    ("tag_nsfw", "NSFW", "nsfw"),
    ("tag_eareating", "耳吃", "eareating"),
    ("tag_tongue", "舌头", "tongue"),
    ("tag_sleep_aid", "助眠", "sleep_aid"),
    ("tag_breathing", "呼吸音", "breathing"),
    ("tag_feet", "足部", "feet"),
    ("tag_kiss", "亲吻", "kiss"),
]

# ---------- 兼容基类 ----------
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): self.extend = extend
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


class Spider(BaseSpider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = "https://asmrhoney.com"
        self.session = None
        self._clips = []
        self._audio_data = {}
        self._search_index = {}
        self._cache_time = 0
        self._audio_cache_time = 0
        self._init_urllib_fallback()

    # ---------- 兼容性层 ----------
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

    def _fetch_json(self, url):
        try:
            if self.session:
                r = self.session.get(url, timeout=30)
                if r.status_code == 200:
                    return r.json()
            elif self._urllib:
                req = self._urllib.Request(url, headers={
                    "User-Agent": UA,
                    "Accept": "application/json",
                    "Referer": self.host + "/",
                })
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[ASMRHoney] _fetch_json error: {e}")
        return None

    def _fetch_html(self, url):
        try:
            if self.session:
                r = self.session.get(url, timeout=15)
                if r.status_code == 200:
                    return r.text
            elif self._urllib:
                req = self._urllib.Request(url, headers={"User-Agent": UA})
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=15) as resp:
                    return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        return ""

    # ---------- 缓存持久化（适配 CACHE_DIR） ----------
    def _cache_file_path(self, name):
        if CACHE_DIR is None:
            return None
        return os.path.join(CACHE_DIR, f"{name}.json")

    def _load_from_cache(self, name, ttl=CACHE_TTL):
        path = self._cache_file_path(name)
        if path is None or not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        if time.time() - mtime > ttl:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None

    def _save_to_cache(self, name, data):
        path = self._cache_file_path(name)
        if path is None:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass

    # ---------- 数据加载 ----------
    def _load_clips(self, force=False):
        now = time.time()
        if not force and self._clips and (now - self._cache_time) < CACHE_TTL:
            return self._clips

        cached = self._load_from_cache("clips")
        if cached and not force:
            self._clips = cached
            self._cache_time = now
            self._build_search_index()
            return self._clips

        data = self._fetch_json(f"{self.host}/data/clips.json")
        if data:
            clips = data.get("clips", [])
            clips = [c for c in clips if c.get("status") == "published"]
            clips.sort(key=lambda c: c.get("publishedAt", ""), reverse=True)
            self._clips = clips
            self._cache_time = now
            self._save_to_cache("clips", clips)
            self._build_search_index()
            return clips

        if self._clips:
            return self._clips
        return []

    def _load_audio(self, force=False):
        now = time.time()
        if not force and self._audio_data and (now - self._audio_cache_time) < CACHE_TTL:
            return self._audio_data

        cached = self._load_from_cache("audio")
        if cached and not force:
            self._audio_data = cached
            self._audio_cache_time = now
            return self._audio_data

        data = self._fetch_json(f"{self.host}/data/audio.json")
        if data:
            self._audio_data = data
            self._audio_cache_time = now
            self._save_to_cache("audio", data)
            return data

        if self._audio_data:
            return self._audio_data
        return {"albums": [], "tracks": []}

    # ---------- 搜索索引 ----------
    def _build_search_index(self):
        index = {}
        for clip in self._clips:
            slug = clip.get("slug", "")
            title = clip.get("title", "").lower()
            creator = clip.get("creator", "").lower()
            tags = [t.lower() for t in clip.get("tags", [])]
            desc = clip.get("description", "").lower()
            for word in title.split():
                index.setdefault(word, []).append(slug)
            for word in creator.split():
                index.setdefault(word, []).append(slug)
            for tag in tags:
                index.setdefault(tag, []).append(slug)
            for word in desc.split():
                if len(word) > 3:
                    index.setdefault(word, []).append(slug)
        self._search_index = index

    # ---------- 契约方法 ----------
    def getDependence(self):
        return []

    def getName(self):
        return "ASMRHoney"

    def init(self, extend=""):
        self.setExtendInfo(extend)
        if requests:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": self.host + "/",
            })
            self.session.verify = False

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
        return bool(re.search(r"\.(?:mp4|m3u8|mp3|m4a|flv|mkv|ts)(?:\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    # ==================== 首页与分类 ====================
    def homeContent(self, filter=False):
        classes = []
        for _, (tid, name) in LANG_MAP.items():
            classes.append({"type_id": tid, "type_name": name})
        for tid, name, _ in TAG_CATEGORIES:
            classes.append({"type_id": tid, "type_name": name})
        classes.append({"type_id": "audio_albums", "type_name": "音频专辑"})
        classes.append({"type_id": "audio_tracks", "type_name": "音频单曲"})
        classes.insert(0, {"type_id": "latest", "type_name": "最新更新"})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        clips = self._load_clips()
        items = self._clips_to_vod_list(clips[:24])
        return {"list": items}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = max(1, self._safe_int(pg))
        page_size = 20

        clips = self._load_clips()
        filtered = []

        if tid == "latest":
            filtered = clips
        elif tid.startswith("lang_"):
            lang_key = tid.replace("lang_", "", 1)
            filtered = [c for c in clips if c.get("language") == lang_key]
        elif tid.startswith("tag_"):
            tag_key = tid.replace("tag_", "", 1)
            orig_tag = None
            for _, _, tag in TAG_CATEGORIES:
                if tag == tag_key:
                    orig_tag = tag
                    break
            if orig_tag:
                filtered = [c for c in clips if orig_tag in c.get("tags", [])]
            else:
                filtered = [c for c in clips if tag_key in c.get("tags", [])]
        elif tid == "audio_albums":
            data = self._load_audio()
            albums = data.get("albums", [])
            total = len(albums)
            start = (page - 1) * page_size
            page_albums = albums[start:start+page_size]
            items = self._albums_to_vod_list(page_albums)
            pagecount = max(1, (total + page_size - 1) // page_size)
            return {
                "list": items, "page": page,
                "pagecount": pagecount, "limit": page_size, "total": total,
            }
        elif tid == "audio_tracks":
            data = self._load_audio()
            tracks = data.get("tracks", [])
            total = len(tracks)
            start = (page - 1) * page_size
            page_tracks = tracks[start:start+page_size]
            items = self._tracks_to_vod_list(page_tracks)
            pagecount = max(1, (total + page_size - 1) // page_size)
            return {
                "list": items, "page": page,
                "pagecount": pagecount, "limit": page_size, "total": total,
            }
        else:
            filtered = clips

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        page_clips = filtered[start:end]
        items = self._clips_to_vod_list(page_clips)
        pagecount = max(1, (total + page_size - 1) // page_size)

        return {
            "list": items, "page": page,
            "pagecount": pagecount, "limit": page_size, "total": total,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)

        clips = self._load_clips()

        if not vod_id.startswith("audio:") and not vod_id.startswith("album:"):
            clip = self._find_clip(clips, vod_id)
            if clip:
                vod = self._clip_to_vod_detail(clip)
                return {"list": [vod]}

        if vod_id.startswith("album:"):
            slug = vod_id.replace("album:", "", 1)
            data = self._load_audio()
            for album in data.get("albums", []):
                if album.get("slug") == slug:
                    vod = self._album_to_vod_detail(album, data.get("tracks", []))
                    return {"list": [vod]}

        if vod_id.startswith("audio:"):
            slug = vod_id.replace("audio:", "", 1)
            data = self._load_audio()
            for track in data.get("tracks", []):
                if track.get("slug") == slug:
                    vod = self._track_to_vod_detail(track)
                    return {"list": [vod]}

        return {"list": []}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick=False, pg="1"):
        page = max(1, self._safe_int(pg))
        page_size = 20

        if not key or not key.strip():
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        words = key.strip().lower().split()
        if not self._search_index:
            self._build_search_index()

        matched_slugs = set()
        for word in words:
            if word in self._search_index:
                matched_slugs.update(self._search_index[word])

        if not matched_slugs:
            return {"list": [], "page": page, "pagecount": 1, "limit": page_size, "total": 0}

        clips = self._load_clips()
        clip_map = {c.get("slug"): c for c in clips}
        results = []
        for slug in matched_slugs:
            clip = clip_map.get(slug)
            if not clip:
                continue
            score = 0
            title = clip.get("title", "").lower()
            creator = clip.get("creator", "").lower()
            tags = [t.lower() for t in clip.get("tags", [])]
            desc = clip.get("description", "").lower()
            if key.lower() in title:
                score += 100
            if key.lower() in creator:
                score += 50
            if any(key.lower() in t for t in tags):
                score += 30
            if key.lower() in desc:
                score += 10
            results.append((score, clip))

        results.sort(key=lambda x: x[0], reverse=True)
        matched_clips = [r[1] for r in results]

        total = len(matched_clips)
        start = (page - 1) * page_size
        end = start + page_size
        page_clips = matched_clips[start:end]
        items = self._clips_to_vod_list(page_clips)
        pagecount = max(1, (total + page_size - 1) // page_size)

        return {
            "list": items, "page": page,
            "pagecount": pagecount, "limit": page_size, "total": total,
        }

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags=None):
        safe = {"parse": 0, "playUrl": "", "url": "", "header": {}}

        try:
            play_url = str(id or "")
            if '$' in play_url:
                play_url = play_url.split('$')[-1].strip()

            if play_url.startswith("http") and self.isVideoFormat(play_url):
                return {
                    "parse": 0, "playUrl": "", "url": play_url,
                    "header": {
                        "User-Agent": UA,
                        "Referer": self.host + "/",
                        "Origin": self.host,
                    }
                }

            if play_url and not play_url.startswith("http"):
                clips = self._load_clips()
                clip = self._find_clip(clips, play_url)
                if clip:
                    video_url = clip.get("videoUrl") or clip.get("video480Url") or ""
                    if video_url:
                        return {
                            "parse": 0, "playUrl": "", "url": video_url,
                            "header": {
                                "User-Agent": UA,
                                "Referer": self.host + "/",
                                "Origin": self.host,
                            }
                        }

                if play_url.startswith("audio:"):
                    track_slug = play_url.replace("audio:", "", 1)
                    data = self._load_audio()
                    for track in data.get("tracks", []):
                        if track.get("slug") == track_slug:
                            audio_url = track.get("audioUrl", "")
                            if audio_url:
                                return {
                                    "parse": 0, "playUrl": "", "url": audio_url,
                                    "header": {
                                        "User-Agent": UA,
                                        "Referer": self.host + "/",
                                    }
                                }
        except Exception as e:
            print(f"[ASMRHoney] playerContent error: {e}")

        return safe

    # ==================== 本地代理 ====================
    def localProxy(self, param):
        url = param.get("url") or param.get("pic") or ""
        if isinstance(url, list):
            url = url[0] if url else ""
        if not url:
            return [404, "text/plain", b""]

        try:
            if not url.startswith("http"):
                url = urljoin(self.host, url)
            if self.session:
                r = self.session.get(url, headers={
                    "User-Agent": UA,
                    "Referer": self.host + "/",
                }, timeout=15)
                if r.status_code == 200 and r.content:
                    ct = r.headers.get("Content-Type", "image/jpeg")
                    return [200, ct, r.content]
            elif self._urllib:
                req = self._urllib.Request(url, headers={"User-Agent": UA, "Referer": self.host + "/"})
                with self._urllib.urlopen(req, context=self._ssl_ctx, timeout=15) as resp:
                    return [200, resp.headers.get("Content-Type", "image/jpeg"), resp.read()]
        except Exception as e:
            print(f"[ASMRHoney] localProxy error: {e}")
        return [404, "text/plain", b""]

    # ==================== 辅助方法 ====================
    @staticmethod
    def _safe_int(val):
        try:
            v = int(str(val or "").strip())
            return v if v > 0 else 1
        except:
            return 1

    def _find_clip(self, clips, slug):
        if not slug:
            return None
        if slug.startswith("clip:"):
            slug = slug[5:]
        for c in clips:
            if c.get("slug") == slug:
                return c
        return None

    def _clips_to_vod_list(self, clips):
        items = []
        for clip in clips:
            slug = clip.get("slug", "")
            title = clip.get("title", "") or slug
            cover = clip.get("coverUrl") or clip.get("coverWebpUrl") or ""
            duration = clip.get("duration", 0)
            creator = clip.get("creator", "")
            remarks = creator
            if duration:
                mins = duration // 60
                secs = duration % 60
                if remarks:
                    remarks += f" | {mins}:{secs:02d}"
                else:
                    remarks = f"{mins}:{secs:02d}"
            items.append({
                "vod_id": slug,
                "vod_name": title,
                "vod_pic": cover,
                "vod_remarks": remarks,
            })
        return items

    def _clip_to_vod_detail(self, clip):
        slug = clip.get("slug", "")
        title = clip.get("title", "") or slug
        cover = clip.get("coverUrl") or clip.get("coverWebpUrl") or ""
        duration = clip.get("duration", 0)
        creator = clip.get("creator", "")
        description = clip.get("description", "")
        tags = clip.get("tags", [])
        language = clip.get("language", "")
        published = clip.get("publishedAt", "")[:10]
        video_url = clip.get("videoUrl", "")
        video_480 = clip.get("video480Url", "")

        play_from = []
        play_urls = []
        if video_url:
            play_from.append("原画")
            play_urls.append(f"{title}${video_url}")
        if video_480:
            play_from.append("480P")
            play_urls.append(f"{title}${video_480}")

        lang_name = {"zh":"中文","ja":"日语","ko":"韩语","en":"英语","mixed":"混合"}.get(language, language)
        duration_str = ""
        if duration:
            mins = duration // 60
            secs = duration % 60
            duration_str = f"{mins}分{secs:02d}秒"

        return {
            "vod_id": slug,
            "vod_name": title,
            "vod_pic": cover,
            "vod_director": "",
            "vod_actor": creator,
            "vod_year": published,
            "vod_area": lang_name,
            "vod_content": description or title,
            "vod_remarks": duration_str,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_urls),
            "vod_tag": ",".join(tags),
        }

    def _albums_to_vod_list(self, albums):
        items = []
        for album in albums:
            slug = album.get("slug", "")
            title = album.get("title", "") or slug
            cover = album.get("coverUrl") or ""
            track_count = album.get("trackCount", 0)
            total_duration = album.get("totalDuration", 0)
            remarks = f"{track_count}首"
            if total_duration:
                hours = total_duration // 3600
                mins = (total_duration % 3600) // 60
                remarks += f" | {hours}h{mins}m"
            items.append({
                "vod_id": f"album:{slug}",
                "vod_name": title,
                "vod_pic": cover,
                "vod_remarks": remarks,
            })
        return items

    def _tracks_to_vod_list(self, tracks):
        items = []
        for track in tracks:
            slug = track.get("slug", "")
            title = track.get("title", "") or slug
            cover = track.get("coverUrl") or ""
            duration = track.get("duration", 0)
            creator = track.get("creator", "")
            remarks = creator or ""
            if duration:
                mins = duration // 60
                secs = duration % 60
                if remarks:
                    remarks += f" | {mins}:{secs:02d}"
                else:
                    remarks = f"{mins}:{secs:02d}"
            items.append({
                "vod_id": f"audio:{slug}",
                "vod_name": title,
                "vod_pic": cover,
                "vod_remarks": remarks,
            })
        return items

    def _album_to_vod_detail(self, album, all_tracks):
        slug = album.get("slug", "")
        title = album.get("title", "") or slug
        cover = album.get("coverUrl") or ""
        creator = album.get("creator", "")
        track_count = album.get("trackCount", 0)
        total_duration = album.get("totalDuration", 0)
        published = str(album.get("publishedAt", ""))[:10]

        album_slug = album.get("slug", "")
        album_tracks = [t for t in all_tracks if t.get("albumSlug") == album_slug]
        if not album_tracks:
            album_tracks = [t for t in all_tracks if t.get("creator") == creator]

        eps = []
        for track in album_tracks:
            t_slug = track.get("slug", "")
            t_title = track.get("title", "") or t_slug
            t_url = track.get("audioUrl", "")
            if t_url:
                eps.append(f"{t_title}${t_url}")
        if not eps:
            eps.append(f"{title}$")

        return {
            "vod_id": f"album:{slug}",
            "vod_name": title,
            "vod_pic": cover,
            "vod_director": "",
            "vod_actor": creator,
            "vod_year": published,
            "vod_area": "音频",
            "vod_content": album.get("title_en", "") or title,
            "vod_remarks": f"{track_count}首 | {total_duration//60}分",
            "vod_play_from": "音频",
            "vod_play_url": "#".join(eps),
        }

    def _track_to_vod_detail(self, track):
        slug = track.get("slug", "")
        title = track.get("title", "") or slug
        cover = track.get("coverUrl") or ""
        creator = track.get("creator", "")
        duration = track.get("duration", 0)
        audio_url = track.get("audioUrl", "")
        published = str(track.get("publishedAt", ""))[:10]
        duration_str = ""
        if duration:
            mins = duration // 60
            secs = duration % 60
            duration_str = f"{mins}分{secs:02d}秒"
        return {
            "vod_id": f"audio:{slug}",
            "vod_name": title,
            "vod_pic": cover,
            "vod_director": "",
            "vod_actor": creator,
            "vod_year": published,
            "vod_area": "音频",
            "vod_content": track.get("title_en", "") or title,
            "vod_remarks": duration_str,
            "vod_play_from": "音频",
            "vod_play_url": f"{title}${audio_url}" if audio_url else "",
        }