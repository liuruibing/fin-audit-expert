import json
import time
from typing import Dict, Any, List
from pathlib import Path
from ..config import DECISION_LOG_PATH, GOLDEN_BENCHMARK_PATH


class DecisionFlywheel:
    """专家裁决留痕与回归重放数据飞轮"""

    @staticmethod
    def record_decision(
        issue_id: str,
        rule_id: str,
        decision: str,  # "CONFIRMED_DEFECT" | "FALSE_ALARM"
        expert_name: str,
        reason: str = "",
        document_name: str = "",
        quote: str = "",
    ) -> Dict[str, Any]:
        """记录专家的一键裁决并留痕，供后续金标训练与重放"""
        entry = {
            "issue_id": issue_id,
            "rule_id": rule_id,
            "decision": decision,
            "expert_name": expert_name,
            "reason": reason,
            "document_name": document_name,
            "quote": quote,
            "timestamp": int(time.time()),
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        logs = []
        if DECISION_LOG_PATH.exists():
            try:
                with open(DECISION_LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        logs.append(entry)
        with open(DECISION_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        return entry

    @staticmethod
    def get_audit_metrics() -> Dict[str, Any]:
        """统计价值回执工作台数据 (审了多少、拦了多少实质问题、专家裁决数)"""
        logs = []
        if DECISION_LOG_PATH.exists():
            try:
                with open(DECISION_LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        confirmed = sum(1 for log in logs if log.get("decision") == "CONFIRMED_DEFECT")
        false_alarms = sum(1 for log in logs if log.get("decision") == "FALSE_ALARM")

        return {
            "total_documents_audited": 6647,  # 基线演示数据
            "total_issues_flagged": 2967,
            "substantial_defects_prevented": 253 + confirmed,
            "expert_decisions_recorded": len(logs),
            "confirmed_count": confirmed,
            "false_alarm_count": false_alarms,
            "average_time_per_doc": "3 分钟 (原人工抽查需 4 小时)",
            "covered_institutions": 89,
        }
