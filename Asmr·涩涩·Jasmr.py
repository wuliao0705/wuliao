import json, urllib.parse, urllib.request

HOST = "https://www.jasmr.net"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": HOST + "/"}


def _get(path, params=None):
    qs = ""
    if params:
        parts = []
        for k, v in params.items():
            if v is None or v == "":
                continue
            if v is True:
                val = "true"
            elif v is False:
                val = "false"
            else:
                val = str(v)
            parts.append(k + "=" + urllib.parse.quote(val))
        if parts:
            qs = "?" + "&".join(parts)
    url = HOST + path + qs
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode()
            try:
                return json.loads(body)
            except Exception:
                return {"error": body[:200]}
    except Exception as e:
        return {"error": str(e)}


def _abs(p):
    if not p:
        return ""
    if p.startswith("http://") or p.startswith("https://"):
        return p
    return HOST + p


def _title_first(d):
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            return ""
    if not isinstance(d, dict):
        return ""
    return d.get("chinese") or d.get("english") or d.get("japanese") or ""


def _circle_name(d):
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            return ""
    if not isinstance(d, dict):
        return ""
    return d.get("romaji") or d.get("kana") or ""


def _json_list(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return []
    if isinstance(v, list):
        return v
    return []


def _tag_display_name(name):
    if not isinstance(name, dict):
        return ""
    return name.get("chinese") or name.get("english") or name.get("japanese") or ""


class Spider:
    def init(self, extend=""):
        self._tag_cache = None
        self._tag_map = {}

    def homeContent(self, filter):
        if not self._tag_cache:
            d = _get("/api/v1/tags")
            if isinstance(d, list):
                self._tag_cache = d
            else:
                self._tag_cache = []
        cls_list = [
            {"type_id": "all", "type_name": "全部"},
            {"type_id": "latest", "type_name": "最新"},
            {"type_id": "popular", "type_name": "热门"},
            {"type_id": "tags", "type_name": "标签"},
        ]
        self._tag_map.clear()
        for t in self._tag_cache:
            if not t.get("videoCount"):
                continue
            name = t.get("name", {})
            display = _tag_display_name(name) or str(t.get("id"))
            eng = name.get("english", display) if isinstance(name, dict) else display
            self._tag_map[str(t.get("id"))] = eng
        return {"class": cls_list, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("latest", "1", False, {})

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or "1"))

        if tid == "tags":
            return self._tag_grid(page)

        tag_fallback = None
        if isinstance(tid, str) and tid.startswith("tag_"):
            tag_fallback = tid[len("tag_"):]
        elif isinstance(tid, str) and tid.isdigit():
            tag_fallback = tid

        limit = 20
        base = {
            "page": page,
            "limit": limit,
            "all": True,
            "r18": True,
            "r15": True,
            "type": "video",
            "date": "alltime",
            "min": 0,
            "max": 6000,
            "tracks": False,
        }

        selected_tag = None
        if isinstance(filter, dict):
            selected_tag = filter.get("tag")

        if tid == "popular":
            base["sort"] = "viewsDescending"
        elif tid == "all":
            base["sort"] = "dateDescending"
            if selected_tag:
                if not self._tag_cache:
                    self.homeContent(False)
                eng = self._tag_map.get(str(selected_tag), selected_tag)
                base["search"] = eng
        elif tid == "latest":
            base["sort"] = "dateDescending"
        else:
            base["sort"] = "dateDescending"
            eng = None
            if not self._tag_cache:
                self.homeContent(False)
            if tag_fallback is not None:
                eng = self._tag_map.get(str(tag_fallback), tag_fallback)
            if not eng and selected_tag:
                eng = self._tag_map.get(str(selected_tag), selected_tag)
            if not eng:
                eng = self._tag_map.get(str(tid), tid)
            base["search"] = eng or tid

        d = _get("/api/v1/search", base)
        if not isinstance(d, dict) or "error" in d or not d.get("results"):
            return {"list": [], "page": page, "pagecount": 1, "limit": limit, "total": 0}

        total = d.get("totalCount", 0) or 0
        pagecount = max(1, (total + limit - 1) // limit)
        vod_list = []
        for r in d.get("results", []):
            name = _title_first(r.get("title")) or r.get("rjCode", "")
            dur = r.get("duration", "") or ""
            circle = _circle_name(r.get("circle"))
            tags = _json_list(r.get("tags", []))
            tag_list = [t.get("english") for t in tags if isinstance(t, dict) and t.get("english")][:2]
            remarks = " | ".join([x for x in [dur, circle] + tag_list if x])
            vid = "{}|{}".format(r.get("id", ""), r.get("rjCode", ""))
            vod_list.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": _abs(r.get("image", "")),
                "vod_remarks": remarks,
            })
        return {"list": vod_list, "page": page, "pagecount": pagecount, "limit": limit, "total": total}

    def _tag_grid(self, page):
        if not self._tag_cache:
            self.homeContent(False)
        items = []
        for t in self._tag_cache:
            if not t.get("videoCount"):
                continue
            name = t.get("name", {})
            display = _tag_display_name(name) or str(t.get("id"))
            tid = str(t.get("id"))
            items.append({
                "vod_id": "tag_" + tid,
                "vod_name": display,
                "vod_pic": "",
                "vod_remarks": str(t.get("videoCount", "")),
                "vod_tag": "folder",
                "style": {"type": "rect", "ratio": 1.0},
            })
        return {"list": items, "page": 1, "pagecount": 1, "limit": len(items), "total": len(items)}

    def detailContent(self, ids):
        id_str = ids[0] if isinstance(ids, list) else ids

        tag_id = None
        if isinstance(id_str, str) and id_str.startswith("tag_"):
            tag_id = id_str[len("tag_"):]
        elif isinstance(id_str, str) and id_str.isdigit():
            tag_id = id_str

        if tag_id is not None:
            return self.categoryContent(tag_id, "1", False, {})

        parts = id_str.split("|")
        rj = parts[-1] if len(parts) > 1 and parts[-1] else id_str
        d = _get("/api/v1/videos", {"code": rj})
        if not isinstance(d, dict) or "error" in d or not d.get("id"):
            return {"list": []}

        title = d.get("title", {})
        if isinstance(title, str):
            try:
                title = json.loads(title)
            except Exception:
                title = {}
        cn = title.get("chinese", "") if isinstance(title, dict) else ""
        en = title.get("english", "") if isinstance(title, dict) else ""
        jp = title.get("japanese", "") if isinstance(title, dict) else ""

        desc = d.get("description", "") or ""
        if isinstance(desc, dict):
            desc = desc.get("english") or desc.get("chinese") or desc.get("japanese") or ""
        if not isinstance(desc, str):
            desc = str(desc) if desc else ""
        if jp and jp not in desc:
            desc += " 日文标题：" + jp
        if en and en != cn and en not in desc:
            desc += " 英文标题：" + en

        age = d.get("ageRating", "all")
        dur = d.get("duration", "")
        lang = d.get("language", "")
        sub = "有字幕" if d.get("subtitled") else "无字幕"
        circle = _circle_name(d.get("circle"))
        meta = "时长：{} | 语言：{} | 分级：{} | 字幕：{}".format(dur, lang, age, sub)
        if circle:
            meta += " | 社团：" + circle

        source_url = _abs(d.get("source", ""))
        tracks = _json_list(d.get("tracks", []))
        if tracks:
            ep_parts = []
            for i, trk in enumerate(tracks):
                tk = trk.get("title", {})
                if isinstance(tk, str):
                    try:
                        tk = json.loads(tk)
                    except Exception:
                        tk = {}
                if isinstance(tk, dict):
                    tn = tk.get("chinese") or tk.get("english") or "Track {}".format(i + 1)
                else:
                    tn = "Track {}".format(i + 1)
                tl = trk.get("length", "")
                ep_parts.append("{} ({})${}".format(tn, tl, source_url))
            play_url = "#".join(ep_parts)
        else:
            play_url = "完整音频$" + source_url

        tags = _json_list(d.get("tags", []))
        tag_names = [t.get("english") for t in tags if isinstance(t, dict) and t.get("english")][:6]

        vod = {
            "vod_id": id_str,
            "vod_name": cn or en or d.get("rjCode", ""),
            "vod_pic": _abs(d.get("image", "") or d.get("thumbnail", "")),
            "vod_play_from": "JASMR",
            "vod_play_url": play_url,
            "type_name": " / ".join(tag_names),
            "vod_year": "",
            "area": lang,
            "vod_remarks": meta,
            "vod_content": desc if isinstance(desc, str) else json.dumps(desc, ensure_ascii=False),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg):
        page = max(1, int(pg or "1"))
        limit = 20
        params = {
            "page": page,
            "limit": limit,
            "all": True,
            "r18": True,
            "r15": True,
            "type": "video",
            "date": "alltime",
            "min": 0,
            "max": 6000,
            "tracks": False,
            "search": key,
            "sort": "relevanceDescending",
        }
        d = _get("/api/v1/search", params)
        if not isinstance(d, dict) or "error" in d or not d.get("results"):
            return {"list": [], "page": page, "pagecount": 1, "limit": limit, "total": 0}

        total = d.get("totalCount", 0) or 0
        pagecount = max(1, (total + limit - 1) // limit)
        vod_list = []
        for r in d.get("results", []):
            name = _title_first(r.get("title")) or r.get("rjCode", "")
            vid = "{}|{}".format(r.get("id", ""), r.get("rjCode", ""))
            dur = r.get("duration", "") or ""
            vod_list.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": _abs(r.get("image", "")),
                "vod_remarks": dur,
            })
        return {"list": vod_list, "page": page, "pagecount": pagecount, "limit": limit, "total": total}

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": id,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }
