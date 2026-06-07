# 批量导入文档到知识库指南

## 支持的文档格式

项目支持以下格式的文档导入：
- **Markdown** (.md)
- **Word** (.docx)
- **PowerPoint** (.pptx)
- **PDF** (.pdf)
- **Excel** (.xlsx, .xls)
- **纯文本** (.txt)
- **JSON** (.json) - 预结构化文档

## 导入方式

### 方式 1：导入整个目录（推荐）

```bash
# 基本用法
./run.sh --ingest knowledge/raw

# 指定领域标签
./run.sh --ingest knowledge/raw --ingest-domain marketing

# 导入并生成 Markdown 文件
./run.sh --ingest knowledge/raw --output-markdown --markdown-output-dir output/
```

### 方式 2：导入单个文件

```bash
./run.sh --ingest knowledge/raw/document.pdf
```

### 方式 3：使用 Python 模块

```bash
# 导入目录
/d/Tools/conda/setup/envs/reactagent/python.exe -m knowledge.pipelines.ingest --dir knowledge/raw --domain general

# 导入单个文件
/d/Tools/conda/setup/envs/reactagent/python.exe -m knowledge.pipelines.ingest --file knowledge/raw/faq.md --domain support

# 查看统计
/d/Tools/conda/setup/envs/reactagent/python.exe -m knowledge.pipelines.ingest --stats
```

## 文档组织结构

建议按以下方式组织文档：

```
knowledge/
├── raw/                    # 原始文档存放目录
│   ├── marketing/          # 按领域分类
│   │   ├── product.pdf
│   │   └── campaign.docx
│   ├── support/
│   │   ├── faq.md
│   │   └── manual.pdf
│   └── general/
│       └── overview.txt
```

## 领域标签说明

领域标签 (domain) 用于分类管理知识：
- `general` - 通用知识（默认）
- `marketing` - 市场营销
- `support` - 客户支持
- `technical` - 技术文档
- `business` - 商业规则
- 可以自定义任意标签

## 文档类型说明

文档类型 (doc_type) 决定存储集合：
- `knowledge` - 知识片段（默认）
- `rule` - 业务规则
- `case` - 案例数据

使用 Python 模块方式可以指定：
```bash
/d/Tools/conda/setup/envs/reactagent/python.exe -m knowledge.pipelines.ingest \
  --dir knowledge/raw/rules \
  --doc-type rule \
  --domain business
```

## 使用步骤

### 1. 准备文档

将要导入的文档放入 `knowledge/raw/` 目录：

```bash
# 复制文档到 raw 目录
cp /path/to/your/documents/* knowledge/raw/
```

### 2. 执行导入

```bash
# 导入所有文档
./run.sh --ingest knowledge/raw --ingest-domain general
```

### 3. 查看统计

```bash
# 查看知识库统计
./run.sh --stats
```

输出示例：
```
[知识库统计]
  knowledge: 156 条
  rules: 23 条
  cases: 45 条
  ──────────
  总计: 224 条
```

## 处理流程

文档导入的处理流程：

1. **格式转换** - 将各种格式转换为 Markdown
2. **内容解析** - 按标题层级拆分段落
3. **文本清洗** - 去除多余空白、特殊字符
4. **智能分块** - 按语义分割成知识片段
5. **向量化** - 生成文本嵌入向量
6. **入库存储** - 存入 ChromaDB

## 输出选项

### 生成 Markdown 文件

如果希望保留转换后的 Markdown 文件：

```bash
./run.sh --ingest knowledge/raw \
  --output-markdown \
  --markdown-output-dir knowledge/processed/
```

这样可以：
- 查看文档的解析结果
- 手动编辑优化后重新导入
- 作为知识库的备份

## 注意事项

1. **大文件处理**：PDF/Word 大文件可能需要较长时间
2. **编码问题**：确保文本文件使用 UTF-8 编码
3. **去重机制**：相同内容不会重复入库（基于内容 hash）
4. **增量导入**：可以随时添加新文档，无需清空知识库
5. **存储位置**：默认存储在 `./chroma_data/` 目录

## 示例：批量导入营销文档

```bash
# 1. 准备文档
mkdir -p knowledge/raw/marketing
cp /path/to/marketing/*.pdf knowledge/raw/marketing/

# 2. 导入并标记为营销领域
./run.sh --ingest knowledge/raw/marketing --ingest-domain marketing

# 3. 查看结果
./run.sh --stats
```

## 清空知识库

如果需要重新开始：

```bash
# 删除 ChromaDB 数据目录
rm -rf ./chroma_data/

# 重新导入
./run.sh --ingest knowledge/raw
```
