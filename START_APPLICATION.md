# How to Start the Prior Authorization Agent Application

## 🚀 **Quick Start (2 Steps)**

### **1. Start the Backend API Server**
```bash
# Option A: Using uvicorn directly (recommended)
python -m uvicorn src.main:app --reload --port 8000

# Option B: Using the main module
python -m src.main
```

### **2. Start the Frontend Dashboard**
```bash
# In a new terminal window
python frontend/serve.py
```

## 🌐 **Access Points**

### **Backend API:**
- **Main API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/api/v1/health

### **Frontend Dashboard:**
- **Dashboard**: http://localhost:8080/simple-dashboard.html
- **Login**: `provider1` / `provider123` or `admin1` / `admin123`

## 📋 **Prerequisites Check**

### **1. Virtual Environment**
```bash
# Check if virtual environment is active
which python
# Should show: /path/to/your/project/venv/bin/python

# If not active, activate it:
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows
```

### **2. Dependencies**
```bash
# Install/update dependencies if needed
pip install -r requirements.txt
```

### **3. Environment Variables**
```bash
# Check if .env file exists
ls -la .env

# If not, copy from example:
cp .env.example .env
```

## 🔧 **Startup Options**

### **Development Mode (with auto-reload):**
```bash
# Backend with auto-reload on code changes
python -m uvicorn src.main:app --reload --port 8000

# Frontend (already has auto-reload)
python frontend/serve.py
```

### **Production Mode:**
```bash
# Backend without auto-reload
python -m uvicorn src.main:app --port 8000

# Or using gunicorn for production
gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### **Custom Port:**
```bash
# Run on different port
python -m uvicorn src.main:app --reload --port 9000
```

## 🧪 **Test the Application**

### **1. Health Check**
```bash
curl http://localhost:8000/api/v1/health
# Should return: {"status": "healthy", "timestamp": "..."}
```

### **2. API Documentation**
Visit: http://localhost:8000/docs

### **3. Login Test**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=provider1&password=provider123"
```

### **4. Frontend Test**
1. Go to: http://localhost:8080/simple-dashboard.html
2. Login with: `provider1` / `provider123`
3. Try submitting a test request

## 🛠️ **Troubleshooting**

### **Port Already in Use:**
```bash
# Find what's using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
python -m uvicorn src.main:app --reload --port 8001
```

### **Import Errors:**
```bash
# Make sure you're in the project root directory
pwd
# Should show: /path/to/your/project

# Make sure virtual environment is active
which python
```

### **Database Issues:**
```bash
# Check if database file exists
ls -la prior_auth.db

# If missing, the app will create it automatically on first run
```

### **Environment Variables:**
```bash
# Check environment variables are loaded
python -c "from src.core.config import get_settings; print(get_settings())"
```

## 📊 **Application Status**

### **Check if Running:**
```bash
# Check backend
curl -s http://localhost:8000/api/v1/health || echo "Backend not running"

# Check frontend
curl -s http://localhost:8080 || echo "Frontend not running"
```

### **View Logs:**
```bash
# Backend logs appear in terminal where uvicorn is running
# Frontend logs appear in terminal where serve.py is running
```

## 🔄 **Restart Application**

### **Clean Restart:**
```bash
# Stop all processes
pkill -f uvicorn
pkill -f "python frontend/serve.py"

# Wait a moment, then restart
python -m uvicorn src.main:app --reload --port 8000 &
python frontend/serve.py &
```

## 🎯 **Success Indicators**

### **Backend Started Successfully:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### **Frontend Started Successfully:**
```
Starting server on http://localhost:8080
Server running at http://localhost:8080/simple-dashboard.html
```

## 🚀 **Ready to Use!**

Once both servers are running:
1. **Backend API**: Ready for requests at http://localhost:8000
2. **Frontend Dashboard**: Ready for users at http://localhost:8080/simple-dashboard.html
3. **Documentation**: Available at http://localhost:8000/docs

The Prior Authorization Agent is now ready to process healthcare authorization requests! 🏥