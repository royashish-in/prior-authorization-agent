#!/bin/bash
# Test execution scripts for the Prior Authorization System

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Prior Authorization System - Test Runner${NC}"
echo "=================================================="

# Function to run tests with specific markers
run_test_category() {
    local category=$1
    local description=$2
    
    echo -e "\n${YELLOW}Running $description...${NC}"
    if pytest tests/ -m "$category" --tb=short -q; then
        echo -e "${GREEN}✅ $description passed${NC}"
    else
        echo -e "${RED}❌ $description failed${NC}"
        return 1
    fi
}

# Parse command line arguments
case "${1:-all}" in
    "unit")
        run_test_category "unit" "Unit Tests"
        ;;
    "integration")
        run_test_category "integration" "Integration Tests"
        ;;
    "performance")
        run_test_category "performance" "Performance Tests"
        ;;
    "security")
        run_test_category "security" "Security Tests"
        ;;
    "fast")
        echo -e "\n${YELLOW}Running Fast Tests (excluding slow tests)...${NC}"
        pytest tests/ -m "not slow" --tb=short -q
        ;;
    "coverage")
        echo -e "\n${YELLOW}Running Tests with Coverage Report...${NC}"
        pytest tests/ --cov=src --cov-report=html --cov-report=term-missing
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    "all")
        echo -e "\n${YELLOW}Running All Tests...${NC}"
        run_test_category "unit" "Unit Tests"
        run_test_category "integration" "Integration Tests"
        run_test_category "security" "Security Tests"
        echo -e "\n${GREEN}✅ All test categories completed${NC}"
        ;;
    "help")
        echo "Usage: $0 [category]"
        echo ""
        echo "Categories:"
        echo "  unit        - Run unit tests only"
        echo "  integration - Run integration tests only"
        echo "  performance - Run performance tests only"
        echo "  security    - Run security tests only"
        echo "  fast        - Run all tests except slow ones"
        echo "  coverage    - Run tests with coverage report"
        echo "  all         - Run all test categories (default)"
        echo "  help        - Show this help message"
        ;;
    *)
        echo -e "${RED}Unknown category: $1${NC}"
        echo "Use '$0 help' for available options"
        exit 1
        ;;
esac