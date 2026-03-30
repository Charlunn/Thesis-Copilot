from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from qnu_copilot.domain.enums import BlockElementType


class RecommendedPaperContract(BaseModel):
    title: str
    language: str
    year: int | None = None
    venue: str | None = None
    download_url: str
    impact_note: str | None = None
    bibtex: str

    @field_validator("title", "download_url", "bibtex")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        language_map = {
            "zh": "zh",
            "cn": "zh",
            "中文": "zh",
            "chinese": "zh",
            "en": "en",
            "英文": "en",
            "english": "en",
        }
        if normalized not in language_map:
            raise ValueError("language must normalize to zh or en")
        return language_map[normalized]


class ReferenceRecommendationContract(BaseModel):
    topic: str
    papers: list[RecommendedPaperContract] = Field(min_length=30)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("topic must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_language_distribution(self) -> "ReferenceRecommendationContract":
        zh_count = sum(1 for paper in self.papers if paper.language == "zh")
        en_count = sum(1 for paper in self.papers if paper.language == "en")
        if zh_count < 15:
            raise ValueError("at least 15 Chinese papers are required")
        if en_count < 15:
            raise ValueError("at least 15 English papers are required")
        return self


class OutlineNodeContract(BaseModel):
    id: str
    level: int
    title: str
    children: list["OutlineNodeContract"] = Field(default_factory=list)

    @field_validator("id", "title")
    @classmethod
    def validate_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_children(self) -> "OutlineNodeContract":
        for child in self.children:
            if child.level != self.level + 1:
                raise ValueError("child level must be parent level plus 1")
        return self


class OutlineContract(BaseModel):
    title: str
    outline: list[OutlineNodeContract] = Field(min_length=3)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_root_levels(self) -> "OutlineContract":
        for node in self.outline:
            if node.level != 1:
                raise ValueError("root nodes must use level 1")
        return self


class ConfirmedOutlineNodeContract(BaseModel):
    id: str
    level: int
    title: str
    enabled: bool = True
    must_be_separate_block: bool = False
    children: list["ConfirmedOutlineNodeContract"] = Field(default_factory=list)

    @field_validator("id", "title")
    @classmethod
    def validate_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_children(self) -> "ConfirmedOutlineNodeContract":
        for child in self.children:
            if child.level != self.level + 1:
                raise ValueError("child level must be parent level plus 1")
        return self


class ConfirmedOutlineContract(BaseModel):
    title: str
    outline: list[ConfirmedOutlineNodeContract] = Field(min_length=3)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_root_levels(self) -> "ConfirmedOutlineContract":
        for node in self.outline:
            if node.level != 1:
                raise ValueError("root nodes must use level 1")
        return self


class ChunkBlockContract(BaseModel):
    block_index: int
    title: str
    outline_node_ids: list[str] = Field(min_length=1)
    goal: str
    minimum_words: int
    citation_focus: list[str] = Field(default_factory=list)

    @field_validator("title", "goal")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized

    @field_validator("minimum_words")
    @classmethod
    def validate_minimum_words(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("minimum_words must be positive")
        return value


class ChunkPlanContract(BaseModel):
    total_blocks: int
    blocks: list[ChunkBlockContract]

    @model_validator(mode="after")
    def validate_blocks(self) -> "ChunkPlanContract":
        if self.total_blocks != len(self.blocks):
            raise ValueError("total_blocks must equal blocks length")
        expected = list(range(1, len(self.blocks) + 1))
        actual = [block.block_index for block in self.blocks]
        if actual != expected:
            raise ValueError("block_index must be contiguous and start from 1")
        return self


class BlockContentElement(BaseModel):
    type: BlockElementType
    text: str | None = None
    items: list[str] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "BlockContentElement":
        if self.type == BlockElementType.LIST:
            if not self.items:
                raise ValueError("list elements must contain items")
            return self
        if not (self.text or "").strip():
            raise ValueError("non-list elements must contain text")
        return self


class BlockContentContract(BaseModel):
    block_index: int
    block_title: str
    content: list[BlockContentElement] = Field(min_length=1)

    @field_validator("block_title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("block_title must not be empty")
        return normalized


class CompressedContextPayload(BaseModel):
    narrative_summary: str
    key_claims: list[str] = Field(default_factory=list)
    used_citations: list[str] = Field(default_factory=list)
    pending_topics: list[str] = Field(default_factory=list)
    style_constraints: list[str] = Field(default_factory=list)

    @field_validator("narrative_summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("narrative_summary must not be empty")
        return normalized


class CompressedContextContract(BaseModel):
    covered_blocks: list[int] = Field(min_length=1)
    compressed_context: CompressedContextPayload

    @model_validator(mode="after")
    def validate_blocks(self) -> "CompressedContextContract":
        expected = sorted(set(self.covered_blocks))
        if self.covered_blocks != expected:
            raise ValueError("covered_blocks must be sorted and unique")
        return self


OutlineNodeContract.model_rebuild()
ConfirmedOutlineNodeContract.model_rebuild()
