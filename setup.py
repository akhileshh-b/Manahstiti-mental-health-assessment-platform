#!/usr/bin/env python3
"""
Manahstiti Setup Script
This script helps set up the Manahstiti mental health assessment platform.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8 or higher"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True

def check_pip():
    """Check if pip is available"""
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], 
                      check=True, capture_output=True)
        print("✅ pip is available")
        return True
    except subprocess.CalledProcessError:
        print("❌ pip is not available")
        return False

def install_requirements():
    """Install required packages"""
    print("\n📦 Installing requirements...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True)
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        return False

def create_env_file():
    """Create .env file from example if it doesn't exist"""
    env_file = Path(".env")
    example_file = Path("environment.example")
    
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    if not example_file.exists():
        print("❌ environment.example file not found")
        return False
    
    try:
        shutil.copy(example_file, env_file)
        print("✅ Created .env file from environment.example")
        print("⚠️  Please edit .env file with your actual API keys")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False

def check_env_variables():
    """Check if required environment variables are set"""
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = ['GROQ_API_KEY', 'QDRANT_API_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var) or os.getenv(var) == f'your_{var.lower()}_here':
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️  Missing or placeholder values for: {', '.join(missing_vars)}")
        print("Please update your .env file with actual API keys")
        return False
    
    print("✅ Required environment variables are set")
    return True

def test_imports():
    """Test if all required packages can be imported"""
    print("\n🧪 Testing imports...")
    
    packages = [
        'flask',
        'flask_cors',
        'pandas',
        'numpy',
        'xgboost',
        'requests',
        'qdrant_client',
        'sentence_transformers',
        'cryptography',
        'dotenv'
    ]
    
    failed_imports = []
    
    for package in packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package}")
            failed_imports.append(package)
    
    if failed_imports:
        print(f"\n❌ Failed to import: {', '.join(failed_imports)}")
        return False
    
    print("\n✅ All packages imported successfully")
    return True

def check_ml_models():
    """Check if ML models exist"""
    model_path = Path("reference/mental_health_xgboost_model.pkl")
    encoder_path = Path("reference/mental_health_label_encoder.pkl")
    
    if model_path.exists() and encoder_path.exists():
        print("✅ ML models found")
        return True
    else:
        print("⚠️  ML models not found in reference/ directory")
        print("The application will work with fallback logic")
        return True

def main():
    """Main setup function"""
    print("🚀 Manahstiti Setup Script")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Check pip
    if not check_pip():
        sys.exit(1)
    
    # Install requirements
    if not install_requirements():
        sys.exit(1)
    
    # Create .env file
    if not create_env_file():
        sys.exit(1)
    
    # Test imports
    if not test_imports():
        print("\n❌ Some packages failed to import. Try running:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    
    # Check ML models
    check_ml_models()
    
    # Check environment variables
    env_ok = check_env_variables()
    
    print("\n" + "=" * 50)
    if env_ok:
        print("🎉 Setup completed successfully!")
        print("\nYou can now run the application with:")
        print("python app.py")
    else:
        print("⚠️  Setup completed with warnings")
        print("\nPlease update your .env file with actual API keys, then run:")
        print("python app.py")
    
    print("\n📚 For more information, see README.md")

if __name__ == "__main__":
    main() 