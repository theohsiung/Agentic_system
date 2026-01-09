"""
mind_map_db 資料庫查詢工具

提供以下函式:
- get_all_modules(): 讀取所有模組名稱
- get_files_by_module(module): 根據模組讀取所有檔案名稱
- get_content_by_file_name(file_name): 根據檔案名稱讀取完整內容
"""

import os
from typing import Optional

import psycopg2
import jieba
from rank_bm25 import BM25Okapi
from dotenv import load_dotenv

# 載入 .env
# 載入 .env
# 嘗試從專案根目錄載入
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
dotenv_path = os.path.join(project_root, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv() # Fallback to default behavior

# 資料庫連線設定
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "mind_map_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def _get_connection():
    """建立資料庫連線"""
    return psycopg2.connect(**DB_CONFIG)


def get_all_modules() -> list[str]:
    """
    讀取資料庫中所有模組名稱 (僅回傳模組名稱)

    Returns:
        list[str]: 模組名稱列表，例如 ['1.商品管理模組', '2.儲位管理模組', ...]
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT module FROM documents ORDER BY module"
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_files_by_module(module: str) -> list[str]:
    """
    根據模組名稱讀取該模組下所有檔案的名稱(僅回傳文件名稱)

    Args:
        module: 模組名稱，例如 '1.商品管理模組'

    Returns:
        list[str]: 檔案名稱列表，例如 ['1.1商品類別維護', '1.2商品主檔維護']
                   如果是空模組，回傳空列表
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_name
                FROM documents
                WHERE module = %s AND file_name IS NOT NULL
                ORDER BY file_name
                """,
                (module,),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_content_by_file_name(file_name: str) -> Optional[str]:
    """
    根據檔案名稱讀取完整內容

    Args:
        file_name: 檔案名稱，例如 '1.1商品類別維護'

    Returns:
        str: 檔案的完整 MD 內容
        None: 如果找不到該檔案
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM documents WHERE file_name = %s",
                (file_name,),
            )
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()


def get_content_by_module(module: str) -> list[dict]:
    """
    根據模組名稱讀取該模組下所有檔案的完整內容

    Args:
        module: 模組名稱，例如 '1.商品管理模組'

    Returns:
        list[dict]: 檔案資訊列表，例如:
            [
                {"file_name": "1.1商品類別維護", "content": "# 1. 功能概述..."},
                {"file_name": "1.2商品主檔維護", "content": "# 1. 功能概述..."},
            ]
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_name, content
                FROM documents
                WHERE module = %s AND content IS NOT NULL
                ORDER BY file_name
                """,
                (module,),
            )
            return [
                {"file_name": row[0], "content": row[1]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def get_all_documents() -> list[tuple[str, str]]:
    """
    讀取資料庫中所有檔案的名稱與內容

    Returns:
        list[tuple[str, str]]: (file_name, content) 列表
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_name, content FROM documents WHERE content IS NOT NULL"
            )
            return [(row[0], row[1]) for row in cur.fetchall()]
    finally:
        conn.close()


def bm25_search(query: str, n: int = 10) -> list[tuple[str, float]]:
    """
    使用 BM25 搜尋資料庫中所有文件，回傳前 n 筆結果

    Args:
        query: 搜尋關鍵字
        n: 回傳前 n 筆結果

    Returns:
        list[tuple[str, float]]: (file_name, score) 列表
    """
    documents = get_all_documents()
    if not documents:
        return []

    # Tokenize documents
    tokenized_corpus = [list(jieba.cut(doc[1])) for doc in documents]
    
    # Initialize BM25
    bm25 = BM25Okapi(tokenized_corpus)
    
    # Fix negative IDF values (common terms)
    # If a term is in >50% of docs, IDF can be negative in BM25Okapi.
    # We enforce a floor of epsilon for IDFs.
    average_idf = sum(bm25.idf.values()) / len(bm25.idf)
    epsilon = average_idf * 0.25
    for word, freq in bm25.idf.items():
        if freq < 0:
            bm25.idf[word] = epsilon

    # Tokenize query
    tokenized_query = list(jieba.cut(query))
    
    # Get scores
    scores = bm25.get_scores(tokenized_query)
    
    # Combine results
    results = []
    for i, score in enumerate(scores):
        if score > 0:
            results.append((documents[i][0], score))
            
    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    
    return results[:n]


if __name__ == "__main__":
    # Test BM25
    print("Testing BM25 search for '商品':")
    results = bm25_search("商品", 5)
    print(results)
    print('-'*50)
    for file_name, score in results:
        print(f"- {file_name}: {score}")
    
    print('-'*50)
    print(get_content_by_module('1.商品管理模組'))