# 파일명: backend/app/main.py
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from app.config import verify_env_integrity, WINDOW_SIZE
from app.database import (
    insert_wiki_node,
    fetch_all_wiki_nodes,
    delete_wiki_node,
    fetch_associated_graph_links,
    fetch_gemini_wiki_nodes,
    fetch_all_wiki_nodes_listing,
    insert_chat_message,
    upsert_project_source_code,
    fetch_project_source_code,
    fetch_all_blueprints_basic
)
from app.gemini import (
    generate_embedding, 
    execute_graph_rag_inference, 
    process_and_save_knowledge_node,
    normalize_and_save_chat_node
)
from app.syncproject import router as project_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("cosmos_wiki")

# Verify environment integrity
verify_env_integrity()

app = FastAPI(title="CosmosWiki Enterprise Modular API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WikiSaveRequest(BaseModel):
    title: str
    content: str

class WikiUpdateRequest(BaseModel):
    id: str
    title: str
    content: str

class NodeManualUpdateRequest(BaseModel):
    title: str
    content: str

class SourceCodeSaveRequest(BaseModel):
    file_id: str
    raw_code: str

class ActiveFile(BaseModel):
    id: str
    path: str

class ChatRequest(BaseModel):
    message: str
    session_id: str = "session_default"
    mode: str = "general"  # "general" or "project"
    active_file: ActiveFile | None = None

class ChatSaveRequest(BaseModel):
    text: str

app.include_router(project_router)

# ----------------------------------------------------------------
# Knowledge management APIs
# ----------------------------------------------------------------

@app.post("/wiki/save")
async def save_wiki_note(request: WikiSaveRequest):
    if not request.title or not request.content:
        raise HTTPException(status_code=400, detail="필수 데이터가 누락되었습니다.")
    try:
        result = process_and_save_knowledge_node(
            title=request.title, 
            content=request.content, 
            created_by="user"
        )
        return {
            "status": "success",
            "message": f"{result['mode_msg']} (링크 {result['links_created']}개 동기화 완료)",
            "data": result['data']
        }
    except Exception as e:
        logger.error(f"Knowledge ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"지식 저장 실패: {str(e)}")

@app.post("/wiki/save-chat-node")
async def save_chat_node_endpoint(request: ChatSaveRequest, background_tasks: BackgroundTasks):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="대화 내용이 누락되었습니다.")
    
    # Process in background
    background_tasks.add_task(normalize_and_save_chat_node, request.text)
    
    return {
        "status": "processing", 
        "message": "백그라운드에서 지식 처리를 시작합니다."
    }

@app.post("/wiki/update")
async def update_wiki_note(request: WikiUpdateRequest):
    if not request.id or not request.title or not request.content:
        raise HTTPException(status_code=400, detail="필수 데이터가 누락되었습니다.")
    try:
        # Avoid circular imports
        from app.database import update_wiki_node, sync_node_graph_relations
        
        new_vector = generate_embedding(request.content)
        db_response = update_wiki_node(request.id, request.title, request.content, new_vector)
        
        # Sync relations
        links_rebuilt = sync_node_graph_relations(request.id, new_vector)
                        
        return {
            "status": "success",
            "message": f"지식 수정 및 링크 {links_rebuilt}개 재동기화 완료",
            "data": db_response.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")

@app.put("/wiki/update/{node_id}")
async def update_knowledge_node_manual(node_id: str, request: NodeManualUpdateRequest):
    if not node_id or not request.title or not request.content:
        raise HTTPException(status_code=400, detail="필수 데이터가 누락되었습니다.")
        
    logger.info(f"Manual node update started: {node_id}")
    try:
        # Avoid circular imports
        from app.database import update_wiki_node, sync_node_graph_relations
        
        new_vector = generate_embedding(request.content)
        db_response = update_wiki_node(node_id, request.title, request.content, new_vector)
        
        # Sync relations
        links_rebuilt = sync_node_graph_relations(node_id, new_vector)
                        
        logger.info(f"Node updated and {links_rebuilt} links synced: {node_id}")
        return {
            "status": "success",
            "message": f"지식 수정 및 링크 {links_rebuilt}개 재동기화 완료",
            "data": db_response.data[0]
        }
    except Exception as e:
        logger.error(f"Manual node update failed for {node_id}: {e}")
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")


# ----------------------------------------------------------------
# Chat inference APIs
# ----------------------------------------------------------------

@app.post("/chat/query")
async def chat_with_cosmos_wiki(request: ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")
        
    try:
        all_nodes = fetch_all_wiki_nodes()
        
        ai_response = execute_graph_rag_inference(
            query=request.message, 
            all_nodes=all_nodes,
            session_id=request.session_id,
            mode=request.mode,
            window_size=WINDOW_SIZE,
            active_file=request.active_file.dict() if request.active_file else None
        )
        
        # Save chat history
        insert_chat_message(
            session_id=request.session_id, 
            role="user", 
            message=request.message, 
            active_mode=request.mode
        )
        insert_chat_message(
            session_id=request.session_id, 
            role="model", 
            message=ai_response["text"], 
            active_mode=request.mode
        )
        
        return {
            "status": "success", 
            "ai_response": ai_response["text"],
            "references": ai_response["references"]
        }
        
    except Exception as e:
        logger.error(f"Chat inference failed: {e}")
        raise HTTPException(status_code=500, detail=f"요청 처리 중 오류가 발생했습니다: {str(e)}")

# ----------------------------------------------------------------
# Knowledge retrieval APIs
# ----------------------------------------------------------------
@app.get("/wiki/nodes")
async def get_all_wiki_nodes():
    try:
        response = fetch_all_wiki_nodes_listing()
        return {"nodes": response.data}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"데이터 조회 실패: {str(e)}"
        )
    
@app.get("/wiki/links/{node_id}")
async def get_associated_graph_links(node_id: str):
    try:
        refined_links = fetch_associated_graph_links(node_id)
        return {"links": refined_links}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"링크 조회 실패: {str(e)}"
        )

@app.delete("/wiki/delete/{node_id}")
async def delete_node_endpoint(node_id: str):
    try:
        logger.info(f"Node deletion started: {node_id}")
        delete_wiki_node(node_id)
        return {"status": "success", "message": f"노드가 삭제되었습니다: {node_id}"}
    except Exception as e:
        logger.error(f"Node deletion failed for {node_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"데이터 삭제 실패: {str(e)}"
        )
        
@app.get("/wiki/nodes/gemini")
async def get_gemini_autonomous_nodes():
    try:
        response = fetch_gemini_wiki_nodes()
        return {"nodes": response.data}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"데이터 로드 실패: {str(e)}"
        )

