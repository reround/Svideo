# db.py
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

db_name = "videohub.db"
DB_FILE = Path(__file__).with_name(db_name)

class VideoInfo(BaseModel):
    id: str
    title: str
    filename: str
    original: str
    duration: Optional[str] = None
    url: str

# ------------------- 连接与初始化 -------------------
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    if  DB_FILE.exists():
        return
    
    with closing(get_conn()) as conn, closing(conn.cursor()) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id        TEXT PRIMARY KEY,
                title     TEXT NOT NULL,
                filename  TEXT NOT NULL,
                original  TEXT NOT NULL,
                duration  TEXT,
                url       TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            );
        """)
        cur.execute("""
            INSERT OR IGNORE INTO counters (name, count) VALUES ('videos', 0);
        """)
        conn.commit()

def insert_video(v: VideoInfo):
    with closing(get_conn()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "INSERT INTO videos(id,title,filename,original,duration,url) VALUES (?,?,?,?,?,?)",
            (v.id, v.title, v.filename, v.original, v.duration, v.url),
        )
        cur.execute("UPDATE counters SET count = count + 1 WHERE name = 'videos'")
        conn.commit()

def delete_video(vid: str) -> bool:
    print(f"deleting video : {vid}")
    with closing(get_conn()) as conn, closing(conn.cursor()) as cur:
        cur.execute("DELETE FROM videos WHERE id=?", (vid,))
        if cur.rowcount > 0:
            cur.execute("UPDATE counters SET count = count - 1 WHERE name = 'videos'")
        conn.commit()
        return cur.rowcount > 0

def get_videos_count() -> int:
    with closing(get_conn()) as conn, closing(conn.cursor()) as cur:
        cur.execute("SELECT count FROM counters WHERE name = 'videos'")
        return cur.fetchone()[0]

def list_videos_paged(skip: int, limit: int) -> List[VideoInfo]:
    """分页查询：从第 skip 条（0 起）开始取 limit 条"""
    with closing(get_conn()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            "SELECT id,title,filename,original,duration,url "
            "FROM videos ORDER BY rowid DESC  LIMIT ? OFFSET ?",
            (limit, skip),
        )
        # ORDER BY rowid DESC 表示插入顺序
        # ORDER BY rowid ASC（升序）排序
        rows = cur.fetchall()
    return [VideoInfo(id=r[0], title=r[1], filename=r[2], original=r[3], duration=r[4], url=r[5])
            for r in rows]

def create_test_data():
    # 初始化数据库
    init_db()
    
    # # 创建10条测试数据
    # test_videos = [
    #     VideoInfo(
    #         id=f"video_{i}",
    #         title=f"测试视频{i}",
    #         filename=f"test_video_{i}.mp4",
    #         original=f"original_{i}.mp4",
    #         duration=f"{i*10}:00",
    #         url=f"https://example.com/video_{i}"
    #     )
    #     for i in range(1, 11)
    # ]
    
    # # 插入测试数据
    # for video in test_videos:
    #     insert_video(video)
    
    # # 打印所有数据以验证
    # videos = list_videos()
    # print(f"成功插入 {len(videos)} 条数据:")
    # for v in videos:
    #     print(f"ID: {v.id}, Title: {v.title}")
        
if __name__ == "__main__":
    create_test_data()
    # l =  list_videos_paged(1, 5)
    # for v in l:
    #     print(v)
        
    # print(delete_video("video_7"))
    
    # l =  list_videos_paged(1, 5)
    # for v in l:
    #     print(v)