# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

G.A.V. (Gentil Assistente de Vendas) is an intelligent WhatsApp sales assistant for Comercial Esperança. This is a Flask-based Python application that integrates with Twilio/Vonage for WhatsApp messaging, uses PostgreSQL for data storage, Redis for session management, and Ollama for AI language processing.

## Development Commands

### Environment Setup
```bash
# Start all services (PostgreSQL, Redis, App)
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services  
docker-compose down

# Rebuild after changes
docker-compose up --build
```

### Database Operations
```bash
# Access PostgreSQL container
docker exec -it bot_postgres_db_funcional psql -U postgres -d postgres

# Initialize/reset database (automatic on first run via init.sql)
# Database schema is in init.sql with comprehensive tables and indexes
```

### Knowledge Base Management
```bash
# Rebuild knowledge base (from IA directory)
python knowledge/knowledge.py

# This generates knowledge_base.json with AI-enhanced product mappings
```

### Testing and Development
```bash
# Application runs on port 8081 (mapped from container port 8080)
# Access: http://localhost:8081

# View application logs
docker-compose logs -f app

# Clear cart via API
curl -X POST http://localhost:8081/clear_cart -H "Content-Type: application/json" -d '{"user_id": "user_phone_number"}'
```

## Architecture Overview

### Core Components

**Main Application** (`IA/app.py`)
- Flask web server handling WhatsApp webhooks
- Async message processing with threading
- Session management and conversation state
- Product search and cart management
- Integration with all sub-systems

**AI/LLM Interface** (`IA/ai_llm/llm_interface.py`)
- Ollama integration for intent detection
- Context-aware conversation understanding
- CNPJ validation and command detection
- Fallback mechanisms for offline operation

**Knowledge Base** (`IA/knowledge/knowledge.py`)
- Intelligent product search with fuzzy matching
- Auto-learning from user interactions
- AI-generated product variations and synonyms
- Persistent learning storage in knowledge_base.json

**Database Layer** (`IA/db/database.py`)
- PostgreSQL integration with comprehensive schema
- Product catalog with pricing and inventory
- Customer management and order tracking
- Session and analytics storage

**Session Management** (`IA/core/session_manager.py`)
- Conversation context and history
- Shopping cart state management
- User interaction tracking
- Quick actions and menu generation

### Key Features

**Intelligent Product Search**
- Fuzzy text matching with typo tolerance
- Knowledge base with learned associations
- Database fallback with suggestions
- Quality analysis of search results

**Cart Management**
- Add/remove/update items with natural language
- Quantity extraction from conversational input
- Duplicate item handling with user choice
- Complete cart clearing functionality

**Human-like AI Interactions**
- Dynamic response generation using AI
- Context-aware personalized messages
- Varied greetings and responses (never repetitive)
- Empathetic error handling
- Natural Brazilian Portuguese expressions

**Customer Journey**
- CNPJ-based customer identification
- Contextual conversation flow
- Automatic checkout process
- Order summary generation

**Communication Channels**
- Twilio WhatsApp integration (primary)
- Vonage WhatsApp support (secondary)
- Async message processing for scalability

## Important Development Notes

### File Structure
```
IA/
├── app.py                 # Main Flask application
├── ai_llm/               # LLM integration
│   ├── llm_interface.py  # Ollama communication
│   └── gav_prompt.txt    # AI system prompt
├── communication/        # WhatsApp clients
│   ├── twilio_client.py  # Twilio integration
│   └── vonage_client.py  # Vonage integration
├── knowledge/            # Smart product search
│   ├── knowledge.py      # Knowledge base engine
│   └── knowledge_base.json # Learned associations
├── db/                   # Database layer
│   └── database.py       # PostgreSQL operations
├── core/                 # Core utilities
│   └── session_manager.py # Session handling
├── utils/                # Helper utilities
│   ├── fuzzy_search.py   # Text matching
│   ├── quantity_extractor.py # Natural language parsing
│   └── logger_config.py  # Logging setup
└── data/                 # Session storage files
```

### Environment Variables (in .env)
```
# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=gav_db

# Redis
REDIS_PASSWORD=your_redis_password
REDIS_HOST=redis
REDIS_PORT=6379

# Ollama AI
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL_NAME=llama3.1

# WhatsApp
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
```

### Key Technical Patterns

**Message Processing Flow**
1. Webhook receives WhatsApp message
2. Async thread processes in background  
3. Session loaded with conversation history
4. Pending actions handled first
5. AI determines user intent OR generates dynamic response
6. Tool routing executes appropriate action
7. AI generates personalized responses when appropriate
8. Response sent via WhatsApp client

**Search Strategy**
1. Knowledge base exact match (fastest)
2. Knowledge base fuzzy search (high quality)
3. Database fuzzy search with suggestions
4. Fallback with typo corrections

**State Management**
- All conversation state in session files
- Shopping cart persisted across interactions
- Context-aware responses based on conversation history
- Automatic learning from successful interactions

### Database Schema Highlights
- Comprehensive product catalog with pricing tiers
- Customer management with credit limits
- Order tracking with detailed item breakdown
- Session analytics and search statistics
- Audit logging for all operations

### Performance Considerations
- Knowledge base cached in memory for speed
- Database queries optimized with proper indexes
- Async message processing prevents timeouts
- Fuzzy search with configurable similarity thresholds
- Session files for lightweight state persistence

## Common Development Tasks

### Adding New Features
1. Define new tool in `llm_interface.py` AVAILABLE_TOOLS
2. Add intent detection logic in LLM prompt
3. Implement tool handler in `app.py` _route_tool function
4. Update session context if needed
5. Add database operations if required

### Debugging Issues
- Check `docker-compose logs -f app` for application logs
- Examine session files in `IA/data/` for state issues
- Use PostgreSQL logs for database problems
- Monitor Ollama connectivity for AI issues

### Modifying AI Behavior
- Edit `IA/ai_llm/gav_prompt.txt` for system instructions and personality
- Use `handle_chitchat` tool for dynamic, personalized responses
- Adjust `generate_personalized_response()` contexts in `llm_interface.py`
- Update knowledge base with `python knowledge/knowledge.py`
- Modify AI temperature and creativity settings for response generation

This is a production-ready WhatsApp commerce assistant with sophisticated natural language processing, persistent learning, and robust error handling.