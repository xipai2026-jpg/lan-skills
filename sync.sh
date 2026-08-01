#!/usr/bin/env bash
# 单向同步：plugins/<插件>/skills/<技能>/  ->  skills/<技能>/
#
# 为什么需要：
#   Claude Code 的 marketplace 认 plugins/ 布局；
#   hermes 的 `skills tap add` 认仓库根目录下的 skills/<名>/SKILL.md。
#   两种客户端都要原生支持，就得有两份——但**唯一事实源永远是 plugins/**。
#
# 用法：
#   ./sync.sh          同步（改完 plugins/ 就跑这个，然后一起提交）
#   ./sync.sh --check  只检查是否已同步，不改文件；不一致时退出码 1（给 CI 用）
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-sync}"
drift=0
count=0

for src in plugins/*/skills/*/; do
  [ -f "${src}SKILL.md" ] || continue
  name="$(basename "$src")"
  dst="skills/$name"
  count=$((count + 1))

  if [ "$MODE" = "--check" ]; then
    if [ ! -d "$dst" ] || ! diff -r -q "$src" "$dst" >/dev/null 2>&1; then
      echo "✗ 不同步: $src -> $dst"
      diff -r -q "$src" "$dst" 2>&1 | sed 's/^/    /' || true
      drift=1
    else
      echo "✓ 已同步: $name"
    fi
  else
    rm -rf "$dst"
    mkdir -p "$(dirname "$dst")"
    cp -R "$src" "$dst"
    echo "→ 已同步: $src -> $dst"
  fi
done

[ "$count" -gt 0 ] || { echo "没找到任何 plugins/*/skills/*/SKILL.md"; exit 1; }

if [ "$MODE" = "--check" ]; then
  [ "$drift" -eq 0 ] || {
    echo
    echo "根目录 skills/ 与 plugins/ 不一致。请在改完 plugins/ 后运行 ./sync.sh 再提交。"
    exit 1
  }
  echo "全部同步 ✅"
else
  echo
  echo "完成。skills/ 是**生成物**，别直接改它——改 plugins/ 再跑本脚本。"
fi
