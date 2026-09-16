# 파일명: backend/app/gemini.py
import json
import ast
import io
import tokenize
import logging
from google import genai
from google.genai import types
from pydantic import BaseModel
from app.config import (
    GEMINI_API_KEY,
    SIMILARITY_THRESHOLD,
    TOP_K_RELATIONS,
    PROJECT_BUDGET_LIMIT,
    COSMOS_BUDGET_LIMIT,
    L1_MAX_LIMIT
)
from app.database import (
    insert_wiki_node,
    update_wiki_node,
    fetch_all_wiki_nodes,
    delete_knowledge_links_by_node,
    fetch_chat_history,
    fetch_project_global_summary,
    update_blueprint_metadata_text,
    upsert_project_source_code,
    fetch_project_source_code,
    insert_blueprint_function
)

# Initialize logger
logger = logging.getLogger("cosmos_wiki")

# Initialize Gemini client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

class ChatNormalizationSchema(BaseModel):
    title: str
    content: str

def generate_embedding(text: str) -> list:
    """Generate text embedding."""
    response = ai_client.models.embed_content(
        model="gemini-embedding-2",
        contents=text
    )
    return response.embeddings[0].values

def compute_cosine_similarity(vec_a: list, vec_b: list) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = sum(a ** 2 for a in vec_a) ** 0.5
    mag_b = sum(b ** 2 for b in vec_b) ** 0.5
    return dot_product / (mag_a * mag_b) if (mag_a * mag_b) > 0 else 0

def minimize_python_source_code(source_code: str) -> str:
    """Minimize Python source code by removing comments and blank lines."""
    if not source_code or not source_code.strip():
        return ""
    
    try:
        source_io = io.StringIO(source_code)
        tokens = tokenize.generate_tokens(source_io.readline)
        minimized_io = io.StringIO()
        
        last_lineno = -1
        last_col = 0
        
        for tok in tokens:
            tok_type = tok.type
            tok_string = tok.string
            start_line, start_col = tok.start
            end_line, end_col = tok.end
            
            if tok_type == tokenize.COMMENT:
                continue
                
            if tok_type in (tokenize.NL, tokenize.NEWLINE):
                if last_lineno != start_line:
                    minimized_io.write("\n")
                    last_lineno = start_line
                    last_col = 0
                continue
            
            if start_line > last_lineno:
                last_col = 0
            if start_col > last_col:
                minimized_io.write(" " * (start_col - last_col))
                
            minimized_io.write(tok_string)
            last_lineno = end_line
            last_col = end_col
            
        lines = [line for line in minimized_io.getvalue().splitlines() if line.strip()]
        return "\n".join(lines)
        
    except Exception as e:
        logger.warning(f"Minification failed, using raw text: {e}")
        lines = [line for line in source_code.splitlines() if line.strip() and not line.strip().startswith("#")]
        return "\n".join(lines)

# ----------------------------------------------------------------
# Knowledge ingestion pipeline
# ----------------------------------------------------------------
def process_and_save_knowledge_node(title: str, content: str, created_by: str = "user") -> dict:
    """Create or overwrite knowledge node based on similarity."""
    current_vector = generate_embedding(content)
    all_nodes = fetch_all_wiki_nodes()
    
    best_match_id = None
    max_similarity = -1.0
    
    if all_nodes:
        for node in all_nodes:
            target_vector = node.get("embedding")
            if isinstance(target_vector, str):
                try: target_vector = json.loads(target_vector)
                except Exception: continue
            
            if target_vector and len(target_vector) == 3072:
                sim = compute_cosine_similarity(current_vector, target_vector)
                if sim > max_similarity:
                    max_similarity = sim
                    best_match_id = node.get("id")

    if max_similarity >= 0.90 and best_match_id:
        matched_node_title = next((n.get("title") for n in all_nodes if n.get("id") == best_match_id), "Unknown")
        logger.info(f"Overwriting node '{matched_node_title}' (similarity: {max_similarity:.4f})")
        delete_knowledge_links_by_node(best_match_id)
        db_response = update_wiki_node(best_match_id, title, content, current_vector)
        inserted_id = best_match_id
        mode_msg = "기존 문서 덮어쓰기 완료"
    else:
        db_response = insert_wiki_node(title, content, current_vector, created_by=created_by)
        inserted_id = db_response.data[0].get("id")
        mode_msg = "새 지식 추가 완료"
                    
    # Avoid circular imports
    from app.database import sync_node_graph_relations
    links_created = sync_node_graph_relations(inserted_id, current_vector)

    return {
        "mode_msg": mode_msg,
        "links_created": links_created,
        "data": db_response.data[0] if db_response.data else {"id": inserted_id}
    }

