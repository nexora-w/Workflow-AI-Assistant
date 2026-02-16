# Development Guide

This guide provides detailed information for developers working on the Workflow AI Assistant project.

## Project Structure

```
Handbook-Project/
├── backend/                 # FastAPI backend application
│   ├── main.py             # Main application entry point
│   ├── database.py         # Database models and ORM setup
│   ├── schemas.py          # Pydantic schemas for validation
│   ├── auth.py             # Authentication and JWT utilities
│   ├── requirements.txt    # Python dependencies
│   ├── Dockerfile          # Backend container configuration
│   └── .env.example        # Environment variables template
├── frontend/               # Next.js frontend application
│   ├── app/                # Next.js App Router pages
│   │   ├── page.tsx        # Main application page
│   │   └── layout.tsx      # Root layout component
│   ├── components/         # React components
│   │   ├── AuthForm.tsx    # Login/Register form
│   │   ├── ChatList.tsx    # Chat list sidebar
│   │   ├── ChatWindow.tsx  # Chat interface
│   │   └── WorkflowVisualization.tsx  # Workflow diagram
│   ├── lib/                # Utilities
│   │   ├── api.ts          # API client and types
│   │   └── store.ts        # Zustand state management
│   ├── styles/             # Global CSS styles
│   ├── package.json        # Node.js dependencies
│   ├── next.config.js      # Next.js configuration
│   ├── tsconfig.json       # TypeScript configuration
│   └── Dockerfile          # Frontend container configuration
├── docker-compose.yml      # Docker services orchestration
├── .gitignore              # Git ignore patterns
└── README.md               # Main documentation

```

## Development Setup

### Backend Development

1. **Create virtual environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Run development server**
   ```bash
   uvicorn main:app --reload
   ```

   The API will be available at http://localhost:8000
   API documentation at http://localhost:8000/docs

### Frontend Development

1. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Set up environment variables**
   ```bash
   cp .env.local.example .env.local
   # Edit .env.local with your configuration
   ```

3. **Run development server**
   ```bash
   npm run dev
   ```

   The app will be available at http://localhost:3000

## API Endpoints

### Authentication

- `POST /auth/register` - Register a new user
  ```json
  {
    "username": "string",
    "email": "user@example.com",
    "password": "string"
  }
  ```

- `POST /auth/login` - Login and receive JWT token
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```

- `GET /auth/me` - Get current user information (requires authentication)

### Chats

- `GET /chats` - List all chats for current user
- `POST /chats` - Create a new chat
  ```json
  {
    "title": "string"
  }
  ```
- `GET /chats/{chat_id}` - Get chat with all messages
- `DELETE /chats/{chat_id}` - Delete a chat

### Messages

- `POST /chats/{chat_id}/messages` - Send a message and get AI response
  ```json
  {
    "content": "string"
  }
  ```

## Database Schema

### Users Table
- `id`: Primary key
- `username`: Unique username
- `email`: Unique email
- `hashed_password`: Bcrypt hashed password
- `created_at`: Account creation timestamp

### Chats Table
- `id`: Primary key
- `user_id`: Foreign key to users
- `title`: Chat title
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

### Messages Table
- `id`: Primary key
- `chat_id`: Foreign key to chats
- `role`: 'user' or 'assistant'
- `content`: Message text
- `workflow_data`: JSON string (optional)
- `created_at`: Message timestamp

## Frontend Architecture

### State Management

The application uses Zustand for state management:

- **Auth Store** (`lib/store.ts`): Manages user authentication state
  - `user`: Current user object
  - `token`: JWT access token
  - `login()`, `register()`, `logout()`, `checkAuth()`

### Components

1. **AuthForm**: Handles user login and registration
2. **ChatList**: Displays list of conversations with create/delete actions
3. **ChatWindow**: Main chat interface with message history and input
4. **WorkflowVisualization**: ReactFlow-based workflow diagram viewer

### API Integration

The `lib/api.ts` file provides a centralized API client:
- Axios instance with base URL configuration
- Automatic JWT token injection via interceptors
- TypeScript types for all API responses

## Workflow Data Format

Workflows are represented as JSON objects:

```json
{
  "nodes": [
    {
      "id": "1",
      "label": "Start",
      "type": "start"
    },
    {
      "id": "2",
      "label": "Process",
      "type": "process"
    },
    {
      "id": "3",
      "label": "Decision",
      "type": "decision"
    },
    {
      "id": "4",
      "label": "End",
      "type": "end"
    }
  ],
  "edges": [
    {
      "from": "1",
      "to": "2"
    },
    {
      "from": "2",
      "to": "3"
    },
    {
      "from": "3",
      "to": "4"
    }
  ]
}
```

Node types:
- `start`: Entry point (purple)
- `process`: Processing step (green)
- `decision`: Decision point (orange)
- `end`: Exit point (violet)

## OpenAI Integration

The backend uses OpenAI's GPT-3.5-turbo model to:
1. Understand user workflow requirements
2. Generate structured workflow data
3. Provide explanations and suggestions

The system message instructs the AI to format workflows as JSON matching our schema.

## Docker Deployment

### Build and run all services
```bash
docker-compose up --build
```

### Run in background
```bash
docker-compose up -d
```

### View logs
```bash
docker-compose logs -f
```

### Stop services
```bash
docker-compose down
```

### Clean up volumes
```bash
docker-compose down -v
```

## Environment Variables

### Backend (.env)
- `DATABASE_URL`: Database connection string
- `SECRET_KEY`: JWT signing key (change in production!)
- `ALGORITHM`: JWT algorithm (HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration time
- `OPENAI_API_KEY`: OpenAI API key

### Frontend (.env.local)
- `NEXT_PUBLIC_API_URL`: Backend API URL

## Security Considerations

1. **JWT Tokens**: Stored in localStorage, included in Authorization header
2. **Password Hashing**: Uses bcrypt with automatic salt generation
3. **CORS**: Configured to allow frontend origin
4. **SQL Injection**: Protected by SQLAlchemy ORM
5. **Environment Variables**: Never commit .env files

## Testing

### Backend Testing
```bash
cd backend
pytest  # Add tests in tests/ directory
```

### Frontend Testing
```bash
cd frontend
npm test  # Add tests for components
```

## Common Issues

### Database Connection
- Ensure MySQL is running
- Check DATABASE_URL format
- Verify credentials

### CORS Errors
- Check NEXT_PUBLIC_API_URL matches backend URL
- Verify CORS settings in main.py

### OpenAI API
- Verify API key is valid
- Check rate limits
- Review error messages in logs

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details
