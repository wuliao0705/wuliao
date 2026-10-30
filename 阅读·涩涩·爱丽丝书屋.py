# -*- coding: utf-8 -*-
# 爱丽丝书屋 ALICESW - 小说爬虫 (TVBox/PeekPro)
# 站点: https://www.alicesw.com/
# 结构: diyquge 模板 CMS
#   - 列表页/首页: 书籍卡片 <a href="/novel/{id}.html">标题</a> + <img data-src=封面>
#   - 详情页: /novel/{id}.html (简介/作者/分类/章数/热度/book_id)
#   - 章节列表: /other/chapters/id/{id}.html -> /book/{book_id}/{key}.html
#   - 章节正文: /book/{book_id}/{key}.html -> div.read-content 内 <p> 段落
#   - 搜索: /search.html?q={keyword}
#   - 分类: /lists/{cid}.html?page={page}

import re
import sys
import json
import requests
from urllib.parse import quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HOST = "https://www.alicesw.com"

# 分类映射 (从首页/书库 all.html 提取，最终以实际 /lists/{id}.html 可访问为准)
CATEGORIES = [
    ("62", "玄幻"), ("68", "武侠"), ("69", "系统"), ("70", "穿越"),
    ("71", "科幻"), ("72", "明星"), ("73", "同人"), ("75", "奇幻"),
    ("79", "经典"), ("61", "校园"), ("64", "都市"), ("63", "乡村"),
    ("65", "乱伦"), ("22", "反差"), ("46", "凌辱"), ("18", "堕落"),
    ("19", "纯爱"), ("47", "百合"), ("52", "伪娘"), ("48", "萝莉"),
    ("50", "正太"), ("56", "熟女"), ("54", "NTR"), ("53", "媚黑"),
    ("58", "调教"), ("59", "言情"), ("82", "耽美"), ("21", "重口"),
    ("57", "其他"),
]


