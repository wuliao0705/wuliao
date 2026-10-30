# -*- coding: utf-8 -*-
"""
18jav.tv TVBox/影视仓 T4 Python 爬虫源  v2 (分组发现页)
==========================================================
平台: KVS (Kernel Video Sharing)

发现页分类轴 (12 个顶级 + 下拉筛选):
  最近更新 / 熱門影片 / 影片主題(15) / 女優列表(3503)
  衣著(17) 身材(13) 交合(11) 玩法(19) 劇情(16) 角色(16) 地點(13) 雜項(9)

接口:
  列表分页  /{path}/?mode=async&function=get_block
              &block_id=list_videos_common_videos_list
              &sort_by={release_at|views|stars}&from={N}      每页 12
  女優分页  /models/?mode=async&function=get_block
              &block_id=list_models_models_list
              &sort_by={topic_nums|views|name}&from={N}       每页 12
  详情      /videos/{code}          code 大小写不敏感
  封面      https://cdn.18jav.tv/storage/{code}/320_180.jpg
  播放      var hlsUrl = "https://sN.hshdkshd.com/hls/<TOKEN>/<EXPIRE>/storage/<code>/<hash>.m3u8"
            ★ 签名+时效, 每次都变 -> 只在 playerContent 实时解析
  搜索      站内 /search/ 已损坏(恒返回 0 部) -> 三级降级
"""
import re
import time

try:
    from base.spider import BaseSpider
except Exception:
    class BaseSpider:
        pass


