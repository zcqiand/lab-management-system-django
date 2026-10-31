#!/usr/bin/env bash
# scripts/gen-shared.sh — 从家族 shared 契约生成 DTO + manifest（design-codegen.md 方案 B）
#
# 硬规则 §4「API 面只认生成物」：
#   DTO      → src/lab_management_system_django/contract/models/  （datamodel-code-generator）
#   manifest → generated/api_manifest.json                          （gen-manifest.py，路由 parity SSOT）
#
# 生成区每次 regen 先删后写 —— 手改会被机械抹掉；禁止任何绕过脚本的手工编辑。
# 手写区：serializers/views/urls（实现缝），serializer 从生成 DTO 变换。
#
# 用法：bash scripts/gen-shared.sh   （无 DB 依赖；L4.codegen.idempotent 复放本脚本）

set -euo pipefail

# 本仓是 submodule：git rev-parse 返回外层 suite 根，禁用（fastapi 同款坑）
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

PKG=lab_management_system_django
SHARED_DIR="$(cd ../lab-management-system-shared && pwd)"
ZONE_ARGS=(-- "src/$PKG/contract/models" "generated/api_manifest.json")
OPENAPI="$SHARED_DIR/generated/openapi/openapi.yaml"

echo "[gen-shared] step 1/5 — shared 仓 emit:openapi（TypeSpec SSOT 单 emit）"
(cd "$SHARED_DIR" && npm run emit:openapi)

# lab openapi 有 RequirementComparison 枚举成员 `- =`——YAML 1.1 把 `= ` 键映到
# value tag（tag:yaml.org,2002:value），PyYAML 系（datamodel-codegen）直接炸。
# 净化：`- =` → `- '='` 语义等价，落 _work/ 临时件（可再生，不进库）。
SANITIZED="_work/openapi-sanitized.yaml"
mkdir -p _work
sed -E 's/^([[:space:]]*)- =$/\1- '"'"'='"'"'/' "$OPENAPI" > "$SANITIZED"

echo "[gen-shared] step 2/5 — datamodel-code-generator（pydantic v2，版本 pyproject dev 钉 exact）"
# lab spec 触发 generator 的 modular 模式（跨 schema $ref 结构决定），输出目录而非单文件——
# 生成区形状按仓如实接受：models/ 下 __init__.py + 分模块 .py
rm -rf "src/$PKG/contract"
mkdir -p "src/$PKG/contract/models"
datamodel-codegen \
  --input "$SANITIZED" \
  --output "src/$PKG/contract/models" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.12 \
  --use-schema-description \
  --disable-timestamp

echo "[gen-shared] step 3/5 — gen-manifest.py（确定性 manifest，键序固定 + [tag,operationId] 排序）"
rm -f generated/api_manifest.json
python scripts/gen-manifest.py "$OPENAPI" --out generated

echo "[gen-shared] step 4/5 — fail-loud 自检（py_compile 生成区全目录）"
python - <<'PYEOF'
import pathlib
import py_compile
import sys

zone_dir = pathlib.Path("src/lab_management_system_django/contract/models")
files = sorted(zone_dir.rglob("*.py"))
if not files:
    print(f"{zone_dir}: 生成区为空", file=sys.stderr)
    sys.exit(1)
try:
    # cfile 指到 gitignore 的 _work/：不在生成区写 __pycache__
    # （会污染 codegen 幂等门的磁盘态对比；fastapi 同款坑）
    pyc = pathlib.Path("_work/gen-shared.pyc")
    pyc.parent.mkdir(parents=True, exist_ok=True)
    for f in files:
        py_compile.compile(str(f), cfile=str(pyc), doraise=True)
except Exception as exc:
    print(f"{exc}", file=sys.stderr)
    sys.exit(1)
print(f"[gen-shared] py_compile OK（{len(files)} files in {zone_dir}）")
PYEOF

echo "[gen-shared] step 5/5 — 漂移 fail-loud（生成区与 git HEAD 不一致即红，含 untracked）"
if [ ! -e .git ]; then
  echo "[gen-shared] SKIP：本仓尚未 git init（用户持有）——漂移检查待 submodule 注册后生效"
elif ! git diff --exit-code --quiet "${ZONE_ARGS[@]}" 2>/dev/null \
  || [ -n "$(git ls-files --others --exclude-standard -- "src/$PKG/contract" "generated/api_manifest.json")" ]; then
  echo "[gen-shared] FATAL: 生成区与 git HEAD 不一致（含 untracked 新文件）" >&2
  echo "[gen-shared]        处理：确认 shared .tsp 变更合法后 git add 生成区并 commit，再重跑本脚本核绿" >&2
  exit 1
fi
echo "[gen-shared] OK — 生成区已与 HEAD 同步（API 面只认生成物，硬规则 §4）"
