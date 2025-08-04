# --- Variables ---
# Use ?= to allow overriding from the command line, e.g., make run-node1 PORT1=8008
PORT1 ?= 8000
DB1 ?= node1.sqlite3
PORT2 ?= 8001
DB2 ?= node2.sqlite3

# Python virtual environment directory
VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest

# --- Phony Targets ---
# Ensures these commands run even if a file with the same name exists.
.PHONY: help install clean init setup-dev-users run-node1 run-node2 test fix setup heroku-reset

# --- Commands ---

# Default target: Show help message.
help:
	@echo "Makefile for SocialDistribution Project"
	@echo ""
	@echo "Usage:"
	@echo "  make setup           - One-command setup: cleans, inits DB, and creates dev users"
	@echo "  make install         - Create virtual environment and install dependencies"
	@echo "  make clean           - Remove database files and migrations"
	@echo "  make init            - Clean and create initial database migrations"
	@echo "  make setup-dev-users - Create superusers 'a' (node1) and 'b' (node2)"
	@echo "  make run-node1       - Migrate and run the first node (Port: $(PORT1), DB: $(DB1))"
	@echo "  make run-node2       - Migrate and run the second node (Port: $(PORT2), DB: $(DB2))"
	@echo "  make test            - Run the test suite using pytest"
	@echo "  make fix             - Run the auto_fix.sh script"
	@echo "  make heroku-reset    - Reset Heroku database and create admin user (for use with 'heroku run')"
	@echo ""
	@echo "You can override ports and db names, e.g.: make run-node1 PORT1=9000 DB1=mynode.sqlite3"

# One-command setup: clean, init migrations, create dev users
setup: init setup-dev-users
	@echo "✅ Full development environment setup is complete."
	@echo "You can now run 'make run-node1' and 'make run-node2' in separate terminals."

# Create venv and install dependencies
install: $(PYTHON)

$(PYTHON): requirements.txt
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	@touch $(PYTHON) # Mark as up-to-date to prevent re-running without changes

# Create default superusers for local development and register nodes with each other
setup-dev-users: install
	@echo "--> Ensuring databases are migrated..."
	DB_NAME=$(DB1) NODE_NAME=node1 $(PYTHON) manage.py migrate --no-input
	DB_NAME=$(DB2) NODE_NAME=node2 $(PYTHON) manage.py migrate --no-input
	@echo "--> Creating superuser 'a' for Node 1..."
	DB_NAME=$(DB1) NODE_NAME=node1 $(PYTHON) manage.py create_node_superuser a 1234 "http://127.0.0.1:$(PORT1)" --display_name a --email "a@example.com"
	@echo "--> Creating superuser 'b' for Node 2..."
	DB_NAME=$(DB2) NODE_NAME=node2 $(PYTHON) manage.py create_node_superuser b 1234 "http://127.0.0.1:$(PORT2)" --display_name b --email "b@example.com"
	@echo "--> Dev users created."
	@echo "--> Registering nodes with each other..."
	# On Node 1's DB, add Node 2 as a remote node
	DB_NAME=$(DB1) NODE_NAME=node1 $(PYTHON) manage.py add_remote_node \
		--host="http://127.0.0.1:$(PORT2)/" \
		--outgoing-user="node1_user" \
		--outgoing-pass="password123" \
		--incoming-user="node2_user" \
		--incoming-pass="password123"
	# On Node 2's DB, add Node 1 as a remote node
	DB_NAME=$(DB2) NODE_NAME=node2 $(PYTHON) manage.py add_remote_node \
		--host="http://127.0.0.1:$(PORT1)/" \
		--outgoing-user="node2_user" \
		--outgoing-pass="password123" \
		--incoming-user="node1_user" \
		--incoming-pass="password123"
	@echo "--> Node registration complete."

# Run the first development server node
run-node1: install
	@echo "--> Migrating database for Node 1..."
	DB_NAME=$(DB1) NODE_NAME=node1 $(PYTHON) manage.py migrate
	@echo "--> Starting Node 1 on http://127.0.0.1:$(PORT1) using $(DB1)"
	DB_NAME=$(DB1) NODE_NAME=node1 $(PYTHON) manage.py runserver $(PORT1)

# Run the second development server node
run-node2: install
	@echo "--> Migrating database for Node 2..."
	DB_NAME=$(DB2) NODE_NAME=node2 $(PYTHON) manage.py migrate
	@echo "--> Starting Node 2 on http://127.0.0.1:$(PORT2) using $(DB2)"
	DB_NAME=$(DB2) NODE_NAME=node2 $(PYTHON) manage.py runserver $(PORT2)

# Remove database files and migrations
clean:
	@echo "--> Cleaning up database files and migrations..."
	rm -f *.sqlite3
	find . -path "*/migrations/00*.py" -not -name "__init__.py" -delete
	find . -path "*/migrations/00*.pyc" -delete
	@echo "Cleanup complete."

# Clean and create initial migrations
init: clean
	@echo "--> Creating new initial migrations..."
	NODE_NAME=default $(PYTHON) manage.py makemigrations
	find . -name "db.sqlite3" -delete
	@echo "Initial migrations created."

# Run the test suite
test: install
	@echo "--> Running tests..."
	$(PYTEST)

# Run the auto-fix script
fix:
	@echo "--> Running auto-fix script..."
	sh ./auto_fix.sh

# Reset Heroku database and create admin user (for use with heroku run)
heroku-reset:
	@echo "--> Resetting Heroku database..."
	python manage.py flush --no-input
	@echo "--> Running migrations..."
	python manage.py migrate --no-input
	@echo "--> Creating admin user 'a' with password '1234'..."
	python manage.py create_node_superuser a 1234 "https://$(shell echo $$HEROKU_APP_NAME).herokuapp.com/" --display_name a --email "a@example.com"
	@echo "✅ Heroku database reset complete. Admin user 'a' created."
