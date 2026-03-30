from enum import Enum


class WorkflowStage(str, Enum):
    REFERENCES = "references"
    PDF_PROCESSING = "pdf_processing"
    OUTLINE_GENERATION = "outline_generation"
    OUTLINE_EDITING = "outline_editing"
    CHUNK_PLANNING = "chunk_planning"
    BLOCK_GENERATION = "block_generation"
    EXPORT = "export"
    DONE = "done"


class GenericStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class ReferenceSourceMode(str, Enum):
    RECOMMENDED = "recommended"
    MANUAL = "manual"


class ReferenceStatus(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    SKIPPED_UNAVAILABLE = "skipped_unavailable"
    SKIPPED_USER_CHOICE = "skipped_user_choice"
    MATCH_FAILED = "match_failed"


class ContractType(str, Enum):
    REFERENCE_RECOMMENDATION = "reference_recommendation"
    OUTLINE = "outline"
    CHUNK_PLAN = "chunk_plan"
    BLOCK_CONTENT = "block_content"
    COMPRESSED_CONTEXT = "compressed_context"


class SkipReason(str, Enum):
    UNAVAILABLE = "unavailable"
    USER_CHOICE = "user_choice"


class BlockElementType(str, Enum):
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    P = "p"
    LIST = "list"
    TABLE_PLACEHOLDER = "table_placeholder"
