# Project Structure & Organization

## Current Structure

```
.kiro/
├── specs/
│   └── prior-authorization-agent/
│       ├── requirements.md    # Detailed system requirements
│       ├── design.md         # System design (empty - to be created)
│       └── tasks.md          # Implementation tasks
└── steering/                 # AI assistant guidance rules
    ├── product.md           # Product overview and purpose
    ├── tech.md              # Technology stack and guidelines
    └── structure.md         # This file - project organization
```

## Project Status
This is a greenfield project in the specification phase. No implementation code exists yet.

## Planned Architecture (Implementation Phase)

### Core Components
- **API Layer**: Request intake, authentication, and response handling
- **Validation Engine**: Medical code validation and policy checking
- **Decision Engine**: Authorization logic and reasoning generation
- **Audit System**: Comprehensive logging and compliance tracking
- **Dashboard**: Provider interface for request management
- **Configuration**: Policy and rule management interface

### Key Modules (Python-based)
- **intake/**: Handle structured authorization requests and data validation
- **validation/**: Medical code validation and policy checking against CMS guidelines
- **decision/**: Authorization logic and reasoning generation with traceable decisions
- **audit/**: Comprehensive logging and compliance tracking
- **notification/**: Real-time alerts and status updates
- **api/**: RESTful endpoints for external system integration
- **config/**: Rule definitions and policy configuration files
- **docs/**: Auto-generated module documentation

## Development Conventions

### File Organization
- Group related functionality into logical modules
- Separate configuration from business logic
- Maintain clear separation between API, business logic, and data layers
- Keep healthcare-specific code isolated for easier compliance auditing

### Documentation Requirements
- All PHI handling code must include security documentation
- API endpoints require comprehensive documentation for integration
- Policy validation logic needs detailed comments referencing specific regulations
- Decision reasoning must be traceable and auditable

### Naming Conventions
- Use healthcare industry standard terminology
- Prefix security-sensitive functions appropriately
- Include medical code types in variable/function names where relevant
- Follow consistent patterns for audit logging functions

### Implementation Guidelines
- Start with core request processing and validation components
- Implement security and audit logging from the beginning
- Build modular components that can be tested independently
- Prioritize HIPAA compliance in all design decisions
- Use Python 3.11+ with proper virtual environment management
- Maintain separate modules for intake, validation, decision engine, and audit logging
- Design for extensibility to support additional healthcare services
- Include comprehensive unit tests with mock data for all business logic