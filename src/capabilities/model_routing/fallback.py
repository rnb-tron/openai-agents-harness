"""模型降级策略"""

from typing import Any, Callable, Optional

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from src.capabilities.model_routing.config import FallbackConfig
from src.core.logging import setup_logger

logger = setup_logger("model_routing.fallback")


# 异常名称到异常类的映射
EXCEPTION_MAP = {
    "APIConnectionError": APIConnectionError,
    "APIError": APIError,
    "APITimeoutError": APITimeoutError,
    "InternalServerError": InternalServerError,
    "RateLimitError": RateLimitError,
}


class ModelFallbackError(Exception):
    """模型降级失败异常"""

    def __init__(self, message: str, errors: list[Exception]):
        super().__init__(message)
        self.errors = errors


class ModelFallback:
    """模型降级执行器"""

    def __init__(self, config: FallbackConfig):
        self.config = config
        self._fallback_errors: list[Exception] = []

    async def execute(self, func: Callable, **kwargs) -> Any:
        """
        执行降级策略

        Args:
            func: 执行函数,接收 model 参数
            **kwargs: 传递给 func 的额外参数

        Returns:
            执行结果

        Raises:
            ModelFallbackError: 所有模型都失败时抛出
        """
        if not self.config.enabled or not self.config.models:
            # 未启用降级,直接执行第一个模型
            if not self.config.models:
                raise ValueError("Fallback models list is empty")
            return await func(model=self.config.models[0], **kwargs)

        self._fallback_errors = []
        last_error: Optional[Exception] = None

        for idx, model in enumerate(self.config.models):
            try:
                if idx > 0:
                    logger.info(f"Fallback to model {idx + 1}/{len(self.config.models)}: {model}")

                result = await func(model=model, **kwargs)

                if idx > 0:
                    logger.info(
                        "fallback_model_success",
                        extra={"model": model, "fallback_index": idx},
                    )

                return result

            except Exception as e:
                last_error = e
                self._fallback_errors.append(e)

                # 检查是否应该降级
                if self._should_fallback(e):
                    logger.warning(
                        "model_fallback_triggered",
                        extra={
                            "model": model,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                else:
                    # 不应该降级的异常,直接抛出
                    logger.error(
                        "non_recoverable_error",
                        extra={
                            "model": model,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                    raise

        # 所有模型都失败
        error_msg = (
            f"All {len(self.config.models)} models failed. Last error: {type(last_error).__name__}: {last_error}"
        )
        logger.error(
            "all_models_failed",
            extra={
                "models_count": len(self.config.models),
                "models_tried": self.config.models,
                "last_error_type": type(last_error).__name__,
                "last_error_message": str(last_error),
            },
        )

        raise ModelFallbackError(error_msg, self._fallback_errors)

    def _should_fallback(self, error: Exception) -> bool:
        """检查是否应该降级"""
        # RetryExecutor wraps its final recoverable error; fallback decisions
        # must still be based on the underlying provider failure.
        root_error = getattr(error, "last_error", error)
        error_type = type(root_error).__name__
        return error_type in self.config.fallback_on

    @property
    def errors(self) -> list[Exception]:
        """获取降级过程中的所有错误"""
        return self._fallback_errors.copy()
