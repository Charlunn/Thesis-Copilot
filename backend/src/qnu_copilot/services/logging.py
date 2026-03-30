from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ErrorLogger:
    """Service for logging errors and events."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logger()

    def _setup_logger(self) -> None:
        """Set up the logger."""
        self.logger = logging.getLogger("qnu_copilot")
        self.logger.setLevel(logging.DEBUG)
        
        # Avoid duplicate handlers
        if not self.logger.handlers:
            # File handler
            log_file = self.log_dir / "error.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # Formatter
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def log_error(
        self,
        project_id: str | None,
        operation: str,
        error: Exception,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an error with context."""
        error_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "details": details or {},
        }
        
        self.logger.error(
            f"Project: {project_id}, Operation: {operation}, "
            f"Error: {type(error).__name__}: {error}",
            extra={"error_info": error_info}
        )
        
        # Also save to structured log file
        self._save_structured_log(error_info, "error")

    def log_warning(
        self,
        project_id: str | None,
        operation: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a warning with context."""
        warning_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "operation": operation,
            "message": message,
            "details": details or {},
        }
        
        self.logger.warning(
            f"Project: {project_id}, Operation: {operation}, "
            f"Warning: {message}",
            extra={"warning_info": warning_info}
        )
        
        self._save_structured_log(warning_info, "warning")

    def log_info(
        self,
        project_id: str | None,
        operation: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an info message with context."""
        info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "operation": operation,
            "message": message,
            "details": details or {},
        }
        
        self.logger.info(
            f"Project: {project_id}, Operation: {operation}, "
            f"Info: {message}",
            extra={"info": info}
        )

    def _save_structured_log(self, log_entry: dict[str, Any], log_type: str) -> None:
        """Save log entry to structured log file."""
        log_file = self.log_dir / f"{log_type}s.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Don't let logging failures crash the app

    def get_recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent error logs."""
        log_file = self.log_dir / "errors.jsonl"
        if not log_file.exists():
            return []
        
        errors = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        errors.append(json.loads(line.strip()))
                    except Exception:
                        continue
        except Exception:
            return []
        
        return errors[-limit:]


def create_error_message_zh(error: Exception, operation: str) -> str:
    """Translate error to user-friendly Chinese message."""
    error_type = type(error).__name__
    
    # Common error translations
    translations = {
        "NotFoundError": f"操作失败：找不到相关资源（{operation}）",
        "ConflictError": f"操作冲突：{operation}步骤尚未完成或已被占用",
        "ValidationError": f"数据验证失败：请检查输入格式是否正确（{operation}）",
        "FileNotFoundError": f"文件未找到：请确认文件路径是否正确（{operation}）",
        "PermissionError": f"权限不足：无法访问或修改文件（{operation}）",
        "JSONDecodeError": f"JSON格式错误：AI返回的内容无法解析，请重试（{operation}）",
        "ValueError": f"参数错误：请检查输入值是否有效（{operation}）",
    }
    
    if error_type in translations:
        return translations[error_type]
    
    # Generic fallback
    return f"{operation}时发生错误：{str(error)}"
