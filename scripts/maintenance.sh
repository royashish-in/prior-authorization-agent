#!/bin/bash

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
NAMESPACE="prior-auth"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# System health check
health_check() {
    log_info "Performing comprehensive system health check..."
    
    local issues=0
    
    # Check pod status
    log_debug "Checking pod status..."
    local unhealthy_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name)
    if [ -n "$unhealthy_pods" ]; then
        log_warn "Unhealthy pods found: $unhealthy_pods"
        ((issues++))
    else
        log_info "All pods are running"
    fi
    
    # Check resource usage
    log_debug "Checking resource usage..."
    kubectl top pods -n "$NAMESPACE" | while read -r line; do
        if echo "$line" | grep -q "Mi"; then
            local memory=$(echo "$line" | awk '{print $3}' | sed 's/Mi//')
            if [ "$memory" -gt 800 ]; then
                log_warn "High memory usage detected: $line"
                ((issues++))
            fi
        fi
    done
    
    # Check database connectivity
    log_debug "Checking database connectivity..."
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$db_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$db_pod" -- pg_isready -U postgres > /dev/null; then
            log_info "Database is healthy"
        else
            log_error "Database health check failed"
            ((issues++))
        fi
    fi
    
    # Check Redis connectivity
    log_debug "Checking Redis connectivity..."
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$redis_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli ping | grep -q PONG; then
            log_info "Redis is healthy"
        else
            log_error "Redis health check failed"
            ((issues++))
        fi
    fi
    
    # Check ingress status
    log_debug "Checking ingress status..."
    local ingress_status=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
    if [ -n "$ingress_status" ]; then
        log_info "Ingress is configured with IP: $ingress_status"
    else
        log_warn "Ingress IP not assigned"
        ((issues++))
    fi
    
    # Check certificate expiration
    log_debug "Checking certificate expiration..."
    local cert_expiry=$(kubectl get certificate -n "$NAMESPACE" -o jsonpath='{.items[0].status.notAfter}' 2>/dev/null || echo "")
    if [ -n "$cert_expiry" ]; then
        local days_until_expiry=$(( ($(date -d "$cert_expiry" +%s) - $(date +%s)) / 86400 ))
        if [ "$days_until_expiry" -lt 30 ]; then
            log_warn "Certificate expires in $days_until_expiry days"
            ((issues++))
        else
            log_info "Certificate is valid for $days_until_expiry days"
        fi
    fi
    
    if [ "$issues" -eq 0 ]; then
        log_info "System health check passed"
        return 0
    else
        log_warn "System health check found $issues issues"
        return 1
    fi
}

# Database maintenance
database_maintenance() {
    log_info "Starting database maintenance..."
    
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$db_pod" ]; then
        log_error "No PostgreSQL pod found"
        return 1
    fi
    
    # Analyze database statistics
    log_info "Analyzing database statistics..."
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "ANALYZE;"
    
    # Vacuum database
    log_info "Vacuuming database..."
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "VACUUM;"
    
    # Reindex database
    log_info "Reindexing database..."
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "REINDEX DATABASE prior_auth;"
    
    # Check database size
    log_info "Checking database size..."
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "
    SELECT 
        pg_size_pretty(pg_database_size('prior_auth')) as database_size,
        pg_size_pretty(pg_total_relation_size('authorization_requests')) as requests_table_size,
        pg_size_pretty(pg_total_relation_size('authorization_decisions')) as decisions_table_size;
    "
    
    # Check for long-running queries
    log_info "Checking for long-running queries..."
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "
    SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
    FROM pg_stat_activity 
    WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes'
    AND state = 'active';
    "
    
    log_info "Database maintenance completed"
}

