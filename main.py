# 网址改变时必须修改变量：index.html 中 的 API_BASE_URL 变量
# 新增
import db
import os
import uuid
import json
import shutil
import asyncio
import subprocess
import aiofiles

from fastapi import Response, Query
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

# ------------------------------------------------------
# 基础配置
# ------------------------------------------------------
ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "videos"  # 原始文件
STATIC_DIR = ROOT / "static"  # 转码后 mp4
CHUNK_SIZE = 256 * 1024  # 流式读取 256 KB

for d in (UPLOAD_DIR, STATIC_DIR):
    d.mkdir(exist_ok=True)

app = FastAPI(title="VideoHub", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# @app.on_event("startup")
# def on_startup():
#     db.init_db()
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    db.init_db()
    yield
    # 关闭时执行（如果需要）


# ------------------------------------------------------
# 数据模型
# ------------------------------------------------------
class VideoInfo(BaseModel):
    id: str
    title: str
    filename: str  # 转码后 mp4 文件名
    original: str  # 原始上传文件名
    duration: Optional[str] = None


# ------------------------------------------------------
# 工具：获取视频时长（ffprobe）
# ------------------------------------------------------
def _get_duration(path: Path) -> str:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        dur = float(json.loads(out)["format"]["duration"])
        return f"{int(dur // 60)}:{int(dur % 60):02d}"
    except Exception:
        return "未知"


# ------------------------------------------------------
# 工具：转码为 h264/aac mp4（异步，防止阻塞）
# ------------------------------------------------------
async def _transcode(in_path: Path, out_path: Path):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _do_transcode, in_path, out_path)


def _do_transcode(src: Path, dst: Path):
    # 如果已经是 h264/aac 可跳过；这里简单统一转码
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


# ------------------------------------------------------
# API：上传
# ------------------------------------------------------
@app.post("/upload", response_model=db.VideoInfo)
async def upload_video(file: UploadFile = File(...), title: str = Form(...)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(400, "请上传视频文件")

    vid = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    raw_path = UPLOAD_DIR / f"{vid}{ext}"
    mp4_path = STATIC_DIR / f"{vid}.mp4"

    with raw_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    await _transcode(raw_path, mp4_path)

    info = db.VideoInfo(
        id=vid,
        title=title,
        filename=mp4_path.name,
        original=file.filename,
        duration=_get_duration(mp4_path),
        url=f"/videos/{mp4_path.name}",  # 本地播放地址
    )
    db.insert_video(info)
    
    # 删除原始文件
    raw_path.unlink()
    return info


@app.get("/videos")
def list_videos(
    response: Response,
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(10, ge=1, le=100, description="每页数量"),
):
    response.headers["Cache-Control"] = "no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # 计算跳过的记录数
    skip = (page - 1) * pageSize

    # 获取视频列表和总数
    videos = db.list_videos_paged(skip=skip, limit=pageSize)
    total = db.get_videos_count()  # 你需要实现这个函数来获取总数

    return {"videos": videos, "total": total}


# ------------------------------------------------------
# API：删除
# ------------------------------------------------------
@app.delete("/videos/{vid}")
def delete_video(vid: str):
    ok = db.delete_video(vid)
    if not ok:
        raise HTTPException(404, "视频不存在")
    
    
    # 删除UPLOAD_DIR中的匹配文件
    for file in UPLOAD_DIR.glob(f"{vid}.*"):
        try:
            file.unlink()
        except PermissionError:
            # 如果文件正在使用，稍后重试
            import time
            time.sleep(0.5)  # 等待500ms
            file.unlink()
    
    # 删除STATIC_DIR中的mp4文件
    static_file = STATIC_DIR / f"{vid}.mp4"
    try:
        static_file.unlink()
    except PermissionError:
        import time
        time.sleep(0.5)  # 等待500ms
        static_file.unlink()
    
    return {"ok": True}
    return {"ok": True}


# ------------------------------------------------------
# 流式播放：支持 Range
# ------------------------------------------------------
# @app.get("/videos/{filename}")
# async def stream_video(filename: str, request: Request):
#     file_path = STATIC_DIR / filename
#     if not file_path.exists():
#         raise HTTPException(404, "文件不存在")

#     file_size = file_path.stat().st_size
#     range_header = request.headers.get("range")

#     start = 0
#     end = file_size - 1
#     status_code = 200

#     if range_header:
#         try:
#             h = range_header.replace("bytes=", "").split("-")
#             start = int(h[0]) if h[0] else 0
#             end = int(h[1]) if h[1] else file_size - 1
#             status_code = 206
#         except ValueError:
#             raise HTTPException(416, "Range Not Satisfiable")

#     def iter_file():
#         with file_path.open("rb") as f:
#             f.seek(start)
#             remaining = end - start + 1
#             while remaining > 0:
#                 read_size = min(CHUNK_SIZE, remaining)
#                 data = f.read(read_size)
#                 if not data:
#                     break
#                 remaining -= len(data)
#                 yield data

#     headers = {
#         "Accept-Ranges": "bytes",
#         "Content-Length": str(end - start + 1),
#         "Content-Range": f"bytes {start}-{end}/{file_size}",
#     }
#     return StreamingResponse(
#         iter_file(), status_code=status_code, headers=headers, media_type="video/mp4"
#     )

@app.get("/videos/{filename}")
async def stream_video(filename: str, request: Request):
    file_path = STATIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    start = 0
    end = file_size - 1
    status_code = 200

    if range_header:
        try:
            h = range_header.replace("bytes=", "").split("-")
            start = int(h[0]) if h[0] else 0
            end = int(h[1]) if h[1] else file_size - 1
            status_code = 206
        except ValueError:
            raise HTTPException(416, "Range Not Satisfiable")

    async def iter_file():
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                await f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    read_size = min(CHUNK_SIZE, remaining)
                    data = await f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        except Exception as e:
            # 确保在发生错误时文件句柄被释放
            print(f"Error while streaming: {e}")
            raise

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Cache-Control": "no-cache",  # 防止缓存导致文件被锁定
    }
    return StreamingResponse(
        iter_file(), 
        status_code=status_code, 
        headers=headers, 
        media_type="video/mp4"
    )



# 假设 index.html 和 main.py 放在同一目录
@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        frontend_html = f.read()  # ← 正确方法名
    return frontend_html


# ------------------------------------------------------
# 启动
# ------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