class Spider:
    """TVBox 小说 Spider 契约"""
    Name = "爱丽丝书屋"
    host = HOST

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.session.trust_env = False
        self.session.cookies.set("theme", "light")

    def init(self, extend=""):
        pass

    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass
        self.session = None

    def getName(self):
        return self.Name

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    # ---------- 工具 ----------

    def _get(self, url, retries=2):
        for i in range(retries + 1):
            try:
                r = self.session.get(url, timeout=15)
                if r.status_code == 200:
                    return r.text
            except Exception:
                pass
        return None

    def _fix_url(self, u):
        if not u:
            return u
        if u.startswith("http"):
            return u
        return HOST + u if u.startswith("/") else HOST + "/" + u

    def _strip_tags(self, s):
        if not s:
            return ""
        s = re.sub(r"<script[^>]*>.*?</script>", " ", s, flags=re.DOTALL)
        s = re.sub(r"<style[^>]*>.*?</style>", " ", s, flags=re.DOTALL)
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    # ---------- 列表页书籍卡片 ----------

    def _extract_books(self, html, max_count=30):
        """提取列表页书籍卡片: /novel/{id}.html + img[data-src] 封面"""
        books = []
        if not html:
            return books
        # 找书籍卡片块 (class-img + info)
        blocks = re.findall(
            r'<div[^>]*class="[^"]*(?:class-img|book-img|list-img|img-box)[^"]*"[^>]*>.*?</div>\s*<div[^>]*class="[^"]*(?:info|book-info|item-info)[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL
        )
        if not blocks:
            # 兜底: 按 a 提取
            links = re.findall(
                r'<a[^>]+href="(/novel/(\d+)\.html)"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )
            seen = set()
            for url, vid, inner in links:
                if vid in seen:
                    continue
                seen.add(vid)
                title = re.sub(r"<[^>]+>", "", inner).strip()
                books.append({
                    "vod_id": vid,
                    "vod_name": title or vid,
                    "vod_pic": "",
                    "vod_remarks": "",
                })
                if len(books) >= max_count:
                    break
            return books

        # 有完整卡片块: 标题在 a>h5 里，封面在上一块 img
        # 简化:直接按 block 内提取
        seen = set()
        for block in blocks:
            vm = re.search(r'href="(/novel/(\d+)\.html)"', block)
            if not vm:
                continue
            vid = vm.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            tm = re.search(r'<h5[^>]*>(.*?)</h5>', block, re.DOTALL)
            title = re.sub(r"<[^>]+>", "", tm.group(1)).strip() if tm else ""
            if not title:
                tm2 = re.search(r'<a[^>]+href="[^"]*novel[\d\.]*html"[^>]*>([^<]{2,})</a>', block)
                title = tm2.group(1).strip() if tm2 else vid
            # 作者/字数
            au = re.search(r'作者：?([^<|]{2,20})', block)
            st = re.search(r'状态[：:]\s*([^<]{1,6})', block)
            remarks = ""
            if au:
                remarks += au.group(1).strip()
            if st:
                remarks += (" " + st.group(1).strip())
            books.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": "",
                "vod_remarks": remarks,
            })
            if len(books) >= max_count:
                break
        return books

    def _extract_cards(self, html, max_count=30):
        """更强健的卡片提取: 优先 class-box 完整块(封面+标题), 否则 a+img 配对"""
        books = []
        if not html:
            return books

        # 方法1: class-box 完整卡片块 (首页精选/更新)
        blocks = re.findall(r'<div class="class-box">(.*?)</div>\s*</div>', html, re.DOTALL)
        seen = set()
        for b in blocks:
            vm = re.search(r'href="/novel/(\d+)\.html"', b)
            if not vm:
                continue
            vid = vm.group(1)
            if vid in seen:
                continue
            im = re.search(r'(?:data-src|src)="(http[^"]+\.(?:jpg|jpeg|png|webp))"', b)
            h5 = re.search(r'<h5[^>]*>(.*?)</h5>', b, re.DOTALL)
            title = self._strip_tags(h5.group(1)) if h5 else vid
            books.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": im.group(1) if im else "",
                "vod_remarks": "",
            })
            seen.add(vid)
            if len(books) >= max_count:
                return books

        # 方法2: <a href=/novel/N.html> + 最近 img data-src 配对 (搜索/分类)
        novel_as = list(re.finditer(
            r'<a[^>]+href="(/novel/(\d+)\.html)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        ))
        for m in novel_as:
            vid = m.group(2)
            if vid in seen:
                continue
            title = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            if not title:
                continue
            # 前 8000 字符内找最近 img
            pre = html[max(0, m.start() - 8000):m.start()]
            im = re.findall(r'(?:data-src|src)="(http[^"]+\.(?:jpg|jpeg|png|webp))"', pre)
            pic = im[-1] if im else ""
            books.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": "",
            })
            seen.add(vid)
            if len(books) >= max_count:
                break
        return books

    # ---------- 首页 ----------

    def homeContent(self, filter=False):
        classes = [{"type_id": cid, "type_name": name} for cid, name in CATEGORIES]
        classes.insert(0, {"type_id": "home", "type_name": "首页"})
        classes.append({"type_id": "update", "type_name": "最近更新"})
        result = {"class": classes, "list": []}
        try:
            html = self._get(HOST + "/")
            result["list"] = self._extract_cards(html)
        except Exception as e:
            print(f"[alicesw] homeContent error: {e}", file=sys.stderr)
        return result

    # ---------- 分类 ----------

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        try:
            page = int(pg) if str(pg).isdigit() else 1
            if tid == "home":
                # 首页 = 最近更新
                url = HOST + "/all/order/update_time+desc.html"
                if page > 1:
                    url = f"{HOST}/all/order/update_time+desc.html?page={page}"
                html = self._get(url)
            elif tid == "update":
                url = f"{HOST}/all/order/update_time+desc.html"
                if page > 1:
                    url = f"{HOST}/all/order/update_time+desc.html?page={page}"
                html = self._get(url)
            else:
                url = f"{HOST}/lists/{tid}.html"
                if page > 1:
                    url = f"{HOST}/lists/{tid}.html?page={page}"
                html = self._get(url)
            books = self._extract_cards(html)
            pagecount = self._extract_pagecount(html)
            if pagecount <= 1 and len(books) >= 5:
                pagecount = page + 1
            if pagecount < page:
                pagecount = page
            return {
                "list": books,
                "page": page,
                "pagecount": pagecount,
                "limit": len(books),
                "total": pagecount * 15,
            }
        except Exception as e:
            print(f"[alicesw] categoryContent error: {e}", file=sys.stderr)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def _extract_pagecount(self, html):
        """从分页区域提取总页数（只信 pagination 区块）"""
        if not html:
            return 1
        # 定位 <ul class="pagination">.....</ul>
        block = ""
        pi = html.find('pagination')
        if pi >= 0:
            end = html.find("</ul>", pi)
            block = html[pi:end] if end > pi else html[pi:pi + 800]
        pages = [int(x) for x in re.findall(r'page=(\d+)', block)]
        if pages:
            return max(pages)
        # laypage 格式: data-page
        dp = [int(x) for x in re.findall(r'data-page="(\d+)"', html) if int(x) > 1]
        if dp:
            return max(dp) + 1
        return 1

    # ---------- 搜索 ----------

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg) if str(pg).isdigit() else 1
            url = f"{HOST}/search.html?q={quote(key)}"
            if page > 1:
                url += f"&p={page}"
            html = self._get(url)
            books = self._extract_search(html)
            pagecount = self._extract_pagecount(html)
            if pagecount <= 1 and len(books) >= 10:
                pagecount = page + 1
            if pagecount < page:
                pagecount = page
            return {
                "list": books,
                "page": page,
                "pagecount": pagecount,
                "limit": len(books),
                "total": pagecount * 20,
            }
        except Exception as e:
            print(f"[alicesw] searchContent error: {e}", file=sys.stderr)
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}

    def _extract_search(self, html, max_count=30):
        """搜索页专用提取: list-group-item (标题/状态/作者/字数/简介/标签)"""
        books = []
        if not html:
            return books
        items = re.findall(r'<div class="list-group-item">(.*?)</div>\s*</div>', html, re.DOTALL)
        if not items:
            return self._extract_cards(html, max_count)
        seen = set()
        for it in items:
            vm = re.search(r'href="/novel/(\d+)\.html"[^>]*>([^<]+(?:<em>[^<]+</em>)?[^<]*)</a>', it)
            if not vm:
                continue
            vid = vm.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            title = self._strip_tags(vm.group(2)).strip()
            # 状态
            st = re.search(r'\[([^\]]{1,8})\]', it)
            status = st.group(1) if st else ""
            # 作者
            au = re.search(r'作者[：:]\s*<a[^>]*>([^<]{2,20})</a>', it)
            author = au.group(1).strip() if au else ""
            # 字数/浏览
            wc = re.search(r'字数[：:]\s*([^<\s]+)', it)
            pv = re.search(r'浏览[：:]\s*([^<\s]+)', it)
            remarks = " ".join([
                f"[{status}]" if status else "",
                author,
                f"字数{wc.group(1)}" if wc else "",
                f"浏览{pv.group(1)}" if pv else "",
            ]).strip()
            # 简介
            ct = re.search(r'class="content-txt">(.*?)</p>', it, re.DOTALL)
            desc = self._strip_tags(ct.group(1)) if ct else ""
            books.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": "",
                "vod_remarks": remarks,
                "vod_content": f"作者：{author}\n状态：{status}\n\n{desc}" if (author or status or desc) else "",
            })
            if len(books) >= max_count:
                break
        return books

    # ---------- 详情 ----------

    def detailContent(self, ids):
        vod = {
            "vod_id": ids[0],
            "vod_name": "",
            "vod_pic": "",
            "vod_remarks": "",
            "type_name": "",
            "vod_content": "",
            "vod_play_from": "",
            "vod_play_url": "",
            "vod_year": "",
            "vod_actor": "",
            "vod_director": "",
        }
        try:
            # detailContent 兼容传入完整 URL，所有 callers 实际只传纯 ID（但防呆）
            raw = ids[0] if isinstance(ids, (list, tuple)) else ids
            m0 = re.search(r"/novel/(\d+)\.html", str(raw))
            if m0:
                vid = m0.group(1)
            else:
                vid = re.search(r"(\d+)", str(raw))
                vid = vid.group(1) if vid else str(raw)
            vod["vod_id"] = vid
            html = self._get(f"{HOST}/novel/{vid}.html")
            if not html:
                return {"list": [vod]}
            # 空壳提示页（未找到该栏目 / 提示信息 1043字节）
            if "提示信息" in html and ("cuteAlert" in html or "未找到" in html):
                # 本小说不存在或被屏蔽
                vod["vod_name"] = f"未找到编号 {vid}"
                vod["vod_content"] = html and self._strip_tags(re.search(r'msg = "([^"]+)"', html).group(1)) if re.search(r'msg = "([^"]+)"', html) else "未找到该作品"
                return {"list": [vod]}

            # 标题 (title标签: 书名-分类-站点；以「-」前半为书名，避免漏h1)
            tm = re.search(r'<title>(.*?)</title>', html)
            if tm:
                tt = tm.group(1).split("-")[0].strip()
                # 书名可能含后缀站点名已在第一段 - 截断
                if tt:
                    vod["vod_name"] = tt

            # 作者: 优先 meta description「由作家XXX创作」
            desc_for_author = re.search(r'name="description"[^>]+content="([^"]+)"', html)
            desc_txt = desc_for_author.group(1) if desc_for_author else ""
            am = re.search(r"由作家([^，。,创]{2,16})(?:创作)?", desc_txt)
            if am:
                author = re.sub(r"\s+", "", am.group(1)).strip("，。, ")
                if author and len(author) <= 12:
                    vod["vod_director"] = author
                    vod["vod_actor"] = author
            # 侧边栏作者（9797等）不可信，不用它

            # 分类: title 第二段或 jianjie 区域
            if tm:
                parts = tm.group(1).split("-")
                if len(parts) >= 2 and parts[1].strip() and len(parts[1].strip()) <= 6:
                    vod["type_name"] = parts[1].strip()
            vm = re.search(r'是一本<a href="[^"]*lists/(\d+)\.html"[^>]*>([^<]{1,10})</a>小说', html)
            if vm:
                vod["type_name"] = vm.group(2).strip()

            # 状态/章节统计 - 站点详情已不直接展示，留空或由简介补充
            status = ""
            _sm = re.search(r"状态[：:]\s*([^\s<]{1,8})", html)
            if _sm:
                status = _sm.group(1).strip("</ ")

            # 封面 (webp/jpeg/png，任意长度hash均可)
            cm_img = re.search(r'<img[^>]+(?:data-src|src)="(https?://img\.321cdn\.com[^"]+)"', html)
            if cm_img:
                vod["vod_pic"] = cm_img.group(1)

            # 简介: class="jianjie" <p>，做 HTML 实体解码
            desc = ""
            dj = html.find('class="jianjie"')
            if dj >= 0:
                sec = html[dj:dj + 4000]
                dm = re.search(r'<p[^>]*>(.*?)</p>', sec, re.DOTALL)
                if dm:
                    import html as _html
                    desc = self._strip_tags(_html.unescape(dm.group(1)))
            if not desc and desc_txt:
                import html as _html
                desc = _html.unescape(desc_txt)

            # 最新章节 (详情页自带5章) -> 章节播放源
            # key 为 12-24 位 hex，章节名需做 HTML 实体解码
            import html as _html
            chapters = []
            chm = re.findall(r'<li>\s*<a href="/book/(\d+)/([0-9a-f]{6,24})\.html"[^>]*>([^<]{2,80})</a>', html)
            for bid, key, name in chm:
                name = _html.unescape(name).strip()
                if name:
                    chapters.append((bid, key, name))
            # 按 key 去重保序（同一章会有重复链接）
            _seen_k = set()
            _uniq = []
            for bid, key, name in chapters:
                if key in _seen_k:
                    continue
                _seen_k.add(key)
                _uniq.append((bid, key, name))
            chapters = _uniq
            book_id = chapters[0][0] if chapters else ""

            # 完整简介组装
            vod_content_parts = []
            if vod["vod_director"]:
                vod_content_parts.append(f"作者：{vod['vod_director']}")
            if vod["type_name"]:
                vod_content_parts.append(f"分类：{vod['type_name']}")
            if status:
                vod_content_parts.append(f"状态：{status}")
            if desc:
                vod_content_parts.append(f"\n{desc}")
            vod["vod_content"] = "\n".join(vod_content_parts)
            if not vod["vod_content"]:
                vod["vod_content"] = desc or "暂无简介"

            # 章节 -> 播放线路 (novel:// 协议: 第X章$URL#第Y章$URL)
            if chapters:
                vod["vod_play_from"] = "正文"
                # 去重保序
                seen = set()
                plays = []
                for bid, key, name in chapters:
                    if key in seen:
                        continue
                    seen.add(key)
                    url = f"{HOST}/book/{bid}/{key}.html"
                    plays.append(f"{name}${url}")
                vod["vod_play_url"] = "#".join(plays)
            else:
                vod["vod_play_from"] = ""
                vod["vod_play_url"] = ""

            # 总是获取完整章节列表（详情页只有5章且倒序）
            if book_id:
                clist = self._get(f"{HOST}/other/chapters/id/{vid}.html")
                if clist:
                    chm = re.findall(r'<a[^>]+href="/book/(\d+)/([a-f0-9]+)\.html"[^>]*>([^<]{2,60})</a>', clist)
                    seen = set()
                    plays = []
                    for bid, key, name in chm:
                        name = name.strip()
                        if not name:
                            continue
                        if key in seen:
                            continue
                        seen.add(key)
                        url = f"{HOST}/book/{bid}/{key}.html"
                        plays.append(f"{name}${url}")
                    if plays:
                        vod["vod_play_from"] = "正文"
                        vod["vod_play_url"] = "#".join(plays)
        except Exception as e:
            print(f"[alicesw] detailContent error: {e}", file=sys.stderr)
        return {"list": [vod]}

    # ---------- 章节正文 ----------

    def _fetch_full_chapter(self, url):
        """抓取章节正文: div.read-content 内 <p> 段落"""
        try:
            if not url:
                return "", ""
            html = self._get(self._fix_url(url))
            if not html:
                return "", ""

            # 章节标题: 优先 j_chapterName，再 title 的 "_" 前半
            title = ""
            jc = re.search(r'class="[^"]*j_chapterName[^"]*"[^>]*>(.*?)</h3>', html, re.DOTALL)
            if jc:
                title = self._strip_tags(jc.group(1))
            if not title:
                tm = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
                if tm:
                    title = self._strip_tags(tm.group(1))
            if not title:
                import html as _html
                tm2 = re.search(r'<title>(.*?)</title>', html)
                if tm2:
                    title = _html.unescape(tm2.group(1).split("_")[0].split("-")[0].strip())

            # 正文
            content = ""
            cm = re.search(r'class="[^"]*(?:read-content|chapter-content|content-area|book_content|j_readContent)[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if not cm:
                # 兜底: 提取所有 <p>
                cm = re.search(r'<div[^>]*class="[^"]*(?:read-content|chapter-content)[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if cm:
                body = cm.group(1)
                paras = re.findall(r'<p[^>]*>(.*?)</p>', body, re.DOTALL)
                lines = []
                for p in paras:
                    t = re.sub(r"<[^>]+>", "", p)
                    t = t.replace("&nbsp;", " ").replace("\u3000", "\u3000")
                    t = t.strip()
                    if t:
                        lines.append(t)
                if not lines:
                    # 直接全文
                    t = self._strip_tags(body)
                    if t:
                        lines.append(t)
                content = "\n\n".join(lines)

            if not content:
                # 最后兜底: 整个页面所有 <p>
                paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
                lines = []
                for p in paras:
                    t = re.sub(r"<[^>]+>", "", p).strip()
                    if t and not any(kw in t for kw in ["首页", "章节列表", "上一章", "下一章", "加入书架", "版权"]):
                        lines.append(t)
                content = "\n\n".join(lines)

            return title, content
        except Exception as e:
            print(f"[alicesw] _fetch_full_chapter error: {e}", file=sys.stderr)
            return "", ""

    def playerContent(self, flag, id, vipFlags=None):
        """返回 novel:// JSON 协议"""
        try:
            url = id if id.startswith("http") else self._fix_url(id)
            title, content = self._fetch_full_chapter(url)
            if not content or len(content) < 10:
                result = {"title": title or "章节", "content": "未找到章节内容，请检查网络"}
                return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}
            result = {"title": title or "章节", "content": content}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}
        except Exception as e:
            result = {"title": "错误", "content": f"异常: {str(e)}"}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}


