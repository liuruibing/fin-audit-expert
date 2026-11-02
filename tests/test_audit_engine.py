import pytest
from backend.core.parser import DocumentParser, TextSpan
from backend.core.rules import SymbolicAuditRules, RuleFinding
from backend.core.harness import HarnessAuditEngine
from backend.core.flywheel import DecisionFlywheel


def test_mock_document_parsing():
    """测试模拟金融中报文档解析"""
    doc = DocumentParser.parse_mock_document()
    assert doc.total_pages == 4
    assert len(doc.spans) > 10
    
    # 测试证据检索功能
    evidence = doc.find_text_evidence("报告截止日2021年6月30日")
    assert evidence is not None
    assert evidence["page"] == 2
    assert len(evidence["bbox"]) == 4


def test_rules_detection():
    """测试规则引擎：时点矛盾、主体矛盾、份额勾稽"""
    doc = DocumentParser.parse_mock_document()
    doc_facts = {
        "report_period": "2022年中期",
        "report_year": "2022",
        "cutoff_date": "2022-06-30",
        "custodian": "中国工商银行股份有限公司",
    }

    # 1. 时点冲突
    time_issues = SymbolicAuditRules.check_time_conflicts(doc_facts, doc.spans)
    assert len(time_issues) >= 1
    assert any("2021" in t.quote for t in time_issues)

    # 2. 托管人主体冲突 (封面工行 vs 备查目录建行)
    entity_issues = SymbolicAuditRules.check_entity_consistency(doc_facts, doc.spans)
    assert len(entity_issues) >= 1
    assert any("建设银行" in e.quote for e in entity_issues)

    # 3. 份额勾稽核算
    math_issues = SymbolicAuditRules.check_share_math_gouji(doc.spans)
    assert len(math_issues) >= 1


def test_harness_grounding_assertion():
    """测试 Harness 纪律中枢：有据才报与防幻觉剔除机制"""
    doc = DocumentParser.parse_mock_document()
    engine = HarnessAuditEngine()

    # 构造一条真实的缺陷，和一条大模型凭空捏造的幻觉缺陷 (原文中完全不存在)
    fake_hallucination = RuleFinding(
        rule_id="HALLUCINATION_TEST",
        title="虚构的会计差错",
        category="SUBSTANTIAL",
        severity="HIGH",
        description="模型自己编造的句子",
        quote="本基金管理人由于计算失误导致多提取了管理费一千万元整",  # 原文中绝对没有
        page=2,
    )

    result = engine.audit_document(doc, llm_findings=[fake_hallucination])

    # 校验：虚构的缺陷必须被 Harness 自动识别并丢弃！
    assert result["summary"]["discarded_hallucinations"] >= 1
    # 真实存在的问题全部被保留并附带物理坐标
    for issue in result["issues"]:
        assert issue["bbox"] is not None
        assert len(issue["bbox"]) == 4
        assert issue["rule_id"] != "HALLUCINATION_TEST"


def test_decision_flywheel():
    """测试专家裁决留痕数据飞轮"""
    entry = DecisionFlywheel.record_decision(
        issue_id="TEST_001",
        rule_id="RULE_TIME_CONFLICT",
        decision="CONFIRMED_DEFECT",
        expert_name="张专家",
        reason="测试确认",
        document_name="test.pdf",
        quote="测试引用"
    )
    assert entry["decision"] == "CONFIRMED_DEFECT"
    assert entry["expert_name"] == "张专家"