# ----------------------------------------------------------------
# Tool definitions
# ----------------------------------------------------------------
def auto_save_knowledge_node(title: str, content: str) -> dict:
    """Automatically save high-value knowledge."""
    try:
        logger.info(f"Saving knowledge node: {title}")
        result = process_and_save_knowledge_node(title=title, content=content, created_by="gemini_agent")
        return {
            "status": "success", 
            "resolved_action": "integrated_save", 
            "node_title": title,
            "message": f"{result['mode_msg']} (링크 {result['links_created']}개 동기화)"
        }
    except Exception as e:
        logger.error(f"Failed to save knowledge node: {e}")
        return {"status": "error", "message": str(e)}

def auto_update_knowledge_node(node_id: str, title: str, content: str) -> dict:
    """Automatically update existing knowledge node."""
    try:
        logger.info(f"Updating knowledge node: {node_id}")
        embedding_vector = generate_embedding(content)
        db_response = update_wiki_node(node_id, title, content, embedding_vector)
        
        # Avoid circular imports
        from app.database import sync_node_graph_relations
        links_rebuilt = sync_node_graph_relations(node_id, embedding_vector)

        return {
            "status": "success", 
            "resolved_action": "integrated_update", 
            "node_id": node_id,
            "message": f"지식 수정 및 링크 {links_rebuilt}개 재동기화 완료"
        }
    except Exception as e:
        logger.error(f"Failed to update knowledge node: {e}")
        return {"status": "error", "message": str(e)}

def update_project_blueprint(node_id: str, type: str, new_summary: str) -> dict:
    """Automatically update project blueprint summary."""
    try:
        logger.info(f"Updating blueprint summary for {type} ({node_id})")
        update_blueprint_metadata_text(node_id, type, new_summary)
        return {
            "status": "success", 
            "resolved_action": "blueprint_meta_update",
            "node_id": node_id,
            "message": f"Successfully updated project blueprint structural meta summary for {type} ({node_id})"
        }
    except Exception as e:
        logger.error(f"Failed to update blueprint summary: {e}")
        return {"status": "error", "message": str(e)}

def read_database_source_code(file_id: str) -> dict:
    """Fetch source code from database."""
    try:
        logger.info(f"Reading source code for file_id: {file_id}")
        code_data = fetch_project_source_code(file_id)
        if code_data:
            return {"status": "success", "raw_code": code_data["raw_code"]}
        return {"status": "error", "message": "해당 파일의 소스코드가 존재하지 않습니다."}
    except Exception as e:
        logger.error(f"Failed to read source code: {e}")
        return {"status": "error", "message": str(e)}

def write_database_source_code(file_id: str, new_code: str) -> dict:
    """Save source code and reindex functions and dependencies."""
    try:
        logger.info(f"Writing source code and reindexing for file_id: {file_id}")
        upsert_project_source_code(file_id, new_code)
        
        # Avoid circular imports
        from app.database import (
            fetch_blueprint_by_id, 
            delete_blueprint_functions_by_file,
            delete_blueprint_relationships_by_source,
            fetch_all_blueprints_basic,
            insert_blueprint_relationship
        )
        
        blueprint_data = fetch_blueprint_by_id(file_id)
        functions_reindexed = 0
        relations_reindexed = 0
        
        if blueprint_data:
            file_path = blueprint_data.get("path", "unknown_path")
            logger.debug(f"Starting AST analysis for path: {file_path}")
            
            delete_blueprint_functions_by_file(file_id)
            delete_blueprint_relationships_by_source(file_id)
            
            all_blueprints = fetch_all_blueprints_basic()
            parsed_node = ast.parse(new_code)
            
            for child in parsed_node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_name = child.name
                    args = [arg.arg for arg in child.args.args]
                    is_async = "async " if isinstance(child, ast.AsyncFunctionDef) else ""
                    signature = f"{is_async}def {func_name}({', '.join(args)})"
                    
                    docstring = ast.get_docstring(child)
                    summary = docstring.split("\n")[0] if docstring else "에이전트 자율 분석 및 정적 인덱싱된 인터페이스"
                    
                    insert_blueprint_function(
                        file_id=file_id,
                        function_name=func_name,
                        signature=signature,
                        summary=summary
                    )
                    functions_reindexed += 1
                    logger.debug(f"Indexed function: {func_name}")
                
                elif isinstance(child, (ast.Import, ast.ImportFrom)):
                    detected_modules = []
                    
                    if isinstance(child, ast.Import):
                        for name in child.names:
                            detected_modules.append(name.name)
                    elif isinstance(child, ast.ImportFrom) and child.module:
                        detected_modules.append(child.module)
                    
                    for mod in detected_modules:
                        expected_suffix = mod.replace(".", "/") + ".py"
                        target_node = next((bp for bp in all_blueprints if bp["path"].endswith(expected_suffix)), None)
                        
                        if target_node and str(target_node["id"]) != str(file_id):
                            insert_blueprint_relationship(
                                relation_type="imports",
                                source_id=file_id,
                                source_type="file",
                                target_id=target_node["id"],
                                target_type="file"
                            )
                            relations_reindexed += 1
                            logger.debug(f"Mapped dependency: {file_path} -> {target_node['path']}")
                                    
        return {
            "status": "success", 
            "resolved_action": "source_code_and_topology_sync",
            "file_id": file_id,
            "message": f"Source code stored successfully. Reindexed {functions_reindexed} functions and {relations_reindexed} dependency relations."
        }
    except Exception as e:
        logger.error(f"Failed to write source code and sync topology: {e}")
        return {"status": "error", "message": str(e)}

