# Workflow AI Assistant

A full-stack application that helps companies design and visualize process workflows using AI, built as a technical test for my SWE internship at Handbook, as requested by CTO Thomas Trihn. It was built with FastAPI, Next.js, MySQL, and OpenAI's API (though limited). The base page was created with the help of GitHub Copilot, with the rest of the features being modified, altered, or added afterwards by me, Johnphr.

## Features

- **User Authentication**: Secure login and registration system with JWT tokens
- **AI-Powered Chatbot**: Interactive chat interface using OpenAI's GPT-4.5 to help design workflows
- **Workflow Visualization**: Automatically generates and displays workflow flowcharts with zoom and pan capabilities
- **Chat History**: Persistent conversation storage with the ability to create, view, and delete chats across sessions
- **Responsive Layout**: 
  - 20% Chat list sidebar
  - 30% Chatbot interface
  - 50% Workflow visualization panel

## Tech Stack

### Backend
- **FastAPI**: Served as the backend service.
- **SQLAlchemy**: SQL toolkit to manage migrations to the db.
- **MySQL**
- **OpenAI API**: Specifically GPT 4.5.
- **JWT**: Secure authentication API.

### Frontend
- **Next**
- **TypeScript**
- **ReactFlow**: Library to create the visual workflows.
- **Zustand**: State management system
- **Axios**: HTTP client for the app

## Getting Started

### Prerequisites

- Docker and Docker Compose (recommended as a quick start)
- OR (if you want to do it without docker i.e: manually):
  - Python 3.11+
  - Node.js 18+
  - MySQL 8.0+

### Option I. Docker Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Johnphr/Handbook-Project.git
   cd Handbook-Project
   ```

2. **Set up environment variables**
   
   Create `backend/.env`:
   ```bash
   DATABASE_URL=mysql+pymysql://root:password@db:3306/handbook_db
   SECRET_KEY=your-secret-key-here-change-in-production
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   OPENAI_API_KEY=your-openai-api-key-here
   ```

   Create `frontend/.env.local`:
   ```bash
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

3. **Start the application**
   ```bash
   docker-compose up --build
   ```

4. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

### Option II. Manual Setup

#### Backend Setup

1. **Navigate to backend directory**
   ```bash
   cd backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run the server**
   ```bash
   python main.py
   ```

#### Frontend Setup

1. **Navigate to frontend directory**
   ```bash
   cd frontend
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Set up environment variables**
   ```bash
   cp .env.local.example .env.local
   # Edit .env.local with your configuration
   ```

4. **Run development server**
   ```bash
   npm run dev
   ```

## Usage

1. **Register/Login**: Create an account or sign in with existing credentials
2. **Create a Chat**: Click "New" to start a new conversation
3. **Ask for Workflow**: Describe the process workflow you need (e.g., "Create a customer onboarding workflow")
4. **View Visualization**: The AI will generate a workflow and visualize it in the right panel
5. **Interact**: Zoom, pan, and explore the generated workflow diagram

## API Endpoints

### Authentication
- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and get access token
- `GET /auth/me` - Get current user info

### Chats
- `GET /chats` - Get all user's chats
- `POST /chats` - Create a new chat
- `GET /chats/{chat_id}` - Get chat with messages
- `DELETE /chats/{chat_id}` - Delete a chat

### Messages
- `POST /chats/{chat_id}/messages` - Send a message and get AI response

## Project Structure

```
Handbook-Project/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── database.py          # Database models and configuration
│   ├── schemas.py           # Pydantic schemas
│   ├── auth.py              # Authentication utilities
│   ├── requirements.txt     # Python dependencies for the project
│   └── Dockerfile          # Backend Docker configuration
├── frontend/
│   ├── app/                 # Next.js App Router pages
│   ├── components/          # React components
│   ├── lib/                 # Utilities and API client
│   ├── styles/              # CSS styles
│   ├── package.json         # Node.js dependencies for the project
│   └── Dockerfile          # Frontend Docker configuration
└── docker-compose.yml       # Docker Compose configuration
```

## Configuration

### OpenAI API Key

To enable AI-powered workflow generation, you need an OpenAI API key, added to `OPENAI_API_KEY` in `backend/.env` :
Without an API key, the application will work only with fallback examples, not actual workflows according to the user's needs.

### Database

The default configuration uses MySQL 8.0, though it can be modified by changing the `DATABASE_URL` in `backend/.env`.

## Security Notes

- Change the `SECRET_KEY` in production
- Use strong passwords for the MySQL root user
- Enable HTTPS in production
- Never, ever, commit `.env` files to version control
- Regularly update dependencies

## License

This project is open source and available under the MIT License.