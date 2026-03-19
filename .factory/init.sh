#!/bin/bash
# Mission initialization script
# Idempotent - safe to run multiple times

set -e

echo "Initializing TradeLab UI Refactoring mission..."

# Install frontend dependencies (including new ones like recharts)
cd frontend
npm install

echo "Initialization complete."
