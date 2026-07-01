import os
import sys
def main():
    print("Python is working.")
    print("Python version:", sys.version)
    print("Python executable:", sys.executable)
    print("Virtual env:", os.environ.get("VIRTUAL_ENV", "not activated"))

if __name__ == "__main__":
    main()