if __name__ == "__main__":
    s = Spider()
    s.init()
    import pprint
    print("=== HOME ===")
    h = s.homeContent(True)
    print(f"分类: {len(h['class'])}")
    for v in h["list"][:5]:
        print(f"  {v['vod_name'][:35]} | {v['vod_pic'][:50]}")
    print("\n=== CATEGORY ===")
    c = s.categoryContent("home", "2")
    print(f"home pg2: {len(c['list'])} pagecount={c['pagecount']}")
    print("\n=== SEARCH ===")
    sr = s.searchContent("干妈")
    print(f"搜索: {len(sr['list'])}")
    for v in sr["list"][:3]:
        print(f"  {v['vod_name'][:30]} | {v['vod_pic'][:50]}")
    print("\n=== DETAIL ===")
    d = s.detailContent(["47487"])
    v = d["list"][0]
    print(f"名称: {v['vod_name'][:40]}")
    print(f"作者: {v['vod_director']}")
    print(f"分类: {v['type_name']}")
    print(f"封面: {v['vod_pic'][:60]}")
    print(f"章节数: {v['vod_play_url'].count('#')+1}")
    print(f"简介: {v['vod_content'][:100]}")
    first = v["vod_play_url"].split("#")[0]
    print(f"首章: {first[:80]}")
    print("\n=== CHAPTER ===")
    p = s.playerContent("正文", first.split("$")[-1])
    print(f"title: {p['url'][:60]}...")
    import json as J
    try:
        dat = J.loads(p["url"].replace("novel://", ""))
        print(f"正文字数: {len(dat.get('content',''))}")
        print(f"正文前100: {dat.get('content','')[:100]}")
    except Exception as e:
        print(f"parse err: {e}")
    s.destroy()
    print("\nDONE")
