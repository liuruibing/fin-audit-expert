import re
from typing import List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP


class RuleFinding:
    def __init__(
        self,
        rule_id: str,
        title: str,
        category: str,       # "SUBSTANTIAL" (实质性) | "DOUBT" (疑点) | "FORMAT" (格式建议)
        severity: str,       # "HIGH" | "MEDIUM" | "LOW"
        description: str,
        quote: str,
        page: int,
        context_quote: Optional[str] = None,
        context_page: Optional[int] = None,
        confidence: float = 1.0,
    ):
        self.rule_id = rule_id
        self.title = title
        self.category = category
        self.severity = severity
        self.description = description
        self.quote = quote
        self.page = page
        self.context_quote = context_quote
        self.context_page = context_page
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "quote": self.quote,
            "page": self.page,
            "context_quote": self.context_quote,
            "context_page": self.context_page,
            "confidence": self.confidence,
        }


class SymbolicAuditRules:
    """符号与确定性逻辑核验规则集"""

    @staticmethod
    def check_time_conflicts(doc_facts: Dict[str, Any], spans: List[Any]) -> List[RuleFinding]:
        """检查报告期与正文各处截止日期是否产生时点穿越/冲突"""
        findings = []
        base_period = doc_facts.get("report_period", "2022年中期")
        base_year = doc_facts.get("report_year", "2022")
        base_cutoff = doc_facts.get("cutoff_date", "2022-06-30")

        # 匹配正文中所有形如 "报告截止日 2021 年 6 月 30 日"、"截至2021-12-31" 的句子
        cutoff_pattern = re.compile(r"(报告截止日|截至|期末时点)[：:\s]*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
        
        for span in spans:
            match = cutoff_pattern.search(span.text)
            if match:
                detected_year = match.group(2)
                detected_month = match.group(3).zfill(2)
                detected_day = match.group(4).zfill(2)
                detected_date_str = f"{detected_year}-{detected_month}-{detected_day}"

                # 如果正文截止年份小于基准年份，说明直接套用上一期未修改
                if detected_year != base_year:
                    findings.append(RuleFinding(
                        rule_id="RULE_TIME_CONFLICT",
                        title="报表截止日期与报告期矛盾",
                        category="SUBSTANTIAL",
                        severity="HIGH",
                        description=f"注明'{match.group(0)}'，但本报告为{base_period}报告，基准截止日应为 {base_cutoff}，存在复制上一期模板未修改风险。",
                        quote=match.group(0),
                        page=span.page,
                        context_quote=f"本报告为 {base_period} 报告",
                        context_page=1,
                        confidence=0.98,
                    ))

        return findings

    @staticmethod
    def check_entity_consistency(doc_facts: Dict[str, Any], spans: List[Any]) -> List[RuleFinding]:
        """检查跨章节的主体名称一致性（如封面托管人 vs 备查文件目录中的托管人）"""
        findings = []
        custodian = doc_facts.get("custodian", "中国工商银行股份有限公司")

        # 已知主流托管行简写/简称
        bank_keywords = ["工商银行", "建设银行", "农业银行", "中国银行", "招商银行", "交通银行", "兴业银行", "中信银行"]
        
        # 寻找封面确定的托管行是哪一家
        base_bank = None
        for b in bank_keywords:
            if b in custodian:
                base_bank = b
                break

        if not base_bank:
            return findings

        # 扫描除封面外的章节，检查是否串入其他银行名称
        for span in spans:
            if span.page == 1:
                continue
            for other_bank in bank_keywords:
                if other_bank != base_bank and other_bank in span.text:
                    if "托管" in span.text or "备查" in span.text or "协议" in span.text:
                        findings.append(RuleFinding(
                            rule_id="RULE_ENTITY_MISMATCH",
                            title="托管人主体名称前后矛盾",
                            category="SUBSTANTIAL",
                            severity="HIGH",
                            description=f"封面注明基金托管人为【{custodian}】，但在第 {span.page} 页此处出现【{other_bank}】，疑似章节复制混入错误主体。",
                            quote=span.text,
                            page=span.page,
                            context_quote=f"基金托管人：{custodian}",
                            context_page=1,
                            confidence=0.95,
                        ))

        return findings

    @staticmethod
    def check_share_math_gouji(spans: List[Any]) -> List[RuleFinding]:
        """检查份额相加、净值乘算等勾稽关系的符号计算"""
        findings = []
        share_pattern = re.compile(
            r"A\s*类份额\s*([\d,]+\.?\d*)\s*份.*C\s*类份额\s*([\d,]+\.?\d*)\s*份.*份额总额\s*([\d,]+\.?\d*)\s*份"
        )

        for span in spans:
            match = share_pattern.search(span.text)
            if match:
                try:
                    share_a = Decimal(match.group(1).replace(",", ""))
                    share_c = Decimal(match.group(2).replace(",", ""))
                    share_total = Decimal(match.group(3).replace(",", ""))
                    
                    calculated_total = share_a + share_c
                    diff = abs(calculated_total - share_total)

                    if diff > Decimal("0.01"):
                        findings.append(RuleFinding(
                            rule_id="RULE_SHARE_MATH_ERROR",
                            title="分级份额与总份额勾稽不平",
                            category="SUBSTANTIAL",
                            severity="HIGH",
                            description=f"A类份额 ({share_a}) + C类份额 ({share_c}) 计算合计为 {calculated_total} 份，但正文披露份额总额为 {share_total} 份，差额 {diff} 份。",
                            quote=match.group(0),
                            page=span.page,
                            confidence=1.0,
                        ))
                    else:
                        # 勾稽成立，作为审计核验通过的疑点留痕
                        findings.append(RuleFinding(
                            rule_id="RULE_SHARE_MATH_VERIFIED",
                            title="份额加总勾稽核验",
                            category="DOUBT",
                            severity="LOW",
                            description=f"A类 ({share_a}) + C类 ({share_c}) = {share_total} 份，数学勾稽成立，需复核期末登记机构确认数据。",
                            quote=match.group(0),
                            page=span.page,
                            confidence=0.90,
                        ))
                except Exception:
                    pass

        return findings

    @staticmethod
    def check_format_conventions(spans: List[Any]) -> List[RuleFinding]:
        """检查日期体例混用等格式规范"""
        findings = []
        has_hyphen_date = False
        has_chinese_date = False
        sample_hyphen = None
        sample_chinese = None

        hyphen_re = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
        chinese_re = re.compile(r"\b\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\b")

        for span in spans:
            m1 = hyphen_re.search(span.text)
            if m1 and not sample_hyphen:
                has_hyphen_date = True
                sample_hyphen = (m1.group(0), span.page)

            m2 = chinese_re.search(span.text)
            if m2 and not sample_chinese:
                has_chinese_date = True
                sample_chinese = (m2.group(0), span.page)

        if has_hyphen_date and has_chinese_date and sample_hyphen and sample_chinese:
            findings.append(RuleFinding(
                rule_id="RULE_STYLE_INCONSISTENCY",
                title="纪年体例写法不统一",
                category="FORMAT",
                severity="LOW",
                description=f"同一份报告内存在 '{sample_chinese[0]}' 与 '{sample_hyphen[0]}' 两种日期写法混用，建议全篇统一使用中文日期体例。",
                quote=sample_hyphen[0],
                page=sample_hyphen[1],
                context_quote=sample_chinese[0],
                context_page=sample_chinese[1],
                confidence=0.85,
            ))

        return findings
