from typing import Any

from app.shared.schemas.response import ErrorResponse, SuccessResponse


def create_success_response(data: Any = None, msg: str = "success") -> SuccessResponse[Any]:
    return SuccessResponse[Any](code=0, msg=msg, data=data)


def create_error_response(msg: str, data: Any = None) -> ErrorResponse[Any]:
    return ErrorResponse[Any](code=1, msg=msg, data=data)


def create_paginated_response(data: list[Any], total: int, page: int, page_size: int, msg: str = "success") -> SuccessResponse[dict]:
    payload = {
        "list": data,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
    return create_success_response(payload, msg)
