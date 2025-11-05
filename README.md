# Svideo

一个由纯 python 构建的简易视频播放网站，路由、静态资源、模板按业务拆分。

```txt
project_root/
|- data/
|   |- videos/          # 原始上传视频
|   |-thumbnails/       # 自动生成的封面
|   |- clips/           # 切片或转码后片段
|- static/              # 仅放公开静态资源（如网页用logo）
|   |- css/             # css 文件
|   |- js/              # js 文件
|   |- img/             # 图片
|- templates/           # html 模板
│   |- macros/          # html 模板宏
```

## TODO

- [x] 视频播放
- [x] 视频上传
- [x] 视频删除
- [x] 分页跳转
- [ ] 视频搜索
- [ ] 视频分类

## 依赖库（详见 pyproject.toml）

- aiofiles
- fastapi
- ffmpeg-python
- python-multipart
- uvicorn
- ...

## 使用方法

```bash
uv sync
uv run main.py
```
