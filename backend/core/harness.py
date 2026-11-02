import re
import uuid
from typing import List, Dict, Any, Optional
from .parser import ParsedDocument
from .classifier import DocumentClassifier, DocumentProfile
from .rules import (
    RuleFinding,
    GlobalAuditRules,
    AnnualReportRules,
    SemiAnnualRules,
    QuarterlyReportRules,
    FundSpecificRules,
    ListedCompanyRules,
)
from .cross_checker import MultiLevelGoujiEngine


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
        scope: str = "GLOBAL",
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
        self.scope = scope

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
            "scope": self.scope,
        }


class HarnessAuditEngine:
    """
    Harness 纪律与约束引擎:
    第 1 步: 智能判型与画像抽取 (年报 / 半年报 / 季报 / 月报 / 周报 / 招募说明书);
    第 2 步: 全局通用金融规则 (格式/主体/单位);
    第 3 步: 按类型与主体分发专属规则处理;
    第 4 步: 有据才报严格断言 (无坐标直接剔除).
    """

    def audit_document(
        self,
        doc: ParsedDocument,
        llm_findings: Optional[List[RuleFinding]] = None,
    ) -> Dict[str, Any]:
        # -------------------------------------------------------------
        # 第 1 步: 先区分文档类型与主体画像
        # -------------------------------------------------------------
        profile: DocumentProfile = DocumentClassifier.classify(doc)

        candidate_findings: List[RuleFinding] = []

        # -------------------------------------------------------------
        # 第 2 步: 执行全局通用金融规则 (所有金融文档通用)
        # -------------------------------------------------------------
        candidate_findings.extend(GlobalAuditRules.check_format_conventions(doc.spans))
        candidate_findings.extend(GlobalAuditRules.check_entity_consistency(profile, doc.spans))
        # 执行场景 1: 多层级数字勾稽与文本合规性校验 (表内/表间/文本/超期日期)
        candidate_findings.extend(MultiLevelGoujiEngine.run_all_checks(doc, profile.cutoff_date))
        # -------------------------------------------------------------
        # 第 3 步: 按文档类型进行专属规则分流处理
        # -------------------------------------------------------------
        if profile.doc_type == "ANNUAL":
            # 年报专属: 审计意见/核数师声明、完整年度截止日
            candidate_findings.extend(AnnualReportRules.check_annual_audit_opinion(doc.spans))
            candidate_findings.extend(AnnualReportRules.check_annual_cutoff_statement(profile, doc.spans))
            
        elif profile.doc_type == "SEMI_ANNUAL":
            # 半年报/中报专属: 中期时点穿越、上一期模板遗留
            candidate_findings.extend(SemiAnnualRules.check_semi_annual_cutoff_conflict(profile, doc.spans))
            
        elif profile.doc_type == "QUARTERLY":
            # 季报专属: 季度末时点
            candidate_findings.extend(QuarterlyReportRules.check_quarterly_period_cutoff(profile, doc.spans))

        # -------------------------------------------------------------
        # 第 4 步: 按机构主体性质进行特殊业务分流处理
        # -------------------------------------------------------------
        if profile.entity_type == "PUBLIC_FUND":
            # 基金专有: 份额代数加总勾稽、业绩比较基准冲突
            candidate_findings.extend(FundSpecificRules.check_share_math_gouji(doc.spans))
            candidate_findings.extend(FundSpecificRules.check_benchmark_consistency(doc.spans))
            
        elif profile.entity_type == "LISTED_COMPANY":
            # 上市公司专有: 港股双柜台代码核对、核数师合规检查
            candidate_findings.extend(ListedCompanyRules.check_listed_compliance(profile, doc.spans))

        # 合并大模型上报的外部线索
        if llm_findings:
            candidate_findings.extend(llm_findings)

        # -------------------------------------------------------------
        # 第 5 步: Harness 纪律检验: 证据严格对齐与坐标检索 (Grounding Check)
        # -------------------------------------------------------------
        verified_issues: List[AuditIssue] = []
        discarded_count = 0

        for f in candidate_findings:
            evidence = doc.find_text_evidence(f.quote, page_hint=f.page)
            if not evidence:
                # 原文无确凿证据，直接物理抛弃
                discarded_count += 1
                continue

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
                scope=f.scope,
            )
            verified_issues.append(issue)

        substantial_count = sum(1 for i in verified_issues if i.category == "SUBSTANTIAL")
        doubt_count = sum(1 for i in verified_issues if i.category == "DOUBT")
        format_count = sum(1 for i in verified_issues if i.category == "FORMAT")

        return {
            "filename": doc.filename,
            "total_pages": doc.total_pages,
            "profile": profile.to_dict(),
            "summary": {
                "total_issues": len(verified_issues),
                "substantial_issues": substantial_count,
                "doubt_issues": doubt_count,
                "format_issues": format_count,
                "discarded_hallucinations": discarded_count,
            },
            "issues": [i.to_dict() for i in verified_issues],
        }
