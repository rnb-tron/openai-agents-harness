"""
Memory API Router
记忆管理API接口
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.response import create_success_response, create_error_response
from src.core.logging import service_logger

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
async def search_memories(request: MemorySearchRequest):
    """
    搜索长期记忆
    
    使用向量检索查找相关的历史记忆
    """
    try:
        # TODO: 需要从app.state获取memory_manager
        # memory_manager = request.app.state.memory_manager
        # results = await memory_manager.search_memories(
        #     user_id=request.user_id,
        #     query=request.query,
        #     top_k=request.top_k,
        # )
        
        # 临时返回空结果
        results = []
        
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
async def clear_session_memory(request: MemoryClearRequest):
    """
    清空会话记忆
    
    清除指定会话的短期和长期记忆
    """
    try:
        # TODO: 需要从app.state获取memory_manager
        # memory_manager = request.app.state.memory_manager
        # success = await memory_manager.clear_session(request.session_id)
        
        # 临时返回成功
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
async def get_memory_stats(user_id: str = Query(None, description="用户ID (可选)")):
    """
    获取记忆统计信息
    
    返回短期和长期记忆的统计数据
    """
    try:
        # TODO: 需要从app.state获取memory_manager
        # memory_manager = request.app.state.memory_manager
        # stats = await memory_manager.get_stats(user_id)
        
        # 临时返回空统计
        stats = {
            "short_term": {
                "count": 0,
                "ttl_seconds": -1,
            },
            "long_term": {
                "total_count": 0,
                "by_type": {},
            },
        }
        
        return create_success_response(data=stats)
        
    except Exception as e:
        service_logger.error(f"Get memory stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Get stats failed: {e}")


@router.post("/cleanup")
async def cleanup_old_memories():
    """
    清理旧记忆
    
    执行记忆维护任务:遗忘策略、去重、归档
    """
    try:
        # TODO: 需要从app.state获取memory_manager
        # memory_manager = request.app.state.memory_manager
        # result = await memory_manager.cleanup_old_memories()
        
        # 临时返回成功
        result = {
            "deleted_count": 0,
            "deduplicated_count": 0,
            "archived_count": 0,
            "processed_users": 0,
        }
        
        return create_success_response(data=result)
        
    except Exception as e:
        service_logger.error(f"Cleanup old memories failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")
