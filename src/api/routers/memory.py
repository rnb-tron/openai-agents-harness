"""
Memory API Router
记忆管理API接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.response import create_success_response, create_error_response
from src.core.logging import service_logger
from src.harness.builder import Harness
from src.harness.deps import get_harness

router = APIRouter(prefix="/memory", tags=["memory"])


class MemorySearchRequest(BaseModel):
    """记忆搜索请求"""
    query: str = Field(..., description="搜索关键词")
    user_id: str = Field(..., description="用户ID")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")


class MemoryClearRequest(BaseModel):
    """清空记忆请求"""
    session_id: str = Field(..., description="会话ID")


@router.post("/search")
async def search_memories(
    request: MemorySearchRequest,
    harness: Harness = Depends(get_harness),
):
    """
    搜索长期记忆
    
    使用向量检索查找相关的历史记忆
    """
    try:
        memory_manager = harness.memory_manager
        results = []
        if memory_manager is not None:
            results = await memory_manager.search_memories(
                user_id=request.user_id,
                query=request.query,
                top_k=request.top_k,
            )
        
        return create_success_response(
            data={
                "query": request.query,
                "user_id": request.user_id,
                "results": results,
                "count": len(results),
            }
        )
        
    except Exception as e:
        service_logger.error(f"Memory search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memory search failed: {e}")


@router.post("/clear")
async def clear_session_memory(
    request: MemoryClearRequest,
    harness: Harness = Depends(get_harness),
):
    """
    清空会话记忆
    
    清除指定会话的短期和长期记忆
    """
    try:
        if harness.memory_manager is not None:
            success = await harness.memory_manager.clear_session(request.session_id)
        else:
            harness.memory_store.clear(request.session_id)
            success = True
        
        if not success:
            return create_error_response(message="Failed to clear session memory")
        
        return create_success_response(
            data={
                "session_id": request.session_id,
                "cleared": True,
            }
        )
        
    except Exception as e:
        service_logger.error(f"Clear session memory failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Clear memory failed: {e}")


@router.get("/stats")
async def get_memory_stats(
    user_id: str = Query(None, description="用户ID (可选)"),
    session_id: str = Query(None, description="会话ID (可选，用于查看短期会话记忆)"),
    harness: Harness = Depends(get_harness),
):
    """
    获取记忆统计信息
    
    返回短期和长期记忆的统计数据
    """
    try:
        if harness.memory_manager is not None:
            stats = await harness.memory_manager.get_stats(user_id, session_id=session_id)
        else:
            stats = {
                "short_term": harness.memory_store.stats(),
                "long_term": {
                    "enabled": False,
                    "total_count": 0,
                    "by_type": {},
                },
            }
        
        return create_success_response(data=stats)
        
    except Exception as e:
        service_logger.error(f"Get memory stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Get stats failed: {e}")


@router.post("/cleanup")
async def cleanup_old_memories(harness: Harness = Depends(get_harness)):
    """
    清理旧记忆
    
    执行记忆维护任务:遗忘策略、去重、归档
    """
    try:
        if harness.memory_manager is not None:
            result = await harness.memory_manager.cleanup_old_memories()
        else:
            result = {
                "skipped": True,
                "reason": "long_term_memory_disabled",
            }
        
        return create_success_response(data=result)
        
    except Exception as e:
        service_logger.error(f"Cleanup old memories failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")
