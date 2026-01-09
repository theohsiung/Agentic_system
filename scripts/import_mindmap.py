#!/usr/bin/env python3
"""
匯入 mindmap 資料夾的 MD 檔案到 PostgreSQL 資料庫

使用方式:
    python scripts/import_mindmap.py

功能:
    1. 掃描 src/datas/mindmap 資料夾
    2. 清空 documents 表
    3. 有 MD 的模組 → 存 module + file_name + content + file_path
    4. 空模組 → 存 module，其他欄位 NULL
"""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# 載入 .env
load_dotenv()

# 資料庫連線設定
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "mind_map_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# mindmap 資料夾路徑
MINDMAP_DIR = Path(__file__).parent.parent / "src" / "datas" / "mindmap"


def get_connection():
    """建立資料庫連線"""
    return psycopg2.connect(**DB_CONFIG)


def clear_table(conn):
    """清空 documents 表"""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE documents RESTART IDENTITY;")
    conn.commit()
    print("已清空 documents 表")


def scan_mindmap_folder():
    """
    掃描 mindmap 資料夾，回傳模組和檔案資訊

    Returns:
        list: [
            {"module": "1.商品管理模組", "files": [{"file_name": "1.1商品類別維護", "file_path": "...", "content": "..."}]},
            {"module": "3.進貨管理模組", "files": []},  # 空模組
        ]
    """
    results = []

    if not MINDMAP_DIR.exists():
        print(f"錯誤: mindmap 資料夾不存在: {MINDMAP_DIR}")
        return results

    # 遍歷 mindmap 下的所有資料夾
    for module_dir in sorted(MINDMAP_DIR.iterdir()):
        if not module_dir.is_dir():
            continue

        # 跳過隱藏資料夾
        if module_dir.name.startswith("."):
            continue

        module_name = module_dir.name
        files = []

        # 掃描該模組下的 MD 檔案
        for md_file in sorted(module_dir.glob("*.md")):
            file_name = md_file.stem  # 不含副檔名
            file_path = str(md_file.absolute())
            content = md_file.read_text(encoding="utf-8")

            files.append({
                "file_name": file_name,
                "file_path": file_path,
                "content": content,
            })

        results.append({
            "module": module_name,
            "files": files,
        })

    return results


def import_to_db(conn, data):
    """
    匯入資料到資料庫

    Args:
        conn: 資料庫連線
        data: scan_mindmap_folder() 的回傳結果
    """
    with conn.cursor() as cur:
        for module_data in data:
            module_name = module_data["module"]
            files = module_data["files"]

            if files:
                # 有檔案的模組：每個檔案一筆記錄
                for file_info in files:
                    cur.execute(
                        """
                        INSERT INTO documents (module, file_name, content, file_path)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            module_name,
                            file_info["file_name"],
                            file_info["content"],
                            file_info["file_path"],
                        ),
                    )
                    print(f"  ✓ {module_name}/{file_info['file_name']}")
            else:
                # 空模組：只存 module，其他為 NULL
                cur.execute(
                    """
                    INSERT INTO documents (module, file_name, content, file_path)
                    VALUES (%s, NULL, NULL, NULL)
                    """,
                    (module_name,),
                )
                print(f"  ○ {module_name} (空模組)")

    conn.commit()


def show_summary(conn):
    """顯示匯入結果摘要"""
    with conn.cursor() as cur:
        # 總筆數
        cur.execute("SELECT COUNT(*) FROM documents")
        total = cur.fetchone()[0]

        # 有內容的筆數
        cur.execute("SELECT COUNT(*) FROM documents WHERE content IS NOT NULL")
        with_content = cur.fetchone()[0]

        # 空模組筆數
        cur.execute("SELECT COUNT(*) FROM documents WHERE content IS NULL")
        empty_modules = cur.fetchone()[0]

        # 模組列表
        cur.execute("SELECT DISTINCT module FROM documents ORDER BY module")
        modules = [row[0] for row in cur.fetchall()]

    print("\n" + "=" * 50)
    print("匯入完成!")
    print("=" * 50)
    print(f"總筆數: {total}")
    print(f"有內容的文件: {with_content}")
    print(f"空模組: {empty_modules}")
    print(f"模組列表: {len(modules)} 個")
    for m in modules:
        print(f"  - {m}")


def main():
    print("開始匯入 mindmap 到資料庫...")
    print(f"資料來源: {MINDMAP_DIR}")
    print(f"目標資料庫: {DB_CONFIG['dbname']}@{DB_CONFIG['host']}")
    print()

    # 掃描資料夾
    print("掃描 mindmap 資料夾...")
    data = scan_mindmap_folder()

    if not data:
        print("沒有找到任何模組資料夾")
        return

    # 連接資料庫
    print("\n連接資料庫...")
    conn = get_connection()

    try:
        # 清空表格
        clear_table(conn)

        # 匯入資料
        print("\n匯入資料...")
        import_to_db(conn, data)

        # 顯示摘要
        show_summary(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
