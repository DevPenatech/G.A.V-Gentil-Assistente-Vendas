# G.A.V. (Gentil Assistente de Vendas)

## Project Overview

G.A.V. is a sophisticated, AI-powered sales assistant designed to interact with customers via WhatsApp. It is built with Python using the Flask framework and integrates with multiple services to provide a comprehensive and intelligent user experience.

### Core Technologies:
- **Backend:** Python (Flask)
- **Database:** PostgreSQL
- **Caching:** Redis
- **AI/LLM:** Ollama
- **Messaging:** Twilio & Vonage for WhatsApp integration
- **Containerization:** Docker

### Architecture:
The application is designed to run in a containerized environment using Docker. It consists of three main services:
1.  **`app`:** The main Flask application that handles business logic, user interactions, and communication with other services.
2.  **`db`:** A PostgreSQL database for storing product information, customer data, and order history.
3.  **`redis`:** A Redis instance for session management and caching.

The system is designed to be highly modular, with separate components for handling AI interactions, database operations, and communication with external services.

## Building and Running

### Prerequisites:
- Docker
- Docker Compose

### Environment Setup:
1.  Create a `.env` file in the root directory with the necessary environment variables (see `CLAUDE.md` for a detailed list).
2.  Run the following command to start all services:
    ```bash
    docker-compose up -d
    ```

### Key Commands:
- **Start all services:** `docker-compose up -d`
- **View application logs:** `docker-compose logs -f app`
- **Stop all services:** `docker-compose down`
- **Rebuild the application:** `docker-compose up --build`

## Development Conventions

### AI Interaction:
The project is moving towards a structured JSON-based communication protocol between the AI and the core application. This approach, as outlined in `Atualizacao.md`, allows for a clear separation between the AI's conversational abilities and the system's need for structured data.

### Database:
The database schema is well-defined and documented in `init.sql`. It includes tables for products, customers, orders, and various other data points required for the application's functionality. The use of comments and clear naming conventions is encouraged.

### Code Structure:
The application is organized into several directories, each with a specific purpose:
- **`IA/`**: The main application directory.
  - **`ai_llm/`**: Handles all interactions with the Ollama language model.
  - **`communication/`**: Manages communication with Twilio and Vonage.
  - **`core/`**: Contains core application logic, such as session management.
  - **`data/`**: Stores session data.
  - **`db/`**: Manages all database interactions.
  - **`knowledge/`**: Contains the knowledge base for the AI.
  - **`logs/`**: Stores application logs.
  - **`scripts/`**: Contains various scripts for development and maintenance.
  - **`utils/`**: Contains utility functions used throughout the application.
