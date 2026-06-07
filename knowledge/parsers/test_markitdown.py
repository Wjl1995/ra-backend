#!/usr/bin/env python3
"""
测试 Microsoft MarkItDown 集成
"""
import sys
sys.path.insert(0, ".")

def test_markitdown_available():
    """测试 MarkItDown 是否可用"""
    try:
        import markitdown
        print("[OK] MarkItDown 已安装，版本:", markitdown.__version__ if hasattr(markitdown, '__version__') else "未知")
        return True
    except ImportError:
        print("[错误] MarkItDown 未安装")
        print("请运行: pip install markitdown")
        return False


def test_basic_conversion():
    """测试基本转换功能"""
    from knowledge.parsers.markitdown_parser import MarkItDownParser

    print("\n[测试] 基本文档转换...")
    parser = MarkItDownParser()

    # 测试 Markdown 文件
    try:
        result = parser.to_markdown("knowledge/raw/example.md")
        print(f"[OK] 成功转换，长度: {len(result)} 字符")
        print("\n预览（前 200 字符）:")
        print("-" * 50)
        print(result[:200])
        print("-" * 50)
        return True
    except Exception as e:
        print(f"[错误] 转换失败: {e}")
        return False


def test_hybrid_parser():
    """测试混合解析器"""
    from knowledge.parsers.markitdown_parser import HybridParser
    from knowledge.parsers.pdf_parser import PdfParser

    print("\n[测试] 混合解析器...")
    parser = HybridParser(PdfParser(), prefer_markitdown=True)

    print(f"[OK] 混合解析器创建成功")
    print(f"支持的扩展名: {parser.supported_extensions()}")
    return True


def test_comparison():
    """对比原生解析器和 MarkItDown"""
    print("\n[对比测试]")
    print("功能对比:")
    print("  原生解析器: 轻量、稳定、基础功能")
    print("  MarkItDown:  强大、OCR、更多格式")
    print("  混合模式:    最佳选择，兼顾两者优势")
    return True


def main():
    print("=" * 60)
    print("Microsoft MarkItDown 集成测试")
    print("=" * 60)

    # 1. 检查安装
    if not test_markitdown_available():
        print("\n请先安装 MarkItDown:")
        print("  pip install markitdown")
        return

    # 2. 测试基本转换
    test_basic_conversion()

    # 3. 测试混合解析器
    test_hybrid_parser()

    # 4. 对比测试
    test_comparison()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n建议:")
    print("1. 使用混合模式（HybridParser）获得最佳效果")
    print("2. 一般场景关闭 OCR（性能考虑）")
    print("3. 处理扫描件时启用 OCR")
    print("\n详细文档: MARKITDOWN_INTEGRATION.md")


if __name__ == "__main__":
    main()