# ----------------------------------------------------------------
# Graph retrieval pipeline
# ----------------------------------------------------------------
def execute_graph_rag_inference(query: str, all_nodes: list, session_id: str = "session_default", mode: str = "general", window_size: int = 20, active_file: dict = None) -> dict:
    context_chunk = ""
    graph_nodes = []
    
    if all_nodes:
        query_vector = generate_embedding(query)
        scored_nodes = []
        
        for node in all_nodes:
            node_vector = node.get("embedding")
            if isinstance(node_vector, str):
                try: node_vector = json.loads(node_vector)
                except Exception: continue
                    
            if not node_vector or len(node_vector) != 3072: continue
                
            sim = compute_cosine_similarity(query_vector, node_vector)
            scored_nodes.append({**node, "similarity": sim})
            
        scored_nodes.sort(key=lambda x: x["similarity"], reverse=True)
        primary_candidates = [n for n in scored_nodes if n["similarity"] > 0.45][:3]
        
        if primary_candidates:
            unique_nodes_map = {}
            
            for p_node in primary_candidates:
                if p_node["id"] not in unique_nodes_map:
                    unique_nodes_map[p_node["id"]] = p_node
                
                p_vector = p_node["embedding"]
                if isinstance(p_vector, str):
                    try: p_vector = json.loads(p_vector)
                    except Exception: pass
                
                current_node_links = []
                for other in scored_nodes:
                    if other["id"] == p_node["id"]: continue
                    
                    o_vector = other["embedding"]
                    if isinstance(o_vector, str):
                        try: o_vector = json.loads(o_vector)
                        except Exception: continue
                        
                    if o_vector and len(o_vector) == 3072:
                        sub_sim = compute_cosine_similarity(p_vector, o_vector)
                        if sub_sim >= SIMILARITY_THRESHOLD:
                            current_node_links.append({**other, "graph_sim": sub_sim})
                
                current_node_links.sort(key=lambda x: x["graph_sim"], reverse=True)
                for rel_node in current_node_links[:2]:
                    if rel_node["id"] not in unique_nodes_map:
                        unique_nodes_map[rel_node["id"]] = rel_node
            
            all_unique_list = list(unique_nodes_map.values())
            all_unique_list.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            graph_nodes = all_unique_list[:6]
                        
            context_chunk = "\n[시스템이 탐색해낸 CosmosWiki 그래프 네트워크 연관 지식 노드]\n"
            
            for idx, gn in enumerate(graph_nodes, 1):
                if len(context_chunk) >= COSMOS_BUDGET_LIMIT:
                    logger.warning(f"Context truncated at {COSMOS_BUDGET_LIMIT} characters")
                    break
                context_chunk += f"■ 연관 지식 노드 {idx} (ID: {gn['id']}, 제목: {gn['title']})\n- 내용: {gn['content']}\n\n"

    if mode == "project":
        global_summary = fetch_project_global_summary()
        blueprint_stream = "### [Stateful Coding Agent Project Context]\n\n"
        
        if active_file and active_file.get("id"):
            active_id = active_file["id"]
            raw_code_data = fetch_project_source_code(active_id)
            if raw_code_data:
                raw_code = raw_code_data.get('raw_code', '')
                
                before_len = len(raw_code)
                raw_code = minimize_python_source_code(raw_code)
                after_len = len(raw_code)
                logger.debug(f"Minified source code from {before_len} to {after_len} chars")
                
                if len(raw_code) > L1_MAX_LIMIT:
                    logger.warning(f"Source code exceeds limit, truncating to {L1_MAX_LIMIT} chars")
                    raw_code = raw_code[:L1_MAX_LIMIT] + "\n# [... File truncated due to Layer 1 budget limits (11,500 char) ...]"
                
                blueprint_stream += f"#### [LAYER 1: RAW SOURCE] 현재 파일 (`{active_file['path']}`)\n```python\n{raw_code}\n```\n\n"
            
            # Avoid circular imports
            from app.database import fetch_direct_dependencies_metadata
            dep_meta = fetch_direct_dependencies_metadata(active_id)
            
            if dep_meta and dep_meta.get("blueprints"):
                valid_blueprints = dep_meta["blueprints"]
                valid_blueprints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                
                layer2_chunk = "#### [LAYER 2: DIRECT DEPENDENCY BLUEPRINTS (DEPTH=1)]\n"
                for bp in valid_blueprints[:8]:
                    if len(blueprint_stream) + len(layer2_chunk) >= PROJECT_BUDGET_LIMIT:
                        logger.warning(f"Layer 2 truncated at {PROJECT_BUDGET_LIMIT} chars")
                        break
                        
                    layer2_chunk += f"##### 컴포넌트: `{bp['path']}` ({bp['type']})\n- 역할: {bp['summary']}\n"
                    file_funcs = [f for f in dep_meta["functions"] if str(f["file_id"]) == str(bp["id"])]
                    if file_funcs:
                        layer2_chunk += "  - 인터페이스 명세:\n"
                        for ff in file_funcs[:3]:
                            layer2_chunk += f"    * `{ff['function_name']}`: `{ff['signature']}` → {ff['summary']}\n"
                
                blueprint_stream += layer2_chunk
                    
        if graph_nodes:
            layer3_chunk = "\n#### [LAYER 3: RELATED BLUEPRINT SUMMARIES]\n"
            for idx, gn in enumerate(graph_nodes[:3], 1):
                if len(blueprint_stream) + len(layer3_chunk) >= PROJECT_BUDGET_LIMIT:
                    logger.warning(f"Layer 3 truncated at {PROJECT_BUDGET_LIMIT} chars")
                    break
                layer3_chunk += f"##### 연관 노드 {idx}: '{gn['title']}'\n- 정제 서머리: {gn['content']}\n"
            
            blueprint_stream += layer3_chunk

        if global_summary:
            layer4_chunk = f"\n#### [LAYER 4: GLOBAL PROJECT OVERVIEW]\n- 아키텍처 개요: {global_summary.get('architecture_summary', '')}\n"
            if len(blueprint_stream) + len(layer4_chunk) < PROJECT_BUDGET_LIMIT:
                blueprint_stream += layer4_chunk
            else:
                logger.warning(f"Layer 4 skipped due to budget limit")

        context_chunk = blueprint_stream

        # [PROMPT INTEGRITY: DO NOT MODIFY]
        system_instruction = (
            "# SYSTEM IDENTITY\n"
            "You are a principal software engineering agent configured in Project Context Mode.\n"
            "You are provided structured visibility over the Code Blueprint Map, Component Interfaces, and the Code Repository.\n\n"
            
            "# RULES & FACTUAL BOUNDARIES (MEMORY-FIRST + ARCHITECTURE-ALIGNED FALLBACK)\n"
            "1. Primary Search Logic: Prioritize and thoroughly exhaust all verified technical facts and source code provided in the active context layer first.\n"
            "2. Constrained Fallback Principle: If details are absent, DO NOT refuse to answer or give a dry non-answer. Transition to high-level reasoning that remains strongly aligned with the existing project architecture, active technology stack (FastAPI, Next.js, SQLite), naming conventions, and dependency structures. Do not pivot to irrelevant frameworks.\n"
            "3. Conditional 3-Tier Delineation: Only when uncertainty, extrapolation, or fallback reasoning is involved, you must distinctly categorize and label insights into these layers to maintain strict observability: [Verified Project Context] (direct facts from source/nodes), [Architecture-Aligned Inference] (probable logic matching project patterns), or [General Industry Suggestion] (high-level standard technical fallback).\n"
            "4. Formatting Constraint: Do not include stylistic block citations, custom quote decorations, or unrequested database source notices.\n\n"

            "# RETRIEVAL & CONTEXT BUDGET POLICY\n"
            "1. Retrieval Priority: When system context layers conflict or overlap, resolve information using this strict hierarchy: Raw Source Code > Blueprint Map > Episodic Memory.\n"
            "2. Context Budget Guard: Avoid invoking tools to load large raw source files unless the execution details are absolutely implementation-critical to the active turn.\n"
            "3. Attention-Aware Anchor Strategy: If an 'active_file' object (containing ID and canonical path) is provided in the payload, interpret it as the user's active cursor focus and primary diagnostic anchor. Prioritize analyzing its context first.\n"
            "4. Anti-Overfitting & Graph Exploration Rule: Never isolate your reasoning or fall into tunnel vision within the active_file. Bugs frequently stem from shared utils, configuration mismatches, or faulty caller/callee contracts in sibling modules. Actively cross-examine Layer 2-B dependency edges and blueprint metrics (strictly limiting exploration depth <= 1) to build a minimally sufficient project-wide understanding before formulating any solution.\n\n"
            
            "# INTEGRITY & SAFE PERSISTENCE POLICY\n"
            "1. Blueprint Consistency Validation: Actively monitor for deleted files or renamed paths against the active Blueprint Map, and strictly reject any invalid or fabricated UUID tokens.\n"
            "2. Safe Persistence Rule: Never archive or persist temporary brainstorming ideas, speculative architecture drafts, or unresolved debugging assumptions into any permanent database record.\n"
            "3. Patch-based Write Policy: Adhere to a minimal patch generation philosophy. Propose and write precise, incremental code modifications over full-file overwrites whenever executing structural source updates.\n\n"
            
            "# DETERMINISTIC TOOL POLICY (CONFIDENCE GATING & ANTI-OVEREXPANSION)\n"
            "Analyze the message stream. Execute tools only when architectural changes are explicit, finalized, and implementation-relevant. Do not over-fire tools on speculative or casual statements.\n"
            "ANTI-OVEREXPANSION RULE: Do not aggressively invoke tools or expand retrieval depth when the active fallback reasoning layer is already contextually sufficient to answer the user constructively. Protect the context budget.\n"
            "- Condition A (Update Blueprint): Invoke update_project_blueprint only when code refactoring, interface changes, or path mutations are fully finalized.\n"
            "  * CONSTRAINT: type parameter must be file or function. node_id must be the exact UUID string from the context. No random generation.\n"
            "- Condition B (Save Knowledge): Invoke auto_save_knowledge_node when a high-value infrastructure asset or core architecture decision is firmly established.\n"
            "- Condition C (Correct Knowledge): Invoke auto_update_knowledge_node only if incoming facts directly supplement or contradict an active episodic record.\n"
            "- Condition D (Read Source): Invoke read_database_source_code using the exact file UUID before answering only if code-level inspection or precise debugging is requested, and the required implementation details are not already sufficiently represented in the active context.\n"
            "- Condition E (Write Source - SAFETY LOCK): Invoke write_database_source_code ONLY after the user explicitly approves the final code implementation or demands synchronization. Never trigger a write autonomously on incomplete drafts."
        )
        
    else:
        # [PROMPT INTEGRITY: DO NOT MODIFY]
        system_instruction = (
            "# SYSTEM IDENTITY\n"
            "You are an intelligent general-purpose assistant with access to episodic memory nodes and persistent knowledge layers.\n"
            "Synthesize insights derived from Episodic Memory nodes, chat history, and your extensive built-in pre-trained world knowledge.\n\n"
            
            "# RULES & FACTUAL BOUNDARIES (GENERAL REASONING FALLBACK)\n"
            "1. Node Prioritization: For topics regarding active sessions, specific users, or archived logs, prioritize extracting answers comprehensively from verified facts present in the nodes.\n"
            "2. Parametric World Knowledge: For non-project and non-technical queries (including public figures, culture, history, and general facts), you must answer directly using your built-in pre-trained parametric memory. Never falsely state you 'lack this information in your database' simply because it is absent from the RAG nodes.\n"
            "3. Broad Reasoning Fallback: If reliable information is unavailable from both retrieved context and your general world knowledge, proactively synthesize a highly logical, helpful, and constructive response based on general reasoning and standard analytical principles. Clearly delineate speculative extensions from active database records.\n"
            "4. Formatting Constraint: Do not insert any formal quotation marks, stylistic citation blocks, or unrequested source data references.\n"
            "5. Integrity Rule: Never archive speculative personal assumptions, temporary drafts, or unverified logs into the persistent memory layers.\n\n"
            
            "# DETERMINISTIC TOOL POLICY\n"
            "Execute tools autonomously based on explicit patterns. Avoid over-triggering.\n"
            "- Condition A (Spontaneous Archiving): Invoke auto_save_knowledge_node when new valuable insights, schedules, or logs worthy of long-term preservation emerge.\n"
            "- Condition B (Spontaneous Correction): Invoke auto_update_knowledge_node only if the current data stream updates or overrides an active memory layout record."

            "Even if specific facts are absent from the RAG nodes, if the query asks for standard historical data, common knowledge, or systemic logic, utilize your built-in parametric knowledge to answer constructively instead of refusing."
        )

    db_history = fetch_chat_history(session_id, window_size)
    contents_payload = []
    
    for turn in db_history:
        contents_payload.append(
            types.Content(
                role=turn["role"],
                parts=[types.Part.from_text(text=turn["message"])]
            )
        )
    
    prompt_content = f"{context_chunk}▶ 사용자의 현재 분석 요청 및 질문:\n{query}"
    contents_payload.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_content)]
        )
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2,
        tools = [auto_save_knowledge_node, 
                 auto_update_knowledge_node, 
                 update_project_blueprint, 
                 read_database_source_code,
                 write_database_source_code]
    )
    
    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents_payload,
        config=config
    )
    
    if response.function_calls:
        for call in response.function_calls:
            logger.info(f"Function triggered: {call.name}")
            args = call.args
            if call.name == "auto_save_knowledge_node":
                auto_save_knowledge_node(title=args["title"], content=args["content"])
            elif call.name == "auto_update_knowledge_node":
                auto_update_knowledge_node(node_id=args["node_id"], title=args["title"], content=args["content"])
            elif call.name == "update_project_blueprint":
                update_project_blueprint(node_id=args["node_id"], type=args["type"], new_summary=args["new_summary"])
            elif call.name == "read_database_source_code": 
                read_database_source_code(file_id=args["file_id"])
            elif call.name == "write_database_source_code":
                write_database_source_code(file_id=args["file_id"], new_code=args["new_code"])

    referenced_nodes = []
    if all_nodes and graph_nodes:
        for gn in graph_nodes[:4]:
            referenced_nodes.append({
                "id": gn["id"],
                "title": gn["title"],
                "similarity": f"{round(gn.get('similarity', 0) * 100, 1)}"
            })

    return {
        "text": response.text,
        "references": referenced_nodes
    }

