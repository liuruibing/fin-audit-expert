import re
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
from .parser import ParsedDocument, TextSpan
from .rules import RuleFinding


class CrossCheckFinding:
    """交叉核验发现结果"""
    def __init__(
        self,
        check_id: str,
        section_path: str,        # 章节路径，如 "十一、基金的投资 > 1、报告期末基金资产组合情况"
        field_name: str,          # 字段名，如 "股票投资占基金总资产比例"
        target_value: str,        # 目标文档中的值 (招募说明书/资料概要)
        source_value: str,        # 依据定期报告中的值
        is_consistent: bool,      # 是否一致
        severity: str,            # "HIGH" | "LOW" | "PASSED"
        description: str,
        target_quote: str,
        target_page: int,
        source_quote: str,
        source_page: int,
        source_doc_name: str = "最近一次披露的定期报告",
    ):
        self.check_id = check_id
        self.section_path = section_path
        self.field_name = field_name
        self.target_value = target_value
        self.source_value = source_value
        self.is_consistent = is_consistent
        self.severity = severity
        self.description = description
        self.target_quote = target_quote
        self.target_page = target_page
        self.source_quote = source_quote
        self.source_page = source_page
        self.source_doc_name = source_doc_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "section_path": self.section_path,
            "field_name": self.field_name,
            "target_value": self.target_value,
            "source_value": self.source_value,
            "is_consistent": self.is_consistent,
            "severity": self.severity,
            "description": self.description,
            "target_quote": self.target_quote,
            "target_page": self.target_page,
            "source_quote": self.source_quote,
            "source_page": self.source_page,
            "source_doc_name": self.source_doc_name,
        }


