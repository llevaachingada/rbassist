import sys
import traceback

try:
    import rbassist
    print("RBAssist module imported successfully")
    
    from rbassist.ui import app
    print("UI App module imported successfully")
    
    print("Attempting to run app...")
    app.run(port=8088, reload=True)

except Exception as e:
    print(f"Error occurred: {e}")
    print("Detailed traceback:")
    traceback.print_exc()
    sys.exit(1)import sys
import traceback

try:
    import rbassist
    print("RBAssist module imported successfully")
    
    from rbassist.ui import app
    print("UI App module imported successfully")
    
    print("Attempting to run app...")
    app.run(port=8088, reload=True)

except Exception as e:
    print(f"Error occurred: {e}")
    print("Detailed traceback:")
    traceback.print_exc()
    sys.exit(1)