Render fix:
- DATABASE_URL is defined before migrations run.
- Migration checks environment safely.
- Python pinned to 3.13.7.
- psycopg binary updated for current Python.
- Explicit Render build/start commands.
- All Python files passed local syntax compilation.

Build: pip install -r requirements.txt
Start: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120

Note: full dependency-install smoke test could not be executed in the file-generation sandbox because that runtime has no internet access. Render itself will install these dependencies.