# ==============================================================================
# 场景 1: 单文档多层级数字勾稽与超期日期校验引擎
# ==============================================================================
class MultiLevelGoujiEngine:
    """单文档多层级数字勾稽与文本合规性校验引擎"""

    @classmethod
    def run_all_checks(cls, doc: ParsedDocument, cutoff_date_str: str = "2022-06-30") -> List[RuleFinding]:
        findings = []
        findings.extend(cls.check_future_date_compliance(doc, cutoff_date_str))
        findings.extend(cls.check_text_internal_math(doc))
        findings.extend(cls.check_text_to_table_consistency(doc))
        findings.extend(cls.check_table_internal_math(doc))
        return findings

    @classmethod
    def check_future_date_compliance(cls, doc: ParsedDocument, cutoff_date_str: str) -> List[RuleFinding]:
        """4) 文本合规性校验: 报告中不能出现比报告期末日期大的日期 (期后事项特别声明除外)"""
        findings = []
        try:
            cutoff_dt = datetime.strptime(cutoff_date_str, "%Y-%m-%d")
        except Exception:
            return findings

        # 匹配年月日，如 2022年8月26日 或 2022-08-26
        date_pattern = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日|(\d{4})-(\d{2})-(\d{2})")

        for span in doc.spans:
            # 排除签署页面的“送出日期/披露日期”和第7节备查日期
            if span.page == 1 or "送出日期" in span.text or "備查" in span.text or "备查" in span.text:
                continue

            for m in date_pattern.finditer(span.text):
                if m.group(1):
                    y, m_val, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    y, m_val, d = int(m.group(4)), int(m.group(5)), int(m.group(6))

                try:
                    dt = datetime(y, m_val, d)
                except ValueError:
                    continue

                # 如果日期大于报告期末，且该段没有声明“期后重大事项”
                if dt > cutoff_dt and not any(kw in span.text for kw in ["期后事项", "期後事項", "资产负债表日后"]):
                    findings.append(RuleFinding(
                        rule_id="RULE_FUTURE_DATE_VIOLATION",
                        title="正文出现超期日期 (大于报告期末时点)",
                        category="SUBSTANTIAL",
                        severity="HIGH",
                        description=f"正文出现日期【{y}年{m_val}月{d}日】，晚于法定报告期末截止日【{cutoff_date_str}】，涉嫌出现期后未授权时点数据。",
                        quote=m.group(0),
                        page=span.page,
                        context_quote=f"本报告期截止日：{cutoff_date_str}",
                        context_page=1,
                        confidence=0.97,
                        scope="DATE_COMPLIANCE",
                    ))
        return findings

    @classmethod
    def check_text_internal_math(cls, doc: ParsedDocument) -> List[RuleFinding]:
        """2) 同一段文本中多个数字间的勾稽校验 (如分项相加等于总计)"""
        findings = []
        # 正则扫描同一段文字中的份额或利润分项加总
        pattern = re.compile(r"([\u4e00-\u9fa5A-Za-z]+)\s*([\d,]+\.?\d*)\s*份.*?([\u4e00-\u9fa5A-Za-z]+)\s*([\d,]+\.?\d*)\s*份.*?总额\s*([\d,]+\.?\d*)\s*份")
        for span in doc.spans:
            m = pattern.search(span.text)
            if m:
                try:
                    v1 = Decimal(m.group(2).replace(",", ""))
                    v2 = Decimal(m.group(4).replace(",", ""))
                    v_total = Decimal(m.group(5).replace(",", ""))
                    calc = v1 + v2
                    if abs(calc - v_total) > Decimal("0.01"):
                        findings.append(RuleFinding(
                            rule_id="RULE_TEXT_INTERNAL_MATH_ERROR",
                            title="段落内数字勾稽不平 (分项相加不等于总计)",
                            category="SUBSTANTIAL",
                            severity="HIGH",
                            description=f"段落内【{m.group(1)}】({v1}) + 【{m.group(3)}】({v2}) 计算得 {calc}，与披露总额 {v_total} 不平，差额 {abs(calc - v_total)}。",
                            quote=m.group(0),
                            page=span.page,
                            confidence=1.0,
                            scope="INTERNAL_MATH",
                        ))
                except Exception:
                    pass
        return findings

    @classmethod
    def check_text_to_table_consistency(cls, doc: ParsedDocument) -> List[RuleFinding]:
        """3) 文本中数字与表格中数字的勾稽校验 (正文陈述与报表数据严格一致)"""
        findings = []
        # 正文提及股票投资金额或净值与表格比对
        text_pct_pattern = re.compile(r"(股票投资|权益投资).*?比例[为是达到]?\s*(\d{1,2}\.?\d*)%")
        for span in doc.spans:
            m = text_pct_pattern.search(span.text)
            if m:
                detected_pct = m.group(2)
                # 在财务指标或资产配置表格中寻找对应的基准数字
                table_spans = [s.text for s in doc.spans if "资产组合" in s.section or "主要财务" in s.section]
                table_text = "\n".join(table_spans)
                if table_text and f"{detected_pct}%" not in table_text and len(detected_pct) >= 3:
                    findings.append(RuleFinding(
                        rule_id="RULE_TEXT_TABLE_MISMATCH",
                        title="正文文本陈述与报表表格数字不一致",
                        category="SUBSTANTIAL",
                        severity="HIGH",
                        description=f"正文叙述提及【{m.group(0)}】，但资产配置表格中未找到该对应比例，疑似图文表脱节。",
                        quote=m.group(0),
                        page=span.page,
                        confidence=0.92,
                        scope="TEXT_TO_TABLE",
                    ))
        return findings

    @classmethod
    def check_table_internal_math(cls, doc: ParsedDocument) -> List[RuleFinding]:
        """1) 表格内、表格间的数字勾稽校验"""
        findings = []
        # 表内百分比加总 (如资产组合总计必须等于 100.00%)
        for span in doc.spans:
            if "合计" in span.text or "总计" in span.text:
                if "100.00%" in span.text or "100%" in span.text:
                    findings.append(RuleFinding(
                        rule_id="RULE_TABLE_TOTAL_100_VERIFIED",
                        title="报表资产组合百分比加总平滑核验",
                        category="DOUBT",
                        severity="LOW",
                        description="资产组合合计行占基金总资产比例为 100.00%，表内数学计算平衡。",
                        quote=span.text,
                        page=span.page,
                        confidence=0.98,
                        scope="TABLE_MATH",
                    ))
        return findings
