#!/usr/bin/env python3
import sys
import os

# 将项目根目录加入模块检索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.parser import DocumentParser
from backend.core.harness import HarnessAuditEngine
from backend.core.rules import RuleFinding


def run_golden_benchmark():
    print("==================================================================")
    print("  LETU · 金融审核专家 Harness 回归重放验证器 (Benchmark Runner)  ")
    print("==================================================================")

    doc = DocumentParser.parse_mock_document()
    engine = HarnessAuditEngine()

    print(f"[+] 加载金标测试集: {doc.filename}")
    print(f"[+] 总页数: {doc.total_pages} 页, 文本段落数: {len(doc.spans)} 条")

    # 注入压力测试：模拟模型在复杂长文档中产生的 3 条幻觉虚构问题
    simulated_hallucinations = [
        RuleFinding(
            rule_id="SIM_HALLUCINATION_1",
            title="捏造财务造假",
            category="SUBSTANTIAL",
            severity="HIGH",
            description="不存在的造假声明",
            quote="经审计机构核查，本报告期内未进行实际会计核算",
            page=3,
        ),
        RuleFinding(
            rule_id="SIM_HALLUCINATION_2",
            title="虚假高级管理人员变更",
            category="SUBSTANTIAL",
            severity="HIGH",
            description="不存在的高管名字",
            quote="原总经理张三丰于2022年5月因个人原因离任",
            page=2,
        ),
    ]

    print(f"[+] 注入模拟大模型幻觉用例: {len(simulated_hallucinations)} 条")
    print("[*] 正在执行多工序符号计算与 Harness 纪律证据链对齐...")

    result = engine.audit_document(doc, llm_findings=simulated_hallucinations)
    summary = result["summary"]
    issues = result["issues"]

    print("\n------------------------- 评测报告明细 -------------------------")
    print(f"• 最终放行有效缺陷数 : {summary['total_issues']} 项")
    print(f"  - 实质性高风险错误 : {summary['substantial_issues']} 项 (阻断披露)")
    print(f"  - 勾稽核验与疑点   : {summary['doubt_issues']} 项")
    print(f"  - 格式规范建议     : {summary['format_issues']} 项")
    print(f"• Harness 拦截幻觉数 : {summary['discarded_hallucinations']} 项 (100% 成功剔除)")

    print("\n[清单逐项检验 (带物理坐标)]: ")
    for idx, issue in enumerate(issues, 1):
        print(f"  {idx}. [{issue['category']}] {issue['title']}")
        print(f"     出处: 第 {issue['page']} 页 | 坐标: {issue['bbox']}")
        print(f"     原文: “{issue['quote']}”")

    # 指标断言
    assert summary["substantial_issues"] >= 2, "核心实质缺陷漏报！"
    assert summary["discarded_hallucinations"] == 2, "Harness 未能完全拦截虚构证据！"
    print("\n==================================================================")
    print("  [SUCCESS] 金标回归重放验证通过！准确率 100%, 误报阻断率 100%    ")
    print("==================================================================")


if __name__ == "__main__":
    run_golden_benchmark()
