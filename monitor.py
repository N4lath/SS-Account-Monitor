"""8591 星塔旅人進度號 → Discord。Python 3.11+，另需 curl。"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

API = "https://api.8591.com.tw/v4/mall/getList"
SCOPE = "66531:2:3:all"


class MonitorError(Exception):
    pass


def request_json(url, payload=None):
    # curl uses the platform TLS trust store; no certificate checks are disabled.
    args = ["curl", "--silent", "--show-error", "--fail-with-body",
            "--connect-timeout", "15", "--max-time", "45",
            "--user-agent", "8591ListingMonitor/1.0",
            "--header", "Accept: application/json", url]
    raw = None
    if payload is None:
        args[1:1] = ["--retry", "2", "--retry-delay", "2"]
    else:
        args += ["--header", "Content-Type: application/json", "--data-binary", "@-"]
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        result = subprocess.run(args, input=raw, capture_output=True, timeout=150)
    except (OSError, subprocess.TimeoutExpired):
        raise MonitorError("网络请求未完成，或找不到 curl。") from None
    if result.returncode:
        # Never print the secret URL or the response body.
        raise MonitorError(f"网络或 HTTP 请求失败（curl {result.returncode}），记录已保留。")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise MonitorError("返回内容不是 JSON；可能是验证页面或网站接口已改变。") from None


def parse_page(response):
    if not isinstance(response, dict) or response.get("code") != 200:
        raise MonitorError("8591 返回异常；不更新商品记录。")
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise MonitorError("8591 商品列表结构改变。")
    total = data.get("total_rows")
    if isinstance(total, bool) or not str(total).isdigit():
        raise MonitorError("8591 商品总数无效。")
    items = []
    for row in data["list"]:
        if not isinstance(row, dict):
            raise MonitorError("8591 商品记录无效。")
        try:
            info = row["game_info"]
            if (int(info["game"]["id"]), int(info["type"]["id"]),
                    int(row["account_tag"])) != (66531, 2, 3):
                raise MonitorError("8591 筛选结果与星塔旅人／帐号／进度号不符。")
            item_id = str(row["id"])
            title = row["ware_title"]
            price = str(row["ware_price"])
            server = info["server"]["name"]
            if not item_id.isdigit() or not isinstance(title, str) or not title or not isinstance(server, str):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise MonitorError("8591 商品必要字段缺失。") from None
        items.append({"id": item_id, "title": title, "price": price,
                      "server": server, "listed": str(row.get("format_time", "")),
                      "url": f"https://www.8591.com.tw/v3/mall/detail/{item_id}"})
    return int(total), items


def fetch_items(get=request_json, page_size=40, max_pages=50, pause=time.sleep):
    items = {}
    offset = 0
    for _ in range(max_pages):
        query = urlencode({"game_id": 66531, "ware_type": 2, "account_tag": 3,
                           "limit": page_size, "offset": offset})
        total, page = parse_page(get(API + "?" + query))
        if total == 0:
            if offset or page:
                raise MonitorError("8591 总数与列表不一致。")
            return []
        if not page:
            raise MonitorError("列表未读完就返回空页；保留原记录。")
        before = len(items)
        items.update({item["id"]: item for item in page})
        if len(items) == before:
            raise MonitorError("分页没有前进；保留原记录。")
        offset += len(page)
        if offset >= total:
            if len(items) < total:
                raise MonitorError("分页期间列表变动，稍后重新检查。")
            return list(items.values())
        pause(1)
    raise MonitorError("商品数量超过扫描上限；保留原记录。")


def webhook_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc not in ("discord.com", "discordapp.com")
            or not re.fullmatch(r"/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_-]+", parsed.path)):
        raise MonitorError("请在 DISCORD_WEBHOOK_URL 填入有效的 Discord Webhook。")
    query = dict(parse_qsl(parsed.query))
    query["wait"] = "true"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def message(item):
    return {"username": "星塔旅人上架通知", "allowed_mentions": {"parse": []},
            "embeds": [{"title": item["title"][:256], "url": item["url"],
                        "color": 0x6C60FF, "description": "發現新的進度號商品",
                        "fields": [{"name": "價格", "value": f"NT$ {item['price']}"[:1024], "inline": True},
                                   {"name": "伺服器", "value": item["server"][:1024], "inline": True},
                                   {"name": "商品編號", "value": item["id"], "inline": True}],
                        "footer": {"text": "8591 · 星塔旅人 · 帳號 · 進度號 · 所有伺服器"},
                        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat()}]}


def send(url, payload):
    response = request_json(url, payload)
    if not isinstance(response, dict) or not response.get("id"):
        raise MonitorError("Discord 未确认发送成功；下次检查会重试。")


def read_state(path):
    if not path.exists():
        return {"version": 1, "scope": SCOPE, "initialized": False, "seen": [], "pending": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        assert state["version"] == 1 and state["scope"] == SCOPE
        assert isinstance(state["initialized"], bool)
        assert isinstance(state["seen"], list) and all(isinstance(x, str) and x.isdigit() for x in state["seen"])
        assert isinstance(state["pending"], dict)
        for key, item in state["pending"].items():
            assert key == item["id"] and key.isdigit()
            assert all(isinstance(item[x], str) for x in ("title", "price", "server", "url"))
            assert item["url"] == f"https://www.8591.com.tw/v3/mall/detail/{key}"
        return state
    except (ValueError, AssertionError, KeyError, TypeError):
        raise MonitorError("状态记录损坏或范围不同；请检查，程序不会自动清空。") from None


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def process(items, path, deliver):
    state = read_state(path)
    if not state["initialized"]:
        if not items:
            raise MonitorError("首次扫描为空，暂不建立基准，以免下一次把旧商品当新品。")
        state["initialized"] = True
        state["seen"] = sorted(item["id"] for item in items)
        save_state(path, state)
        print(f"已建立基准：{len(items)} 件现有商品；之后只通知新编号。")
        return
    known = set(state["seen"]) | set(state["pending"])
    for item in items:
        if item["id"] not in known:
            state["pending"][item["id"]] = item
    # Save pending before posting, so a partially failed run can resume.
    if state["pending"]:
        save_state(path, state)
    sent = 0
    for key, item in list(state["pending"].items()):
        deliver(message(item))
        state["seen"].append(key)
        state["seen"] = sorted(set(state["seen"]))
        del state["pending"][key]
        save_state(path, state)
        sent += 1
        time.sleep(1)
    print(f"检查完成：{len(items)} 件在售商品，发送 {sent} 条新商品通知。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="读取实际列表，不发通知或写状态")
    parser.add_argument("--test-discord", action="store_true", help="发送一条连接测试消息")
    parser.add_argument("--state", type=Path, default=Path(".monitor/state.json"))
    args = parser.parse_args()
    try:
        if args.preview:
            items = fetch_items()
            print(json.dumps(items, ensure_ascii=False, indent=2))
            print(f"共 {len(items)} 件符合条件。")
            return 0
        url = webhook_url(os.environ.get("DISCORD_WEBHOOK_URL", ""))
        if args.test_discord:
            send(url, {"username": "星塔旅人上架通知", "allowed_mentions": {"parse": []},
                       "content": "✅ 通知連接測試成功。監測範圍：8591 星塔旅人／帳號／進度號／所有伺服器。"})
            print("Discord 测试消息已发送。")
            return 0
        process(fetch_items(), args.state, lambda payload: send(url, payload))
        return 0
    except (MonitorError, OSError) as error:
        print(f"检查失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
