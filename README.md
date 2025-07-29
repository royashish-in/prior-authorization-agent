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
```

5. Run the application:
```bash
python -m src.main
```

The API will be available at `http://localhost:8000`

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

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
│   ├── core/              # Core configuration and utilities
│   └── main.py            # Application entry point
├── tests/                 # Test suite
├── docs/                  # Documentation
├── config/                # Configuration files
├── requirements.txt       # Python dependencies
└── .env.example          # Environment variables template
```

## Security

This application handles Protected Health Information (PHI) and implements:

- AES-256 encryption for data at rest
- TLS 1.3+ for data in transit
- Role-based access controls
- Comprehensive audit logging
- HIPAA compliance measures

## License

This project is proprietary software for healthcare automation.

## Support

For technical support and questions, please refer to the documentation in the `docs/` directory.