#!/bin/bash

# Setup script for Prior Authorization Agent testing environment
# This script sets up the necessary environment variables for testing

echo "Setting up Prior Authorization Agent test environment..."

# Export the PHI master key for testing
export PHI_MASTER_KEY="development-phi-master-key-for-testing-purposes-2024"

# Verify the environment is set up correctly
echo "Testing PHI encryption initialization..."
python -c "from src.core.encryption import PHIEncryption; enc = PHIEncryption(); print('✓ PHI Encryption initialized successfully')"

echo "Testing application startup..."
python -c "from src.main import app; print('✓ Application started successfully')"

echo ""
echo "Environment setup complete!"
echo "You can now run tests with: pytest tests/"
echo "Or start the application with: python -m src.main"