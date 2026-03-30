from __future__ import annotations

from fastapi import APIRouter

from qnu_copilot.services.aigc import AIGCService


def create_aigc_router() -> APIRouter:
    """Create AIGC checking router."""
    router = APIRouter()
    aigc_service = AIGCService()

    @router.get("/aigc/detection-prompt")
    def get_detection_prompt(content: str) -> dict[str, str]:
        """Get AIGC detection prompt with content."""
        prompt = aigc_service.get_detection_prompt(content)
        return {
            "prompt": prompt,
            "model_hint": aigc_service.get_model_hint(),
            "instructions": aigc_service.get_instructions(),
        }

    @router.get("/aigc/reduction-prompt")
    def get_reduction_prompt(content: str) -> dict[str, str]:
        """Get AIGC reduction prompt with content."""
        prompt = aigc_service.get_reduction_prompt(content)
        return {
            "prompt": prompt,
            "model_hint": aigc_service.get_model_hint(),
            "instructions": aigc_service.get_instructions(),
        }

    @router.post("/aigc/analyze")
    def analyze_aigc_score(content: str, detected_score: int) -> dict:
        """Analyze AIGC score and provide suggestions."""
        report = aigc_service.get_aigc_report(content, detected_score)
        return report

    @router.get("/aigc/thresholds")
    def get_thresholds() -> dict[str, int]:
        """Get AIGC threshold values."""
        return {
            "warning": aigc_service.get_threshold("warning"),
            "danger": aigc_service.get_threshold("danger"),
            "critical": aigc_service.get_threshold("critical"),
        }

    return router
