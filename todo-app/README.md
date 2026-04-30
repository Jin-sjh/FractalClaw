# Todo Application - Full Stack

A complete Todo application with React frontend, FastAPI backend, and SQLite database.

## Project Structure

```
todo-app/
├── frontend/          # React frontend application
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── api.js     # API service for backend communication
│   │   └── App.jsx    # Main application component
│   ├── package.json
│   └── README.md
├── backend/           # FastAPI backend application
│   ├── main.py        # FastAPI application with RESTful endpoints
│   ├── models.py      # Pydantic models for data validation
│   ├── database.py    # SQLite database connection and operations
│   └── requirements.txt
├── database/          # SQLite database files
│   └── todos.db       # SQLite database file (created automatically)
└── README.md          # This file
```

## Features

### Frontend (React)
- View list of all todo items
- Add new todo items
- Edit existing todo items
- Delete todo items
- Mark todos as complete/incomplete
- Responsive user interface

### Backend (FastAPI)
- RESTful API endpoints for CRUD operations
- Data validation with Pydantic models
- SQLite database integration
- CORS support for frontend communication

### Database (SQLite)
- Todos table with schema:
  - `id`: Primary key (INTEGER)
  - `title`: Todo title (TEXT, NOT NULL)
  - `description`: Todo description (TEXT)
  - `is_completed`: Completion status (BOOLEAN, DEFAULT FALSE)
  - `created_at`: Creation timestamp (DATETIME)
  - `updated_at`: Last update timestamp (DATETIME)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | /todos   | Create a new todo |
| GET    | /todos   | Get all todos |
| GET    | /todos/{id} | Get a specific todo |
| PUT    | /todos/{id} | Update a todo |
| DELETE | /todos/{id} | Delete a todo |

## Getting Started

### Prerequisites
- Python 3.7+
- Node.js 14+
- npm or yarn

### Installation

1. **Backend Setup**
   ```bash
   cd backend
   pip install -r requirements.txt
   python main.py
   ```

2. **Frontend Setup**
   ```bash
   cd frontend
   npm install
   npm start
   ```

3. **Access the Application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## Development

### Backend Development
- FastAPI server runs on port 8000
- Uses SQLite database stored in `database/todos.db`
- Database is automatically created on first run

### Frontend Development
- React development server runs on port 3000
- Hot reloading enabled for development
- API calls configured to communicate with backend

## Technologies Used

### Frontend
- React 18
- JavaScript (ES6+)
- CSS3 for styling
- Fetch API for HTTP requests

### Backend
- FastAPI 0.100+
- Python 3.7+
- SQLite3
- Pydantic for data validation
- Uvicorn ASGI server

## License

This project is open source and available under the MIT License.