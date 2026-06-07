# Microsoft MarkItDown 集成指南

## 📦 安装

### 基础安装
```bash
# 激活 conda 环境
conda activate reactagent

# 安装 MarkItDown
pip install markitdown
```

### 完整安装（含 OCR）
```bash
# 安装带 OCR 支持的版本
pip install markitdown[ocr]

# 或者单独安装 OCR 依赖
pip install pytesseract pillow
```

## 🔄 使用方式

### 方式 1：直接使用 MarkItDown 解析器

修改 `knowledge/parsers/__init__.py`，启用 MarkItDown：

```python
from .markitdown_parser import MarkItDownParser

# 创建解析器实例
parser = MarkItDownParser(enable_ocr=True)
markdown = parser.to_markdown("document.pdf")
```

### 方式 2：混合模式（推荐）

使用 `HybridParser`，自动选择最佳解析器：

```python
from .markitdown_parser import HybridParser
from .pdf_parser import PdfParser

# 创建混合解析器（MarkItDown 优先，PdfParser 备用）
parser = HybridParser(
    fallback_parser=PdfParser(),
    prefer_markitdown=True
)

markdown = parser.to_markdown("document.pdf")
```

### 方式 3：全局配置

在 `config.py` 中添加配置项：

```python
# 文档解析配置
USE_MARKITDOWN = True          # 是否使用 MarkItDown
MARKITDOWN_OCR = False         # 是否启用 OCR（需要额外依赖）
FALLBACK_TO_NATIVE = True      # 失败时是否回退到原生解析器
```

## 🎯 集成步骤

### 步骤 1：安装依赖

```bash
./run.sh --help  # 确保环境正常
pip install markitdown
```

### 步骤 2：测试 MarkItDown

创建测试脚本 `test_markitdown.py`：

```python
from knowledge.parsers.markitdown_parser import MarkItDownParser

parser = MarkItDownParser()
markdown = parser.to_markdown("knowledge/raw/example.md")
print(markdown[:500])  # 打印前 500 字符
```

运行测试：
```bash
/d/Tools/conda/setup/envs/reactagent/python.exe test_markitdown.py
```

### 步骤 3：更新解析器注册

修改 `knowledge/parsers/__init__.py`：

```python
from .base import BaseParser
from .pdf_parser import PdfParser
from .docx_parser import DocxParser
from .pptx_parser import PptxParser
from .xlsx_parser import XlsxParser
from .markitdown_parser import MarkItDownParser, HybridParser

# 全局配置
USE_MARKITDOWN = True

def get_parser(file_extension: str) -> BaseParser:
    """根据文件扩展名获取对应的解析器"""
    
    if USE_MARKITDOWN:
        # 使用混合模式
        native_parsers = {
            ".pdf": PdfParser(),
            ".docx": DocxParser(),
            ".pptx": PptxParser(),
            ".xlsx": XlsxParser(),
        }
        
        fallback = native_parsers.get(file_extension)
        if fallback:
            return HybridParser(fallback, prefer_markitdown=True)
    
    # 原生解析器
    parsers = {
        ".pdf": PdfParser(),
        ".docx": DocxParser(),
        ".pptx": PptxParser(),
        ".xlsx": XlsxParser(),
    }
    
    return parsers.get(file_extension)
```

### 步骤 4：导入文档测试

```bash
# 导入测试文档
./run.sh --ingest knowledge/raw --ingest-domain test

# 查看结果
./run.sh --stats
```

## 📊 性能对比

| 功能 | 原生解析器 | MarkItDown | 混合模式 |
|------|-----------|------------|----------|
| PDF 文本提取 | ✅ 基础 | ✅✅ 增强 | ✅✅ 最佳 |
| PDF 表格 | ✅ 基础 | ✅✅ 更好 | ✅✅ 最佳 |
| Word 格式保留 | ✅ 基础 | ✅✅ 更好 | ✅✅ 最佳 |
| 图片 OCR | ❌ 不支持 | ✅ 支持 | ✅ 支持 |
| 音视频元数据 | ❌ 不支持 | ✅ 支持 | ✅ 支持 |
| 稳定性 | ✅✅ 高 | ✅ 中 | ✅✅ 最高 |
| 依赖大小 | 小 | 中等 | 中等 |

## 🎨 高级功能

### 1. 图片 OCR

```python
# 启用 OCR
parser = MarkItDownParser(enable_ocr=True)

# 处理包含图片的 PDF
markdown = parser.to_markdown("scanned_document.pdf")
```

### 2. 音视频处理

```python
# 提取音频文件元数据
markdown = parser.to_markdown("podcast.mp3")
# 输出：标题、作者、时长等元数据
```

### 3. ZIP 压缩包

```python
# 批量处理 ZIP 中的文档
markdown = parser.to_markdown("documents.zip")
# 自动解压并处理内部所有支持的文档
```

## ⚠️ 注意事项

1. **OCR 依赖**：需要安装 Tesseract OCR 引擎
   - Windows: 下载安装包 https://github.com/UB-Mannheim/tesseract/wiki
   - 配置环境变量：`TESSERACT_PATH`

2. **性能考虑**：
   - MarkItDown 功能更强，但速度可能稍慢
   - 大批量导入时，可以选择禁用 OCR

3. **回退机制**：
   - 使用 `HybridParser` 确保稳定性
   - MarkItDown 失败时自动使用原生解析器

4. **版本兼容**：
   - 定期更新 MarkItDown：`pip install --upgrade markitdown`

## 🚀 推荐配置

对于大多数场景，推荐使用**混合模式**：

```python
# 在 config.py 中
USE_MARKITDOWN = True          # 启用 MarkItDown
MARKITDOWN_OCR = False         # 一般情况下关闭 OCR（性能考虑）
FALLBACK_TO_NATIVE = True      # 启用回退机制
```

需要 OCR 时单独处理：
```bash
# 针对扫描件启用 OCR
python -m knowledge.pipelines.ingest \
  --file scanned.pdf \
  --use-ocr
```

## 📝 总结

**集成价值：** ⭐⭐⭐⭐⭐
- 显著提升解析质量
- 扩展支持的文档类型
- 保持向后兼容
- 维护成本低

**建议：** 立即集成，使用混合模式！
