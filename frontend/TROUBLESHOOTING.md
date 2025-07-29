# Frontend Troubleshooting Guide

## 🚨 Login Issues - "Unknown Error"

### Quick Fix Steps:

#### 1. **Check Backend Server**
```bash
# Test if backend is running
curl http://127.0.0.1:8000/api/v1/health

# If not running, start it:
python -m src.main
```

#### 2. **Use the Frontend Server (Recommended)**
```bash
# Start the frontend server
python frontend/serve.py

# Then open: http://localhost:8080/simple-dashboard.html
```

#### 3. **Run Backend Test**
```bash
# Test all backend functionality
python frontend/test-backend.py
```

---

## 🔍 Common Issues and Solutions

### Issue 1: CORS Error
**Symptoms:** 
- "Network error" in browser console
- "Access to XMLHttpRequest blocked by CORS policy"

**Solution:**
```bash
# Use the frontend server instead of opening HTML directly
python frontend/serve.py
```

### Issue 2: Backend Not Running
**Symptoms:**
- "Connection refused" error
- "ERR_NETWORK" in console

**Solution:**
```bash
# Start the backend server
cd /path/to/project
source venv/bin/activate
python -m src.main
```

### Issue 3: Wrong API URL
**Symptoms:**
- 404 errors
- "Cannot connect to server"

**Check:**
- Backend should be running on `http://127.0.0.1:8000`
- Frontend should use `http://localhost:8080`

### Issue 4: Authentication Fails
**Symptoms:**
- "Login failed" with valid credentials
- 401 Unauthorized errors

**Debug Steps:**
```bash
# Test login directly
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"
```

---

## 🧪 Testing Steps

### Step 1: Test Backend
```bash
python frontend/test-backend.py
```

### Step 2: Start Frontend Server
```bash
python frontend/serve.py
```

### Step 3: Open Dashboard
Open: `http://localhost:8080/simple-dashboard.html`

### Step 4: Login
- Username: `provider1`
- Password: `provider123`

---

## 🔧 Debug Mode

### Enable Console Logging
1. Open browser Developer Tools (F12)
2. Go to Console tab
3. Look for error messages

### Common Console Errors:

#### "Mixed Content" Error
**Fix:** Use HTTPS or serve both frontend and backend on HTTP

#### "CORS Policy" Error
**Fix:** Use the frontend server (`python frontend/serve.py`)

#### "Network Error"
**Fix:** Check if backend is running on port 8000

---

## 📋 Checklist

Before reporting issues, verify:

- [ ] Backend server is running (`curl http://127.0.0.1:8000/api/v1/health`)
- [ ] Frontend server is running (`python frontend/serve.py`)
- [ ] Using correct URL (`http://localhost:8080/simple-dashboard.html`)
- [ ] Browser console shows no CORS errors
- [ ] Test credentials work (`provider1` / `provider123`)

---

## 🚀 Alternative Access Methods

### Method 1: Frontend Server (Recommended)
```bash
python frontend/serve.py
# Open: http://localhost:8080/simple-dashboard.html
```

### Method 2: Direct HTML (May have CORS issues)
```bash
# Open frontend/simple-dashboard.html directly in browser
open frontend/simple-dashboard.html
```

### Method 3: Python HTTP Server
```bash
cd frontend
python -m http.server 8080
# Open: http://localhost:8080/simple-dashboard.html
```

---

## 🔍 Advanced Debugging

### Check Network Requests
1. Open Developer Tools (F12)
2. Go to Network tab
3. Try to login
4. Look for failed requests

### Check CORS Headers
```bash
curl -I -X OPTIONS "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Origin: http://localhost:8080"
```

### Test API Directly
```bash
# Test login
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"

# Test with token
TOKEN="your_token_here"
curl -X GET "http://127.0.0.1:8000/api/v1/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 📞 Still Having Issues?

### Gather This Information:
1. **Browser Console Errors** (F12 → Console)
2. **Network Tab Errors** (F12 → Network)
3. **Backend Server Logs**
4. **Test Results** (`python frontend/test-backend.py`)

### Common Solutions:
- **Restart both servers** (backend and frontend)
- **Clear browser cache** (Ctrl+Shift+R)
- **Try different browser** (Chrome, Firefox, Safari)
- **Check firewall settings** (allow ports 8000 and 8080)

The most common issue is CORS, which is solved by using the frontend server instead of opening the HTML file directly!