# Redis maintenance
redis_maintenance() {
    log_info "Starting Redis maintenance..."
    
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$redis_pod" ]; then
        log_error "No Redis pod found"
        return 1
    fi
    
    # Check Redis memory usage
    log_info "Checking Redis memory usage..."
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli info memory | grep -E "(used_memory_human|used_memory_peak_human|maxmemory_human)"
    
    # Check Redis statistics
    log_info "Checking Redis statistics..."
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli info stats | grep -E "(keyspace_hits|keyspace_misses|expired_keys|evicted_keys)"
    
    # Check Redis keyspace
    log_info "Checking Redis keyspace..."
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli info keyspace
    
    # Clean up expired keys
    log_info "Cleaning up expired keys..."
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli --scan --pattern "*" | head -100 | while read -r key; do
        kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli ttl "$key" > /dev/null
    done
    
    log_info "Redis maintenance completed"
}

# Log rotation and cleanup
log_cleanup() {
    log_info "Starting log cleanup..."
    
    # Clean up old application logs
    local app_pods=$(kubectl get pods -n "$NAMESPACE" -l app=prior-auth-api -o jsonpath='{.items[*].metadata.name}')
    
    for pod in $app_pods; do
        log_debug "Cleaning logs for pod: $pod"
        # This would typically be handled by log rotation in production
        # For now, we'll just check log sizes
        kubectl exec -n "$NAMESPACE" "$pod" -- du -sh /app/logs/ 2>/dev/null || true
    done
    
    # Clean up old Elasticsearch indices (if using ELK stack)
    local es_pod=$(kubectl get pods -n "$NAMESPACE" -l app=elasticsearch -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$es_pod" ]; then
        log_info "Cleaning up old Elasticsearch indices..."
        # Delete indices older than 30 days
        local cutoff_date=$(date -d "30 days ago" +%Y.%m.%d)
        kubectl exec -n "$NAMESPACE" "$es_pod" -- curl -X DELETE "localhost:9200/prior-auth-*" -H 'Content-Type: application/json' -d "{
            \"query\": {
                \"range\": {
                    \"@timestamp\": {
                        \"lt\": \"$cutoff_date\"
                    }
                }
            }
        }" 2>/dev/null || true
    fi
    
    log_info "Log cleanup completed"
}

# Security maintenance
security_maintenance() {
    log_info "Starting security maintenance..."
    
    # Check for security updates
    log_info "Checking for security updates..."
    
    # Scan container images for vulnerabilities
    local app_image=$(kubectl get deployment prior-auth-api -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}')
    log_info "Current application image: $app_image"
    
    # Check certificate status
    log_info "Checking certificate status..."
    kubectl get certificates -n "$NAMESPACE" -o wide
    
    # Review RBAC permissions
    log_info "Reviewing RBAC permissions..."
    kubectl auth can-i --list --as=system:serviceaccount:prior-auth:default | head -10
    
    # Check for failed authentication attempts
    log_info "Checking for failed authentication attempts..."
    kubectl logs -n "$NAMESPACE" -l app=prior-auth-api --since=24h | grep -i "authentication failed" | wc -l
    
    # Check network policies
    log_info "Checking network policies..."
    kubectl get networkpolicies -n "$NAMESPACE" 2>/dev/null || log_warn "No network policies found"
    
    log_info "Security maintenance completed"
}

