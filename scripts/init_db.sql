-- Enable required PostgreSQL extensions for vectors and fuzzy text search
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
