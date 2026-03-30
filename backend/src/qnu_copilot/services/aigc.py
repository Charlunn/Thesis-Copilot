from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AIGCService:
    """Service for AIGC detection and reduction."""

    CONFIG_FILE = "aigc_reduction.json"

    def __init__(self, assets_root: Path | None = None) -> None:
        if assets_root:
            self.assets_root = assets_root
        else:
            self.assets_root = Path(__file__).resolve().parents[2] / "assets"
        self.prompts_root = self.assets_root / "prompts"
        self._config: dict[str, Any] | None = None

    def load_config(self) -> dict[str, Any]:
        """Load AIGC reduction configuration."""
        if self._config is not None:
            return self._config

        config_path = self.prompts_root / self.CONFIG_FILE
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        else:
            self._config = self._get_default_config()

        return self._config

    def _get_default_config(self) -> dict[str, Any]:
        """Get default AIGC configuration."""
        return {
            "threshold": {
                "warning": 30,
                "danger": 50,
                "critical": 70,
            },
            "suggestions": {
                "low": "AIGC 率较低，可以正常导出",
                "medium": "AIGC 率中等，建议进行一次降低处理后再导出",
                "high": "AIGC 率较高，必须进行降低处理后再导出",
                "very_high": "AIGC 率很高，必须多次降低处理",
            },
        }

    def get_detection_prompt(self, content: str) -> str:
        """Get AIGC detection prompt with content."""
        config = self.load_config()
        template = config.get("detection_prompt", "")
        return template.replace("{content}", content)

    def get_reduction_prompt(self, content: str) -> str:
        """Get AIGC reduction prompt with content."""
        config = self.load_config()
        template = config.get("reduction_prompt", "")
        return template.replace("{content}", content)

    def get_model_hint(self) -> str:
        """Get recommended model for AIGC processing."""
        config = self.load_config()
        return config.get("model_hint", "通用大模型")

    def get_instructions(self) -> list[str]:
        """Get instructions for AIGC processing."""
        config = self.load_config()
        return config.get("instructions", [])

    def get_threshold(self, level: str) -> int:
        """Get threshold value for a given level."""
        config = self.load_config()
        thresholds = config.get("threshold", {})
        return thresholds.get(level, 50)

    def get_suggestion(self, aigc_score: int) -> tuple[str, str]:
        """Get suggestion based on AIGC score.
        
        Returns:
            tuple of (level, message)
        """
        config = self.load_config()
        thresholds = config.get("threshold", {})
        suggestions = config.get("suggestions", {})

        warning = thresholds.get("warning", 30)
        danger = thresholds.get("danger", 50)
        critical = thresholds.get("critical", 70)

        if aigc_score < warning:
            return "low", suggestions.get("low", "AIGC 率较低")
        elif aigc_score < danger:
            return "medium", suggestions.get("medium", "AIGC 率中等")
        elif aigc_score < critical:
            return "high", suggestions.get("high", "AIGC 率较高")
        else:
            return "very_high", suggestions.get("very_high", "AIGC 率很高")

    def get_aigc_report(self, content: str, detected_score: int) -> dict[str, Any]:
        """Generate AIGC report with suggestions.
        
        Args:
            content: The text content to analyze
            detected_score: The AIGC score (0-100) from detection
            
        Returns:
            Dictionary containing report information
        """
        level, suggestion = self.get_suggestion(detected_score)
        
        return {
            "score": detected_score,
            "level": level,
            "suggestion": suggestion,
            "needs_reduction": level in ("high", "very_high"),
            "reduction_count": 1 if level == "high" else (2 if level == "very_high" else 0),
            "reduction_prompt": self.get_reduction_prompt(content),
            "model_hint": self.get_model_hint(),
            "instructions": self.get_instructions(),
        }

    def extract_blocks_content(self, blocks: list[dict[str, Any]]) -> str:
        """Extract text content from generation blocks for AIGC checking."""
        content_parts = []
        
        for block in sorted(blocks, key=lambda x: x.get("block_index", 0)):
            block_title = block.get("block_title", "")
            content_parts.append(f"【{block_title}】")
            
            block_content = block.get("normalized_json", {}) or block
            content = block_content.get("content", [])
            
            for element in content:
                element_type = element.get("type", "")
                text = element.get("text", "")
                if element_type in ("h1", "h2", "h3", "p") and text:
                    content_parts.append(text)
                    
                if element_type == "list":
                    items = element.get("items", [])
                    for item in items:
                        if item:
                            content_parts.append(f"• {item}")
        
        return "\n\n".join(content_parts)
