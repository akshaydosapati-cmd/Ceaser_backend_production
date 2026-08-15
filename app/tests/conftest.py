import os


# Establish the test database before any application module is imported.
# Individual API suites may still override get_db with their own isolated
# StaticPool engine, but the global application engine must never bind to a
# developer or production DATABASE_URL during collection.
os.environ["DATABASE_URL"] = "sqlite://"
