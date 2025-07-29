#!/bin/bash

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_BUCKET="${BACKUP_BUCKET:-prior-auth-backups}"
AWS_REGION="${AWS_REGION:-us-east-1}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
NAMESPACE="prior-auth"

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

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/prior-auth-backup-$TIMESTAMP"

# Create backup directory
create_backup_dir() {
    log_info "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
}

# Backup PostgreSQL database
backup_database() {
    log_info "Starting database backup..."
    
    # Get database pod
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$db_pod" ]; then
        log_error "No PostgreSQL pod found"
        return 1
    fi
    
    # Create database dump
    log_info "Creating database dump from pod: $db_pod"
    kubectl exec -n "$NAMESPACE" "$db_pod" -- pg_dump -U postgres -d prior_auth --no-password > "$BACKUP_DIR/database_$TIMESTAMP.sql"
    
    # Compress the dump
    gzip "$BACKUP_DIR/database_$TIMESTAMP.sql"
    
    log_info "Database backup completed: database_$TIMESTAMP.sql.gz"
}

# Backup Redis data
backup_redis() {
    log_info "Starting Redis backup..."
    
    # Get Redis pod
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$redis_pod" ]; then
        log_error "No Redis pod found"
        return 1
    fi
    
    # Create Redis backup
    log_info "Creating Redis backup from pod: $redis_pod"
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli BGSAVE
    
    # Wait for backup to complete
    sleep 5
    
    # Copy dump file
    kubectl cp "$NAMESPACE/$redis_pod:/data/dump.rdb" "$BACKUP_DIR/redis_$TIMESTAMP.rdb"
    
    # Compress the dump
    gzip "$BACKUP_DIR/redis_$TIMESTAMP.rdb"
    
    log_info "Redis backup completed: redis_$TIMESTAMP.rdb.gz"
}

# Backup Kubernetes configurations
backup_k8s_configs() {
    log_info "Starting Kubernetes configuration backup..."
    
    local k8s_backup_dir="$BACKUP_DIR/k8s-configs"
    mkdir -p "$k8s_backup_dir"
    
    # Backup all resources in the namespace
    kubectl get all -n "$NAMESPACE" -o yaml > "$k8s_backup_dir/all-resources.yaml"
    kubectl get configmaps -n "$NAMESPACE" -o yaml > "$k8s_backup_dir/configmaps.yaml"
    kubectl get secrets -n "$NAMESPACE" -o yaml > "$k8s_backup_dir/secrets.yaml"
    kubectl get pvc -n "$NAMESPACE" -o yaml > "$k8s_backup_dir/persistent-volumes.yaml"
    kubectl get ingress -n "$NAMESPACE" -o yaml > "$k8s_backup_dir/ingress.yaml"
    
    # Backup HPA configurations
    kubectl get hpa -n "$NAMESPACE" -o yaml > "$k8s_backup_dir/hpa.yaml" 2>/dev/null || true
    
    log_info "Kubernetes configuration backup completed"
}

# Backup application logs
backup_logs() {
    log_info "Starting application logs backup..."
    
    local logs_backup_dir="$BACKUP_DIR/logs"
    mkdir -p "$logs_backup_dir"
    
    # Get application pods
    local app_pods=$(kubectl get pods -n "$NAMESPACE" -l app=prior-auth-api -o jsonpath='{.items[*].metadata.name}')
    
    for pod in $app_pods; do
        log_info "Backing up logs from pod: $pod"
        kubectl logs -n "$NAMESPACE" "$pod" --previous > "$logs_backup_dir/${pod}_previous.log" 2>/dev/null || true
        kubectl logs -n "$NAMESPACE" "$pod" > "$logs_backup_dir/${pod}_current.log" 2>/dev/null || true
    done
    
    # Compress logs
    tar -czf "$BACKUP_DIR/logs_$TIMESTAMP.tar.gz" -C "$logs_backup_dir" .
    rm -rf "$logs_backup_dir"
    
    log_info "Application logs backup completed"
}

