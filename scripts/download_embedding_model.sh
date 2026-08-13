#!/usr/bin/env bash
# 下载本地 ONNX 句向量模型（量化多语言 MiniLM，维度 384，中文友好）。
#
# 该模型是二进制产物（约 135MB），不纳入 git 仓库。
# 生产容器已通过 docker cp 部署该模型；本脚本仅用于本地开发 / 重新拉取。
#
# 用法：
#   bash scripts/download_embedding_model.sh
#
# 国内网络使用 hf-mirror.com 镜像；如需切换官方源，把 BASE 改为
# https://huggingface.co 即可（需可访问境外网络）。
set -euo pipefail

BASE="${HF_MIRROR:-https://hf-mirror.com}"
REPO="Xenova/paraphrase-multilingual-MiniLM-L12-v2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/models/embedding/Xenova_paraphrase-multilingual-MiniLM-L12-v2"
ONNX_DIR="$OUT_DIR/onnx"

mkdir -p "$OUT_DIR" "$ONNX_DIR"

FILES=(
  "config.json"
  "tokenizer.json"
  "tokenizer_config.json"
  "special_tokens_map.json"
  "onnx/model_quantized.onnx"
)

for f in "${FILES[@]}"; do
  url="$BASE/$REPO/resolve/main/$f"
  dest="$OUT_DIR/$f"
  if [ -s "$dest" ]; then
    echo "skip (exists): $f"
  else
    echo "download: $url"
    curl -L -o "$dest" "$url"
  fi
done

echo "DONE -> $OUT_DIR"
echo "embedding_service.DEFAULT_MODEL_DIR 指向此目录。"
