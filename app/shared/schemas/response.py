from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    code: int = Field(..., description="response status code")
    msg: str = Field(default="", description="response message")
    data: T | None = Field(default=None, description="response data")


class SuccessResponse(BaseResponse[T]):
    code: int = Field(default=0, description="success code")
    msg: str = Field(default="success", description="success message")


class ErrorResponse(BaseResponse[T]):
    code: int = Field(default=1, description="error code")
    msg: str = Field(..., description="error message")
