# Copy .env.example to .env for local development
import os
import shutil

if not os.path.exists(".env"):
    shutil.copy(".env.example", ".env")
    print(".env file created from .env.example")
