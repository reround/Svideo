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
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Header

from pathlib import Path
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

# ------------------------------------------------------
# 基础配置
# ------------------------------------------------------
ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"  # 数据目录
VEDEOS_DIR = DATA_DIR / "videos"  # 原始视频文件
CLIPS_DIR = DATA_DIR / "clips"  # 转码后 mp4
THUMBNAILS_DIR = DATA_DIR / "thumbnails"  # 自动生成的封面
STATIC_DIR = ROOT / "static"

CHUNK_SIZE = 256 * 1024  # 流式读取 256 KB
is_transcode = False  # 视频是否转码
vedio_suffix = ".xxx"  # 保存的视频的后缀，用于隐藏视频，防止直接访问

for d in (DATA_DIR, STATIC_DIR, THUMBNAILS_DIR, CLIPS_DIR, VEDEOS_DIR):
    d.mkdir(exist_ok=True)


# @app.on_event("startup")
# def on_startup():
#     db.init_db()
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    print("startup")
    db.init_db()
    yield
    print("shutdown")
    # 关闭时执行（如果需要）


app = FastAPI(title="VideoHub", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 1. 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")
# 2. 创建模板实例
templates = Jinja2Templates(directory="templates")


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
    raw_path = VEDEOS_DIR / f"{vid}{ext}"
    mp4_path = CLIPS_DIR / f"{vid}{vedio_suffix}"

    if is_transcode:  # 如果需要转码
        with raw_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        await _transcode(raw_path, mp4_path)
        # 删除原始文件
        raw_path.unlink()
    else:  # 如果不需要转码
        with mp4_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

    info = db.VideoInfo(
        id=vid,
        title=title,
        filename=mp4_path.name,
        original=file.filename,
        duration=_get_duration(mp4_path),
        url=f"/videos/{mp4_path.name}",  # 本地播放地址
    )
    db.insert_video(info)
    return info


# ------------------------------------------------------
# API：获取视频列表
# ------------------------------------------------------
@app.get("/videos")
def list_videos(
    request: Request,                     # 关键：声明 Request 参数
    response: Response,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    accept: str | None = Header(None),
):
    response.headers["Cache-Control"] = "no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    skip = (page - 1) * pageSize
    videos = db.list_videos_paged(skip=skip, limit=pageSize)
    total = db.get_videos_count()

    total_pages = (total + pageSize - 1) // pageSize   # 总页数
    # 如果前端要 JSON，就返回 JSON
    if accept and "application/json" in accept:
        return {
            "videos": videos,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        }


# ------------------------------------------------------
# API：删除
# ------------------------------------------------------
@app.delete("/videos/{vid}")
def delete_video(vid: str):
    ok = db.delete_video(vid)
    if not ok:
        raise HTTPException(404, "视频不存在")

    # 删除STATIC_DIR中的mp4文件
    static_file = CLIPS_DIR / f"{vid}{vedio_suffix}"
    try:
        static_file.unlink()
    except PermissionError:
        import time

        time.sleep(0.5)  # 等待500ms
        static_file.unlink()

    return {"ok": True}


@app.get("/videos/{filename}")
async def stream_video(filename: str, request: Request):
    file_path = CLIPS_DIR / filename
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
            async with aiofiles.open(file_path, "rb") as f:
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
        iter_file(), status_code=status_code, headers=headers, media_type="video/mp4"
    )


# 假设 index.html 和 main.py 放在同一目录
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # with open("index.html", "r", encoding="utf-8") as f:
    #     frontend_html = f.read()  # ← 正确方法名
    # return frontend_html
    return templates.TemplateResponse("index.html", {"request": request})


# ------------------------------------------------------
# 启动
# ------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
