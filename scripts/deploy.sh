#!/bin/bash

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${ENVIRONMENT:-production}"
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-prior-auth-api}"

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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    fi
    
    if ! command -v kubectl &> /dev/null; then
        missing_tools+=("kubectl")
    fi
    
    if ! command -v aws &> /dev/null; then
        missing_tools+=("aws")
    fi
    
    if ! command -v terraform &> /dev/null; then
        missing_tools+=("terraform")
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Build and push Docker image
build_and_push_image() {
    log_info "Building and pushing Docker image..."
    
    cd "$PROJECT_ROOT"
    
    # Get ECR login token
    aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    # Build image
    local image_tag="latest"
    if [ -n "${GITHUB_SHA:-}" ]; then
        image_tag="$GITHUB_SHA"
    fi
    
    local image_uri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${image_tag}"
    
    log_info "Building image: $image_uri"
    docker build -t "$image_uri" .
    
    # Push image
    log_info "Pushing image: $image_uri"
    docker push "$image_uri"
    
    # Tag as latest
    docker tag "$image_uri" "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:latest"
    docker push "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:latest"
    
    echo "$image_uri" > /tmp/image_uri
    log_info "Image built and pushed successfully"
}

# Deploy infrastructure with Terraform
deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd "$PROJECT_ROOT/deployment/terraform"
    
    # Initialize Terraform
    terraform init
    
    # Plan deployment
    terraform plan -var="environment=$ENVIRONMENT" -out=tfplan
    
    # Apply deployment
    terraform apply tfplan
    
    # Get outputs
    terraform output -json > /tmp/terraform_outputs.json
    
    log_info "Infrastructure deployed successfully"
}

# Update kubeconfig
update_kubeconfig() {
    log_info "Updating kubeconfig..."
    
    local cluster_name="prior-auth-cluster"
    aws eks update-kubeconfig --region "$AWS_REGION" --name "$cluster_name"
    
    log_info "Kubeconfig updated successfully"
}

# Deploy to Kubernetes
deploy_to_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    cd "$PROJECT_ROOT"
    
    # Apply namespace first
    kubectl apply -f deployment/k8s/namespace.yaml
    
    # Apply secrets and configmaps
    kubectl apply -f deployment/k8s/secrets.yaml
    kubectl apply -f deployment/k8s/configmap.yaml
    
    # Deploy database and Redis
    kubectl apply -f deployment/k8s/postgres-deployment.yaml
    kubectl apply -f deployment/k8s/redis-deployment.yaml
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    kubectl wait --for=condition=ready pod -l app=postgres -n prior-auth --timeout=300s
    
    # Wait for Redis to be ready
    log_info "Waiting for Redis to be ready..."
    kubectl wait --for=condition=ready pod -l app=redis -n prior-auth --timeout=300s
    
    # Update image in deployment
    if [ -f /tmp/image_uri ]; then
        local image_uri=$(cat /tmp/image_uri)
        sed -i "s|image: prior-auth-api:latest|image: $image_uri|g" deployment/k8s/app-deployment.yaml
    fi
    
    # Deploy application
    kubectl apply -f deployment/k8s/app-deployment.yaml
    
    # Deploy ingress
    kubectl apply -f deployment/k8s/ingress.yaml
    
    # Wait for deployment to be ready
    log_info "Waiting for application deployment to be ready..."
    kubectl wait --for=condition=available deployment/prior-auth-api -n prior-auth --timeout=600s
    
    log_info "Kubernetes deployment completed successfully"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Get a pod name
    local pod_name=$(kubectl get pods -n prior-auth -l app=prior-auth-api -o jsonpath='{.items[0].metadata.name}')
    
    if [ -n "$pod_name" ]; then
        kubectl exec -n prior-auth "$pod_name" -- python -m alembic upgrade head
        log_info "Database migrations completed successfully"
    else
        log_error "No application pods found"
        exit 1
    fi
}

# Health check
health_check() {
    log_info "Performing health check..."
    
    # Get service endpoint
    local service_ip=$(kubectl get service prior-auth-api-service -n prior-auth -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    
    if [ -z "$service_ip" ]; then
        service_ip=$(kubectl get service prior-auth-api-service -n prior-auth -o jsonpath='{.spec.clusterIP}')
    fi
    
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

# Rollback function
rollback() {
    log_warn "Rolling back deployment..."
    
    # Get previous revision
    local previous_revision=$(kubectl rollout history deployment/prior-auth-api -n prior-auth | tail -2 | head -1 | awk '{print $1}')
    
    if [ -n "$previous_revision" ]; then
        kubectl rollout undo deployment/prior-auth-api -n prior-auth --to-revision="$previous_revision"
        kubectl rollout status deployment/prior-auth-api -n prior-auth
        log_info "Rollback completed successfully"
    else
        log_error "No previous revision found for rollback"
        exit 1
    fi
}

# Main deployment function
main() {
    log_info "Starting deployment process..."
    
    # Get AWS account ID
    export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    
    case "${1:-deploy}" in
        "deploy")
            check_prerequisites
            build_and_push_image
            deploy_infrastructure
            update_kubeconfig
            deploy_to_kubernetes
            run_migrations
            health_check
            log_info "Deployment completed successfully!"
            ;;
        "rollback")
            check_prerequisites
            update_kubeconfig
            rollback
            ;;
        "infrastructure")
            check_prerequisites
            deploy_infrastructure
            ;;
        "app")
            check_prerequisites
            build_and_push_image
            update_kubeconfig
            deploy_to_kubernetes
            run_migrations
            health_check
            ;;
        *)
            echo "Usage: $0 [deploy|rollback|infrastructure|app]"
            exit 1
            ;;
    esac
}

# Trap errors and cleanup
trap 'log_error "Deployment failed"; exit 1' ERR

main "$@"