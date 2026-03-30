from __future__ import annotations

from pathlib import Path


class TemplateChecker:
    """Service for checking template assets."""

    DEFAULT_TEMPLATE_ID = "qnu-undergraduate-v1"

    REQUIRED_TEMPLATES = {
        "qnu-undergraduate-v1": "青海师范大学本科毕业论文模板",
    }

    def __init__(self, assets_root: Path | None = None) -> None:
        if assets_root:
            self.assets_root = assets_root
        else:
            self.assets_root = Path(__file__).resolve().parents[2] / "assets"
        self.templates_root = self.assets_root / "templates"

    def check_template(self, template_id: str) -> dict[str, str | bool]:
        """Check if a template exists and return its status."""
        template_path = self.templates_root / f"{template_id}.docx"
        
        result = {
            "template_id": template_id,
            "template_name": self.REQUIRED_TEMPLATES.get(template_id, "自定义模板"),
            "exists": template_path.exists(),
            "path": str(template_path),
        }
        
        if result["exists"]:
            # Check file size
            try:
                size = template_path.stat().st_size
                result["size_bytes"] = size
                result["size_mb"] = round(size / (1024 * 1024), 2)
            except Exception:
                result["size_bytes"] = 0
                result["size_mb"] = 0
        
        return result

    def check_all_templates(self) -> list[dict[str, str | bool]]:
        """Check all required templates."""
        results = []
        for template_id, template_name in self.REQUIRED_TEMPLATES.items():
            result = self.check_template(template_id)
            result["template_name"] = template_name
            results.append(result)
        return results

    def get_default_template_status(self) -> dict[str, str | bool]:
        """Get status of the default template."""
        return self.check_template(self.DEFAULT_TEMPLATE_ID)

    def is_template_available(self, template_id: str) -> bool:
        """Check if a specific template is available."""
        template_path = self.templates_root / f"{template_id}.docx"
        return template_path.exists()
