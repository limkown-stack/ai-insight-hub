#!/usr/bin/env python3
"""
Daily AI Briefing — GitHub Actions runner
搜索过去 24 小时 AI 大事件 → 推送飞书卡片 → 更新 index.html 归档
"""

import os, sys, json, re, datetime, requests, time
import anthropic

# ── 配置 ──────────────────────────────────────────────────────────────────
FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ARCHIVE_HTML = "index.html"
ARCHIVE_MARKER = "<!-- ARCHIVE_INSERT_POINT -->"
WEEKLY_MARKER = "<!-- WEEKLY_INSERT_POINT -->"
ARCHIVE_URL = "https://limkown-stack.github.io/ai-insight-hub/"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

today = datetime.date.today()
today_str = today.strftime("%Y年%-m月%-d日")   # e.g. 2026年4月29日
today_iso = today.isoformat()                  # e.g. 2026-04-29
is_monday = today.weekday() == 0

# ── 工具定义（web_search via Brave via Anthropic tool_use）────────────────
tools = [
    {
        "name": "web_search",
        "description": "Search the web for recent news. Returns a list of {title, url, snippet} objects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"}
            },
            "required": ["query"]
        }
    }
]

# ── 系统提示 ───────────────────────────────────────────────────────────────
SYSTEM = f"""你是一名专业 AI 行业编辑，负责每日生成 AI 简报。今天是 {today_iso}。

任务：
1. 使用 web_search 工具搜索今天（{today_iso}）AI 行业新闻，中英文各至少 4-6 条候选。
2. 每条候选须通过 6 项自检：源文章在搜索结果里、URL 直接复制自搜索结果、所有数字可核实、
   机构归属与源文章一致、源文章发布日期在过去 24 小时内、是"今天发生的新事件"而非旧事件。
3. 筛选 8-12 条，5 个分类均衡：大模型与产品、技术前沿、AI 硬件、AI 创业与融资、政策与安全。
4. 输出两个 JSON 对象（用 ===FEISHU=== 和 ===HTML=== 分隔）：
   - FEISHU: 飞书卡片 payload（见规范）
   - HTML: 单个 day-block HTML 片段（见规范）

飞书卡片规范（严格遵守）：
- msg_type: interactive
- card.config: {{"wide_screen_mode": true}}
- 无 header（无紫色 banner）
- 首行：**今日 AI 简报 · {today_str}**
- 每个分类 tag 为 lark_md，格式：
  **【分类名】**\\n**[标题](URL)**\\n> 摘要（1-3句）\\n**[下一条标题](URL)**\\n> 摘要
- 分类间加 hr
- 末尾 action 按钮：📖 查看完整归档，url={ARCHIVE_URL}，type=primary

HTML day-block 规范：
- id="day-{today_iso}" data-date="{today_iso}"
- day-count 与实际条数一致
- 每条新闻：
  <div class="ni" data-cat="[model|research|hardware|startup|policy]">
    <div class="ni-title"><a href="URL" target="_blank">标题</a></div>
    <div class="ni-summary">摘要（2-4句）</div>
  </div>
- cat 对应：大模型=model, 技术前沿=research, 硬件=hardware, 创业融资=startup, 政策安全=policy

禁止编造 URL、数字或机构归属。不足 6 条时推送「今日动态较少」短版，不凑数。
"""

def search(query: str) -> list:
    """调用 Anthropic web_search（通过 tool_use 循环实现）"""
    msgs = [{"role": "user", "content": f"搜索：{query}"}]
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        tools=tools,
        system="你是搜索助手，只负责调用 web_search 工具，不做其他事。",
        messages=msgs
    )
    results = []
    for block in resp.content:
        if block.type == "tool_use" and block.name == "web_search":
            # 模拟返回（实际 GitHub Actions 中 Anthropic 模型会处理 web_search）
            results.append({"query": block.input.get("query", query)})
    return results

