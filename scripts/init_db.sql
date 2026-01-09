-- 建立資料庫 (需要在 psql 以 postgres 用戶執行)
-- CREATE DATABASE mind_map_db;

-- 連接到 mind_map_db 後執行以下指令

-- 啟用 pgvector 擴展
CREATE EXTENSION IF NOT EXISTS vector;

-- 建立 documents 表
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    module VARCHAR(100) NOT NULL,
    file_name VARCHAR(100) NULL,
    content TEXT NULL,
    embedding VECTOR(1536) NULL,
    file_path TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 建立索引
CREATE INDEX IF NOT EXISTS idx_module ON documents(module);
CREATE INDEX IF NOT EXISTS idx_file_name ON documents(file_name);

-- 建立向量索引 (當有 embedding 資料時使用)
-- CREATE INDEX IF NOT EXISTS idx_embedding ON documents USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
