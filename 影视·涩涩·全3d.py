# -*- coding: utf-8 -*-
"""
rule34video.com TVBox/影视仓 T4 Python 爬虫源  (中文版)
==============================================================
平台: KVS (Kernel Video Sharing) 变体, block_id 带 custom_ 前缀

发现页 12 个顶级分类:
  最近更新 / 最多观看 / 最高评分 / 作品主题 / 作者列表
  类型画风 / 身材外观 / 角色设定 / 行为体位 / 剧情关系 / Futa专区 / 声音视角

接口要点 (全部实测):
  列表分页  /{path}/?mode=async&function=get_block&block_id={BLOCK}
              &sort_by={post_date|video_viewed|rating|most_favourited|duration}
              &flag1={|2109|192|15|4747|1821}&from={N}
            ★ 必须走 async: 整页第1页序列与 async 不一致, 会跨页重复
            ★ latest-updates 块只认 post_date, 换排序返回 0 条
  搜索分页  页码参数是 from_videos (不是 from), 否则每页都返回第 1 页
  详情      /video/{id}/{slug}/   ★ 无 slug 会 404, 用 '-' 占位即可
  播放      详情页 flashvars: video_url / video_alt_url / video_alt_url2 / _url3
            = 360p / 480p / 720p / 1080p 的 mp4 直链, 带 ?v-acctoken= 签名
            ★ token 每次请求详情页都重签 -> 只在 playerContent 实时解析
            ★ 无需 Referer, 支持 Range (HTTP 206)
"""
import re
import time

try:
    from base.spider import BaseSpider
except Exception:
    class BaseSpider:
        pass


