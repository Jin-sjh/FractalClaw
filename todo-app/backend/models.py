from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TodoBase(BaseModel):
    """Base model for todo items with common fields."""
    title: str = Field(..., min_length=1, max_length=200, description="The title of the todo item")
    description: Optional[str] = Field(None, max_length=1000, description="Detailed description of the todo item")
    is_completed: bool = Field(False, description="Whether the todo item is completed")


class TodoCreate(TodoBase):
    """Model for creating a new todo item."""
    pass


class TodoUpdate(BaseModel):
    """Model for updating an existing todo item."""
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="The title of the todo item")
    description: Optional[str] = Field(None, max_length=1000, description="Detailed description of the todo item")
    is_completed: Optional[bool] = Field(None, description="Whether the todo item is completed")


class TodoResponse(TodoBase):
    """Model for todo item response with all fields."""
    id: int = Field(..., description="Unique identifier for the todo item")
    created_at: datetime = Field(..., description="Timestamp when the todo was created")
    updated_at: datetime = Field(..., description="Timestamp when the todo was last updated")

    class Config:
        from_attributes = True


class TodoToggle(BaseModel):
    """Model for toggling todo completion status."""
    is_completed: bool = Field(..., description="New completion status")


class MessageResponse(BaseModel):
    """Generic message response model."""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str
    success: bool = False