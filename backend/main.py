from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path
import shutil
import uuid

from .core.parser import DocumentParser
from .core.harness import HarnessAuditEngine
from .core.model_client import FinancialAuditModelClient
from .core.flywheel import DecisionFlywheel
from .config import BASE_DIR, SAMPLES_DIR

app = FastAPI(
    title="FinAudit-Expert (金融信披审核专家系统)",
    description="基于金融垂类大模型与 Harness 框架体系的智能审核中台",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = HarnessAuditEngine()
model_client = FinancialAuditModelClient()

# 当前内存缓存，演示方便
active_audit_result: Dict[str, Any] = {}
active_parsed_doc: Any = None


class DecisionRequest(BaseModel):
    issue_id: str
    rule_id: str
    decision: str  # CONFIRMED_DEFECT | FALSE_ALARM
    expert_name: str
    reason: Optional[str] = ""
    document_name: Optional[str] = ""
    quote: Optional[str] = ""

class DiagnoseRequest(BaseModel):
    title: str
    description: str
    quote: str

class CopilotAskRequest(BaseModel):
    question: str
    issue_id: Optional[str] = None
class SaveKbFileRequest(BaseModel):
    filename: str
    content: str


class SynthesizeRuleRequest(BaseModel):
    issue_title: str
    issue_quote: str
    expert_reason: str
    severity: Optional[str] = "HIGH"


from .config import SUPPORTED_MODELS, ACTIVE_MODEL_ID, ACTIVE_PROVIDER

current_model_id = ACTIVE_MODEL_ID
current_provider = ACTIVE_PROVIDER


class ModelSelectRequest(BaseModel):
    model_id: str


class SampleSwitchRequest(BaseModel):
    sample_name: str


@app.on_event("startup")
def startup_event():
    global active_audit_result, active_parsed_doc
    active_parsed_doc = DocumentParser.parse_mock_document("swlx")
    active_audit_result = engine.audit_document(active_parsed_doc)


@app.get("/api/models")
def get_models():
    """获取系统支持的所有模型引擎与当前选用状态"""
    global current_model_id, current_provider
    return {
        "active_model_id": current_model_id,
        "active_provider": current_provider,
        "models": SUPPORTED_MODELS,
    }


@app.post("/api/models/select")
def select_model(req: ModelSelectRequest):
    """切换当前审核大模型底座 (如 Gemini 3.8 Flash, Qwen2.5-32B)"""
    global current_model_id, current_provider
    matched = next((m for m in SUPPORTED_MODELS if m["id"] == req.model_id), None)
    if not matched:
        raise HTTPException(status_code=400, detail="不支持的模型标识")

    current_model_id = matched["id"]
    current_provider = matched["provider"]
    model_client.set_provider(current_provider, current_model_id)
    return {
        "status": "success",
        "active_model_id": current_model_id,
        "active_provider": current_provider,
        "message": f"已成功切换为 {matched['name']}",
    }


@app.post("/api/audit/switch-sample")
def switch_sample(req: SampleSwitchRequest):
    """切换当前审阅的示例文档"""
    global active_audit_result, active_parsed_doc
    active_parsed_doc = DocumentParser.parse_mock_document(req.sample_name)
    active_audit_result = engine.audit_document(active_parsed_doc)
    return get_current_audit()
# -------------------------------------------------------------
# Markdown 规则知识库与专家标注自学习 API
# -------------------------------------------------------------
from .core.rule_kb_engine import RuleKbEngine

@app.get("/api/kb/rules")
def get_kb_rules():
    """获取知识库中加载的所有 Markdown 规则条目"""
    rules = RuleKbEngine.load_all_rules()
    return {"rules": [r.to_dict() for r in rules]}


@app.get("/api/kb/files")
def get_kb_files():
    """获取所有规则 Markdown 源文件列表及内容"""
    files = RuleKbEngine.get_kb_files()
    return {"files": files}


@app.post("/api/kb/files/save")
def save_kb_file(req: SaveKbFileRequest):
    """保存或更新指定的 Markdown 规则文件"""
    success = RuleKbEngine.save_kb_file(req.filename, req.content)
    if not success:
        raise HTTPException(status_code=500, detail="保存规则文件失败")
    return {"status": "success", "message": f"规则文件 {req.filename} 已成功更新"}


@app.post("/api/decisions/synthesize-rule")
def synthesize_rule_from_decision(req: SynthesizeRuleRequest):
    """
    通过专家的样本裁决标注，调用大模型自动提炼生成一条新的 Markdown 规则
    并持久化追加到 rules_kb/99_user_learned.md，即刻生效！
    """
    prompt_for_ai = (
        f"业务专家在复核金融报告时裁决了一条真实缺陷：\n"
        f"• 问题标题：{req.issue_title}\n"
        f"• 样本原文引用：“{req.issue_quote}”\n"
        f"• 专家判定理由：{req.expert_reason}\n\n"
        f"请作为资深合规规则架构师，将这一专家裁决抽象为一条通用的 Markdown 格式审核准则（包含：审核关注点、违规识别特征、修正要求）。\n"
        f"要求：精炼通顺、专业严谨，控制在 100 字内。"
    )
    
    generated_text = ""
    try:
        ans = model_client.ask_document_copilot(
            question=prompt_for_ai,
            doc_context=f"问题：{req.issue_title}，引文：{req.issue_quote}",
        )
        if ans and ans.get("reply"):
            generated_text = ans["reply"]
    except Exception:
        generated_text = f"严格审核该项是否与法定披露基准保持完全一致，杜绝出现“{req.issue_quote[:30]}”类似错漏。"

    res = RuleKbEngine.append_user_learned_rule(
        rule_title=req.issue_title,
        issue_quote=req.issue_quote,
        expert_reason=req.expert_reason,
        severity=req.severity or "HIGH",
        generated_rule_text=generated_text,
    )
    res["generated_rule_text"] = generated_text
    return res


@app.get("/api/audit/current")
def get_current_audit():
    """获取当前正在审阅的文档及其问题清单和版面坐标"""
    global active_audit_result, active_parsed_doc
    if not active_audit_result:
        active_parsed_doc = DocumentParser.parse_mock_document("swlx")
        active_audit_result = engine.audit_document(active_parsed_doc)

    return {
        "audit": active_audit_result,
        "doc_pages": [
            {
                "page": p,
                "spans": [s.to_dict() for s in active_parsed_doc.spans if s.page == p],
            }
            for p in range(1, active_parsed_doc.total_pages + 1)
        ],
    }
# -------------------------------------------------------------
# 场景 2 & 场景 3: 跨文档交叉核对业务 API
# -------------------------------------------------------------
from .core.cross_checker import CrossDocumentAuditor

@app.get("/api/cross-check/prospectus")
def get_prospectus_cross_check():
    """场景 2: 用定期报告校验更新的《招募说明书》核对结果"""
    return CrossDocumentAuditor.audit_prospectus()


@app.get("/api/cross-check/factsheet")
def get_factsheet_cross_check():
    """场景 3: 用定期报告校验《基金产品资料概要》核对结果"""
    return CrossDocumentAuditor.audit_factsheet()
@app.post("/api/audit/diagnose")
def diagnose_single_issue(req: DiagnoseRequest):
    """卡片就地极速 AI 诊断"""
    global active_audit_result
    doc_facts = active_audit_result.get("doc_facts", {})
    analysis = model_client.diagnose_issue(req.title, req.description, req.quote, doc_facts)
    return {"analysis": analysis}
@app.post("/api/audit/upload")
async def upload_and_audit(file: UploadFile = File(...)):
    """上传真实 PDF 研报并执行 Harness 全自动审核流水线"""
    global active_audit_result, active_parsed_doc
    
    file_id = uuid.uuid4().hex[:8]
    save_path = SAMPLES_DIR / f"{file_id}_{file.filename}"
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        active_parsed_doc = DocumentParser.parse_pdf(str(save_path))
        active_audit_result = engine.audit_document(active_parsed_doc)
        return {
            "status": "success",
            "message": f"成功审核文档: {file.filename}",
            "summary": active_audit_result["summary"],
        }
    except Exception as e:
        # 回退为 mock 并报提示
        active_parsed_doc = DocumentParser.parse_mock_document()
        active_audit_result = engine.audit_document(active_parsed_doc)
        return {
            "status": "warning",
            "message": f"真实 PDF 解析异常 ({str(e)})，已回退为标准信披样本",
            "summary": active_audit_result["summary"],
        }


@app.post("/api/decisions")
def record_expert_decision(req: DecisionRequest):
    """专家一键裁决留痕 (确认缺陷 / 误报)"""
    global active_audit_result
    entry = DecisionFlywheel.record_decision(
        issue_id=req.issue_id,
        rule_id=req.rule_id,
        decision=req.decision,
        expert_name=req.expert_name,
        reason=req.reason or "",
        document_name=req.document_name or "",
        quote=req.quote or "",
    )

    # 动态更新当前内存清单的状态
    if "issues" in active_audit_result:
        for item in active_audit_result["issues"]:
            if item["id"] == req.issue_id:
                item["status"] = req.decision

    return {"status": "success", "recorded": entry}


@app.post("/api/copilot/ask")
def ask_copilot(req: CopilotAskRequest):
    """向审核专家提问"""
    global active_audit_result, active_parsed_doc
    doc_context = "\n".join([s.text for s in active_parsed_doc.spans])[:1500]
    issue_context = ""
    if req.issue_id and "issues" in active_audit_result:
        for i in active_audit_result["issues"]:
            if i["id"] == req.issue_id:
                issue_context = f"问题: {i['title']}, 说明: {i['description']}, 证据: {i['quote']}"
                break

    answer = model_client.ask_document_copilot(req.question, doc_context, issue_context)
    return answer


@app.get("/api/metrics")
def get_metrics():
    """获取价值回执大屏数据"""
    return DecisionFlywheel.get_audit_metrics()


# 挂载前端静态文件
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
