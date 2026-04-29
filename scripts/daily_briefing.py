#!/usr/bin/env python3
"""
Daily AI Briefing — GitHub Actions runner (no LLM API required)
duckduckgo-search → 分类过滤 → 飞书卡片 + index.html 归档
"""

import os, sys, json, re, datetime, time, textwrap
import requests

try:
    from duckduckgo_search import DDGS
except ImportError:
    os.system("pip install duckduckgo-search -q")
    from duckduckgo_search import DDGS

# ── 配置 ──────────────────────────────────────────────────────────────────
FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
ARCHIVE_HTML   = "index.html"
ARCHIVE_MARKER = "<!-- ARCHIVE_INSERT_POINT -->"
ARCHIVE_URL    = "https://limkown-stack.github.io/ai-insight-hub/"

today     = datetime.date.today()
today_str = today.strftime("%Y年%-m月%-d日")
today_iso = today.isoformat()

# 分类关键词映射
CATEGORIES = {
    "model": {
        "label": "大模型与产品",
        "color_var": "var(--c-model)",
        "keywords": [
            "GPT", "Claude", "Gemini", "DeepSeek", "Llama", "Qwen", "通义",
            "大模型", "LLM", "model", "ChatGPT", "Grok", "豆包", "文心",
            "mistral", "phi", "release", "launch", "发布", "上线", "更新",
            "MiniMax", "智谱", "Moonshot", "kimi", "百川", "spark", "讯飞"
        ]
    },
    "research": {
        "label": "技术前沿",
        "color_var": "var(--c-research)",
        "keywords": [
            "research", "paper", "arxiv", "benchmark", "reasoning", "agent",
            "multimodal", "robotics", "机器人", "具身", "强化学习", "RL",
            "论文", "技术", "算法", "架构", "世界模型", "agentic", "RAG",
            "embodied", "VLA", "diffusion", "transformer", "attention"
        ]
    },
    "hardware": {
        "label": "AI 硬件",
        "color_var": "var(--c-hardware)",
        "keywords": [
            "NVIDIA", "英伟达", "GPU", "chip", "芯片", "Blackwell", "Rubin",
            "华为昇腾", "Ascend", "TPU", "NPU", "AMD", "Intel", "算力",
            "datacenter", "数据中心", "semiconductor", "半导体", "H100",
            "H200", "B200", "寒武纪", "海光", "昆仑芯", "hardware"
        ]
    },
    "startup": {
        "label": "AI 创业与融资",
        "color_var": "var(--c-startup)",
        "keywords": [
            "funding", "raises", "投资", "融资", "startup", "valuation",
            "Series", "seed", "venture", "VC", "亿美元", "billion", "million",
            "估值", "轮", "Sequoia", "红杉", "a16z", "投融资", "IPO",
            "acquisition", "收购", "merger", "创业"
        ]
    },
    "policy": {
        "label": "政策与安全",
        "color_var": "var(--c-policy)",
        "keywords": [
            "regulation", "policy", "法规", "监管", "safety", "安全",
            "EU", "欧盟", "FTC", "Congress", "White House", "白宫",
            "发改委", "工信部", "网信办", "治理", "governance", "ban",
            "禁止", "合规", "copyright", "版权", "bias", "risk", "风险"
        ]
    }
}

# 搜索查询
SEARCH_QUERIES = [
    f"AI artificial intelligence news {today.strftime('%B %d %Y')}",
    f"OpenAI Anthropic Google AI announcement {today.strftime('%B %d %Y')}",
    f"AI model release funding {today.strftime('%B %d %Y')}",
    f"人工智能 大模型 新闻 {today_iso}",
    f"AI 融资 发布 {today_iso}",
    f"AI chip hardware semiconductor {today.strftime('%B %d %Y')}",
]