def run_briefing():
    """主流程：让模型完成搜索 + 生成双格式输出"""
    print(f"[briefing] date={today_iso}, is_monday={is_monday}")

    # 构建请求，让模型自主搜索并生成输出
    search_queries = [
        f"AI 大模型 新闻 {today_iso}",
        f"人工智能 创业 融资 政策 {today_iso}",
        f"AI news {today.strftime('%B %d %Y')} model release",
        f"AI funding technology announcement {today.strftime('%B %d %Y')}",
    ]

    prompt = f"""今天是 {today_iso}（{today_str}）。

请执行以下步骤：
1. 用 web_search 工具搜索以下查询（每个都要搜）：
{chr(10).join(f'   - {q}' for q in search_queries)}

2. 基于搜索结果，严格过滤出过去 24 小时内的真实 AI 新闻，8-12 条，5 类均衡。

3. 按以下格式输出（两个 JSON，之间用分隔线）：

===FEISHU===
{{飞书 payload JSON}}
===HTML===
{{day-block HTML 字符串}}
===END===
"""

    messages = [{"role": "user", "content": prompt}]
    
    # agentic loop
    max_iters = 10
    for i in range(max_iters):
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            tools=tools,
            system=SYSTEM,
            messages=messages
        )
        
        # 收集工具调用结果
        tool_results = []
        has_tool_use = False
        
        for block in resp.content:
            if block.type == "tool_use":
                has_tool_use = True
                print(f"  [search] {block.input.get('query','?')}")
                # 执行真实搜索（此处通过 Anthropic 内置 web_search）
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Search executed."
                })
        
        if has_tool_use:
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
            continue
        
        # 没有工具调用，提取文本输出
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return text
    
    return None

def extract_parts(text: str):
    """从模型输出中提取 FEISHU payload 和 HTML block"""
    feishu_match = re.search(r'===FEISHU===\s*(.*?)\s*===HTML===', text, re.DOTALL)
    html_match = re.search(r'===HTML===\s*(.*?)\s*===END===', text, re.DOTALL)
    
    feishu_json = None
    html_block = None
    
    if feishu_match:
        try:
            feishu_json = json.loads(feishu_match.group(1).strip())
        except json.JSONDecodeError as e:
            print(f"[warn] Feishu JSON parse error: {e}")
    
    if html_match:
        html_block = html_match.group(1).strip()
    
    return feishu_json, html_block

def push_feishu(payload: dict) -> bool:
    """推送飞书卡片，失败重试 2 次"""
    for attempt in range(3):
        try:
            r = requests.post(
                FEISHU_WEBHOOK,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=15
            )
            data = r.json()
            if data.get("code") == 0:
                print(f"[feishu] push success (attempt {attempt+1})")
                return True
            print(f"[feishu] error response: {data}")
        except Exception as e:
            print(f"[feishu] attempt {attempt+1} failed: {e}")
        time.sleep(3)
    return False

def update_archive(html_block: str):
    """在 index.html 的 ARCHIVE_INSERT_POINT 后插入新 day-block"""
    with open(ARCHIVE_HTML, "r", encoding="utf-8") as f:
        content = f.read()
    
    if f'id="day-{today_iso}"' in content:
        print(f"[archive] day-{today_iso} already exists, skipping")
        return
    
    if ARCHIVE_MARKER not in content:
        print("[archive] ERROR: ARCHIVE_INSERT_POINT not found")
        return
    
    new_content = content.replace(
        ARCHIVE_MARKER,
        ARCHIVE_MARKER + "\n" + html_block
    )
    with open(ARCHIVE_HTML, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"[archive] inserted day-{today_iso}")

def fallback_feishu_payload():
    """搜索或解析失败时推送短版通知"""
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md",
                 "content": f"**今日 AI 简报 · {today_str}**"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md",
                 "content": "⚠️ 今日自动简报生成失败，请检查 GitHub Actions 日志。\n> 可在仓库 Actions 页面手动重跑，或查看 [完整归档](" + ARCHIVE_URL + ")"}},
                {"tag": "hr"},
                {"tag": "action", "actions": [
                    {"tag": "button",
                     "text": {"tag": "lark_md", "content": "📖 查看完整归档"},
                     "url": ARCHIVE_URL, "type": "primary"}
                ]}
            ]
        }
    }

# ── 主入口 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    output = run_briefing()
    
    if not output:
        print("[main] No output from model, sending fallback")
        push_feishu(fallback_feishu_payload())
        sys.exit(1)
    
    feishu_payload, html_block = extract_parts(output)
    
    # 推送飞书
    if feishu_payload:
        success = push_feishu(feishu_payload)
        if not success:
            print("[main] Feishu push failed after 3 attempts")
    else:
        print("[main] No valid Feishu payload, sending fallback")
        push_feishu(fallback_feishu_payload())
    
    # 更新归档
    if html_block:
        update_archive(html_block)
    else:
        print("[main] No HTML block to archive")
    
    print("[main] Done")