class Spider(BaseSpider):

    HOST = "https://18jav.tv"
    CDN = "https://cdn.18jav.tv"
    VBLOCK = "list_videos_common_videos_list"
    MBLOCK = "list_models_models_list"
    PLACE = "https://cdn.18jav.tv/assets/images/placeholder-md.jpg"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # ---- 影片主題 (15 个主分类, 体量最大) ----
    CATS = [
        ("chinese-subtitle", "中文字幕"), ("uncensored", "無碼解放"),
        ("taiwan-av", "台灣AV"), ("jav", "日本AV"), ("uniform", "制服誘惑"),
        ("roleplay", "角色劇情"), ("pantyhose", "絲襪"), ("sex-only", "直接開啪"),
        ("bdsm", "主奴調教"), ("groupsex", "多P群交"), ("intrusion", "進犯"),
        ("pov", "男友視角"), ("hixxen-cam", "流出"), ("lesbian", "女同歡愉"),
    ]

    # ---- 标签按站点原分组 (113 个) ----
    GROUPS = [
        ("clothing", "衣著", [
            ("wedding-dress", "婚紗"), ("swimsuit", "水着"), ("stockings", "吊帶襪"),
            ("sportswear", "運動裝"), ("school-uniform", "校服"), ("pantyhose", "絲襪"),
            ("maid", "女僕"), ("knee-socks", "過膝襪"), ("kimono", "和服"),
            ("kemonomimi", "獸耳"), ("glasses", "眼鏡娘"),
            ("flesh-toned-pantyhose", "肉絲"), ("fishnets", "漁網"),
            ("cheongsam", "旗袍"), ("bunny-girl", "兔女郎"),
            ("black-pantyhose", "黑絲"), ("Cosplay", "Cosplay"),
        ]),
        ("body", "身材", [
            ("big-tits", "巨乳"), ("small-tits", "貧乳"), ("mature-woman", "熟女"),
            ("girl", "少女"), ("dainty", "嬌小"), ("tall", "長身"),
            ("beautiful-leg", "美腿"), ("beautiful-butt", "美尻"),
            ("hairless-pussy", "白虎"), ("short-hair", "短髮"),
            ("suntan", "黑肉"), ("tattoo", "紋身"), ("flexible-body", "軟體"),
        ]),
        ("union", "交合", [
            ("creampie", "中出"), ("blowjob", "口交"), ("cum-in-mouth", "口爆"),
            ("facial", "顏射"), ("deep-throat", "深喉"), ("squirting", "潮吹"),
            ("tit-wank", "乳交"), ("footjob", "腳交"), ("kiss", "接吻"),
            ("spasms", "痙攣"), ("anal-sex", "肛交"),
        ]),
        ("play", "玩法", [
            ("tune", "調教"), ("gangbang", "多P"), ("3p", "3P"),
            ("chizyo", "痴女"), ("chikan", "痴漢"), ("intrusion", "進犯"),
            ("gang-intrusion", "集團進犯"), ("insult", "凌辱"), ("bondage", "綑綁"),
            ("torture", "刑具"), ("massage", "按摩"), ("outdoor", "露出"),
            ("soapland", "泡姬"), ("quickie", "瞬間插入"), ("piss", "放尿"),
            ("crapulence", "泥醉"), ("breast-milk", "母乳"),
            ("masochism-guy", "男M"), ("10-times-a-day", "一日十回"),
        ]),
        ("plot", "劇情", [
            ("ntr", "NTR"), ("affair", "出軌"), ("kinship", "親屬"),
            ("sex-beside-husband", "夫目前犯"), ("temptation", "誘惑"),
            ("love-potion", "媚藥"), ("hypnosis", "催眠"), ("time-stop", "時間停止"),
            ("hixxen-cam", "流出"), ("virginity", "童貞"), ("age-difference", "年齡差"),
            ("avenge", "復仇"), ("black", "黑人"), ("giant", "巨漢"),
            ("ugly-man", "醜男"), ("rainy-day", "下雨天"),
        ]),
        ("role", "角色", [
            ("wife", "人妻"), ("housewife", "家政婦"), ("widow", "未亡人"),
            ("teacher", "老師"), ("private-teacher", "家庭教師"), ("ol", "OL"),
            ("nurse", "護士"), ("doctor", "醫生"), ("idol", "偶像"),
            ("female-anchor", "主播"), ("flight-attendant", "空姐"),
            ("club-hostess-and-sex-worker", "風俗娘"), ("team-manager", "球隊經理"),
            ("detective", "搜查官"), ("fugitive", "逃犯"), ("couple", "情侶"),
        ]),
        ("place", "地點", [
            ("school", "學校"), ("library", "圖書館"), ("gym-room", "健身房"),
            ("hot-spring", "溫泉"), ("bathing-place", "洗浴場"),
            ("swimming-pool", "泳池"), ("toilet", "廁所"), ("tram", "電車"),
            ("car", "汽車"), ("store", "便利店"), ("prison", "監獄"),
            ("magic-mirror", "魔鏡號"), ("first-night", "處女"),
        ]),
        ("misc", "雜項", [
            ("fc2", "FC2"), ("madou", "麻豆"), ("taiwan", "台灣"),
            ("more-than-4-hours", "4小時以上"), ("video-recording", "錄像"),
            ("variety-show", "綜藝"), ("thanksgiving", "感謝祭"),
            ("festival", "節日主題"), ("debut-retires", "處女作/引退作"),
        ]),
    ]

    VSORTS = [("release_at", "最近更新"), ("views", "最多觀看"), ("stars", "近期最佳")]
    MSORTS = [("topic_nums", "最多影片"), ("views", "最多觀看"), ("name", "名稱")]

    # ================= 生命周期 =================
    def init(self, extend=""):
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,zh-CN;q=0.8,en;q=0.7",
            "Referer": self.HOST + "/",
        }
        self._sess = None
        try:
            import requests
            self._sess = requests.Session()
            self._sess.headers.update(self.headers)
        except Exception:
            pass
        # slug -> 中文名, 供搜索映射
        self._name_map = {}
        for s, n in self.CATS:
            self._name_map[s.lower()] = n
        for _, _, tags in self.GROUPS:
            for s, n in tags:
                self._name_map[s.lower()] = n

    def destroy(self):
        try:
            if self._sess:
                self._sess.close()
        except Exception:
            pass

    def getName(self):
        return "18JAV"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|avi|mkv|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    # ================= 网络 =================
    def _fetch(self, url, timeout=15, retry=2):
        for i in range(retry + 1):
            if self._sess is not None:
                try:
                    r = self._sess.get(url, timeout=timeout)
                    if r.status_code == 200 and r.text:
                        r.encoding = "utf-8"
                        return r.text
                except Exception:
                    pass
            try:
                import curl_cffi.requests as cr
                r = cr.get(url, impersonate="chrome120", timeout=timeout,
                           headers={"Referer": self.HOST + "/"})
                if r.status_code == 200 and r.text:
                    r.encoding = "utf-8"
                    return r.text
            except Exception:
                pass
            if i < retry:
                time.sleep(0.4 + i * 0.4)
        return ""

    # 榜单页只认固定 sort_by, 传错会返回 0 条
    FIXED_SORT = {"latest-updates": "release_at", "hot": "views"}

    def _vurl(self, path, sort_by="release_at", page=1):
        """★ 必须始终走 async: 整页 ?sort_by= 会被站点忽略(恒按 release_at),
           且整页第1页与 async 分页序列不一致会造成跨页重复
           ★ latest-updates 只接受 release_at, hot 只接受 views, 否则返回空"""
        p = str(path).strip("/")
        sort_by = self.FIXED_SORT.get(p, sort_by)
        base = f"{self.HOST}/{p}/"
        return (f"{base}?mode=async&function=get_block&block_id={self.VBLOCK}"
                f"&sort_by={sort_by}&from={max(1, int(page))}")

    def _murl(self, sort_by="topic_nums", page=1):
        base = self.HOST + "/models/"
        return (f"{base}?mode=async&function=get_block&block_id={self.MBLOCK}"
                f"&sort_by={sort_by}&from={max(1, int(page))}")

    # ================= 解析 =================
    def _parse_list(self, html):
        """视频卡片: 同一 code 有封面/标题两个 <a>, 按 code 去重"""
        out, seen = [], set()
        titles = {}
        for m in re.finditer(
                r'<h6 class="title">\s*<a[^>]+href="[^"]*?/videos/([^"/?]+)"[^>]*>(.*?)</a>',
                html, re.S):
            code = m.group(1).strip()
            txt = re.sub(r'<[^>]+>', '', m.group(2))
            titles[code.lower()] = re.sub(r'\s+', ' ', txt).strip()

        card = re.compile(
            r'<a[^>]+href="[^"]*?/videos/([^"/?]+)"[^>]*>\s*'
            r'<img[^>]*?(?:data-src|src)="([^"]+)"[^>]*>'
            r'(?:(?!</a>).)*?<span class="label">([^<]*)</span>', re.S)
        for m in card.finditer(html):
            code, pic, dur = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            key = code.lower()
            if key in seen:
                continue
            seen.add(key)
            if "placeholder" in pic or not pic.startswith("http"):
                pic = f"{self.CDN}/storage/{code}/320_180.jpg"
            out.append({"vod_id": code, "vod_name": titles.get(key) or code,
                        "vod_pic": pic, "vod_remarks": dur})

        if not out and titles:
            for key, name in titles.items():
                out.append({"vod_id": key, "vod_name": name,
                            "vod_pic": f"{self.CDN}/storage/{key}/320_180.jpg",
                            "vod_remarks": ""})
        return out

    def _parse_models(self, html):
        """女優卡片 -> folder 条目, 点进去列她的片"""
        out, seen = [], set()
        pat = re.compile(
            r'href="[^"]*?/models/([^"/?]+)"'
            r'(?:(?!</a>).)*?<h6 class="title">([^<]*)</h6>'
            r'\s*<span>([^<]*)</span>', re.S)
        for m in pat.finditer(html):
            slug, name, cnt = m.group(1).strip(), m.group(2).strip(), m.group(3)
            if slug.lower() in seen:
                continue
            seen.add(slug.lower())
            num = re.search(r'([\d,]+)', cnt or "")
            out.append({
                "vod_id": "model:" + slug,
                "vod_name": name or slug,
                "vod_pic": self.PLACE,
                "vod_remarks": (num.group(1) + " 部") if num else "",
                "vod_tag": "folder",      # ★ TVBox: 点击进入下一级列表
                "style": {"type": "oval", "ratio": 1.0},
            })
        return out

    def _enrich_model_pics(self, models):
        """站点女優头像是占位 svg -> 换成她最新一部影片的封面, 并发抓取"""
        def one(item):
            slug = item["vod_id"].split(":", 1)[1]
            html = self._fetch(self._vurl("models/" + slug, "release_at", 1),
                               timeout=8, retry=0)
            m = re.search(r'/videos/([^"/?]+)"', html or "")
            if m:
                item["vod_pic"] = f"{self.CDN}/storage/{m.group(1)}/320_180.jpg"
        try:
            from concurrent.futures import ThreadPoolExecutor, wait
            with ThreadPoolExecutor(max_workers=12) as ex:
                wait([ex.submit(one, it) for it in models], timeout=12)
        except Exception:
            pass
        return models

    @staticmethod
    def _pagecount(html, default=1):
        nums = [int(x) for x in re.findall(r'from:(\d+)', html or "")]
        return max(nums) if nums else default

    # ================= 发现页 =================
    def homeContent(self, filter=""):
        classes = [
            {"type_id": "latest-updates", "type_name": "最近更新"},
            {"type_id": "hot", "type_name": "熱門影片"},
            {"type_id": "topic", "type_name": "影片主題"},
            {"type_id": "models", "type_name": "女優列表"},
        ]
        classes += [{"type_id": "g:" + gid, "type_name": gname}
                    for gid, gname, _ in self.GROUPS]

        vsort = {"key": "sort", "name": "排序",
                 "value": [{"n": n, "v": v} for v, n in self.VSORTS]}
        filters = {
            # 榜单页站点只支持单一排序, 不给筛选避免用户选到空列表
            "topic": [
                {"key": "cat", "name": "主題",
                 "value": [{"n": n, "v": s} for s, n in self.CATS]},
                vsort,
            ],
            "models": [
                {"key": "msort", "name": "排序",
                 "value": [{"n": n, "v": v} for v, n in self.MSORTS]},
            ],
        }
        for gid, gname, tags in self.GROUPS:
            filters["g:" + gid] = [
                {"key": "tag", "name": gname,
                 "value": [{"n": n, "v": s} for s, n in tags]},
                vsort,
            ]

        return {"class": classes, "filters": filters,
                "list": self.homeVideoContent().get("list", [])}

    def homeVideoContent(self):
        """首页推荐: 最近更新 + 熱門 混合去重"""
        out, seen = [], set()
        for path in ("latest-updates", "hot"):
            for v in self._parse_list(self._fetch(self._vurl(path), retry=1)):
                k = v["vod_id"].lower()
                if k not in seen:
                    seen.add(k)
                    out.append(v)
        return {"list": out}

    # ================= 分类 =================
    def _resolve_path(self, tid, extend):
        """把 tid + 筛选 解析成站点路径"""
        tid = str(tid or "").strip()
        e = extend or {}

        if tid == "topic":
            return "categories/" + (e.get("cat") or self.CATS[0][0])
        if tid.startswith("g:"):
            gid = tid[2:]
            for g, _, tags in self.GROUPS:
                if g == gid:
                    return "tags/" + (e.get("tag") or tags[0][0])
            return "tags/" + (e.get("tag") or "big-tits")
        if tid.startswith("tag:"):
            return "tags/" + tid[4:]
        if tid.startswith("cat:"):
            return "categories/" + tid[4:]
        if tid.startswith("model:"):
            return "models/" + tid[6:]
        return tid or "latest-updates"

    def categoryContent(self, tid, pg, filter=True, extend=None):
        page = int(pg or 1)
        extend = extend or {}
        tid = str(tid or "").strip()

        # 女優列表: 返回 folder 条目
        if tid == "models":
            msort = extend.get("msort") or "topic_nums"
            html = self._fetch(self._murl(msort, page))
            models = self._enrich_model_pics(self._parse_models(html))
            pc = self._pagecount(html, page if models else 1)
            return {"list": models, "page": page, "pagecount": pc,
                    "limit": len(models) or 12, "total": pc * 12}

        sort_by = extend.get("sort") or "release_at"
        path = self._resolve_path(tid, extend)
        html = self._fetch(self._vurl(path, sort_by, page))
        vlist = self._parse_list(html)
        pc = self._pagecount(html, page if vlist else 1)
        return {"list": vlist, "page": page, "pagecount": pc,
                "limit": len(vlist) or 12, "total": pc * 12}

    # ================= 详情 =================
    @staticmethod
    def _norm_id(ids):
        if isinstance(ids, (list, tuple)):
            raw = str(ids[0]) if ids else ""
        else:
            raw = str(ids if ids is not None else "")
        raw = raw.split("#")[0].split(",")[0].strip()
        raw = re.sub(r'^https?://[^/]+/', '', raw)
        raw = re.sub(r'^videos/', '', raw).strip("/")
        return raw

    def detailContent(self, ids):
        code = self._norm_id(ids)
        # 误点 folder 条目时不炸
        if code.startswith("model:") or code.startswith("g:"):
            return {"list": []}

        html = self._fetch(f"{self.HOST}/videos/{code}", retry=3)
        vod = {
            "vod_id": code, "vod_name": code,
            "vod_pic": f"{self.CDN}/storage/{code}/preview.jpg",
            "vod_year": "", "vod_area": "日本", "vod_remarks": "",
            "vod_actor": "", "vod_director": "", "vod_content": "",
            "type_name": "",
            "vod_play_from": "18JAV",
            "vod_play_url": "正片$" + code,   # ★ 只存番号, 播放时换新签名
        }
        if not html:
            print(f"[18jav] detail fetch failed: {code}")
            return {"list": [vod]}

        m = (re.search(r'<div class="header-left">\s*<h4>(.*?)</h4>', html, re.S)
             or re.search(r'og:title"\s+content="([^"]*)"', html)
             or re.search(r'<title>([^<]*)</title>', html))
        if m:
            vod["vod_name"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip()

        m = re.search(r'og:image"\s+content="([^"]*)"', html)
        if m:
            vod["vod_pic"] = m.group(1)

        actors = re.findall(r'href="[^"]*?/models/[^"]+"[^>]*>\s*<span[^>]*title="([^"]+)"', html)
        if actors:
            vod["vod_actor"] = ",".join(dict.fromkeys(actors))

        # 本片标签只在含 /tags/ 的那个 h5 内(侧栏是全站标签云, 要排除)
        own, cats = [], []
        m = re.search(r'<h5[^>]*>((?:(?!</h5>).)*?/tags/(?:(?!</h5>).)*?)</h5>', html, re.S)
        if m:
            blk = m.group(1)
            cats = [x.strip() for x in re.findall(r'class="cat"[^>]*>([^<]+)</a>', blk)] \
                or [x.strip() for x in
                    re.findall(r'href="[^"]*?/categories/[^"]+"[^>]*>([^<]+)</a>', blk)]
            own = [x.strip() for x in re.findall(r'href="[^"]*?/tags/[^"]+"[^>]*>([^<]+)</a>', blk)]
        allt = list(dict.fromkeys(cats + own))
        if allt:
            vod["type_name"] = "/".join(allt[:6])

        m = re.search(r'#icon-clock"></use></svg>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            vod["vod_remarks"] = m.group(1).strip()

        desc = []
        if allt:
            desc.append("标签: " + "/".join(allt))
        if vod["vod_actor"]:
            desc.append("女優: " + vod["vod_actor"])
        m = re.search(r'#icon-eye"></use></svg>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            desc.append("觀看: " + m.group(1).strip())
        vod["vod_content"] = " | ".join(desc) or vod["vod_name"]
        return {"list": [vod]}

    # ================= 播放 =================
    def _resolve_hls(self, code):
        html = self._fetch(f"{self.HOST}/videos/{code}", retry=3)
        if not html:
            return ""
        m = re.search(r'var\s+hlsUrl\s*=\s*"([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m:
            return m.group(1)
        m = re.search(r'og:video"\s+content="([^"]+)"', html)
        return m.group(1) if m else ""

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        target = raw.split("$", 1)[1].strip() if "$" in raw else raw.strip()
        url = target if (".m3u8" in target or ".mp4" in target) \
            else self._resolve_hls(self._norm_id(target))
        if not url:
            print(f"[18jav] play resolve FAILED: {target}")
            return {"parse": 0, "url": "", "header": {}}
        print(f"[18jav] play -> {url[:110]}")
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": self.UA, "Referer": self.HOST + "/"}}

    # ================= 搜索 =================
    def searchContent(self, key, quick=False, pg="1"):
        key = str(key or "").strip()
        page = int(pg or 1)
        if not key:
            return {"list": []}
        low = key.lower()

        # 1) 命中主題名 / 标签名 / slug -> 直接列表
        for prefix, table in (("categories/", self.CATS),
                              ("tags/", [t for _, _, ts in self.GROUPS for t in ts])):
            for slug, name in table:
                if key == name or low == slug.lower():
                    html = self._fetch(self._vurl(prefix + slug, "release_at", page))
                    vlist = self._parse_list(html)
                    if vlist:
                        return {"list": vlist, "page": page,
                                "pagecount": self._pagecount(html, page),
                                "limit": len(vlist), "total": 9999}

        # 2) 女優名 -> 她的片单
        mhtml = self._fetch(self._murl("topic_nums", 1), retry=1)
        for mm in self._parse_models(mhtml):
            if mm["vod_name"] == key:
                slug = mm["vod_id"].split(":", 1)[1]
                html = self._fetch(self._vurl("models/" + slug, "release_at", page))
                vlist = self._parse_list(html)
                if vlist:
                    return {"list": vlist, "page": page,
                            "pagecount": self._pagecount(html, page),
                            "limit": len(vlist), "total": 9999}

        if page > 1:
            return {"list": []}

        # 3) 番号直查
        if re.match(r'^[A-Za-z0-9][A-Za-z0-9\-_]{2,}$', key):
            d = (self.detailContent(key).get("list") or [{}])[0]
            if d.get("vod_name") and d["vod_name"].lower() != key.lower():
                return {"list": [{"vod_id": d["vod_id"], "vod_name": d["vod_name"],
                                  "vod_pic": d["vod_pic"],
                                  "vod_remarks": d.get("vod_remarks", "")}]}

        # 4) 降级: 扫榜单按标题过滤
        hits, seen = [], set()
        for path in ("latest-updates", "hot"):
            for p in range(1, 6):
                html = self._fetch(self._vurl(path, "release_at", p), retry=1)
                if not html:
                    break
                for v in self._parse_list(html):
                    k = v["vod_id"].lower()
                    if k in seen:
                        continue
                    if key in v["vod_name"] or low in v["vod_name"].lower():
                        seen.add(k)
                        hits.append(v)
                if len(hits) >= 24:
                    break
            if len(hits) >= 24:
                break
        return {"list": hits}

    def localProxy(self, param):
        return None
