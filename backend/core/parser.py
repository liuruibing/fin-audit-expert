import os
from typing import List, Dict, Any, Optional
import re
from difflib import SequenceMatcher

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class TextSpan:
    def __init__(self, text: str, page: int, bbox: List[float], section: str = ""):
        self.text = text.strip()
        self.page = page  # 1-based page index
        self.bbox = bbox  # [x0, y0, x1, y1]
        self.section = section

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "page": self.page,
            "bbox": self.bbox,
            "section": self.section,
        }


class ParsedDocument:
    def __init__(self, filename: str, total_pages: int, spans: List[TextSpan], sections: List[Dict[str, Any]]):
        self.filename = filename
        self.total_pages = total_pages
        self.spans = spans
        self.sections = sections

    def find_text_evidence(self, query: str, page_hint: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        在文档中检索引用文本，返回精确命中或最高相似度的坐标。
        如果最大相似度低于阈值，返回 None (表明为大模型幻觉虚构的证据)。
        """
        if not query or not query.strip():
            return None

        clean_query = re.sub(r"\s+", "", query)
        best_match = None
        best_ratio = 0.0

        # 如果指定了页码，优先在指定页检索
        candidate_spans = self.spans
        if page_hint is not None:
            page_spans = [s for s in self.spans if s.page == page_hint]
            if page_spans:
                candidate_spans = page_spans

        for span in candidate_spans:
            clean_span = re.sub(r"\s+", "", span.text)
            if not clean_span:
                continue

            # 1. 严格包含匹配
            if clean_query in clean_span or clean_span in clean_query:
                return {
                    "matched_text": span.text,
                    "page": span.page,
                    "bbox": span.bbox,
                    "similarity": 1.0,
                    "section": span.section,
                }

            # 2. 模糊相似度计算
            ratio = SequenceMatcher(None, clean_query, clean_span).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = span

        if best_ratio >= 0.75 and best_match:
            return {
                "matched_text": best_match.text,
                "page": best_match.page,
                "bbox": best_match.bbox,
                "similarity": round(best_ratio, 3),
                "section": best_match.section,
            }

        return None

    def get_section_text(self, section_name_prefix: str) -> str:
        """获取某个章节下的拼接文本"""
        matched_spans = [s for s in self.spans if section_name_prefix in s.section]
        return "\n".join([s.text for s in matched_spans])


class DocumentParser:
    @staticmethod
    def parse_pdf(file_path: str, max_pages: Optional[int] = None) -> ParsedDocument:
        """从真实 PDF 中解析文本及其实际几何坐标"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        if not fitz:
            raise RuntimeError("PyMuPDF (fitz) is not installed")

        doc = fitz.open(file_path)
        spans: List[TextSpan] = []
        sections: List[Dict[str, Any]] = []

        current_section = "封面/引言"
        section_regex = re.compile(r"^(第[一二三四五六七八九十0-9]+[节部分]|§?\s*[1-9]\.[0-9]?)\s*(.*)")

        total_in_pdf = len(doc)
        pages_to_read = min(total_in_pdf, max_pages) if max_pages else total_in_pdf

        for page_idx in range(pages_to_read):
            page_num = page_idx + 1
            
            # 使用 textpage 提取 blocks
            blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
            for b in blocks:
                if len(b) >= 5:
                    x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                    clean_text = text.strip()
                    if not clean_text:
                        continue

                    # 判断是否为章节标题
                    match = section_regex.match(clean_text)
                    if match:
                        current_section = clean_text[:40]
                        sections.append({"title": current_section, "page": page_num, "bbox": [x0, y0, x1, y1]})

                    spans.append(TextSpan(text=clean_text, page=page_num, bbox=[round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)], section=current_section))

        doc.close()
        return ParsedDocument(filename=os.path.basename(file_path), total_pages=total_in_pdf, spans=spans, sections=sections)

    @staticmethod
    def parse_mock_document(sample_name: str = "swlx") -> ParsedDocument:
        """构造用于开箱演示与测试的真实金融研报样本数据，支持多份报告切换"""
        if sample_name == "aia_2024":
            aia_path = "backend/data/samples/AIA_2024_Annual_Report.pdf"
            if os.path.exists(aia_path):
                # 真实 371 页友邦保险 2024 年报，为保证前端秒级响应优先加载前 20 页供双栏高亮审阅
                return DocumentParser.parse_pdf(aia_path, max_pages=20)
        elif sample_name == "aia_2022":
            aia_path = "backend/data/samples/AIA_2022_Annual_Report.pdf"
            if os.path.exists(aia_path):
                return DocumentParser.parse_pdf(aia_path, max_pages=20)
        if sample_name == "fgth":
            # 富国天惠成长混合 2023年年度报告
            spans = [
                TextSpan("富国天惠精选成长混合型证券投资基金（LOF）", page=1, bbox=[100, 150, 500, 180], section="封面"),
                TextSpan("2023 年年度报告", page=1, bbox=[200, 220, 400, 250], section="封面"),
                TextSpan("基金管理人：富国基金管理有限公司", page=1, bbox=[120, 400, 450, 420], section="封面"),
                TextSpan("基金托管人：中国建设银行股份有限公司", page=1, bbox=[120, 440, 450, 460], section="封面"),
                TextSpan("送出日期：2024年3月29日", page=1, bbox=[120, 480, 350, 500], section="封面"),

                TextSpan("§2 基金基本情况", page=2, bbox=[80, 100, 250, 120], section="§2 基金基本情况"),
                TextSpan("业绩比较基准：中证800指数收益率*70% + 中债综合指数收益率*30%", page=2, bbox=[80, 140, 550, 165], section="§2 基金基本情况"),
                TextSpan("投资目标：本基金主要投资于具有良好成长性的上市股票。", page=2, bbox=[80, 180, 450, 200], section="§2 基金基本情况"),

                TextSpan("§4 管理人报告", page=3, bbox=[80, 100, 250, 120], section="§4 管理人报告"),
                TextSpan("报告期内业绩比较基准误写为：沪深300指数收益率*70% + 同业存款利率*30%", page=3, bbox=[80, 140, 540, 165], section="§4 管理人报告"),
                TextSpan("注：报告截止日 2022 年 12 月 31 日，期末基金资产净值变动较大。", page=3, bbox=[80, 180, 500, 205], section="§4 管理人报告"),

                TextSpan("§7 备查文件目录", page=4, bbox=[80, 100, 220, 120], section="§7 备查文件"),
                TextSpan("1. 基金合同及招募说明书；", page=4, bbox=[100, 140, 350, 160], section="§7 备查文件"),
                TextSpan("2. 招商银行股份有限公司托管协议与报告备查文件。", page=4, bbox=[100, 180, 480, 205], section="§7 备查文件"),
            ]
            sections = [
                {"title": "封面", "page": 1, "bbox": [100, 150, 500, 180]},
                {"title": "§2 基金基本情况", "page": 2, "bbox": [80, 100, 250, 120]},
                {"title": "§4 管理人报告", "page": 3, "bbox": [80, 100, 250, 120]},
                {"title": "§7 备查文件", "page": 4, "bbox": [80, 100, 220, 120]},
            ]
            return ParsedDocument(filename="富国天惠精选成长混合型证券投资基金_2023年年度报告.pdf", total_pages=4, spans=spans, sections=sections)

        # 默认：申万菱信中证申万证券 2022年中报
        spans = [
            TextSpan("申万菱信中证申万证券行业指数分级证券投资基金", page=1, bbox=[100, 150, 500, 180], section="封面"),
            TextSpan("2022 年中期报告", page=1, bbox=[200, 220, 400, 250], section="封面"),
            TextSpan("基金管理人：申万菱信基金管理有限公司", page=1, bbox=[120, 400, 450, 420], section="封面"),
            TextSpan("基金托管人：中国工商银行股份有限公司", page=1, bbox=[120, 440, 450, 460], section="封面"),
            TextSpan("送出日期：2022年8月26日", page=1, bbox=[120, 480, 350, 500], section="封面"),

            TextSpan("§2 基金基本情况", page=2, bbox=[80, 100, 250, 120], section="§2 基金基本情况"),
            TextSpan("2.1 基金基本信息", page=2, bbox=[80, 140, 220, 160], section="§2 基金基本情况"),
            TextSpan("注：报告截止日 2021 年 6 月 30 日，本基金份额净值 0.8394 元。", page=2, bbox=[80, 180, 520, 205], section="§2 基金基本情况"),
            TextSpan("本报告期为 2022 年 1 月 1 日至 2022 年 6 月 30 日止半年度。", page=2, bbox=[80, 220, 480, 240], section="§2 基金基本情况"),

            TextSpan("§3 主要财务指标和基金净值表现", page=3, bbox=[80, 100, 320, 120], section="§3 财务指标"),
            TextSpan("截至 2022-06-30，本基金份额规模如下：", page=3, bbox=[80, 140, 380, 160], section="§3 财务指标"),
            TextSpan("境内 A 类份额 2,233,444,879.68 份，C 类份额 53,888,573.87 份，份额总额 2,287,333,453.55 份。", page=3, bbox=[80, 180, 540, 210], section="§3 财务指标"),
            TextSpan("期末资产净值 1,919,986,714.26 元，期末单位净值 0.8394 元。", page=3, bbox=[80, 230, 450, 250], section="§3 财务指标"),

            TextSpan("§7 备查文件目录", page=4, bbox=[80, 100, 220, 120], section="§7 备查文件"),
            TextSpan("7.1 备查文件目录清单如下：", page=4, bbox=[80, 140, 300, 160], section="§7 备查文件"),
            TextSpan("1. 中国证监会准予基金募集注册的文件；", page=4, bbox=[100, 180, 400, 200], section="§7 备查文件"),
            TextSpan("2. 基金合同、托管协议、招募说明书；", page=4, bbox=[100, 210, 380, 230], section="§7 备查文件"),
            TextSpan("3. 中国建设银行股份有限公司托管业务备查文件与合规声明。", page=4, bbox=[100, 240, 490, 265], section="§7 备查文件"),
        ]

        sections = [
            {"title": "封面", "page": 1, "bbox": [100, 150, 500, 180]},
            {"title": "§2 基金基本情况", "page": 2, "bbox": [80, 100, 250, 120]},
            {"title": "§3 财务指标", "page": 3, "bbox": [80, 100, 320, 120]},
            {"title": "§7 备查文件", "page": 4, "bbox": [80, 100, 220, 120]},
        ]
        return ParsedDocument(filename="申万菱信中证申万证券行业指数分级证券投资基金_2022年中期报告.pdf", total_pages=4, spans=spans, sections=sections)
