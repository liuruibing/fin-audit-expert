import re
from typing import Dict, Any, List
from .parser import ParsedDocument


class DocumentProfile:
    """金融文档画像元数据"""
    def __init__(
        self,
        doc_type: str,          # ANNUAL | SEMI_ANNUAL | QUARTERLY | MONTHLY | WEEKLY | PROSPECTUS | ANNOUNCEMENT
        doc_type_name: str,     # 中文显示名: "年度报告" / "半年度报告" ...
        entity_type: str,       # LISTED_COMPANY (上市公司) | PUBLIC_FUND (公募基金) | ASSET_MGMT (资管机构)
        entity_name: str,       # 主体全称 (如 "友邦保險控股有限公司" / "申万菱信基金管理有限公司")
        report_year: str,       # "2024"
        period_text: str,       # "2024年度" / "2022年半年度"
        cutoff_date: str,       # "2024-12-31" / "2022-06-30"
        is_audited: bool,       # 是否属于法定审计报告 (年报为 True, 季报/月报通常为 False)
        stock_code: str = "",   # 股票/基金代码 (如 "1299" / "163113")
    ):
        self.doc_type = doc_type
        self.doc_type_name = doc_type_name
        self.entity_type = entity_type
        self.entity_name = entity_name
        self.report_year = report_year
        self.period_text = period_text
        self.cutoff_date = cutoff_date
        self.is_audited = is_audited
        self.stock_code = stock_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "doc_type_name": self.doc_type_name,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "report_year": self.report_year,
            "period_text": self.period_text,
            "cutoff_date": self.cutoff_date,
            "is_audited": self.is_audited,
            "stock_code": self.stock_code,
        }


class DocumentClassifier:
    """金融文档自动判型分类与画像分析器 (第一步工序)"""

    @staticmethod
    def classify(doc: ParsedDocument) -> DocumentProfile:
        # 提取前 5 页文本作为特征判定池
        front_spans = [s.text for s in doc.spans if s.page <= 5]
        front_text = "\n".join(front_spans)
        filename = doc.filename

        # 1. 抽取年份 (从封面或文件名中识别四位年份)
        year_match = re.search(r"(20\d{2})", filename)
        if not year_match:
            year_match = re.search(r"(20\d{2})", front_text)
        report_year = year_match.group(1) if year_match else "2024"

        # 2. 判定文档类型 (年报 / 半年报 / 季报 / 月报 / 周报 / 招募说明书 / 临时公告)
        doc_type = "ANNUAL"
        doc_type_name = f"{report_year}年 年度报告"
        cutoff_date = f"{report_year}-12-31"
        is_audited = True

        combined_feature = f"{filename}\n{front_text}"

        if any(kw in combined_feature for kw in ["招募說明書", "招募说明书", "招股说明书", "發售說明書"]):
            doc_type = "PROSPECTUS"
            doc_type_name = "招募说明书/发行文件"
            is_audited = False
        elif any(kw in combined_feature for kw in ["週報", "周报", "每周策略", "weekly"]):
            doc_type = "WEEKLY"
            doc_type_name = f"{report_year}年 投研策略周报"
            is_audited = False
        elif any(kw in combined_feature for kw in ["月度報告", "月报", "月度持仓", "monthly"]):
            doc_type = "MONTHLY"
            doc_type_name = f"{report_year}年 月度运作报告"
            is_audited = False
        elif any(kw in combined_feature for kw in ["第一季度", "第二季度", "第三季度", "第四季度", "一季报", "二季报", "三季报", "四季报", "Q1", "Q3"]):
            doc_type = "QUARTERLY"
            doc_type_name = f"{report_year}年 季度报告"
            cutoff_date = f"{report_year}-03-31"
            is_audited = False
        elif any(kw in combined_feature for kw in ["中期報告", "中期报告", "半年度報告", "半年度报告", "中报", "interim"]):
            doc_type = "SEMI_ANNUAL"
            doc_type_name = f"{report_year}年 半年度/中期报告"
            cutoff_date = f"{report_year}-06-30"
            is_audited = False
        elif any(kw in combined_feature for kw in ["臨時公告", "临时公告", "重大事项", "澄清公告"]):
            doc_type = "ANNOUNCEMENT"
            doc_type_name = "临时公告与重大事项"
            is_audited = False
        else:
            # 默认年度报告
            doc_type = "ANNUAL"
            doc_type_name = f"{report_year}年 年度报告"
            cutoff_date = f"{report_year}-12-31"
            is_audited = True

        # 3. 通用判定主体性质与名称 (完全无具体公司硬编码)
        entity_type = "PUBLIC_FUND"
        entity_name = "金融资管机构"
        stock_code = ""

        # 通用股票/股份代码抽取
        code_match = re.search(r"(股份代[號号]|股票代码|证券代码|代码)[：:\s]*([0-9]{4,6})", front_text)
        if code_match:
            stock_code = code_match.group(2)

        # 通用抽取公司/主体名称 (寻找含有有限公司/股份有限公司/集团的段落)
        company_match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9（）()]+(?:股份有限公司|控股有限公司|有限公司|集團有限公司|集团有限公司))", front_text)
        if company_match:
            entity_name = company_match.group(1).strip()

        # 根据文本特征自适应区分主体属性
        if stock_code or any(kw in combined_feature for kw in ["股份代號", "上市公佈", "董事會報告", "港幣櫃台", "人民幣櫃台"]):
            entity_type = "LISTED_COMPANY"
            if not entity_name or entity_name == "金融资管机构":
                entity_name = front_spans[0] if front_spans else "上市公司"
        elif any(kw in combined_feature for kw in ["理财有限责任公司", "理财子公司", "理财产品", "财富管理"]):
            entity_type = "BANK_WEALTH"
        elif any(kw in combined_feature for kw in ["证券投资基金", "基金管理人", "基金托管人", "招募说明书", "LOF", "ETF"]):
            entity_type = "PUBLIC_FUND"
            if not entity_name or entity_name == "金融资管机构":
                entity_name = front_spans[0] if front_spans else "公募证券投资基金"
        return DocumentProfile(
            doc_type=doc_type,
            doc_type_name=doc_type_name,
            entity_type=entity_type,
            entity_name=entity_name,
            report_year=report_year,
            period_text=doc_type_name,
            cutoff_date=cutoff_date,
            is_audited=is_audited,
            stock_code=stock_code,
        )
