class AppError(Exception):
    status_code = 400
    error_code = "app_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def get_user_message(self, operation: str = "操作") -> str:
        """Get user-friendly Chinese error message."""
        return self.message


class InvalidInputError(AppError):
    status_code = 400
    error_code = "invalid_input"

    def get_user_message(self, operation: str = "操作") -> str:
        return f"输入无效：请检查输入格式是否正确（{operation}）"


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"

    def get_user_message(self, operation: str = "操作") -> str:
        return f"未找到：相关资源不存在，请刷新后重试（{operation}）"


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"

    def get_user_message(self, operation: str = "操作") -> str:
        return f"状态冲突：当前步骤尚未完成或已被占用，请等待完成后再试（{operation}）"


class ContractValidationError(AppError):
    status_code = 422
    error_code = "contract_validation_failed"

    def get_user_message(self, operation: str = "操作") -> str:
        return f"验证失败：AI返回的JSON格式不符合要求，请重试（{operation}）"