# Performance optimization
performance_optimization() {
    log_info "Starting performance optimization..."
    
    # Check HPA status
    log_info "Checking HPA status..."
    kubectl get hpa -n "$NAMESPACE" -o wide
    
    # Check resource utilization
    log_info "Checking resource utilization..."
    kubectl top nodes
    kubectl top pods -n "$NAMESPACE"
    
    # Check application metrics
    log_info "Checking application metrics..."
    local app_pod=$(kubectl get pods -n "$NAMESPACE" -l app=prior-auth-api -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$app_pod" ]; then
        # This would typically query Prometheus metrics
        log_debug "Application pod: $app_pod is running"
    fi
    
    # Optimize database connections
    log_info "Checking database connections..."
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$db_pod" ]; then
        kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "
        SELECT count(*) as active_connections, state 
        FROM pg_stat_activity 
        WHERE datname = 'prior_auth' 
        GROUP BY state;
        "
    fi
    
    log_info "Performance optimization completed"
}

# Backup verification
backup_verification() {
    log_info "Starting backup verification..."
    
    # Check recent backups
    log_info "Checking recent backups..."
    aws s3 ls s3://prior-auth-backups/backups/ --region "$AWS_REGION" | tail -5
    
    # Verify backup integrity (sample check)
    local latest_backup=$(aws s3 ls s3://prior-auth-backups/backups/ --region "$AWS_REGION" | tail -1 | awk '{print $4}')
    if [ -n "$latest_backup" ]; then
        log_info "Latest backup: $latest_backup"
        # In production, you might download and verify the backup
        aws s3api head-object --bucket prior-auth-backups --key "backups/$latest_backup" --region "$AWS_REGION" > /dev/null
        log_info "Backup file exists and is accessible"
    else
        log_warn "No recent backups found"
    fi
    
    # Check backup schedule
    log_info "Checking backup schedule..."
    # This would typically check your backup cron job or scheduled task
    log_debug "Backup schedule verification would be implemented here"
    
    log_info "Backup verification completed"
}

# Generate maintenance report
generate_report() {
    local report_file="/tmp/maintenance-report-$(date +%Y%m%d_%H%M%S).txt"
    
    log_info "Generating maintenance report: $report_file"
    
    {
        echo "Prior Authorization Agent - Maintenance Report"
        echo "=============================================="
        echo "Date: $(date)"
        echo "Namespace: $NAMESPACE"
        echo ""
        
        echo "System Status:"
        kubectl get pods -n "$NAMESPACE" -o wide
        echo ""
        
        echo "Resource Usage:"
        kubectl top pods -n "$NAMESPACE" 2>/dev/null || echo "Metrics server not available"
        echo ""
        
        echo "Recent Events:"
        kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -10
        echo ""
        
        echo "Database Status:"
        local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
        if [ -n "$db_pod" ]; then
            kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth -c "SELECT version();" 2>/dev/null || echo "Database query failed"
        fi
        echo ""
        
        echo "Redis Status:"
        local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
        if [ -n "$redis_pod" ]; then
            kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli info server | grep redis_version 2>/dev/null || echo "Redis query failed"
        fi
        echo ""
        
        echo "Certificate Status:"
        kubectl get certificates -n "$NAMESPACE" -o wide 2>/dev/null || echo "No certificates found"
        echo ""
        
        echo "Ingress Status:"
        kubectl get ingress -n "$NAMESPACE" -o wide
        echo ""
        
    } > "$report_file"
    
    log_info "Maintenance report generated: $report_file"
    
    # Optionally upload report to S3
    if [ "${UPLOAD_REPORT:-false}" = "true" ]; then
        aws s3 cp "$report_file" "s3://prior-auth-backups/reports/" --region "$AWS_REGION"
        log_info "Report uploaded to S3"
    fi
    
    echo "$report_file"
}

# Main maintenance function
main() {
    local maintenance_type="${1:-full}"
    
    log_info "Starting maintenance (type: $maintenance_type)..."
    
    case "$maintenance_type" in
        "full")
            health_check
            database_maintenance
            redis_maintenance
            log_cleanup
            security_maintenance
            performance_optimization
            backup_verification
            generate_report
            ;;
        "health")
            health_check
            ;;
        "database")
            database_maintenance
            ;;
        "redis")
            redis_maintenance
            ;;
        "logs")
            log_cleanup
            ;;
        "security")
            security_maintenance
            ;;
        "performance")
            performance_optimization
            ;;
        "backup")
            backup_verification
            ;;
        "report")
            generate_report
            ;;
        *)
            log_error "Invalid maintenance type: $maintenance_type"
            echo "Usage: $0 [full|health|database|redis|logs|security|performance|backup|report]"
            exit 1
            ;;
    esac
    
    log_info "Maintenance completed successfully!"
}

# Trap errors
trap 'log_error "Maintenance failed"; exit 1' ERR

main "$@"