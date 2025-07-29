# Prior Authorization Agent - Operations Runbook

## Table of Contents
1. [System Overview](#system-overview)
2. [Deployment Procedures](#deployment-procedures)
3. [Monitoring and Alerting](#monitoring-and-alerting)
4. [Backup and Recovery](#backup-and-recovery)
5. [Troubleshooting](#troubleshooting)
6. [Maintenance Procedures](#maintenance-procedures)
7. [Security Procedures](#security-procedures)
8. [Emergency Procedures](#emergency-procedures)

## System Overview

### Architecture Components
- **Application**: Python FastAPI application running in Kubernetes
- **Database**: PostgreSQL with encrypted PHI data
- **Cache**: Redis for policy and decision caching
- **Load Balancer**: NGINX with SSL termination
- **Monitoring**: Prometheus, Grafana, and ELK stack
- **Infrastructure**: AWS EKS with auto-scaling

### Key Metrics
- **Response Time**: 95% of requests < 2 minutes
- **Availability**: 99.9% uptime target
- **Throughput**: 1000+ concurrent requests
- **Error Rate**: < 0.1% for 5xx errors

## Deployment Procedures

### Standard Deployment
```bash
# 1. Deploy infrastructure
cd deployment/terraform
terraform plan -var="environment=production"
terraform apply

# 2. Deploy application
./scripts/deploy.sh deploy

# 3. Verify deployment
kubectl get pods -n prior-auth
curl -f https://api.prior-auth.your-domain.com/health
```

### Rollback Procedure
```bash
# Quick rollback to previous version
./scripts/rollback.sh previous

# Rollback to specific revision
./scripts/rollback.sh revision 5

# Emergency rollback (scale down and rollback)
./scripts/rollback.sh emergency
```

### Blue-Green Deployment
```bash
# 1. Deploy to staging environment
ENVIRONMENT=staging ./scripts/deploy.sh app

# 2. Run smoke tests
./scripts/smoke-tests.sh staging

# 3. Switch traffic to new version
kubectl patch service prior-auth-api-service -n prior-auth \
  --type='json' -p='[{"op": "replace", "path": "/spec/selector/version", "value": "blue"}]'

# 4. Monitor for issues and rollback if needed
```

## Monitoring and Alerting

### Key Dashboards
- **Application Dashboard**: http://grafana.internal/d/app-dashboard
- **Infrastructure Dashboard**: http://grafana.internal/d/infra-dashboard
- **Security Dashboard**: http://grafana.internal/d/security-dashboard

### Critical Alerts
1. **High Error Rate**: > 0.1% 5xx errors for 5 minutes
2. **High Response Time**: 95th percentile > 2 minutes for 5 minutes
3. **Database Down**: PostgreSQL connection failure for 1 minute
4. **Pod Crash Loop**: Container restart rate > 0 for 5 minutes
5. **High Memory Usage**: > 80% memory usage for 5 minutes

### Alert Response Procedures

#### High Error Rate Alert
1. Check application logs: `kubectl logs -n prior-auth -l app=prior-auth-api --tail=100`
2. Check database connectivity: `kubectl exec -n prior-auth <db-pod> -- pg_isready`
3. Check external service status (CMS API, policy services)
4. Scale up pods if needed: `kubectl scale deployment prior-auth-api -n prior-auth --replicas=5`
5. If persistent, initiate rollback procedure

#### Database Connection Failure
1. Check database pod status: `kubectl get pods -n prior-auth -l app=postgres`
2. Check database logs: `kubectl logs -n prior-auth <postgres-pod>`
3. Verify database service: `kubectl get svc postgres-service -n prior-auth`
4. If pod is down, check persistent volume: `kubectl get pv,pvc -n prior-auth`
5. Restart database pod if needed: `kubectl delete pod -n prior-auth <postgres-pod>`

## Backup and Recovery

### Automated Backups
- **Schedule**: Daily at 2:00 AM UTC
- **Retention**: 30 days
- **Location**: S3 bucket `prior-auth-backups`
- **Components**: Database, Redis, K8s configs, application logs

### Manual Backup
```bash
# Full backup
./scripts/backup.sh full

# Database only
./scripts/backup.sh database

# List available backups
./scripts/disaster-recovery.sh list
```

### Recovery Procedures

#### Full System Recovery
```bash
# 1. Enable maintenance mode
./scripts/disaster-recovery.sh maintenance-on

# 2. Restore from backup
./scripts/disaster-recovery.sh restore prior-auth-backup-20250124_020000.tar.gz

# 3. Verify system health
./scripts/disaster-recovery.sh verify

# 4. Disable maintenance mode
./scripts/disaster-recovery.sh maintenance-off
```

#### Point-in-Time Recovery
```bash
# Restore to specific time
./scripts/disaster-recovery.sh point-in-time "2025-01-24 14:30:00"
```

## Troubleshooting

### Common Issues

#### Application Won't Start
**Symptoms**: Pods in CrashLoopBackOff state
**Diagnosis**:
```bash
kubectl describe pod -n prior-auth <pod-name>
kubectl logs -n prior-auth <pod-name> --previous
```
**Solutions**:
- Check environment variables and secrets
- Verify database connectivity
- Check resource limits and requests
- Review application configuration

#### High Memory Usage
**Symptoms**: Memory usage > 80%, pods being OOMKilled
**Diagnosis**:
```bash
kubectl top pods -n prior-auth
kubectl describe pod -n prior-auth <pod-name>
```
**Solutions**:
- Increase memory limits in deployment
- Check for memory leaks in application logs
- Scale horizontally instead of vertically
- Review caching configuration

#### Database Performance Issues
**Symptoms**: Slow query responses, high CPU on database pod
**Diagnosis**:
```bash
kubectl exec -n prior-auth <db-pod> -- psql -U postgres -d prior_auth -c "SELECT * FROM pg_stat_activity;"
kubectl exec -n prior-auth <db-pod> -- psql -U postgres -d prior_auth -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```
**Solutions**:
- Analyze slow queries and add indexes
- Increase database resources
- Optimize application queries
- Consider read replicas for read-heavy workloads

### Log Analysis

#### Application Logs
```bash
# View recent application logs
kubectl logs -n prior-auth -l app=prior-auth-api --tail=100 -f

# Search for errors
kubectl logs -n prior-auth -l app=prior-auth-api | grep -i error

# View logs in Kibana
# Navigate to http://kibana.internal and search for: kubernetes.namespace_name:"prior-auth"
```

#### Audit Logs
```bash
# View audit logs
kubectl logs -n prior-auth -l app=prior-auth-api | grep '"level":"AUDIT"'

# Check security events
kubectl logs -n prior-auth -l app=prior-auth-api | grep '"level":"SECURITY"'
```

## Maintenance Procedures

### Scheduled Maintenance

#### Database Maintenance
```bash
# 1. Enable maintenance mode
./scripts/disaster-recovery.sh maintenance-on

# 2. Scale down application
kubectl scale deployment prior-auth-api -n prior-auth --replicas=0

# 3. Perform database maintenance
kubectl exec -n prior-auth <db-pod> -- psql -U postgres -d prior_auth -c "VACUUM ANALYZE;"
kubectl exec -n prior-auth <db-pod> -- psql -U postgres -d prior_auth -c "REINDEX DATABASE prior_auth;"

# 4. Scale up application
kubectl scale deployment prior-auth-api -n prior-auth --replicas=3

# 5. Disable maintenance mode
./scripts/disaster-recovery.sh maintenance-off
```

#### Certificate Renewal
```bash
# Check certificate expiration
kubectl get certificates -n prior-auth

# Renew certificates (if using cert-manager)
kubectl delete certificate prior-auth-tls -n prior-auth
kubectl apply -f deployment/k8s/ingress.yaml
```

#### Security Updates
```bash
# 1. Update base images
docker build -t prior-auth-api:security-update .

# 2. Deploy with rolling update
kubectl set image deployment/prior-auth-api -n prior-auth \
  prior-auth-api=prior-auth-api:security-update

# 3. Monitor rollout
kubectl rollout status deployment/prior-auth-api -n prior-auth
```

### Performance Optimization

#### Database Optimization
```bash
# Analyze table statistics
kubectl exec -n prior-auth <db-pod> -- psql -U postgres -d prior_auth -c "
SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;"

# Check index usage
kubectl exec -n prior-auth <db-pod> -- psql -U postgres -d prior_auth -c "
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;"
```

#### Cache Optimization
```bash
# Check Redis memory usage
kubectl exec -n prior-auth <redis-pod> -- redis-cli info memory

# Check cache hit rates
kubectl exec -n prior-auth <redis-pod> -- redis-cli info stats | grep keyspace
```

## Security Procedures

### Security Monitoring
- Monitor failed authentication attempts
- Check for unusual access patterns
- Review audit logs for PHI access
- Monitor certificate expiration dates

### Incident Response

#### Security Breach Detection
1. **Immediate Actions**:
   - Isolate affected systems
   - Preserve evidence
   - Notify security team
   - Document timeline

2. **Investigation**:
   - Analyze audit logs
   - Check access patterns
   - Review system changes
   - Identify scope of breach

3. **Containment**:
   - Revoke compromised credentials
   - Update security rules
   - Apply security patches
   - Monitor for further activity

4. **Recovery**:
   - Restore from clean backups
   - Update security configurations
   - Implement additional monitoring
   - Conduct security review

### Compliance Procedures

#### HIPAA Compliance Check
```bash
# Check PHI encryption status
kubectl exec -n prior-auth <app-pod> -- python -c "
from src.core.encryption import verify_encryption_status
print(verify_encryption_status())
"

# Review audit logs for PHI access
kubectl logs -n prior-auth -l app=prior-auth-api | grep '"phi_accessed":true'

# Check access controls
kubectl auth can-i --list --as=system:serviceaccount:prior-auth:default
```

## Emergency Procedures

### Emergency Contacts
- **On-Call Engineer**: +1-555-0123
- **Security Team**: security@company.com
- **Database Admin**: dba@company.com
- **Infrastructure Team**: infra@company.com

### Emergency Scenarios

#### Complete System Outage
1. **Assessment** (5 minutes):
   - Check monitoring dashboards
   - Verify infrastructure status
   - Identify root cause

2. **Communication** (10 minutes):
   - Notify stakeholders
   - Update status page
   - Activate incident response team

3. **Recovery** (30 minutes):
   - Execute disaster recovery plan
   - Restore from latest backup
   - Verify system functionality

4. **Post-Incident**:
   - Conduct post-mortem
   - Update procedures
   - Implement preventive measures

#### Data Breach Response
1. **Immediate** (15 minutes):
   - Isolate affected systems
   - Preserve audit logs
   - Notify security team

2. **Assessment** (1 hour):
   - Determine scope of breach
   - Identify affected data
   - Document timeline

3. **Notification** (24 hours):
   - Notify regulatory authorities
   - Inform affected parties
   - Prepare public statement

4. **Remediation**:
   - Implement security fixes
   - Enhance monitoring
   - Update security procedures

### Emergency Commands

#### Quick System Status
```bash
# Check all pods
kubectl get pods -n prior-auth

# Check services
kubectl get svc -n prior-auth

# Check ingress
kubectl get ingress -n prior-auth

# Check recent events
kubectl get events -n prior-auth --sort-by='.lastTimestamp'
```

#### Emergency Scaling
```bash
# Scale up quickly
kubectl scale deployment prior-auth-api -n prior-auth --replicas=10

# Check resource usage
kubectl top nodes
kubectl top pods -n prior-auth
```

#### Emergency Shutdown
```bash
# Scale down all applications
kubectl scale deployment prior-auth-api -n prior-auth --replicas=0
kubectl scale deployment postgres -n prior-auth --replicas=0
kubectl scale deployment redis -n prior-auth --replicas=0

# Enable maintenance mode
./scripts/disaster-recovery.sh maintenance-on
```

## Contact Information

### Team Contacts
- **DevOps Team**: devops@company.com
- **Development Team**: dev@company.com
- **Security Team**: security@company.com
- **Compliance Team**: compliance@company.com

### Vendor Contacts
- **AWS Support**: Case management console
- **Database Vendor**: support@postgresql.org
- **Monitoring Vendor**: support@grafana.com

### Escalation Matrix
1. **Level 1**: On-call engineer
2. **Level 2**: Team lead
3. **Level 3**: Engineering manager
4. **Level 4**: CTO/VP Engineering