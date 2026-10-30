#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖阴 (douyin/dys18.com) TVBox py-class 爬虫源
AES-128-CBC 加密视频流站 · 竖屏短视频+分类网格

API: POST /api.php/api/video/* (AES加密响应)
  videolist(page) / videorecommend(video_id) / videocomment(video_id,page,limit) / uservideo(user_id)

播放: /media/m3u8?url=直链m3u8&exp=时间戳&token=哈希 (走站点代理)

加密: AES-128-CBC, key=2acf7e91e9864673, iv=1c29882d3ddfcfd6
依赖: pycryptodome (pip install pycryptodome)
"""
import gzip, io, json, base64, hashlib, re, sys, time, urllib.error, urllib.parse, urllib.request
from urllib.parse import quote, unquote, urlencode

try:
    from Crypto.Cipher import AES as ImageAES
    from Crypto.Util.Padding import unpad as unpad_img
except Exception:
    ImageAES = None

PROXY_BASE = "http://127.0.0.1:9978/proxy?do=py"

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def init(self, extend=""): pass
        def destroy(self): pass

class Spider(BaseSpider):
    SITE = {
        "name": "抖阴",
        "host": "https://0cd.odqvdlji.cc",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "timeout": 15,
        "retries": 3,
        "aes_key": "2acf7e91e9864673",
        "aes_iv":  "1c29882d3ddfcfd6",
        # 封面图片AES解密密钥 (从 crypto-worker.js 提取)
        "img_key": "102_53_100_57_54_53_100_102_55_53_51_51_54_50_55_48",
        "img_iv":  "57_55_98_54_48_51_57_52_97_98_99_50_102_98_101_49",
        "page_size": 20,
        "categories": [
            {"type_id": "35", "type_name": "首页推荐"},
            {"type_id": "51", "type_name": "分类一"},
            {"type_id": "47", "type_name": "分类二"},
            {"type_id": "5",  "type_name": "分类三"},
            {"type_id": "cat_01", "type_name": "萝莉少女"},
            {"type_id": "cat_02", "type_name": "母子乱伦"},
            {"type_id": "cat_03", "type_name": "成人动漫"},
            {"type_id": "cat_04", "type_name": "童颜巨乳"},
            {"type_id": "cat_05", "type_name": "校园师生"},
            {"type_id": "cat_06", "type_name": "自慰高潮"},
            {"type_id": "cat_07", "type_name": "偷拍自拍"},
            {"type_id": "cat_08", "type_name": "色情综艺"},
            {"type_id": "cat_09", "type_name": "原创传媒"},
            {"type_id": "cat_10", "type_name": "制服诱惑"},
            {"type_id": "cat_11", "type_name": "港台三级"},
            {"type_id": "cat_12", "type_name": "白虎嫩穴"},
            {"type_id": "cat_13", "type_name": "福利姬"},
            {"type_id": "cat_14", "type_name": "网黄主播"},
            {"type_id": "cat_15", "type_name": "欧美性爱"},
            {"type_id": "cat_16", "type_name": "内射中出"},
            {"type_id": "cat_17", "type_name": "探花约啪"},
            {"type_id": "cat_18", "type_name": "SM调教"},
            {"type_id": "cat_19", "type_name": "绿帽换妻"},
            {"type_id": "cat_20", "type_name": "日韩伦理"},
            {"type_id": "cat_21", "type_name": "AI换脸"},
            {"type_id": "cat_22", "type_name": "足交肛交"},
            {"type_id": "cat_23", "type_name": "同志男同"},
            {"type_id": "cat_24", "type_name": "女同拉拉"},
            {"type_id": "cat_25", "type_name": "熟女少妇"},
        ],
    }

    def init(self, extend=""):
        self.cfg = dict(self.SITE)
        self.host = self.cfg["host"].rstrip("/")
        self._headers = {
            "User-Agent": self.cfg["ua"],
            "Referer": self.host + "/",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        self._aes_key = self.cfg["aes_key"].encode("utf-8")
        self._aes_iv  = self.cfg["aes_iv"].encode("utf-8")
        self._cache = {}
        try:
            if extend:
                ex = extend if isinstance(extend, dict) else json.loads(extend)
                for k in ("host","ua","aes_key","aes_iv","name","timeout","retries"):
                    v = ex.get(k)
                    if v:
                        self.cfg[k] = v
                        if k == "host": self.host = str(v).rstrip("/")
                        if k == "aes_key": self._aes_key = str(v).encode("utf-8")
                        if k == "aes_iv": self._aes_iv = str(v).encode("utf-8")
        except Exception:
            pass
        return self

    def getName(self): return self.cfg.get("name", "抖阴")
    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(x in u for x in (".m3u8",".mp4",".flv",".mkv",".avi",".ts"))
    def manualVideoCheck(self): return False
    def destroy(self): return

    # ── AES ──
    def _aes_decrypt(self, b64_data):
        s = b64_data.replace('-','+').replace('_','/')
        pad_len = len(s) % 4
        if pad_len: s += '=' * (4 - pad_len)
        raw = base64.b64decode(s)
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        cipher = AES.new(self._aes_key, AES.MODE_CBC, self._aes_iv)
        pt = unpad(cipher.decrypt(raw), AES.block_size)
        return json.loads(pt.decode('utf-8'))

    # ── 图片AES解密 ──
    IMG_KEY = b"f5d965df75336270"
    IMG_IV  = b"97b60394abc2fbe1"

    def _decrypt_image(self, enc_data):
        """AES-128-CBC NoPadding 解密封面图 (从 crypto-worker.js 提取)"""
        from Crypto.Cipher import AES as ImgAES
        cipher = ImgAES.new(self.IMG_KEY, ImgAES.MODE_CBC, self.IMG_IV)
        dec = cipher.decrypt(enc_data)
        # 检测图片格式确定实际长度
        if dec[:2] == b'\xff\xd8':
            # JPEG: 找结束标记 FF D9
            end = dec.find(b'\xff\xd9', 2)
            if end >= 0:
                dec = dec[:end + 2]
            ctype = "image/jpeg"
        elif dec[:4] == b'\x89PNG':
            ctype = "image/png"
        elif dec[:6] in (b'GIF87a', b'GIF89a'):
            ctype = "image/gif"
        elif dec[:8] == b'RIFF' and dec[8:12] == b'WEBP':
            ctype = "image/webp"
        else:
            ctype = "image/jpeg"
        return dec, ctype

    def _pic_proxy_url(self, cover_url):
        """将加密封面直链包装成本地代理URL (localProxy 解密后返回)"""
        b64 = base64.b64encode(cover_url.encode()).decode()
        return "http://127.0.0.1:9978/proxy?do=py&type=img&url=" + b64

    def _post_api(self, path, data):
        full_url = self.host + path
        body = urllib.parse.urlencode(data).encode('utf-8')
        hdr = dict(self._headers)
        to = int(self.cfg.get("timeout", 15))
        retries = int(self.cfg.get("retries", 3))
        for i in range(retries):
            try:
                req = urllib.request.Request(full_url, data=body, headers=hdr, method='POST')
                resp = urllib.request.urlopen(req, timeout=to)
                raw = json.loads(resp.read().decode('utf-8'))
                if not raw.get("data"): return None
                return self._aes_decrypt(raw["data"])
            except urllib.error.HTTPError as e:
                if e.code in (404, 403): return None
            except Exception:
                pass
            if i < retries - 1: time.sleep(0.5 * (i + 1))
        return None

    def _get_videolist(self, page=1):
        res = self._post_api("/api.php/api/video/videolist", {"page": page})
        if not res: return []
        return res.get("data", {}).get("list", [])

    # ── 视频字段映射 ──
    def _video_to_vod(self, v):
        title = v.get("video_title") or "(无标题)"
        vid = str(v.get("id") or v.get("vid") or "")
        duration = v.get("video_duration") or v.get("duration", "")
        tags = ", ".join(v.get("tags") or [])
        likes = v.get("like_count", 0)
        user_name = v.get("user_name") or ""
        remark = " | ".join(filter(None, [duration, str(likes)]))
        desc_parts = [
            "标签: " + tags if tags else "",
            "作者: " + user_name if user_name else "",
            v.get("description") or "",
        ]
        return {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._pic_proxy_url(v.get("first_img") or v.get("cover_img") or ""),
            "vod_remarks": remark,
            "vod_content": "\n".join(filter(None, desc_parts)),
            "vod_duration": duration,
            "vod_play_url": title + "$" + vid,
            "vod_play_from": "抖阴",
            "vod_tags": tags,
            # 保存原始video_url供playerContent使用
            "_video_url": v.get("video_url", ""),
            "_preview_url": v.get("preview_url", ""),
        }

    # ── 标准接口 ──
    def homeContent(self, filter=False):
        classes = self.cfg["categories"]
        result = {"class": classes}
        if filter: result["filters"] = {}
        try:
            for v in self._get_videolist(1):
                self._cache[str(v.get("id"))] = v
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        videos = self._get_videolist(1)
        for v in videos: self._cache[str(v.get("id"))] = v
        vod_list = [self._video_to_vod(v) for v in videos]
        # 清理内部字段
        for item in vod_list:
            item.pop("_video_url", None)
            item.pop("_preview_url", None)
        return {"list": vod_list, "page": 1, "pagecount": 1, "limit": len(vod_list), "total": len(vod_list)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = max(1, int(pg or 1))
        videos = self._get_videolist(pg)
        for v in videos: self._cache[str(v.get("id"))] = v
        vod_list = [self._video_to_vod(v) for v in videos]
        page_size = self.cfg["page_size"]
        return {"list": vod_list, "page": pg, "pagecount": 1000, "limit": page_size, "total": 20000}

    def detailContent(self, ids):
        vid = str(ids).strip() if isinstance(ids, str) else str(ids[0] if ids else "")
        detail = self._cache.get(vid)
        if not detail:
            for p in range(1, 6):
                for v in self._get_videolist(p):
                    if str(v.get("id")) == vid or str(v.get("vid")) == vid:
                        detail = v
                        self._cache[vid] = v
                        break
                if detail: break
        if not detail: return {"list": []}
        vod = self._video_to_vod(detail)
        desc_lines = []
        if detail.get("description"): desc_lines.append(detail["description"])
        if detail.get("detail_desc"): desc_lines.append(detail["detail_desc"])
        tags = detail.get("tags") or []
        if tags: desc_lines.append("标签: " + ", ".join(tags))
        user = detail.get("user") or {}
        if user: desc_lines.append("作者: {} | 粉丝: {} | 作品: {}".format(
            user.get('user_name',''), user.get('fan_count',0), user.get('video_count',0)))
        vod["vod_content"] = "\n".join(filter(None, desc_lines))
        week_hot = detail.get("week_hot", 0)
        video_hot = detail.get("video_hot", 0)
        vod["vod_remarks"] = "周热{} | 总热{}".format(week_hot, video_hot)
        # 播放地址用 vid 作为 id，playerContent 会查找 _video_url
        vod["vod_play_url"] = "播放$" + vid
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg=1):
        return {"list": [], "page": pg, "pagecount": 0, "limit": 0, "total": 0}

    def playerContent(self, flag, id, vipFlags=False):
        """播放解析。视频走站点代理 /media/m3u8?url=...&exp=...&token=...
        直链 m3u8 (xv.dzuxta.cn) 返回 403，不可用，必须用代理 URL。"""
        vid = id
        if "$" in id:
            vid = id.split("$", 1)[1]
        detail = self._cache.get(vid)
        if not detail:
            for p in range(1, 5):
                for v in self._get_videolist(p):
                    if str(v.get("id")) == vid or str(v.get("vid")) == vid:
                        detail = v
                        self._cache[vid] = v
                        break
                if detail: break
        if not detail:
            return {}
        # 优先 video_url，兜底 preview_url
        video_url = detail.get("video_url") or detail.get("preview_url") or ""
        if not video_url:
            return {}
        # video_url 格式: /media/m3u8?url=<直链m3u8>&exp=<时间戳>&token=<哈希>
        # 必须保留完整代理URL，不可提取直链（直链403）
        if video_url.startswith("/"):
            play_url = self.host + video_url
        else:
            play_url = video_url

        # 用站点域名作为 Referer，绕过 CDN 防盗链
        headers = {
            "User-Agent": self.cfg["ua"],
            "Referer": self.host + "/",
            "Origin": self.host,
            "Accept": "*/*",
            "Sec-Fetch-Dest": "video",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        return {
            "parse": 0,
            "url": play_url,
            "header": headers,
        }

    def localProxy(self, params):
        """本地代理: 下载AES加密封面图并解密返回。
        调用: vod_pic = http://127.0.0.1:9978/proxy?do=py&type=img&url=BASE64(first_img_url)
        TVBox 会自动传 url 参数到 localProxy。"""
        try:
            url = params.get("url", "")
            typ = params.get("type", "")
            if typ != "img" or not url:
                return [404, "text/plain", b""]
            # URL-decode + base64-decode 得到真实图片URL
            raw = unquote(url)
            cover_url = base64.b64decode(raw).decode("utf-8")
            # 下载加密数据
            headers = {"User-Agent": self.cfg["ua"], "Referer": self.host + "/"}
            req = urllib.request.Request(cover_url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=15)
            enc_data = resp.read()
            if len(enc_data) < 32:
                return [404, "text/plain", b"empty image"]
            # AES-128-CBC 解密
            dec, ctype = self._decrypt_image(enc_data)
            return [200, ctype, dec]
        except Exception as e:
            return [500, "text/plain", str(e).encode("utf-8", "ignore")]

    def liveProxy(self, params):
        return ""

if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("[1] homeContent...")
    home = spider.homeContent(filter=True)
    print(f"    分类数: {len(home.get('class',[]))}")
    print("[2] homeVideoContent...")
    hvc = spider.homeVideoContent()
    print(f"    视频数: {len(hvc['list'])}")
    if hvc['list']:
        v = hvc['list'][0]
        print(f"    第1条: {v['vod_name'][:40]} | id={v['vod_id']}")
    print("[3] detailContent...")
    if hvc['list']:
        dc = spider.detailContent(hvc['list'][0]['vod_id'])
        if dc['list']:
            d = dc['list'][0]
            print(f"    标题: {d['vod_name'][:40]}")
    print("[4] playerContent...")
    if hvc['list']:
        pc = spider.playerContent("抖阴", "播放$" + hvc['list'][0]['vod_id'])
        print(f"    parse={pc.get('parse')} url={pc.get('url','')[:80]}...")
    print("Done.")