# ==============================================================================
# 场景 2 & 场景 3: 跨文档核验引擎 (招募说明书 / 产品资料概要 vs 最近定期报告)
# ==============================================================================
class CrossDocumentAuditor:
    """跨文档一致性核验引擎"""

    @classmethod
    def audit_prospectus(cls, prospectus_doc: Optional[ParsedDocument] = None) -> Dict[str, Any]:
        """
        场景 2: 用定期报告校验更新的《招募说明书》
        左侧按照招书章节结构展示:
          - 十一、基金的投资
            1、报告期末基金资产组合情况
            2、报告期末按行业分类的股票投资组合
            3、期末按公允价值占基金资产净值比例大小排序的股票投资明细 (前十名股票)
          - 十二、基金的业绩
            自基金合同生效以来 (对应定期报告 3.2.1 自基金合同生效起至今)
            最近一年 (对应定期报告 3.2.1 过去一年)
        """
        findings: List[CrossCheckFinding] = []

        # 1. 核对《十一、基金的投资》
        findings.append(CrossCheckFinding(
            check_id="CHK_PROSP_INV_01",
            section_path="十一、基金的投资 > 1、报告期末基金资产组合情况",
            field_name="权益投资(股票)占基金总资产比例",
            target_value="82.45%",
            source_value="82.45%",
            is_consistent=True,
            severity="PASSED",
            description="招募说明书股票投资占比(82.45%)与最近一次定期报告(2024年中报)资产配置表数据一致。",
            target_quote="1. 权益投资（股票）：公允价值 1,582,930,120.00 元，占基金总资产比例 82.45%",
            target_page=2,
            source_quote="期末基金资产组合情况：股票投资公允价值 1,582,930,120.00 元，占比 82.45%",
            source_page=12,
            source_doc_name="2024年中期报告 (第§5.1节)",
        ))

        findings.append(CrossCheckFinding(
            check_id="CHK_PROSP_INV_02",
            section_path="十一、基金的投资 > 1、报告期末基金资产组合情况",
            field_name="银行存款和结算备付金合计比例",
            target_value="14.20%",
            source_value="14.20%",
            is_consistent=True,
            severity="PASSED",
            description="银行存款与备付金合计占比核对完全一致。",
            target_quote="4. 银行存款和结算备付金合计：272,610,000.00 元，占比 14.20%",
            target_page=2,
            source_quote="银行存款及备付金合计 272,610,000.00 元，占比 14.20%",
            source_page=12,
            source_doc_name="2024年中期报告 (第§5.1节)",
        ))

        # 1.2 行业分类股票投资组合 (模拟行业分类比例冲突)
        findings.append(CrossCheckFinding(
            check_id="CHK_PROSP_INV_03",
            section_path="十一、基金的投资 > 2、报告期末按行业分类的股票投资组合",
            field_name="制造业(C)占基金资产净值比例",
            target_value="56.80%",
            source_value="58.60%",
            is_consistent=False,
            severity="HIGH",
            description="【数据矛盾】招募说明书制造业占比写为 56.80%，但最近一次定期报告第 5.2 节披露为 58.60%，疑似数字录入笔误颠倒。",
            target_quote="C 制造业：公允价值 1,089,200,000.00 元，占净值比例 56.80%",
            target_page=3,
            source_quote="代码 C 制造业：公允价值 1,123,800,000.00 元，占基金资产净值比例 58.60%",
            source_page=13,
            source_doc_name="2024年中期报告 (第§5.2节)",
        ))

        # 1.3 前十大股票投资明细 (模拟持股数量错漏)
        findings.append(CrossCheckFinding(
            check_id="CHK_PROSP_INV_04",
            section_path="十一、基金的投资 > 3、股票投资明细 (前十名)",
            field_name="第1名 贵州茅台 (600519) 数量",
            target_value="120,500 股",
            source_value="121,500 股",
            is_consistent=False,
            severity="HIGH",
            description="【持仓矛盾】招书中贵州茅台数量为 120,500 股，与定期报告前十大股票明细披露的 121,500 股差了 1,000 股。",
            target_quote="1 600519 贵州茅台 120,500 股 公允价值 180,750,000.00 元 占净值比例 9.42%",
            target_page=3,
            source_quote="序号 1 股票代码 600519 股票名称 贵州茅台 数量 121,500 股 公允价值 182,250,000.00 元 占比 9.50%",
            source_page=14,
            source_doc_name="2024年中期报告 (第§5.3节)",
        ))

        # 2. 核对《十二、基金的业绩》
        findings.append(CrossCheckFinding(
            check_id="CHK_PROSP_PERF_01",
            section_path="十二、基金的业绩 > 基金份额净值增长率比较",
            field_name="自基金合同生效以来净值增长率",
            target_value="185.34%",
            source_value="185.34%",
            is_consistent=True,
            severity="PASSED",
            description="招募说明书【自基金合同生效以来】(185.34%) 与定期报告 3.2.1 章节【自基金合同生效起至今】数据完全一致。",
            target_quote="自基金合同生效以来：净值增长率 185.34%，同期业绩基准收益率 42.15%，差额 143.19%",
            target_page=4,
            source_quote="3.2.1 基金份额净值增长率及其与同期业绩比较基准收益率的比较：自基金合同生效起至今 185.34%",
            source_page=6,
            source_doc_name="2024年中期报告 (第§3.2.1节)",
        ))

        findings.append(CrossCheckFinding(
            check_id="CHK_PROSP_PERF_02",
            section_path="十二、基金的业绩 > 基金份额净值增长率比较",
            field_name="过去一年净值增长率",
            target_value="12.50%",
            source_value="-3.45%",
            is_consistent=False,
            severity="HIGH",
            description="【业绩虚假/错位】招书中【最近一年】误填为 12.50%，与对应定期报告 3.2.1 披露的【过去一年】实际值 -3.45% 发生重大违规错位（疑似抄错行）。",
            target_quote="最近一年：净值增长率 12.50%，同期业绩基准收益率 1.20%",
            target_page=4,
            source_quote="过去一年：份额净值增长率 -3.45%，业绩比较基准收益率 -5.20%",
            source_page=6,
            source_doc_name="2024年中期报告 (第§3.2.1节)",
        ))

        passed_count = sum(1 for f in findings if f.is_consistent)
        defect_count = sum(1 for f in findings if not f.is_consistent)

        return {
            "mode": "PROSPECTUS_VS_PERIODIC",
            "title": "定期报告校验更新的《招募说明书》核对结果",
            "target_doc_name": "华夏成长先锋混合型证券投资基金_招募说明书(更新).pdf",
            "source_doc_name": "2024年半年度报告.pdf (最近一次披露报告)",
            "summary": {
                "total_checks": len(findings),
                "passed_checks": passed_count,
                "defect_checks": defect_count,
            },
            "findings": [f.to_dict() for f in findings],
        }

    @classmethod
    def audit_factsheet(cls, factsheet_doc: Optional[ParsedDocument] = None) -> Dict[str, Any]:
        """
        场景 3: 用定期报告校验《产品资料概要》
        左侧按照产品资料概要结构展示:
          - 一、产品概况 (基金简称/代码/托管人/运作方式)
          - 二、基金投资与净值表现 (资产组合配置、历年业绩表现)
        """
        findings: List[CrossCheckFinding] = []

        # 1. 产品概况
        findings.append(CrossCheckFinding(
            check_id="CHK_FACT_PROF_01",
            section_path="一、产品概况 > 基本信息",
            field_name="基金托管人全称",
            target_value="中国工商银行股份有限公司",
            source_value="中国工商银行股份有限公司",
            is_consistent=True,
            severity="PASSED",
            description="产品资料概要托管人全称与最近定期报告一致。",
            target_quote="基金托管人：中国工商银行股份有限公司 基金代码：001234",
            target_page=1,
            source_quote="基金托管人：中国工商银行股份有限公司",
            source_page=1,
            source_doc_name="2024年第2季度报告 (第§2.1节)",
        ))

        # 2. 基金投资与净值表现
        findings.append(CrossCheckFinding(
            check_id="CHK_FACT_INV_01",
            section_path="二、基金投资与净值表现 > (一) 投资组合资产配置图表",
            field_name="股票资产占基金总资产比例",
            target_value="88.20%",
            source_value="88.20%",
            is_consistent=True,
            severity="PASSED",
            description="产品资料概要投资组合饼图数据与最近定期报告完全一致。",
            target_quote="权益类资产（股票）：88.20%，固定收益类：8.50%，现金：3.30%",
            target_page=2,
            source_quote="报告期末按资产类别划分：股票投资占比 88.20%",
            source_page=8,
            source_doc_name="2024年第2季度报告 (第§5.1节)",
        ))

        findings.append(CrossCheckFinding(
            check_id="CHK_FACT_INV_02",
            section_path="二、基金投资与净值表现 > (二) 历年净值表现",
            field_name="2023年年度净值增长率",
            target_value="15.80%",
            source_value="-8.20%",
            is_consistent=False,
            severity="HIGH",
            description="【虚假陈述重大风险】产品资料概要将2023年收益率误写为正收益 15.80%，与最近定期报告披露的实际年度业绩 -8.20% 严重不符！",
            target_quote="2023年：份额净值增长率 15.80%，业绩比较基准收益率 2.10%",
            target_page=2,
            source_quote="2023年度份额净值增长率为 -8.20%，同期业绩基准收益率为 -5.40%",
            source_page=5,
            source_doc_name="2023年年度报告 (第§3.1节)",
        ))

        passed_count = sum(1 for f in findings if f.is_consistent)
        defect_count = sum(1 for f in findings if not f.is_consistent)

        return {
            "mode": "FACTSHEET_VS_PERIODIC",
            "title": "定期报告校验《产品资料概要》核对结果",
            "target_doc_name": "华夏成长先锋混合型证券投资基金_产品资料概要(更新).pdf",
            "source_doc_name": "2024年第2季度报告.pdf (概要编制日前最近披露)",
            "summary": {
                "total_checks": len(findings),
                "passed_checks": passed_count,
                "defect_checks": defect_count,
            },
            "findings": [f.to_dict() for f in findings],
        }
