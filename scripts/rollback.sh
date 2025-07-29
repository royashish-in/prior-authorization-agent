#!/bin/bash

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${ENVIRONMENT:-production}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show deployment history
show_history() {
    log_info "Deployment history:"
    kubectl rollout history deployment/prior-auth-api -n prior-auth
}

# Rollback to specific revision
rollback_to_revision() {
    local revision="$1"
    
    log_warn "Rolling back to revision $revision..."
    
    # Perform rollback
    kubectl rollout undo deployment/prior-auth-api -n prior-auth --to-revision="$revision"
    
    # Wait for rollback to complete
    log_info "Waiting for rollback to complete..."
    kubectl rollout status deployment/prior-auth-api -n prior-auth --timeout=600s
    
    # Verify rollback
    log_info "Verifying rollback..."
    local current_revision=$(kubectl get deployment prior-auth-api -n prior-auth -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
    log_info "Current revision after rollback: $current_revision"
    
    # Health check
    health_check
    
    log_info "Rollback to revision $revision completed successfully"
}

# Rollback to previous revision
rollback_previous() {
    log_warn "Rolling back to previous revision..."
    
    # Get current and previous revisions
    local current_revision=$(kubectl get deployment prior-auth-api -n prior-auth -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
    local previous_revision=$((current_revision - 1))
    
    if [ "$previous_revision" -lt 1 ]; then
        log_error "No previous revision available"
        exit 1
    fi
    
    rollback_to_revision "$previous_revision"
}

# Health check after rollback
health_check() {
    log_info "Performing health check..."
    
    # Wait for pods to be ready
    kubectl wait --for=condition=ready pod -l app=prior-auth-api -n prior-auth --timeout=300s
    
    # Port forward for testing
    kubectl port-forward service/prior-auth-api-service 8080:80 -n prior-auth &
    local port_forward_pid=$!
    
    sleep 5
    
    # Test health endpoint
    if curl -f http://localhost:8080/health; then
        log_info "Health check passed"
    else
        log_error "Health check failed"
        kill $port_forward_pid
        exit 1
    fi
    
    kill $port_forward_pid
}

# Emergency rollback (scales down to 0 and back up)
emergency_rollback() {
    log_warn "Performing emergency rollback..."
    
    # Scale down to 0
    log_info "Scaling down deployment..."
    kubectl scale deployment prior-auth-api -n prior-auth --replicas=0
    
    # Wait for scale down
    kubectl wait --for=delete pod -l app=prior-auth-api -n prior-auth --timeout=300s
    
    # Rollback to previous revision
    rollback_previous
    
    log_info "Emergency rollback completed"
}

# Database rollback (if migrations need to be reverted)
database_rollback() {
    local target_revision="$1"
    
    log_warn "Rolling back database to revision $target_revision..."
    
    # Get a pod name
    local pod_name=$(kubectl get pods -n prior-auth -l app=prior-auth-api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -n "$pod_name" ]; then
        kubectl exec -n prior-auth "$pod_name" -- python -m alembic downgrade "$target_revision"
        log_info "Database rollback completed"
    else
        log_error "No application pods found"
        exit 1
    fi
}

# Main function
main() {
    # Update kubeconfig
    aws eks update-kubeconfig --region "$AWS_REGION" --name "prior-auth-cluster"
    
    case "${1:-help}" in
        "history")
            show_history
            ;;
        "previous")
            rollback_previous
            ;;
        "revision")
            if [ -z "${2:-}" ]; then
                log_error "Please specify revision number"
                exit 1
            fi
            rollback_to_revision "$2"
            ;;
        "emergency")
            emergency_rollback
            ;;
        "database")
            if [ -z "${2:-}" ]; then
                log_error "Please specify target database revision"
                exit 1
            fi
            database_rollback "$2"
            ;;
        "help"|*)
            echo "Usage: $0 [history|previous|revision <num>|emergency|database <revision>]"
            echo ""
            echo "Commands:"
            echo "  history              Show deployment history"
            echo "  previous             Rollback to previous revision"
            echo "  revision <num>       Rollback to specific revision"
            echo "  emergency            Emergency rollback (scale down and rollback)"
            echo "  database <revision>  Rollback database to specific revision"
            exit 1
            ;;
    esac
}

# Trap errors
trap 'log_error "Rollback failed"; exit 1' ERR

main "$@"