#!/bin/bash

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_BUCKET="${BACKUP_BUCKET:-prior-auth-backups}"
AWS_REGION="${AWS_REGION:-us-east-1}"
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

# List available backups
list_backups() {
    log_info "Available backups:"
    aws s3 ls "s3://$BACKUP_BUCKET/backups/" --region "$AWS_REGION" | sort -r
}

# Download backup from S3
download_backup() {
    local backup_name="$1"
    local restore_dir="/tmp/restore-$(date +%Y%m%d_%H%M%S)"
    
    log_info "Downloading backup: $backup_name"
    mkdir -p "$restore_dir"
    
    # Download from S3
    aws s3 cp "s3://$BACKUP_BUCKET/backups/$backup_name" "/tmp/$backup_name" --region "$AWS_REGION"
    
    # Extract backup
    tar -xzf "/tmp/$backup_name" -C "$restore_dir"
    
    echo "$restore_dir"
}

# Restore database
restore_database() {
    local restore_dir="$1"
    local db_file=$(find "$restore_dir" -name "database_*.sql.gz" | head -1)
    
    if [ -z "$db_file" ]; then
        log_error "No database backup file found"
        return 1
    fi
    
    log_info "Restoring database from: $(basename "$db_file")"
    
    # Get database pod
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$db_pod" ]; then
        log_error "No PostgreSQL pod found"
        return 1
    fi
    
    # Stop application pods to prevent connections during restore
    log_info "Scaling down application pods..."
    kubectl scale deployment prior-auth-api -n "$NAMESPACE" --replicas=0
    
    # Wait for pods to terminate
    kubectl wait --for=delete pod -l app=prior-auth-api -n "$NAMESPACE" --timeout=300s
    
    # Drop and recreate database
    log_info "Recreating database..."
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -c "DROP DATABASE IF EXISTS prior_auth;"
    kubectl exec -n "$NAMESPACE" "$db_pod" -- psql -U postgres -c "CREATE DATABASE prior_auth;"
    
    # Restore database
    log_info "Restoring database data..."
    gunzip -c "$db_file" | kubectl exec -i -n "$NAMESPACE" "$db_pod" -- psql -U postgres -d prior_auth
    
    # Scale application back up
    log_info "Scaling up application pods..."
    kubectl scale deployment prior-auth-api -n "$NAMESPACE" --replicas=3
    
    # Wait for pods to be ready
    kubectl wait --for=condition=available deployment/prior-auth-api -n "$NAMESPACE" --timeout=600s
    
    log_info "Database restore completed successfully"
}

# Restore Redis data
restore_redis() {
    local restore_dir="$1"
    local redis_file=$(find "$restore_dir" -name "redis_*.rdb.gz" | head -1)
    
    if [ -z "$redis_file" ]; then
        log_error "No Redis backup file found"
        return 1
    fi
    
    log_info "Restoring Redis from: $(basename "$redis_file")"
    
    # Get Redis pod
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$redis_pod" ]; then
        log_error "No Redis pod found"
        return 1
    fi
    
    # Stop Redis
    log_info "Stopping Redis service..."
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli SHUTDOWN NOSAVE || true
    
    # Wait a moment for shutdown
    sleep 5
    
    # Copy backup file to pod
    gunzip -c "$redis_file" > "/tmp/dump.rdb"
    kubectl cp "/tmp/dump.rdb" "$NAMESPACE/$redis_pod:/data/dump.rdb"
    
    # Restart Redis pod
    log_info "Restarting Redis pod..."
    kubectl delete pod -n "$NAMESPACE" "$redis_pod"
    
    # Wait for new pod to be ready
    kubectl wait --for=condition=ready pod -l app=redis -n "$NAMESPACE" --timeout=300s
    
    # Clean up
    rm -f "/tmp/dump.rdb"
    
    log_info "Redis restore completed successfully"
}

