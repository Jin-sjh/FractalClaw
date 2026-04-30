import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
import os

# Database file path
DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'todos.db')


def get_connection():
    """Create and return a database connection."""
    # Ensure the database directory exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn


def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create todos table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            is_completed BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DATABASE_PATH}")


def create_todo(title: str, description: Optional[str] = None) -> Dict[str, Any]:
    """Create a new todo item."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO todos (title, description, is_completed, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, description, False, datetime.now(), datetime.now()))
    
    todo_id = cursor.lastrowid
    conn.commit()
    
    # Fetch the created todo
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    todo = dict(cursor.fetchone())
    
    conn.close()
    return todo


def get_all_todos() -> List[Dict[str, Any]]:
    """Get all todo items."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM todos ORDER BY created_at DESC')
    todos = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return todos


def get_todo_by_id(todo_id: int) -> Optional[Dict[str, Any]]:
    """Get a todo item by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    row = cursor.fetchone()
    
    conn.close()
    return dict(row) if row else None


def update_todo(todo_id: int, title: Optional[str] = None, description: Optional[str] = None, 
                is_completed: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """Update a todo item."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # First check if todo exists
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    existing = cursor.fetchone()
    
    if not existing:
        conn.close()
        return None
    
    # Update fields if provided
    updates = []
    params = []
    
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    
    if is_completed is not None:
        updates.append("is_completed = ?")
        params.append(is_completed)
    
    updates.append("updated_at = ?")
    params.append(datetime.now())
    
    params.append(todo_id)
    
    update_query = f"UPDATE todos SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(update_query, params)
    
    conn.commit()
    
    # Fetch updated todo
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    todo = dict(cursor.fetchone())
    
    conn.close()
    return todo


def delete_todo(todo_id: int) -> bool:
    """Delete a todo item. Returns True if deleted, False if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # First check if todo exists
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    if not cursor.fetchone():
        conn.close()
        return False
    
    cursor.execute('DELETE FROM todos WHERE id = ?', (todo_id,))
    conn.commit()
    
    conn.close()
    return True


def toggle_todo_completion(todo_id: int) -> Optional[Dict[str, Any]]:
    """Toggle the completion status of a todo item."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    new_status = not row['is_completed']
    cursor.execute('''
        UPDATE todos 
        SET is_completed = ?, updated_at = ?
        WHERE id = ?
    ''', (new_status, datetime.now(), todo_id))
    
    conn.commit()
    
    # Fetch updated todo
    cursor.execute('SELECT * FROM todos WHERE id = ?', (todo_id,))
    todo = dict(cursor.fetchone())
    
    conn.close()
    return todo


# Initialize database when module is imported
if __name__ == "__main__":
    init_db()
    print("Database initialization complete.")