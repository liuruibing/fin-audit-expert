from typing import List, Dict, Any, Optional
import uuid
from .parser import ParsedDocument
from .rules import RuleFinding, SymbolicAuditRules


class AuditIssue:
    def __init__(
        self,
        id: str,
        rule_id: str,
        title: str,
        category: str,       # "SUBSTANTIAL" | "DOUBT" | "FORMAT"
        severity: str,       # "HIGH" | "MEDIUM" | "LOW"
        description: str,
        quote: str,
        page: int,
        bbox: List[float],
        context_quote: Optional[str] = None,
        context_page: Optional[int] = None,
        context_bbox: Optional[List[float]] = None,
        confidence: float = 1.0,
        status: str = "PENDING",  # PENDING | CONFIRMED_DEFECT | FALSE_ALARM
    ):
        self.id = id
        self.rule_id = rule_id
        self.title = title
        self.category = category
        self.severity = severity
        self.description = description
        self.quote = quote
        self.page = page
        self.bbox = bbox
        self.context_quote = context_quote
        self.context_page = context_page
        self.context_bbox = context_bbox
        self.confidence = confidence
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "quote": self.quote,
            "page": self.page,
            "bbox": self.bbox,
            "context_quote": self.context_quote,
            "context_page": self.context_page,
            "context_bbox": self.context_bbox,
            "confidence": self.confidence,
            "status": self.status,
        }


class HarnessAuditEngine:
    """
    Harness 纪律与约束引擎:
    1. 有据才报: 严格检验证据链，拿不到原文精确物理坐标的一律剔除；
    2. 分级分列: 拆分实质性缺陷、格式类与疑点；
    3. 符号与大模型协同: 融合推理结果并排除冲突。
    """

    def __init__(self):
        self.rules = SymbolicAuditRules()

    def audit_document(
        self,
        doc: ParsedDocument,
        doc_facts: Optional[Dict[str, Any]] = None,
        llm_findings: Optional[List[RuleFinding]] = None,
    ) -> Dict[str, Any]:
        if doc_facts is None:
            # 默认从文档抽取基础事实锚点 (封面要素)
            doc_facts = self._extract_baseline_facts(doc)

        candidate_findings: List[RuleFinding] = []

        # 1. 运行符号与确定性逻辑规则
        candidate_findings.extend(self.rules.check_time_conflicts(doc_facts, doc.spans))
        candidate_findings.extend(self.rules.check_entity_consistency(doc_facts, doc.spans))
        candidate_findings.extend(self.rules.check_share_math_gouji(doc.spans))
        candidate_findings.extend(self.rules.check_format_conventions(doc.spans))
        candidate_findings.extend(self.rules.check_benchmark_consistency(doc.spans))

        # 2. 合并 LLM 上报的线索 (如有)
        if llm_findings:
            candidate_findings.extend(llm_findings)

        # 3. Harness 纪律检验: 证据严格对齐与坐标检索 (Grounding Check)
        verified_issues: List[AuditIssue] = []
        discarded_count = 0

        for f in candidate_findings:
            # 主出处坐标比对
            evidence = doc.find_text_evidence(f.quote, page_hint=f.page)
            if not evidence:
                # 证据无法在原文档中找到，判定为大模型幻觉虚构，直接抛弃！
                discarded_count += 1
                continue

            # 对照处坐标比对 (如有)
            context_bbox = None
            if f.context_quote:
                ctx_evidence = doc.find_text_evidence(f.context_quote, page_hint=f.context_page)
                if ctx_evidence:
                    context_bbox = ctx_evidence["bbox"]

            issue = AuditIssue(
                id=f"ISSUE_{uuid.uuid4().hex[:8].upper()}",
                rule_id=f.rule_id,
                title=f.title,
                category=f.category,
                severity=f.severity,
                description=f.description,
                quote=evidence["matched_text"],
                page=evidence["page"],
                bbox=evidence["bbox"],
                context_quote=f.context_quote,
                context_page=f.context_page,
                context_bbox=context_bbox,
                confidence=f.confidence,
            )
            verified_issues.append(issue)

        # 4. 统计汇总
        substantial_count = sum(1 for i in verified_issues if i.category == "SUBSTANTIAL")
        doubt_count = sum(1 for i in verified_issues if i.category == "DOUBT")
        format_count = sum(1 for i in verified_issues if i.category == "FORMAT")

        return {
            "filename": doc.filename,
            "total_pages": doc.total_pages,
            "doc_facts": doc_facts,
            "summary": {
                "total_issues": len(verified_issues),
                "substantial_issues": substantial_count,
                "doubt_issues": doubt_count,
                "format_issues": format_count,
                "discarded_hallucinations": discarded_count,
            },
            "issues": [i.to_dict() for i in verified_issues],
        }

    def _extract_baseline_facts(self, doc: ParsedDocument) -> Dict[str, Any]:
        """从第一页(封面)抽取产品全称、报告期、管理人、托管人作为基准事实锚点"""
        page1_spans = [s.text for s in doc.spans if s.page == 1]
        text = "\n".join(page1_spans)

        # 默认提取
        product_name = page1_spans[0] if page1_spans else doc.filename
        manager = "基金管理有限公司"
        custodian = "托管银行股份有限公司"
        report_period = "年度报告"
        report_year = "2023"
        cutoff_date = "2023-12-31"

        for line in page1_spans:
            if "管理人" in line:
                manager = line.split("：")[-1].strip()
            elif "托管人" in line:
                custodian = line.split("：")[-1].strip()
            elif "中期" in line or "半年度" in line:
                report_period = "中期报告"
                cutoff_date = "2022-06-30"
                report_year = "2022"
            elif "年度报告" in line:
                report_period = "年度报告"
                cutoff_date = "2023-12-31"
                report_year = "2023"

        return {
            "product_name": product_name,
            "report_period": report_period,
            "report_year": report_year,
            "cutoff_date": cutoff_date,
            "manager": manager,
            "custodian": custodian,
        }
