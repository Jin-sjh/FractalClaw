from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import datetime

from models import TodoCreate, TodoUpdate, TodoResponse, MessageResponse
import database

# Create FastAPI application
app = FastAPI(
    title="Todo API",
    description="A RESTful API for managing todo items",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    database.init_db()
    print("Database initialized successfully")

# Root endpoint - Health check
@app.get("/", response_model=MessageResponse)
async def root():
    return MessageResponse(message="Todo API is running", success=True)

# Create a new todo
@app.post("/todos", response_model=TodoResponse, status_code=201)
async def create_todo(todo: TodoCreate):
    try:
        new_todo = database.create_todo(
            title=todo.title,
            description=todo.description
        )
        return new_todo
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get all todos
@app.get("/todos", response_model=List[TodoResponse])
async def get_all_todos():
    try:
        todos = database.get_all_todos()
        return todos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get a specific todo by ID
@app.get("/todos/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: int):
    todo = database.get_todo_by_id(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

# Update a todo
@app.put("/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(todo_id: int, todo: TodoUpdate):
    updated_todo = database.update_todo(
        todo_id=todo_id,
        title=todo.title,
        description=todo.description,
        is_completed=todo.is_completed
    )
    if updated_todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return updated_todo

# Delete a todo
@app.delete("/todos/{todo_id}", response_model=MessageResponse)
async def delete_todo(todo_id: int):
    success = database.delete_todo(todo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Todo not found")
    return MessageResponse(message="Todo deleted successfully", success=True)

# Toggle todo completion status
@app.patch("/todos/{todo_id}/toggle", response_model=TodoResponse)
async def toggle_todo(todo_id: int):
    toggled_todo = database.toggle_todo_completion(todo_id)
    if toggled_todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return toggled_todo

# Run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)