# Prior Authorization Agent

An intelligent healthcare automation system that processes prior authorization requests for outpatient imaging services (MRI, CT scans, X-rays) for US-based healthcare payers.

## Features

- Automated prior authorization workflow processing
- Real-time validation against coverage policies and CMS guidelines
- HIPAA-compliant data handling with AES-256 encryption
- Comprehensive audit logging and compliance reporting
- RESTful API with OAuth 2.0 authentication
- High-performance processing (95% of requests under 2 minutes)
- Scalable architecture supporting 1000+ concurrent requests

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Virtual environment tool (venv, conda, etc.)

### Installation

1. Clone the repository and navigate to the project directory

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration

# For sensitive tokens, create .env.local (already gitignored):
echo "HUGGINGFACE_API_TOKEN=your_actual_token_here" > .env.local
echo "KIRO_CODE=your_actual_kiro_code_here" >> .env.local
```

### Starting the Application

**Backend API Server:**
```bash
# Development mode (recommended)
python -m uvicorn src.main:app --reload --port 8000

# Or using the main module
python -m src.main
```

**Frontend Dashboard:**
```bash
# In a new terminal window
python frontend/serve.py
```

### Access Points

**Backend API:**
- Main API: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs` (Swagger UI)
- Alternative Docs: `http://localhost:8000/redoc`
- Health Check: `http://localhost:8000/api/v1/health`

**Frontend Dashboard:**
- Dashboard: `http://localhost:8080/simple-dashboard.html`
- Login: Use credentials configured in environment variables (see .env.example)
- Default test users: `provider1` / `admin1` (passwords set via environment)

## Health Checks

The application provides several health check endpoints for monitoring:

- `GET /api/v1/health` - Basic health status
- `GET /api/v1/health/detailed` - Comprehensive system status
- `GET /api/v1/health/ready` - Kubernetes readiness probe
- `GET /api/v1/health/live` - Kubernetes liveness probe

## Development

### Running Tests

```bash
pytest tests/ -v --cov=src
```

### Code Formatting

```bash
black src/ tests/
flake8 src/ tests/
```

### Type Checking

```bash
mypy src/
```

## Project Structure

```
├── src/                    # Application source code
│   ├── api/               # API endpoints and routers
│   ├── auth/              # Authentication and authorization
│   ├── core/              # Core configuration and utilities
│   ├── database/          # Database models and connections
│   ├── models/            # Pydantic models
│   ├── services/          # Business logic services
│   └── main.py            # Application entry point
├── tests/                 # Test suite
├── docs/                  # Documentation
├── frontend/              # Web dashboard
├── deployment/            # Docker and Kubernetes configs
├── scripts/               # Utility scripts
├── requirements.txt       # Python dependencies
└── .env.example          # Environment variables template
```

## Security

This application handles Protected Health Information (PHI) and implements:

- AES-256 encryption for data at rest
- TLS 1.3+ for data in transit
- Role-based access controls with proper authorization checks
- Input sanitization to prevent injection attacks
- Secure credential management (no hardcoded passwords)
- Comprehensive audit logging with sanitized inputs
- HIPAA compliance measures

**Security Improvements:**
- Fixed code injection vulnerabilities
- Removed hardcoded credentials
- Added authorization bypass protection
- Implemented log injection prevention

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For technical support and questions, please refer to the documentation in the `docs/` directory.