def ddg_search(query: str, max_results: int = 8) -> list:
    """DuckDuckGo 搜索，返回 [{title, href, body}]"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                region="wt-wt",
                safesearch="off",
                timelimit="d",   # past day
                max_results=max_results
            ))
        return results
    except Exception as e:
        print(f"  [ddg] search error for '{query}': {e}")
        time.sleep(2)
        return []

def score_category(text: str) -> str:
    """根据关键词打分，返回最匹配的分类"""
    text_lower = text.lower()
    scores = {}
    for cat, info in CATEGORIES.items():
        score = sum(1 for kw in info["keywords"] if kw.lower() in text_lower)
        scores[cat] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "model"

def is_ai_relevant(item: dict) -> bool:
    """过滤非 AI 新闻"""
    text = (item.get("title","") + " " + item.get("body","")).lower()
    ai_keywords = ["ai", "artificial intelligence", "人工智能", "大模型", "llm",
                   "machine learning", "deep learning", "neural", "openai",
                   "anthropic", "google deepmind", "deepseek", "nvidia gpu"]
    return any(kw in text for kw in ai_keywords)

def truncate(text: str, max_chars: int = 120) -> str:
    """截断摘要"""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"

def collect_news() -> list:
    """搜索 + 去重 + 分类，返回最终新闻列表"""
    seen_urls = set()
    seen_titles = set()
    candidates = []

    for query in SEARCH_QUERIES:
        print(f"  [search] {query}")
        results = ddg_search(query)
        time.sleep(1.5)  # 避免限速

        for r in results:
            url   = r.get("href", "")
            title = r.get("title", "").strip()
            body  = r.get("body", "").strip()

            # 去重
            title_key = re.sub(r'\W+', '', title.lower())[:40]
            if not url or not title or url in seen_urls or title_key in seen_titles:
                continue
            # AI 相关性过滤
            if not is_ai_relevant(r):
                continue
            # 过滤明显非新闻页
            skip_domains = ["reddit.com", "youtube.com", "twitter.com",
                            "x.com", "wikipedia.org", "amazon.com"]
            if any(d in url for d in skip_domains):
                continue

            seen_urls.add(url)
            seen_titles.add(title_key)
            cat = score_category(title + " " + body)
            candidates.append({
                "title":   title,
                "url":     url,
                "summary": truncate(body, 130),
                "cat":     cat
            })

    # 每类取最多 3 条，总数控制在 8-12
    by_cat = {c: [] for c in CATEGORIES}
    for item in candidates:
        by_cat[item["cat"]].append(item)

    final = []
    # 每类至少 1 条，大模型/创业最多 3 条，其他最多 2 条
    limits = {"model": 3, "research": 2, "hardware": 2, "startup": 3, "policy": 2}
    for cat in CATEGORIES:
        items = by_cat[cat][:limits[cat]]
        final.extend(items)
        if len(final) >= 12:
            break

    # 保证至少 6 条（不够则从候选里补）
    if len(final) < 6:
        extras = [i for i in candidates if i not in final]
        final.extend(extras[:max(0, 6 - len(final))])

    print(f"  [collect] {len(final)} items selected")
    return final[:12]

# ── 飞书 payload 生成 ─────────────────────────────────────────────────────
def make_feishu_payload(news: list) -> dict:
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
         "content": f"**今日 AI 简报 · {today_str}**"}},
        {"tag": "hr"}
    ]

    # 按分类分组
    by_cat = {c: [] for c in CATEGORIES}
    for item in news:
        by_cat[item["cat"]].append(item)

    first_cat = True
    for cat, info in CATEGORIES.items():
        items = by_cat[cat]
        if not items:
            continue
        if not first_cat:
            elements.append({"tag": "hr"})
        first_cat = False

        lines = [f"**【{info['label']}】**"]
        for item in items:
            lines.append(f"**[{item['title']}]({item['url']})**")
            lines.append(f"> {item['summary']}")
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                          "content": "\n".join(lines)}})

    elements += [
        {"tag": "hr"},
        {"tag": "action", "actions": [{
            "tag": "button",
            "text": {"tag": "lark_md", "content": "📖 查看完整归档"},
            "url": ARCHIVE_URL,
            "type": "primary"
        }]}
    ]
    return {"msg_type": "interactive", "card": {
        "config": {"wide_screen_mode": True},
        "elements": elements
    }}

def make_feishu_short() -> dict:
    """今日动态较少时的短版"""
    return {"msg_type": "interactive", "card": {
        "config": {"wide_screen_mode": True},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
             "content": f"**今日 AI 简报 · {today_str}**"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "今日 AI 行业动态较少，未找到足够的最新资讯。\n> 可访问完整归档查看历史简报。"}},
            {"tag": "hr"},
            {"tag": "action", "actions": [{
                "tag": "button",
                "text": {"tag": "lark_md", "content": "📖 查看完整归档"},
                "url": ARCHIVE_URL, "type": "primary"
            }]}
        ]
    }}

# ── HTML day-block 生成 ───────────────────────────────────────────────────
def make_html_block(news: list) -> str:
    by_cat = {c: [] for c in CATEGORIES}
    for item in news:
        by_cat[item["cat"]].append(item)

    cat_groups = []
    for cat, info in CATEGORIES.items():
        items = by_cat[cat]
        if not items:
            continue
        ni_html = ""
        for item in items:
            ni_html += (
                f'          <div class="ni" data-cat="{cat}">'
                f'<div class="ni-title"><a href="{item["url"]}" target="_blank">'
                f'{item["title"]}</a></div>'
                f'<div class="ni-summary">{item["summary"]}</div></div>\n'
            )
        cat_groups.append(
            f'      <div class="cat-group" data-cat="{cat}">\n'
            f'        <div class="cat-header"><div class="cat-dot" '
            f'style="background:{info["color_var"]}"></div>'
            f'{info["label"]}<span class="cat-count">{len(items)}条</span></div>\n'
            f'        <div class="news-grid">\n{ni_html}'
            f'        </div>\n'
            f'      </div>\n'
        )

    body = "".join(cat_groups)
    return (
        f'  <div class="day-block" id="day-{today_iso}" data-date="{today_iso}">\n'
        f'    <div class="day-divider"></div>\n'
        f'    <div class="day-header">\n'
        f'      <div class="day-title">{today_str}</div>\n'
        f'      <div class="day-count">{len(news)}条</div>\n'
        f'      <div class="day-toggle">▾</div>\n'
        f'    </div>\n'
        f'    <div class="day-body">\n'
        f'{body}'
        f'    </div>\n'
        f'  </div><!-- /day-block {today_iso} -->\n'
    )

# ── 推送 & 归档 ──────────────────────────────────────────────────────────
def push_feishu(payload: dict) -> bool:
    for attempt in range(3):
        try:
            r = requests.post(FEISHU_WEBHOOK, json=payload,
                              headers={"Content-Type": "application/json; charset=utf-8"},
                              timeout=15)
            data = r.json()
            if data.get("code") == 0:
                print(f"[feishu] OK (attempt {attempt+1})")
                return True
            print(f"[feishu] error: {data}")
        except Exception as e:
            print(f"[feishu] attempt {attempt+1}: {e}")
        time.sleep(3)
    return False

def update_archive(html_block: str):
    with open(ARCHIVE_HTML, "r", encoding="utf-8") as f:
        content = f.read()
    if f'id="day-{today_iso}"' in content:
        print(f"[archive] day-{today_iso} already present, skip")
        return
    if ARCHIVE_MARKER not in content:
        print("[archive] ERROR: ARCHIVE_INSERT_POINT missing")
        return
    new_content = content.replace(ARCHIVE_MARKER,
                                  ARCHIVE_MARKER + "\n" + html_block)
    with open(ARCHIVE_HTML, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"[archive] inserted day-{today_iso}")

# ── 主入口 ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[main] date={today_iso}")
    news = collect_news()

    if len(news) < 6:
        print(f"[main] only {len(news)} items, sending short card")
        push_feishu(make_feishu_short())
        sys.exit(0)

    push_feishu(make_feishu_payload(news))
    update_archive(make_html_block(news))
    print("[main] done")
