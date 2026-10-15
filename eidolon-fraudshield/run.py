#!/usr/bin/env python3
"""Run: python run.py. Override HOST/PORT environment variables as needed."""
import os
from fraudshield.server import serve
if __name__=='__main__':
    serve(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','8000')))