class Spider(BaseSpider):

    HOST = "https://rule34video.com"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 各页面对应的 KVS 块 id (传错块 id 会返回 0 条)
    B_LATEST = "custom_list_videos_latest_videos_list"
    B_COMMON = "custom_list_videos_common_videos"
    B_SEARCH = "custom_list_videos_videos_list_search"
    B_MODELS = "list_models_models_list"
    B_CATS = "list_categories_categories_list"

    # 榜单: (tid, 中文名, 路径, 块id)
    RANKS = [
        ("latest", "最近更新", "latest-updates", B_LATEST),
        ("popular", "最多观看", "most-popular", B_COMMON),
        ("rated", "最高评分", "top-rated", B_COMMON),
    ]

    VSORTS = [("post_date", "最新发布"), ("video_viewed", "观看最多"),
              ("rating", "评分最高"), ("most_favourited", "收藏最多"),
              ("duration", "时长最长")]
    FLAGS = [("", "全部"), ("2109", "男女"), ("192", "男同"),
             ("15", "Futa"), ("4747", "音乐MV"), ("1821", "Iwara")]
    CSORTS = [("total_videos", "影片最多"), ("title", "名称排序"),
              ("avg_videos_popularity", "最受欢迎"), ("avg_videos_rating", "评分最高")]

    # ---- 标签分组 (标签 ID 全部实测有效, 名称已汉化) ----
    GROUPS = [
        ("style", "类型画风", [
            ("366", "2D动画"), ("37514", "MMD"), ("1147", "CGI建模"),
            ("1144", "动画"), ("861", "游戏"), ("1970", "游戏实况"),
            ("35217", "游戏画廊"), ("883", "里番"), ("305", "兽人"),
            ("1512", "拟人兽"), ("1821", "Iwara"), ("4747", "PMV"),
            ("2111", "音乐"), ("3215", "4K高清"), ("1287", "VR"),
            ("360", "循环"), ("4787", "Patreon"),
        ]),
        ("body", "身材外观", [
            ("1091", "巨乳"), ("118452", "大胸"), ("92259", "超大巨乳"),
            ("92264", "极巨乳"), ("6929", "大臀"), ("39924", "极巨臀"),
            ("4426", "粗腿"), ("3739", "丰满"), ("1047", "长发"),
            ("66949", "金发"), ("298", "红发"), ("2878", "粉发"),
            ("107", "乳摇"), ("70534", "臀摇"), ("2273", "哥特"),
            ("1543", "乳环"), ("40276", "运动服"), ("2011", "内裤半褪"),
        ]),
        ("role", "角色设定", [
            ("15", "Futa"), ("1010", "女性"), ("2009", "裸体女性"),
            ("2031", "单人女"), ("477", "独处"), ("1898", "一女"),
            ("1897", "一男"), ("560", "熟女"), ("565", "魅魔"),
            ("4385", "魅魔尾"), ("65744", "恶魔"), ("3094", "姐妹"),
            ("4198", "啦啦队"), ("397", "孕妇"), ("4692", "丑男"),
            ("358", "马"), ("29456", "V家"),
        ]),
        ("act", "行为体位", [
            ("2073", "中出"), ("4161", "肛内中出"), ("22", "口交"),
            ("353", "深喉"), ("6948", "口爆"), ("159", "吞精"),
            ("55", "颜射"), ("60", "射精"), ("50", "乳交"),
            ("122", "手交"), ("13", "肛交"), ("11", "后入"),
            ("5478", "站立后入"), ("1901", "骑乘"), ("2910", "传教士"),
            ("1083", "背后"), ("2863", "指奸"), ("1911", "插入"),
            ("2151", "女性被插入"), ("4", "双插"), ("8", "群交"),
            ("104", "前后夹击"), ("5929", "男女性爱"), ("43", "百合"),
            ("192", "男同"), ("9802", "性爱"), ("5913", "沙滩性爱"),
            ("7257", "紧致"), ("5717", "骑乘摇动"),
        ]),
        ("plot", "剧情关系", [
            ("2585", "NTR"), ("1441", "出轨"), ("5043", "出轨人妻"),
            ("175", "乱伦"), ("1440", "绿帽"), ("4264", "绿帽视角"),
            ("2054", "女性主导"), ("24", "束缚"), ("127", "BDSM"),
            ("2799", "捆手"), ("1072", "打屁股"), ("3102", "触手"),
            ("3237", "怪物"), ("3886", "被附身"), ("26548", "成长"),
            ("11257", "胸部成长"), ("3218", "哭泣"), ("587", "吞食"),
        ]),
        ("futa", "Futa专区", [
            ("15", "Futa"), ("3254", "Futa对女"), ("4575", "Futa更大"),
            ("2577", "Futa插入"), ("137", "Futa对Futa"), ("378", "Futa对男"),
            ("3513", "巨根"), ("2983", "超巨根"), ("1515", "大根"),
            ("5978", "大黑根"), ("38136", "极巨蛋"), ("11120", "超巨蛋"),
        ]),
        ("sound", "声音视角", [
            ("3593", "女性呻吟"), ("2584", "愉悦呻吟"), ("23", "有声"),
            ("6346", "性爱音效"), ("5723", "尖叫"), ("1064", "高潮"),
            ("2106", "女性高潮"), ("2", "POV"), ("5959", "主视角"),
            ("2634", "POV对视"), ("4843", "体内视角"), ("1890", "情趣玩具"),
            ("1195", "跳蛋"), ("11271", "特写"),
        ]),
    ]

    # ---- 作品主题名称汉化表 (站点返回英文, 这里映射常见作品) ----
    CAT_CN = {
        "3D": "3D建模", "2D": "2D动画", "MMD": "MMD舞蹈", "iwara": "Iwara",
        "Hentai": "里番动画", "Koikatsu": "恋活", "original": "原创",
        "Overwatch": "守望先锋", "Genshin Impact": "原神",
        "zenless zone zero": "绝区零", "Honkai Star Rail": "崩坏：星穹铁道",
        "Honkai Impact": "崩坏3", "Wuthering Waves": "鸣潮",
        "Final Fantasy": "最终幻想", "Final Fantasy vii": "最终幻想7",
        "final fantasy vii remake": "最终幻想7 重制版",
        "final fantasy xiv": "最终幻想14",
        "Resident Evil": "生化危机", "Resident Evil 8: Village": "生化危机8 村庄",
        "Resident Evil 2 Remake": "生化危机2 重制版",
        "Resident Evil 4 Remake": "生化危机4 重制版",
        "Pokemon": "宝可梦", "Dead or Alive": "死或生", "Dead or Alive 5": "死或生5",
        "Sonic the Hedgehog": "索尼克", "Hololive": "Hololive",
        "League of Legends": "英雄联盟", "Marvel": "漫威",
        "Marvel Rivals": "漫威争锋", "DC Comics": "DC漫画", "DC Universe": "DC宇宙",
        "The Elder Scrolls V: Skyrim": "上古卷轴5 天际",
        "Five Nights at Freddy's": "玩具熊的五夜后宫",
        "Fortnite": "堡垒之夜", "Street Fighter": "街头霸王",
        "Nier Automata": "尼尔 机械纪元",
        "My Little Pony Friendship is Magic": "小马宝莉",
        "blue archive": "蔚蓝档案", "World of Warcraft": "魔兽世界",
        "The sims": "模拟人生", "The sims 4": "模拟人生4",
        "My Hero Academia": "我的英雄学院", "Kantai Collection": "舰队Collection",
        "vocaloid": "V家 初音", "Mugen": "Mugen", "VR Chat": "VRChat",
        "Azur Lane": "碧蓝航线", "Naruto": "火影忍者",
        "fate grand order": "FGO", "Fate": "Fate", "The Witcher": "巫师",
        "The Witcher 3: Wild Hunt": "巫师3 狂猎", "Roblox": "Roblox",
        "Tomb Raider": "古墓丽影", "Cyberpunk 2077": "赛博朋克2077",
        "Touhou": "东方Project", "The Legend of Zelda": "塞尔达传说",
        "Uma Musume": "赛马娘", "Wild Life": "Wild Life",
        "Mass Effect": "质量效应", "Mortal Kombat": "真人快打",
        "Super Mario": "超级马力欧", "Mario": "马力欧",
        "helluva boss": "极恶老大", "Metroid": "银河战士",
        "Baldurs Gate": "博德之门", "One Piece": "海贼王",
        "stellar blade": "剑星", "Taimanin RPGX": "对魔忍", "Asmr": "ASMR",
        "Honey Select": "Honey Select", "Honey Select 2": "Honey Select 2",
        "Rwby": "RWBY", "Second Life": "第二人生",
        "chainsaw man": "电锯人", "Teen Titans": "少年泰坦",
        "Tekken": "铁拳", "Elden Ring": "艾尔登法环", "Minecraft": "我的世界",
        "Persona": "女神异闻录", "Nikke: Goddess of Victory": "妮姬 胜利女神",
        "Spiderman": "蜘蛛侠", "Batman": "蝙蝠侠", "Apex Legends": "Apex英雄",
        "Dragon Ball": "龙珠", "Dragon Ball Z": "龙珠Z",
        "Soul Calibur": "灵魂能力", "Digimon": "数码宝贝", "Bleach": "死神",
        "Disney": "迪士尼", "Undertale": "传说之下", "Star Wars": "星球大战",
        "Animal Crossing": "动物森友会", "Kimetsu no Yaiba": "鬼灭之刃",
        "The Last of Us 2": "最后生还者2", "Splatoon": "斯普拉遁",
        "arknights": "明日方舟", "Doujin game": "同人游戏",
        "Dress up Darling": "更衣人偶", "Life is Strange": "奇异人生",
        "kono subarashii sekai ni shukufuku wo!": "为美好的世界献上祝福",
        "sousou no frieren | frieren beyond journeys end": "葬送的芙莉莲",
        "King of Fighters": "拳皇", "Halo": "光环", "Beat Banger": "Beat Banger",
        "Virt-A-Mate": "Virt-A-Mate", "Heroine Rumble 2": "Heroine Rumble 2",
        "tmp": "其他",
    }

    # ================= 生命周期 =================
    def init(self, extend=""):
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.HOST + "/",
        }
        self._sess = None
        try:
            import requests
            self._sess = requests.Session()
            self._sess.headers.update(self.headers)
        except Exception:
            pass

    def destroy(self):
        try:
            if self._sess:
                self._sess.close()
        except Exception:
            pass

    def getName(self):
        return "R34视频"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(mp4|m3u8|flv|mkv|webm)(/|\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    # ================= 网络 =================
    def _direct_get(self, url, timeout=30, allow_redirects=True):
        """绕过 peekpro2 注入的代理垫片, 直连上游取详情页。成功返回 Response, 否则 None。

        背景: 上游新增 kt_acctoken 防盗链 —— 播放 token 绑定"取详情页那次连接的 IP",
        而 kt_acctoken 的值就是那个 IP 的 base64。播放器最终是从设备直连取 mp4 的
        (设备 IP 本来就暴露给上游), 所以详情请求走直连不额外损失隐私, 且能拿到
        设备绑定的 kt_acctoken cookie; 垫片会剥 Set-Cookie, 走垫片永远拿不到它,
        播放必 403。

        实现: 垫片 patch 时把原始 requests.Session.request 存在自己的闭包里,
        取出来直接调用即可直连。仅检测到垫片时才走此路径, 取不到或直连失败
        一律静默返回 None, 由调用方回退常规 _fetch(走垫片/网关)。
        """
        try:
            import requests
            if not getattr(requests, "_pp2_patched", False):
                return None
            patched = requests.Session.request
            orig = None
            if getattr(patched, "__closure__", None):
                for cell in patched.__closure__:
                    try:
                        v = cell.cell_contents
                    except ValueError:
                        continue
                    if callable(v) and getattr(v, "__module__", "") == "requests.sessions":
                        orig = v
                        break
            if orig is None or self._sess is None:
                return None
            r = orig(self._sess, "GET", url, timeout=timeout,
                     allow_redirects=allow_redirects)
            if r is not None and getattr(r, "status_code", 0) == 200 and r.text:
                r.encoding = "utf-8"
                return r
        except Exception:
            pass
        return None

    def _player_cookie(self, keep=None):
        """会话里上游的防盗链 cookie 串, 供播放器原样带上。"""
        if keep is None:
            keep = ("kt_acctoken", "__ddg8_", "__ddg1_", "__ddg9_", "PHPSESSID")
        try:
            if self._sess is None:
                return ""
            return "; ".join("%s=%s" % (k, v)
                             for k, v in self._sess.cookies.items() if k in keep)
        except Exception:
            return ""

    def _fetch(self, url, timeout=18, retry=2):
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

    def _block_url(self, path, block, page=1, sort_by="post_date", flag1="",
                   extra="", page_key="from"):
        """★ 始终走 async block: 整页第1页序列与 async 不一致, 会造成跨页重复
           ★ 搜索块页码参数是 from_videos, 传 from 会恒定返回第 1 页"""
        base = f"{self.HOST}/{str(path).strip('/')}/"
        u = (f"{base}?mode=async&function=get_block&block_id={block}"
             f"&sort_by={sort_by}&{page_key}={max(1, int(page))}")
        if flag1:
            u += f"&flag1={flag1}"
        if extra:
            u += extra
        return u

    # ================= 解析 =================
    def _parse_list(self, html):
        """
        卡片: <div class="item thumb ..." data-video-card-id="ID">
                <a class="th" href=".../video/ID/slug/" title="标题">
                  <img data-original="...320x180/3.jpg">
                  <div class="time">2:19</div>
        """
        out, seen = [], set()
        for b in re.split(r'(?=<div class="item thumb)', html):
            m = re.search(r'href="[^"]*?/video/(\d+)/([^"/]*)/?"[^>]*title="([^"]*)"', b)
            if not m:
                continue
            vid, slug, title = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)

            pic = ""
            p = (re.search(r'data-original="([^"]+)"', b)
                 or re.search(r'<img[^>]+src="(https?://[^"]+)"', b))
            if p:
                pic = p.group(1)

            dur = ""
            d = re.search(r'<div class="time">([^<]*)</div>', b)
            if d:
                dur = d.group(1).strip()

            rate = ""
            r = re.search(r'>\s*(\d+%)\s*(?:\(|<)', b)
            if r:
                rate = r.group(1)

            marks = [x for x in (dur, "高清" if "custom-hd" in b else "", rate) if x]
            out.append({
                "vod_id": f"{vid}/{slug}" if slug else vid,
                "vod_name": self._unescape(title) or vid,
                "vod_pic": pic,
                "vod_remarks": " ".join(marks),
            })
        return out

    @staticmethod
    def _unescape(s):
        s = str(s or "")
        for a, b in (("&amp;", "&"), ("&#34;", '"'), ("&quot;", '"'),
                     ("&#39;", "'"), ("&apos;", "'"), ("&lt;", "<"),
                     ("&gt;", ">"), ("&nbsp;", " ")):
            s = s.replace(a, b)
        return re.sub(r'\s+', ' ', s).strip()

    def _parse_models(self, html):
        """作者卡片 -> folder 条目, 点击进入其作品列表"""
        out, seen = [], set()
        for b in re.split(r'(?=<div class="item)', html):
            m = re.search(r'href="[^"]*?/models/([^"/?]+)/"', b)
            if not m:
                continue
            slug = m.group(1)
            if slug.lower() in seen:
                continue
            seen.add(slug.lower())
            n = (re.search(r'<div class="name">([^<]*)</div>', b)
                 or re.search(r'alt="([^"]*)"', b))
            p = (re.search(r'data-original="(https?://[^"]+)"', b)
                 or re.search(r'<img[^>]+src="(https?://[^"]+)"', b))
            c = re.search(r'<span>(\d+%)</span>', b)
            out.append({
                "vod_id": "model:" + slug,
                "vod_name": self._unescape(n.group(1)) if n else slug,
                "vod_pic": p.group(1) if p else "",
                "vod_remarks": ("好评 " + c.group(1)) if c else "",
                "vod_tag": "folder",
                "style": {"type": "oval", "ratio": 1.0},
            })
        return out

    def _parse_cats(self, html):
        """
        主題卡片两种 markup:
          async 块 : <div class="thumb item"><a class="th" href="/categories/3d/">
                       <img src=".."><div class="thumb_title">3D</div>
          索引页   : <a href="/categories/ben-10/" class="item"><div class="position">3</div>
                       <img ..><div class="name">Ben 10<div class="count">..359
        """
        out, seen = [], set()
        # ★ 先切到 items 容器: nav/sidebar 也有大量 /categories/ 链接
        i = html.find(self.B_CATS + "_items")
        if i >= 0:
            html = html[i:]
        # ★ 再切掉分页容器: 分页锚点 /categories/2/ 形状与卡片一致
        j = html.find(self.B_CATS + "_pagination")
        if j > 0:
            html = html[:j]

        for b in re.split(r'(?=<a\s[^>]*href="[^"]*?/categories/[a-z0-9-]+/")', html):
            m = re.match(r'<a\s[^>]*href="[^"]*?/categories/([a-z0-9-]+)/"', b)
            if not m:
                continue
            slug = m.group(1)
            if slug.isdigit() or slug in seen:
                continue
            seen.add(slug)
            seg = b[:1200]

            n = (re.search(r'<div class="thumb_title">([^<]*)</div>', seg)
                 or re.search(r'<div class="name">\s*([^<]{1,60})', seg)
                 or re.search(r'<img[^>]+alt="([^"]*)"', seg))
            raw = self._unescape(n.group(1)) if n else slug.replace("-", " ")
            name = self.CAT_CN.get(raw, raw)

            cnt = ""
            c = (re.search(r'<div class="count">(?:(?!</div>).)*?([\d][\d,]*)\s*<', seg, re.S)
                 or re.search(r'<span>\s*([\d][\d,]*)\s*</span>', seg))
            if c:
                cnt = c.group(1)

            p = re.search(r'<img[^>]+(?:data-original|src)="(https?://[^"]+)"', seg)
            out.append({
                "vod_id": "cat:" + slug,
                "vod_name": name[:40],
                "vod_pic": p.group(1) if p else "",
                "vod_remarks": (cnt + " 部") if cnt else "",
                "vod_tag": "folder",
            })
        return out

    @staticmethod
    def _pagecount(html, default=1):
        nums = [int(x) for x in re.findall(r'from(?:_videos\+from_albums)?:(\d+)',
                                          html or "")]
        return max(nums) if nums else default

    # ================= 发现页 =================
    def homeContent(self, filter=""):
        classes = [{"type_id": k, "type_name": n} for k, n, _, _ in self.RANKS]
        classes += [
            {"type_id": "topic", "type_name": "作品主题"},
            {"type_id": "models", "type_name": "作者列表"},
        ]
        classes += [{"type_id": "g:" + g, "type_name": n} for g, n, _ in self.GROUPS]

        vsort = {"key": "sort", "name": "排序",
                 "value": [{"n": n, "v": v} for v, n in self.VSORTS]}
        vflag = {"key": "flag", "name": "取向",
                 "value": [{"n": n, "v": v} for v, n in self.FLAGS]}

        filters = {}
        for k, _, _, blk in self.RANKS:
            # latest 块只吃 post_date, 换排序会返回空, 故只给取向筛选
            filters[k] = [vflag] if blk == self.B_LATEST else [vsort, vflag]
        filters["topic"] = [{"key": "csort", "name": "排序",
                             "value": [{"n": n, "v": v} for v, n in self.CSORTS]}]
        for gid, gname, tags in self.GROUPS:
            filters["g:" + gid] = [
                {"key": "tag", "name": gname,
                 "value": [{"n": n, "v": t} for t, n in tags]},
                vsort, vflag,
            ]

        return {"class": classes, "filters": filters,
                "list": self.homeVideoContent().get("list", [])}

    def homeVideoContent(self):
        html = self._fetch(self._block_url("latest-updates", self.B_LATEST, 1))
        return {"list": self._parse_list(html)}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter=True, extend=None):
        page = int(pg or 1)
        e = extend or {}
        tid = str(tid or "").strip()

        # --- 作品主题索引 (folder) ---
        if tid == "topic":
            csort = e.get("csort") or "total_videos"
            html = self._fetch(self._block_url("categories", self.B_CATS, page, csort))
            cats = self._parse_cats(html)
            pc = self._pagecount(html, page if cats else 1)
            return {"list": cats, "page": page, "pagecount": pc,
                    "limit": len(cats) or 36, "total": pc * 36}

        # --- 作者索引 (folder) ---
        if tid == "models":
            html = self._fetch(self._block_url("models", self.B_MODELS, page, ""))
            ms = self._parse_models(html)
            pc = self._pagecount(html, page if ms else 1)
            return {"list": ms, "page": page, "pagecount": pc,
                    "limit": len(ms) or 48, "total": pc * 48}

        sort_by = e.get("sort") or "post_date"
        flag1 = e.get("flag") or ""

        if tid.startswith("g:"):
            gid = tid[2:]
            tag_id = e.get("tag") or ""
            if not tag_id:
                for g, _, tags in self.GROUPS:
                    if g == gid and tags:
                        tag_id = tags[0][0]
                        break
            path, block = f"tags/{tag_id or '15'}", self.B_COMMON
        elif tid.startswith("tag:"):
            path, block = "tags/" + tid[4:], self.B_COMMON
        elif tid.startswith("cat:"):
            path, block = "categories/" + tid[4:], self.B_COMMON
        elif tid.startswith("model:"):
            path, block = "models/" + tid[6:], self.B_COMMON
        else:
            hit = [(p, b) for k, _, p, b in self.RANKS if k == tid]
            path, block = hit[0] if hit else ("latest-updates", self.B_LATEST)
            if block == self.B_LATEST:
                sort_by = "post_date"

        html = self._fetch(self._block_url(path, block, page, sort_by, flag1))
        vlist = self._parse_list(html)
        # ★ 榜单页 (most-popular / top-rated) 与部分 flag1 组合站点直接返回空块
        #   (例: flag1=4747 音乐MV)。此时退化成不带 flag1 再取一次, 避免空白页
        if not vlist and flag1:
            html = self._fetch(self._block_url(path, block, page, sort_by, ""))
            vlist = self._parse_list(html)
        pc = self._pagecount(html, page if vlist else 1)
        per = len(vlist) or 24
        return {"list": vlist, "page": page, "pagecount": pc,
                "limit": per, "total": pc * per}

    # ================= 详情 =================
    @staticmethod
    def _norm_id(ids):
        """兼容 list/str/int, 支持 '4587243' / '4587243/slug' / 完整 URL"""
        if isinstance(ids, (list, tuple)):
            raw = str(ids[0]) if ids else ""
        else:
            raw = str(ids if ids is not None else "")
        raw = raw.split("#")[0].split(",")[0].strip()
        m = re.search(r'/video/(\d+)(?:/([^/?]*))?', raw)
        if m:
            return m.group(1), (m.group(2) or "")
        raw = raw.strip("/")
        if "/" in raw:
            a, b = raw.split("/", 1)
            if a.isdigit():
                return a, b.strip("/")
        m = re.search(r'(\d{3,})', raw)
        return (m.group(1) if m else raw), ""

    def _detail_url(self, vid, slug=""):
        """★ /video/{id}/ 无 slug 会 404, 任意占位 slug 都能正常返回"""
        return f"{self.HOST}/video/{vid}/{slug or '-'}/"

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        if isinstance(raw, str) and (raw.startswith("model:") or raw.startswith("cat:")):
            return {"list": []}

        vid, slug = self._norm_id(ids)
        html = self._fetch(self._detail_url(vid, slug), retry=3)
        vod = {
            "vod_id": f"{vid}/{slug}" if slug else vid,
            "vod_name": vid, "vod_pic": "", "vod_year": "", "vod_area": "",
            "vod_remarks": "", "vod_actor": "", "vod_director": "",
            "vod_content": "", "type_name": "",
            "vod_play_from": "R34视频", "vod_play_url": "",
        }
        if not html:
            print(f"[r34] 详情抓取失败: {vid}")
            vod["vod_play_url"] = "正片$" + vod["vod_id"]
            return {"list": [vod]}

        m = (re.search(r"video_title:\s*'((?:[^'\\]|\\.)*)'", html)
             or re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S))
        if m:
            vod["vod_name"] = self._unescape(re.sub(r'<[^>]+>', '', m.group(1)))

        m = re.search(r"video_models:\s*'((?:[^'\\]|\\.)*)'", html)
        if m and m.group(1).strip():
            vod["vod_actor"] = self._unescape(m.group(1))

        m = re.search(r"video_categories:\s*'((?:[^'\\]|\\.)*)'", html)
        if m and m.group(1).strip():
            cats = [self.CAT_CN.get(x.strip(), x.strip())
                    for x in self._unescape(m.group(1)).split(",") if x.strip()]
            vod["type_name"] = "/".join(cats[:6])

        tags = ""
        m = re.search(r"video_tags:\s*'((?:[^'\\]|\\.)*)'", html)
        if m:
            tags = self._unescape(m.group(1))

        infos = [self._unescape(re.sub(r'<[^>]+>', '', x))
                 for x in re.findall(r'<div class="item_info">(.*?)</div>', html, re.S)]
        infos = [x for x in infos if x]
        rate = re.search(r'class="voters count"[^>]*>([^<]+)<', html)
        # infos 顺序: 发布时间 / 观看数 / 时长
        dur = infos[2] if len(infos) > 2 else ""
        vod["vod_remarks"] = " ".join(
            x for x in (dur, ("好评 " + rate.group(1).strip()) if rate else "") if x)
        if infos:
            vod["vod_year"] = infos[0]

        p = re.search(r'(https?://[^"\']+/videos_screenshots/\d+/' + re.escape(vid)
                      + r'/(?:320x180|336x189)/\d+\.jpg)', html)
        if p:
            vod["vod_pic"] = p.group(1)
        else:
            p = re.search(r'preview_url\s*:\s*[\'"]([^\'"]+)[\'"]', html)
            if p:
                vod["vod_pic"] = p.group(1)

        desc = []
        if vod["type_name"]:
            desc.append("主题: " + vod["type_name"])
        if vod["vod_actor"]:
            desc.append("作者: " + vod["vod_actor"])
        if len(infos) > 1:
            desc.append("观看: " + infos[1])
        if tags:
            desc.append("标签: " + tags)
        vod["vod_content"] = " | ".join(desc) or vod["vod_name"]

        # 播放线路: 站点提供 360/480/720/1080 四档
        # ★ mp4 直链带 v-acctoken 签名, 每次请求详情页都会重签
        #   -> 这里只登记清晰度档位, 真实地址在 playerContent 现取
        qs = self._quality_map(html)
        if qs:
            vod["vod_play_from"] = "$$$".join(q[0] for q in qs)
            vod["vod_play_url"] = "$$$".join(
                f"{q[0]}${vod['vod_id']}|{q[1]}" for q in qs)
        else:
            vod["vod_play_url"] = "正片$" + vod["vod_id"]
        return {"list": [vod]}

    # ================= 播放 =================
    QKEYS = [("video_url", "video_url_text"),
             ("video_alt_url", "video_alt_url_text"),
             ("video_alt_url2", "video_alt_url2_text"),
             ("video_alt_url3", "video_alt_url3_text"),
             ("video_alt_url4", "video_alt_url4_text")]

    def _quality_map(self, html):
        """返回 [(档名, flashvars字段), ...], 高清优先"""
        out = []
        for ukey, tkey in self.QKEYS:
            if not re.search(ukey + r":\s*'(https?://[^']+)'", html):
                continue
            t = re.search(tkey + r":\s*'([^']*)'", html)
            out.append(((t.group(1).strip() if t and t.group(1).strip() else ukey), ukey))

        def rank(x):
            n = re.search(r'(\d+)', x[0])
            return -int(n.group(1)) if n else 0
        out.sort(key=rank)
        return out

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        target = raw.split("$", 1)[1].strip() if "$" in raw else raw.strip()

        want = ""
        if "|" in target:
            target, want = target.split("|", 1)
            want = want.strip()

        if re.search(r'\.mp4|\.m3u8', target):
            url = target
        else:
            vid, slug = self._norm_id(target)
            durl = self._detail_url(vid, slug)
            html = ""
            # 详情请求优先直连: 只有直连才能拿到设备绑定的 kt_acctoken,
            # 否则播放器带不上防盗链 cookie, 上游一律 403。
            dr = self._direct_get(durl)
            if dr is not None and ("flashvars" in dr.text or "get_file" in dr.text):
                html = dr.text
            if not html:
                html = self._fetch(durl, retry=3)
            url = ""
            if html:
                if want:
                    m = re.search(want + r":\s*'(https?://[^']+)'", html)
                    if m:
                        url = m.group(1)
                if not url:
                    for _, ukey in self._quality_map(html):
                        m = re.search(ukey + r":\s*'(https?://[^']+)'", html)
                        if m:
                            url = m.group(1)
                            break
                if not url:
                    m = re.search(
                        r'href="(https?://[^"]*/get_file/[^"]*\.mp4/[^"]*)"', html)
                    if m:
                        url = m.group(1)

        if not url:
            print(f"[r34] 播放解析失败: {target} 档位={want}")
            return {"parse": 0, "url": "", "header": self._player_header()}

        print(f"[r34] 播放 {want or '自动'} -> {url[:100]}")
        return {"parse": 0, "playUrl": "", "url": url,
                "header": self._player_header()}

    def _player_header(self):
        """播放器请求头。

        关键: 必须带上 kt_acctoken。上游校验播放 URL 时会比对 cookie 里的
        kt_acctoken 与 URL 中 v-acctoken 的签名来源, 缺了直接 403。
        """
        h = {"User-Agent": self.UA, "Referer": self.HOST + "/"}
        ck = self._player_cookie()
        if ck:
            h["Cookie"] = ck
        return h

    # ================= 搜索 =================
    def searchContent(self, key, quick=False, pg="1"):
        key = str(key or "").strip()
        page = int(pg or 1)
        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}
        try:
            from urllib.parse import quote
            kw = quote(key)
        except Exception:
            kw = key.replace(" ", "%20")

        # ★ 页码参数是 from_videos (不是 from), 否则每页都返回第 1 页
        html = self._fetch(self._block_url(
            f"search/{kw}", self.B_SEARCH, page, "post_date",
            extra=f"&q={kw}", page_key="from_videos"))
        vlist = self._parse_list(html)

        # 站点只索引英文标签, 中文词直接搜为空 -> 用中文名反查主题/标签 slug
        if not vlist and page == 1:
            en = self._cn_to_en(key)
            if en:
                html = self._fetch(self._block_url(
                    en[0], self.B_COMMON, 1, "post_date"))
                vlist = self._parse_list(html)

        pc = self._pagecount(html, page if vlist else 1)
        return {"list": vlist, "page": page, "pagecount": pc,
                "limit": len(vlist) or 24, "total": pc * (len(vlist) or 24)}

    def _cn_to_en(self, key):
        """中文关键词 -> 站点路径。命中主题中文名 或 标签中文名"""
        k = key.strip()
        for slug_en, cn in self.CAT_CN.items():
            if k == cn:
                slug = re.sub(r'[^a-z0-9]+', '-', slug_en.lower()).strip('-')
                if slug:
                    return [f"categories/{slug}"]
        for _, _, tags in self.GROUPS:
            for tid, cn in tags:
                if k == cn:
                    return [f"tags/{tid}"]
        return []

    def localProxy(self, param):
        return None