# Restore Kubernetes configurations
restore_k8s_configs() {
    local restore_dir="$1"
    local k8s_dir="$restore_dir/k8s-configs"
    
    if [ ! -d "$k8s_dir" ]; then
        log_error "No Kubernetes configuration backup found"
        return 1
    fi
    
    log_info "Restoring Kubernetes configurations..."
    
    # Apply configurations (excluding secrets for security)
    if [ -f "$k8s_dir/configmaps.yaml" ]; then
        kubectl apply -f "$k8s_dir/configmaps.yaml"
    fi
    
    if [ -f "$k8s_dir/persistent-volumes.yaml" ]; then
        kubectl apply -f "$k8s_dir/persistent-volumes.yaml"
    fi
    
    if [ -f "$k8s_dir/ingress.yaml" ]; then
        kubectl apply -f "$k8s_dir/ingress.yaml"
    fi
    
    if [ -f "$k8s_dir/hpa.yaml" ]; then
        kubectl apply -f "$k8s_dir/hpa.yaml"
    fi
    
    log_info "Kubernetes configurations restored successfully"
}

# Verify system health after restore
verify_restore() {
    log_info "Verifying system health after restore..."
    
    # Check pod status
    log_info "Checking pod status..."
    kubectl get pods -n "$NAMESPACE"
    
    # Wait for all pods to be ready
    kubectl wait --for=condition=ready pod -l app=prior-auth-api -n "$NAMESPACE" --timeout=300s
    kubectl wait --for=condition=ready pod -l app=postgres -n "$NAMESPACE" --timeout=300s
    kubectl wait --for=condition=ready pod -l app=redis -n "$NAMESPACE" --timeout=300s
    
    # Test database connectivity
    log_info "Testing database connectivity..."
    local db_pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n "$NAMESPACE" "$db_pod" -- pg_isready -U postgres
    
    # Test Redis connectivity
    log_info "Testing Redis connectivity..."
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli ping
    
    # Test application health endpoint
    log_info "Testing application health..."
    kubectl port-forward service/prior-auth-api-service 8080:80 -n "$NAMESPACE" &
    local port_forward_pid=$!
    
    sleep 10
    
    if curl -f http://localhost:8080/health; then
        log_info "Application health check passed"
    else
        log_error "Application health check failed"
        kill $port_forward_pid
        return 1
    fi
    
    kill $port_forward_pid
    
    log_info "System health verification completed successfully"
}

# Full disaster recovery
full_recovery() {
    local backup_name="$1"
    
    log_info "Starting full disaster recovery with backup: $backup_name"
    
    # Download and extract backup
    local restore_dir=$(download_backup "$backup_name")
    
    # Restore components
    restore_database "$restore_dir"
    restore_redis "$restore_dir"
    restore_k8s_configs "$restore_dir"
    
    # Verify system health
    verify_restore
    
    # Clean up
    rm -rf "$restore_dir"
    rm -f "/tmp/$backup_name"
    
    log_info "Full disaster recovery completed successfully"
}

# Point-in-time recovery
point_in_time_recovery() {
    local target_time="$1"
    
    log_info "Starting point-in-time recovery to: $target_time"
    
    # Find the closest backup before the target time
    local backup_name=$(aws s3 ls "s3://$BACKUP_BUCKET/backups/" --region "$AWS_REGION" | \
        awk -v target="$target_time" '$1 " " $2 < target {print $4}' | \
        sort -r | head -1)
    
    if [ -z "$backup_name" ]; then
        log_error "No backup found before target time: $target_time"
        return 1
    fi
    
    log_info "Using backup: $backup_name for point-in-time recovery"
    full_recovery "$backup_name"
}

