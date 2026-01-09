## postgresql

```bash
# 進入 postgres user
sudo su postgres

# 檢查 postgresql 版本
psql --version

# 建立資料庫
createdb <db_name>

# 進入資料庫
psql <db_name>

# 列出所有資料庫
psql -l

# 進入資料庫
psql <db_name>

# 退出資料庫
\q

# 退出 postgres user
exit

# 刪除資料庫
dropdb <db_name>
```

## 操作數據表

inside DB
> create table <table_name> (
    <column_name> <data_type> <constraints>,
    <column_name> <data_type> <constraints>,
    ...
);
> \dt # 列出所有表
> \d <table_name> # 列出表結構
# 加入新欄位
> alter table <table_name> add column <column_name> <data_type> <constraints>;
# 重命名表
> alter table <table_name> rename to <new_table_name>;
# 插入新資料
> insert into <table_name> values (<value1>, <value2>, ...)
# 更新資料
> update <table_name> set <column_name> = <value> where <condition>
# 刪除資料
> delete from <table_name> where <condition>
> select * from <table_name>

---
# 一直需要打重複指令建立表格很麻煩，故
$ nano <table_name>.sql
...
create table <table_name> (
    <column_name> <data_type> <constraints>,
    <column_name> <data_type> <constraints>,
    ...
);
...
$ psql <db_name>
> -i <table_name>.sql
> \dt
---

## 數據類型 dtype

* 數值型
- integer
- real (float)
- serial (idx)

* 字串型
- char
- varchar
- text

* 日期型
- date
- time
- timestamp

* Other
- Array
- JSON
- boolean
- XML
- UUID
- inet


