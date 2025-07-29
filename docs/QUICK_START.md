# Prior Authorization Agent - Quick Start Guide

## 🚀 Get Started in 5 Minutes

This guide will get you up and running with the Prior Authorization Agent quickly.

---

## ⚡ Prerequisites

- Python 3.11+ installed
- Project downloaded and virtual environment activated
- Terminal/command line access

---

## 📋 Step 1: Start the Application

```bash
# Navigate to project directory
cd prior-authorization-agent

# Activate virtual environment
source venv/bin/activate

# Start the server
python -m src.main
```

**✅ Success Indicator:**
```
INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
Prior Authorization Agent starting up...
INFO: Application startup complete.
```

---

## 🔍 Step 2: Verify System Health

```bash
curl http://127.0.0.1:8000/api/v1/health
```

**Expected Response:**
```json
{"status": "healthy", "version": "1.0.0", "environment": "development"}
```

---

## 🔐 Step 3: Login and Get Token

```bash
# Login as healthcare provider
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"
```

**Save the `access_token` from the response!**

---

## 📝 Step 4: Submit Your First Authorization Request

### Create Sample Request File
```bash
cat > sample_request.json << 'EOF'
{
  "request_id": "req_2024_quickstart",
  "provider_id": "prov_12345",
  "patient_demographics": {
    "patient_id": "enc_pat_quickstart_demo",
    "age": 45,
    "gender": "female",
    "insurance_id": "enc_ins_demo_123",
    "member_id": "enc_mem_demo_456"
  },
  "diagnosis_codes": [
    {
      "code": "M25.511",
      "description": "Pain in right shoulder",
      "category": "musculoskeletal"
    }
  ],
  "procedure_codes": [
    {
      "code": "73221",
      "description": "MRI upper extremity without contrast",
      "category": "radiology"
    }
  ],
  "clinical_notes": "Patient presents with chronic right shoulder pain lasting 6 months. Conservative treatment with physical therapy has failed. MRI needed to evaluate for rotator cuff tear.",
  "procedure_type": "mri",
  "urgency_level": "routine"
}
EOF
```

### Submit Request
```bash
# Get token and submit request in one command
TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123" | \
  python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST "http://127.0.0.1:8000/api/v1/authorization/requests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

**✅ Success Response:**
```json
{
  "request_id": "req_2025_xxxxxx",
  "status": "submitted",
  "message": "Authorization request submitted successfully"
}
```

---

## 📊 Step 5: Check Request Status

```bash
# Replace {request_id} with the ID from step 4
curl -X GET "http://127.0.0.1:8000/api/v1/authorization/requests/{request_id}" \
  -H "Authorization: Bearer $TOKEN"
```

**Response Shows:**
- Current processing stage
- Progress percentage
- Estimated completion time
- Next actions required

---

## 🎯 Step 6: View Dashboard

```bash
# Get provider dashboard summary
curl -X GET "http://127.0.0.1:8000/api/v1/dashboard/summary/prov_12345" \
  -H "Authorization: Bearer $TOKEN"
```

**Shows:**
- Total requests
- Approval rates
- Processing times
- Recent activity

---

## 🌐 Step 7: Explore Interactive Documentation

Open your browser and visit:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

**Features:**
- Test all endpoints interactively
- View detailed schemas
- Copy working code examples
- Understand authentication requirements

---

## 🎉 Congratulations!

You've successfully:
- ✅ Started the Prior Authorization Agent
- ✅ Authenticated as a healthcare provider
- ✅ Submitted an authorization request
- ✅ Checked request status
- ✅ Accessed the provider dashboard
- ✅ Explored the API documentation

---

## 🔄 Common Workflows

### Typical Provider Workflow
```bash
# 1. Login
TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123" | \
  python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# 2. Submit request
curl -X POST "http://127.0.0.1:8000/api/v1/authorization/requests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @your_request.json

# 3. Check status
curl -X GET "http://127.0.0.1:8000/api/v1/authorization/requests/{request_id}" \
  -H "Authorization: Bearer $TOKEN"

# 4. Get decision (when ready)
curl -X GET "http://127.0.0.1:8000/api/v1/decisions/request/{request_id}" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 👥 Test User Accounts

| Username | Password | Role | Use For |
|----------|----------|------|---------|
| `provider1` | `provider123` | Healthcare Provider | Submit requests |
| `admin1` | `admin123` | Payer Admin | Review policies |
| `compliance1` | `compliance123` | Compliance Officer | Audit logs |

---

## 🛠 Useful Commands

### Health Check
```bash
curl http://127.0.0.1:8000/api/v1/health
```

### Get Current User Info
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

### List All Provider Requests
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/dashboard/requests/prov_12345" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🚨 Troubleshooting

### Server Won't Start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process if needed
pkill -f "python -m src.main"
```

### Authentication Fails
- Check username/password spelling
- Ensure you're using the correct test accounts
- Verify the server is running

### Request Validation Errors
- Use standard ICD-10 and CPT codes
- Include all required fields
- Check the API documentation for schema details

### Token Expired
```bash
# Get a new token
TOKEN=$(curl -s -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123" | \
  python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

---

## 📚 Next Steps

1. **Read the Full User Guide**: `docs/USER_GUIDE.md`
2. **Explore API Reference**: `docs/API_REFERENCE.md`
3. **Try Different User Roles**: Login as admin1 or compliance1
4. **Test Error Scenarios**: Submit invalid requests to see error handling
5. **Integrate with Your System**: Use the API in your healthcare application

---

## 💡 Pro Tips

- **Save your token**: Store it in a variable to avoid re-authentication
- **Use the interactive docs**: Swagger UI is great for testing
- **Check logs**: Application logs show detailed processing information
- **Monitor health**: Use health endpoints for system monitoring
- **Handle errors**: Always check response status codes

You're now ready to use the Prior Authorization Agent effectively! 🎯