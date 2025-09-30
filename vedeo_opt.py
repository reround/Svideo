@app.post("/upload_video/", dependencies=[Depends(get_current_active_user)])
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type.startswith("video"):
        raise HTTPException(400, "Not a video")
    if file.size > 100 * 1024 * 1024:
        raise HTTPException(400, "File too large")
    file_path = f"uploads/{uuid4().hex}_{file.filename}"
    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(10 * 1024 * 1024):
            await f.write(chunk)
    # TODO: 异步转码、写库
    return {"video_id": new_id, "msg": "ok"}


@app.get("/hls/{uuid}/index.m3u8")
async def hls_index(uuid: str):
    path = f"hls/{uuid}/index.m3u8"
    if not os.path.exists(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="application/vnd.apple.mpegurl")

@app.get("/download/{video_id}")
async def download(video_id: int, user=Depends(get_current_active_user)):
    vid = crud.get_video(video_id)
    if not vid or not user.can("download"):
        raise HTTPException(403, "No permission")
    return FileResponse(vid.storage_path, filename=vid.title+".mp4",
                        content_disposition="attachment")