"""從 KB markdown 檔案抽出 YAML block，parse 成 KBEntry。

KB 來源檔案位於：
    C:\\Users\\Admin\\Desktop\\AIC測試\\files\\

格式特徵：
- 檔名 pattern: `poker-kb-reference-entry-*-reviewed.md`
- 第一個 ```yaml ... ``` block 是真正的 entry 資料
- yaml 內可能有 `# ===` 之類的 comment lines（yaml.safe_load 會處理）
- yaml content key 是 `zh-tw`（pydantic field 是 `zh_tw`，schema 用 alias 處理）

行為：
- 失敗的 entry 跳過 + print warning，不要 crash 整個 load。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

import yaml

from .schema import KBEntry

# KB markdown source directory（hardcoded for V4 Phase 4，Phase 5 後可改 settings）
KB_FILES_DIR = Path(r"C:\Users\Admin\Desktop\AIC測試\files")

# 只 load 已 review 完成的條目
KB_FILE_GLOB = "poker-kb-reference-entry-*-reviewed.md"


def parse_yaml_block(md_content: str) -> Optional[dict]:
    """從 markdown 抓出第一個 ```yaml ... ``` block 並 parse 成 dict。

    回傳 None 表示找不到 yaml block 或 parse 失敗。
    """
    # 用 [\s\S] 確保跨行；非貪婪匹配第一個 yaml block
    m = re.search(r"```yaml\s*\n([\s\S]+?)\n```", md_content)
    if not m:
        return None

    yaml_text = m.group(1)
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        print(f"[adapter_md] yaml parse error: {e}")
        return None

    if not isinstance(data, dict):
        return None

    return data


def load_all_entries(directory: Path = KB_FILES_DIR) -> Iterator[KBEntry]:
    """掃描 directory 下所有 reviewed md 檔，yield 出 KBEntry。

    失敗的 entry 跳過 + print warning，不影響其他 entry。
    """
    if not directory.exists():
        print(f"[adapter_md] KB directory not found: {directory}")
        return

    for md_file in sorted(directory.glob(KB_FILE_GLOB)):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[adapter_md] failed to read {md_file.name}: {e}")
            continue

        data = parse_yaml_block(content)
        if not data:
            print(f"[adapter_md] no yaml block in {md_file.name}, skipping")
            continue

        try:
            entry = KBEntry.model_validate(data)
        except Exception as e:
            # pydantic ValidationError 或其他 — 跳過，不要拖垮整個 load
            print(f"[adapter_md] failed to validate {md_file.name}: {e}")
            continue

        yield entry
