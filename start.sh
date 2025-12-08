#!/bin/bash

# Find processes using port 8080
netstat -ano | findstr :8080

# Kill the process by its Process ID (PID)
# Replace <PID> with the actual Process ID found in the previous command
taskkill /PID <PID> /F

source .venv/bin/activate
rbassist ui