import os
import re
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RULES_KB_DIR = BASE_DIR / "rules_kb"


class RuleKbEntry:
    def __init__(
        self,
        rule_id: str,
        title: str,
        category: str,
        severity: str,
        content: str,
        file_source: str,
    ):
        self.rule_id = rule_id
        self.title = title
        self.category = category
        self.severity = severity
        self.content = content
        self.file_source = file_source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "content": self.content,
            "file_source": self.file_source,
        }


class RuleKbEngine:
    """Markdown 规则知识库加载器与动态维护引擎 (无硬编码)"""

    @classmethod
    def load_all_rules(cls) -> List[RuleKbEntry]:
        """扫描 rules_kb/*.md 提取所有已定义的结构化审核规则"""
        if not RULES_KB_DIR.exists():
            return []

        entries = []
        md_files = sorted(RULES_KB_DIR.glob("*.md"))
        for md_path in md_files:
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    text = f.read()
                entries.extend(cls._parse_markdown_rules(text, md_path.name))
            except Exception as e:
                print(f"Failed to parse rule file {md_path}: {e}")

        return entries

    @classmethod
    def get_kb_files(cls) -> List[Dict[str, str]]:
        """获取所有规则 md 文件名与内容供前端知识库管理"""
        files = []
        if not RULES_KB_DIR.exists():
            return files

        for md_path in sorted(RULES_KB_DIR.glob("*.md")):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    content = f.read()
                files.append({
                    "filename": md_path.name,
                    "title": md_path.stem.replace("_", " ").upper(),
                    "content": content,
                })
            except Exception:
                pass
        return files

    @classmethod
    def save_kb_file(cls, filename: str, content: str) -> bool:
        """支持在线更新修改某个 Markdown 规则文件"""
        target = RULES_KB_DIR / filename
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False

    @classmethod
    def append_user_learned_rule(
        cls,
        rule_title: str,
        issue_quote: str,
        expert_reason: str,
        severity: str = "HIGH",
        generated_rule_text: str = "",
    ) -> Dict[str, Any]:
        """将专家在界面上的真缺陷标注转化为一条永久生效的 Markdown 规则"""
        RULES_KB_DIR.mkdir(parents=True, exist_ok=True)
        user_md_path = RULES_KB_DIR / "99_user_learned.md"

        rule_num = int(time.time() % 10000)
        rule_id = f"RULE_USER_{rule_num}"
        date_str = time.strftime("%Y-%m-%d %H:%M:%S")

        rule_block = f"\n\n---\n\n## 规则：{rule_title} (专家裁决自动提炼)\n"
        rule_block += f"- **规则编号**：`{rule_id}`\n"
        rule_block += f"- **提炼时间**：{date_str}\n"
        rule_block += f"- **风险等级**：`{severity}`\n"
        rule_block += f"- **标注样本出处**：“{issue_quote[:100]}”\n"
        rule_block += f"- **专家裁决理由**：{expert_reason}\n"
        if generated_rule_text:
            rule_block += f"- **审核准则要求**：\n  {generated_rule_text.strip()}\n"
        else:
            rule_block += f"- **审核准则要求**：\n  严格审查该项表述是否与披露基准完全吻合，杜绝‘{issue_quote[:50]}’类错漏。\n"

        with open(user_md_path, "a", encoding="utf-8") as f:
            f.write(rule_block)

        return {
            "rule_id": rule_id,
            "title": rule_title,
            "severity": severity,
            "status": "SAVED_TO_KB",
            "file": "99_user_learned.md",
        }

    @classmethod
    def get_prompt_context_for_llm(cls, doc_type: str = "ANNUAL") -> str:
        """为大模型生成当前的 Markdown 规则上下文指导"""
        rules = cls.load_all_rules()
        lines = ["【金融信息披露通用与专项审核准则知识库 (Markdown)】:"]
        for r in rules:
            lines.append(f"• [{r.rule_id}] {r.title} (等级: {r.severity}):")
            summary = r.content.replace("\n", " ")[:150]
            lines.append(f"  {summary}")
        return "\n".join(lines)

    @classmethod
    def _parse_markdown_rules(cls, text: str, filename: str) -> List[RuleKbEntry]:
        """从 Markdown 文件中按二级标题提取规则"""
        entries = []
        sections = re.split(r"\n(?=##\s+)", text)
        for sec in sections:
            if not sec.strip().startswith("##"):
                continue
            title_match = re.search(r"^##\s*(.*)", sec)
            title = title_match.group(1).strip() if title_match else "未命名规则"
            
            id_match = re.search(r"规则编号[：:\s]*`?([A-Za-z0-9_]+)`?", sec)
            rule_id = id_match.group(1) if id_match else f"R_{abs(hash(title)) % 10000}"

            sev_match = re.search(r"风险等级[：:\s]*`?([A-Za-z]+)`?", sec)
            severity = sev_match.group(1) if sev_match else "HIGH"

            entries.append(RuleKbEntry(
                rule_id=rule_id,
                title=title,
                category="SUBSTANTIAL" if severity == "HIGH" else "DOUBT",
                severity=severity,
                content=sec.strip(),
                file_source=filename,
            ))
        return entries
