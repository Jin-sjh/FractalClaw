"""Tool base classes and core types for FractalClaw tools system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from fractalclaw.tools.context import ToolContext


class ToolParameters(BaseModel):
    """Base class for tool parameters using Pydantic for validation."""

    model_config = {"extra": "forbid"}


@dataclass
class ToolResult:
    """Tool execution result with structured output."""

    title: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def truncated(
        cls,
        title: str,
        output: str,
        full_output_path: Optional[str] = None,
        **extra_metadata: Any,
    ) -> "ToolResult":
        """Create a truncated result with metadata about truncation."""
        return cls(
            title=title,
            output=output,
            metadata={
                "truncated": full_output_path is not None,
                "full_output_path": full_output_path,
                **extra_metadata,
            },
        )

    @classmethod
    def error(cls, title: str, error_message: str, **extra_metadata: Any) -> "ToolResult":
        """Create an error result."""
        return cls(
            title=title,
            output=f"Error: {error_message}",
            metadata={"error": True, "error_message": error_message, **extra_metadata},
        )


@dataclass
class ToolInfo:
    """Tool information for discovery and documentation."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: Optional[str] = None
    requires_permissions: list[str] = field(default_factory=list)


class BaseTool(ABC):
    """Abstract base class for all tools.

    Tools should inherit from this class and implement the execute method.
    Use Pydantic models for parameter validation.

    Example:
        class ReadParameters(ToolParameters):
            file_path: str = Field(description="The absolute path to the file")
            offset: Optional[int] = Field(default=None, description="Starting line number")

        class ReadTool(BaseTool):
            name = "read"
            description = "Read file contents"
            parameters_model = ReadParameters

            async def execute(self, params: ReadParameters, ctx: ToolContext) -> ToolResult:
                content = await self._read_file(params.file_path)
                return ToolResult(title=Path(params.file_path).name, output=content)
    """

    name: ClassVar[str]
    description: ClassVar[str]
    parameters_model: ClassVar[type[ToolParameters]]
    category: ClassVar[str] = "general"
    tags: ClassVar[list[str]] = []
    version: ClassVar[str] = "1.0.0"

    @abstractmethod
    async def execute(self, params: ToolParameters, ctx: "ToolContext") -> ToolResult:
        """Execute the tool with validated parameters.

        Args:
            params: Validated parameters from parameters_model
            ctx: Execution context with session info and permission access

        Returns:
            ToolResult with title, output, and metadata
        """
        pass

    def to_schema(self) -> dict[str, Any]:
        """Convert tool definition to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_model.model_json_schema(),
            },
        }

    def to_info(self) -> ToolInfo:
        """Get tool information for discovery."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters_schema=self.parameters_model.model_json_schema(),
            category=self.category,
            tags=self.tags,
            version=self.version,
            requires_permissions=self._get_required_permissions(),
        )

    def _get_required_permissions(self) -> list[str]:
        """Get list of permissions required by this tool.

        Override this method to specify required permissions.
        """
        return []


class ToolNotFoundError(Exception):
    """Raised when a tool is not found in the registry."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found")


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, tool_name: str, message: str, cause: Optional[Exception] = None):
        self.tool_name = tool_name
        self.message = message
        self.cause = cause
        super().__init__(f"Tool '{tool_name}' execution failed: {message}")


class ToolValidationError(Exception):
    """Raised when tool parameter validation fails."""

    def __init__(self, tool_name: str, errors: list[dict[str, Any]]):
        self.tool_name = tool_name
        self.errors = errors
        error_messages = [e.get("msg", str(e)) for e in errors]
        super().__init__(f"Tool '{tool_name}' validation failed: {'; '.join(error_messages)}")