def normalize_and_save_chat_node(raw_text: str):
    """Normalize chat message and save to knowledge network."""
    try:
        # [PROMPT INTEGRITY: DO NOT MODIFY]
        prompt = f"""
        다음 대화 내용에서 인사말, 사족, 대화형 조사(예: 형님, 미안합니다, 오 ㅎㅎㅎ 등)를 완전히 제거하고, 
        나중에 RAG 시스템이 문맥 검색하기 가장 좋은 형태의 객관적이고 완성된 지식 문서(Markdown 포맷)로 정제해줘.
        또한 정제된 내용에 어울리는 명확하고 직관적인 한 줄 짜리 핵심 제목(Title)도 함께 생성해라.
        
        [대화 내용]
        {raw_text}
        """
        
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=ChatNormalizationSchema
            )
        )
    
        cleaned_text = response.text.strip()
        data = json.loads(cleaned_text)
        
        extracted_title = data.get("title", "정제된 대화 지식")
        extracted_content = data.get("content", "")
        
        if not extracted_content:
            logger.warning("Normalization canceled: empty content")
            return
            
        result = process_and_save_knowledge_node(
            title=extracted_title, 
            content=extracted_content, 
            created_by="chat_hover_button"
        )
        logger.info(f"Normalized and saved chat node: {extracted_title}")
        
    except Exception as e:
        logger.error(f"Normalization failed: {e}")