# Create emergency maintenance page
enable_maintenance_mode() {
    log_info "Enabling maintenance mode..."
    
    # Create maintenance page deployment
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: maintenance-page
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: maintenance-page
  template:
    metadata:
      labels:
        app: maintenance-page
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        volumeMounts:
        - name: maintenance-html
          mountPath: /usr/share/nginx/html
      volumes:
      - name: maintenance-html
        configMap:
          name: maintenance-page-config
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-page-config
  namespace: $NAMESPACE
data:
  index.html: |
    <!DOCTYPE html>
    <html>
    <head>
        <title>System Maintenance</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; margin-top: 100px; }
            .container { max-width: 600px; margin: 0 auto; }
            h1 { color: #333; }
            p { color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>System Under Maintenance</h1>
            <p>The Prior Authorization system is currently undergoing maintenance.</p>
            <p>We apologize for any inconvenience and will be back online shortly.</p>
            <p>For urgent matters, please contact support.</p>
        </div>
    </body>
    </html>
---
apiVersion: v1
kind: Service
metadata:
  name: maintenance-page-service
  namespace: $NAMESPACE
spec:
  selector:
    app: maintenance-page
  ports:
  - port: 80
    targetPort: 80
EOF
    
    # Update ingress to point to maintenance page
    kubectl patch ingress prior-auth-ingress -n "$NAMESPACE" --type='json' \
        -p='[{"op": "replace", "path": "/spec/rules/0/http/paths/0/backend/service/name", "value": "maintenance-page-service"}]'
    
    log_info "Maintenance mode enabled"
}

# Disable maintenance mode
disable_maintenance_mode() {
    log_info "Disabling maintenance mode..."
    
    # Restore ingress to point to application
    kubectl patch ingress prior-auth-ingress -n "$NAMESPACE" --type='json' \
        -p='[{"op": "replace", "path": "/spec/rules/0/http/paths/0/backend/service/name", "value": "prior-auth-api-service"}]'
    
    # Remove maintenance page resources
    kubectl delete deployment maintenance-page -n "$NAMESPACE" || true
    kubectl delete service maintenance-page-service -n "$NAMESPACE" || true
    kubectl delete configmap maintenance-page-config -n "$NAMESPACE" || true
    
    log_info "Maintenance mode disabled"
}

# Main function
main() {
    case "${1:-help}" in
        "list")
            list_backups
            ;;
        "restore")
            if [ -z "${2:-}" ]; then
                log_error "Please specify backup name"
                exit 1
            fi
            full_recovery "$2"
            ;;
        "point-in-time")
            if [ -z "${2:-}" ]; then
                log_error "Please specify target time (YYYY-MM-DD HH:MM:SS)"
                exit 1
            fi
            point_in_time_recovery "$2"
            ;;
        "database")
            if [ -z "${2:-}" ]; then
                log_error "Please specify backup name"
                exit 1
            fi
            local restore_dir=$(download_backup "$2")
            restore_database "$restore_dir"
            rm -rf "$restore_dir"
            ;;
        "redis")
            if [ -z "${2:-}" ]; then
                log_error "Please specify backup name"
                exit 1
            fi
            local restore_dir=$(download_backup "$2")
            restore_redis "$restore_dir"
            rm -rf "$restore_dir"
            ;;
        "maintenance-on")
            enable_maintenance_mode
            ;;
        "maintenance-off")
            disable_maintenance_mode
            ;;
        "verify")
            verify_restore
            ;;
        "help"|*)
            echo "Usage: $0 [list|restore <backup>|point-in-time <time>|database <backup>|redis <backup>|maintenance-on|maintenance-off|verify]"
            echo ""
            echo "Commands:"
            echo "  list                    List available backups"
            echo "  restore <backup>        Full system restore from backup"
            echo "  point-in-time <time>    Point-in-time recovery (YYYY-MM-DD HH:MM:SS)"
            echo "  database <backup>       Restore only database from backup"
            echo "  redis <backup>          Restore only Redis from backup"
            echo "  maintenance-on          Enable maintenance mode"
            echo "  maintenance-off         Disable maintenance mode"
            echo "  verify                  Verify system health"
            exit 1
            ;;
    esac
}

# Trap errors
trap 'log_error "Disaster recovery failed"; exit 1' ERR

main "$@"