"""Noah 版：从私有 CunFetch Worker 拉取素材到本地。

这就是原版 README 里写了但公开仓库里没有的 --pull-r2 的替代品。
原版拉取模块已从公开仓库移除，这里用 Worker 自带的 /api/objects + /media 实现，
不依赖作者的私有本地工具。

用法（在你自己电脑上，Token 不要写进文件）：
  set CUNFETCH_TOKEN=你的Token
  python local/pull_inbox.py --worker https://cunfetch.<你的子域名>.workers.dev --out D:/CunContent/inbox

流程：
  1. GET /api/objects（带 Bearer Token）拿清单
  2. 每个素材用 /media/<key> 下载（Noah 版 /media 也要 Token，脚本会带上）
  3. 落盘到 --out/<日期>_<档位>_<篇名>/，并 POST /api/feedback 回写“已下载”

注意：本版不做云端备份，拉取后本地就是唯一副本，
R2 上的原素材 7 天后会自动清理，所以要及时拉取。

只用 Python 标准库，不用装额外依赖。
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


def req(url, token, method="GET", data=None):
    r = urllib.request.Request(url, method=method, data=data)
    r.add_header("Authorization", f"Bearer {token}")
    if data:
        r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", required=True, help="Worker 地址，例如 https://cunfetch.xxx.workers.dev")
    ap.add_argument("--token", default=os.environ.get("CUNFETCH_TOKEN", ""), help="Token，优先用环境变量 CUNFETCH_TOKEN")
    ap.add_argument("--out", default="D:/CunContent/inbox", help="本地落盘目录")
    ap.add_argument("--date", default="", help="只拉某一天，格式 YYYYMMDD，留空则拉全部未下载")
    args = ap.parse_args()
    if not args.token:
        print("缺少 Token：请设环境变量 CUNFETCH_TOKEN，或用 --token 传入（不要写进配置文件）", file=sys.stderr)
        return 2
    worker = args.worker.rstrip("/")
    out_root = Path(args.out)
    raw = req(f"{worker}/api/objects", args.token)
    items = json.loads(raw)["items"]
    done = skipped = 0
    for date, slots in sorted(items.items()):
        if args.date and date != args.date:
            continue
        for slot, slugs in slots.items():
            for slug, entry in slugs.items():
                kind = entry.get("kind", "video")
                prefix = "articles" if kind == "article" else "inbox"
                base = f"{prefix}/{date}/{slot}/{slug}"
                # 视频线 files 是文件名，图文线 files 是 平台/文件名
                files = entry.get("files", {})
                if not files:
                    continue
                dest = out_root / f"{date}_{slot}_{slug}"
                dest.mkdir(parents=True, exist_ok=True)
                for rel in files:
                    if rel in ("meta.json", "status.json"):
                        continue
                    key = f"{base}/{rel}"
                    data = req(f"{worker}/media/{key}", args.token)
                    target = dest / Path(rel).name if kind == "video" else dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() and target.stat().st_size == len(data):
                        skipped += 1
                        continue
                    target.write_bytes(data)
                    done += 1
                # 回写已下载状态
                try:
                    req(f"{worker}/api/feedback", args.token, method="POST",
                        data=json.dumps({"slug": slug, "slot": slot, "date": date, "kind": kind, "downloaded": True}).encode())
                except Exception as e:
                    print(f"feedback 失败 {slug}: {e}")
    print(f"拉取完成：新下载 {done} 个文件，跳过已存在 {skipped} 个，落盘 {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
