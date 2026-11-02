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


class CopilotAskRequest(BaseModel):
    question: str
    issue_id: Optional[str] = None


@app.on_event("startup")
def startup_event():
    global active_audit_result, active_parsed_doc
    # 启动时预热一份经典基金中报样本文档
    active_parsed_doc = DocumentParser.parse_mock_document()
    active_audit_result = engine.audit_document(active_parsed_doc)


@app.get("/api/audit/current")
def get_current_audit():
    """获取当前正在审阅的文档及其问题清单和版面坐标"""
    global active_audit_result, active_parsed_doc
    if not active_audit_result:
        active_parsed_doc = DocumentParser.parse_mock_document()
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
