DROP TABLE IF EXISTS documents CASCADE;
CREATE TABLE documents
(
    id      bigserial PRIMARY KEY,
    content text
);
INSERT INTO documents (content)
VALUES ('PostgreSQL is a powerful database system'),
       ('BM25 is an effective ranking function'),
       ('Full text search with custom scoring');

CREATE INDEX docs_idx ON documents USING bm25 (content) WITH (text_config='english');

SELECT *
FROM documents
ORDER BY content <@> 'database system'
LIMIT 5;

SELECT *
FROM documents
ORDER BY content <@> to_bm25query('database system', 'docs_idx')
LIMIT 5;

EXPLAIN
SELECT *
FROM documents
ORDER BY content <@> 'database system'
LIMIT 5;