# Upload backup to S3
upload_to_s3() {
    log_info "Uploading backup to S3..."
    
    # Create archive
    local archive_name="prior-auth-backup-$TIMESTAMP.tar.gz"
    tar -czf "/tmp/$archive_name" -C "$BACKUP_DIR" .
    
    # Upload to S3
    aws s3 cp "/tmp/$archive_name" "s3://$BACKUP_BUCKET/backups/$archive_name" --region "$AWS_REGION"
    
    # Verify upload
    if aws s3 ls "s3://$BACKUP_BUCKET/backups/$archive_name" --region "$AWS_REGION" > /dev/null; then
        log_info "Backup successfully uploaded to S3: s3://$BACKUP_BUCKET/backups/$archive_name"
    else
        log_error "Failed to upload backup to S3"
        return 1
    fi
    
    # Clean up local files
    rm -f "/tmp/$archive_name"
}

# Clean up old backups
cleanup_old_backups() {
    log_info "Cleaning up backups older than $RETENTION_DAYS days..."
    
    # Calculate cutoff date
    local cutoff_date=$(date -d "$RETENTION_DAYS days ago" +%Y%m%d)
    
    # List and delete old backups
    aws s3 ls "s3://$BACKUP_BUCKET/backups/" --region "$AWS_REGION" | while read -r line; do
        local backup_date=$(echo "$line" | awk '{print $4}' | grep -o '[0-9]\{8\}' | head -1)
        if [ -n "$backup_date" ] && [ "$backup_date" -lt "$cutoff_date" ]; then
            local backup_file=$(echo "$line" | awk '{print $4}')
            log_info "Deleting old backup: $backup_file"
            aws s3 rm "s3://$BACKUP_BUCKET/backups/$backup_file" --region "$AWS_REGION"
        fi
    done
    
    log_info "Old backup cleanup completed"
}

# Send notification
send_notification() {
    local status="$1"
    local message="$2"
    
    # This is a placeholder for notification logic
    # You can integrate with SNS, Slack, email, etc.
    log_info "Notification: $status - $message"
    
    # Example SNS notification (uncomment and configure as needed)
    # aws sns publish --topic-arn "arn:aws:sns:$AWS_REGION:123456789012:backup-notifications" \
    #     --message "$message" --subject "Prior Auth Backup $status" --region "$AWS_REGION"
}

# Health check before backup
health_check() {
    log_info "Performing health check before backup..."
    
    # Check if all pods are running
    local unhealthy_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name)
    if [ -n "$unhealthy_pods" ]; then
        log_warn "Some pods are not running: $unhealthy_pods"
    fi
    
    # Check database connectivity
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$db_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$db_pod" -- pg_isready -U postgres > /dev/null; then
            log_info "Database is healthy"
        else
            log_error "Database health check failed"
            return 1
        fi
    fi
    
    # Check Redis connectivity
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$redis_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli ping | grep -q PONG; then
            log_info "Redis is healthy"
        else
            log_error "Redis health check failed"
            return 1
        fi
    fi
    
    log_info "Health check completed successfully"
}

# Main backup function
main() {
    local backup_type="${1:-full}"
    
    log_info "Starting backup process (type: $backup_type)..."
    
    # Perform health check
    if ! health_check; then
        send_notification "FAILED" "Backup failed during health check"
        exit 1
    fi
    
    # Create backup directory
    create_backup_dir
    
    case "$backup_type" in
        "full")
            backup_database
            backup_redis
            backup_k8s_configs
            backup_logs
            ;;
        "database")
            backup_database
            ;;
        "redis")
            backup_redis
            ;;
        "configs")
            backup_k8s_configs
            ;;
        "logs")
            backup_logs
            ;;
        *)
            log_error "Invalid backup type: $backup_type"
            echo "Usage: $0 [full|database|redis|configs|logs]"
            exit 1
            ;;
    esac
    
    # Upload to S3
    upload_to_s3
    
    # Clean up old backups
    cleanup_old_backups
    
    # Clean up local backup directory
    rm -rf "$BACKUP_DIR"
    
    send_notification "SUCCESS" "Backup completed successfully: prior-auth-backup-$TIMESTAMP.tar.gz"
    log_info "Backup process completed successfully!"
}

# Trap errors
trap 'log_error "Backup failed"; send_notification "FAILED" "Backup process failed"; exit 1' ERR

main "$@"