# ----------------------------------------------------------------
# Source code management APIs
# ----------------------------------------------------------------

@app.get("/project/source-code/{file_id}")
async def get_project_source_code(file_id: str):
    """Fetch source code by file ID."""
    try:
        code_data = fetch_project_source_code(file_id)
        if not code_data:
            raise HTTPException(status_code=404, detail="해당 파일의 소스코드를 찾을 수 없습니다.")
        return {"status": "success", "source_code": code_data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"소스코드 조회 실패: {str(e)}")

@app.post("/project/source-code")
async def save_project_source_code(request: SourceCodeSaveRequest):
    """Save or update source code."""
    if not request.file_id or not request.raw_code:
        raise HTTPException(status_code=400, detail="필수 파라미터가 누락되었습니다.")
    try:
        upsert_project_source_code(request.file_id, request.raw_code)
        return {"status": "success", "message": "소스코드 동기화 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"소스코드 저장 실패: {str(e)}")

# ----------------------------------------------------------------
# Blueprint retrieval APIs
# ----------------------------------------------------------------

@app.get("/project/blueprints")
async def get_project_blueprints_router():
    """Fetch basic blueprints."""
    try:
        blueprint_pool = fetch_all_blueprints_basic()
        return {"blueprints": blueprint_pool}
    except Exception as e:
        logger.error(f"Failed to fetch blueprints: {e}")
        raise HTTPException(status_code=500, detail=f"청사진 조회 실패: {str(e)}")