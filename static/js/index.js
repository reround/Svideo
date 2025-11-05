
// 每 30 秒自动刷新一次
// setInterval(loadVideoList, 30_000);

const API_BASE_URL = 'http://192.168.3.94:8000';
let currentVideoId = null;

/* ========== 分页相关 ========== */
const PAGE_SIZE = 8;               // 每页条数，可自行调整
let page = 1;                      // 当前页码
let totalPages = 1;                // 总页数


/* 初次加载 */
window.addEventListener('load', () => loadVideoList(1));

// 添加跳转到指定页的函数
function gotoPage() {
    const input = document.getElementById('gotoPageInput');
    const targetPage = parseInt(input.value);
    
    if (isNaN(targetPage) || targetPage < 1 || targetPage > totalPages) {
        showMessage('请输入有效的页码', 'error');
        return;
    }
    
    loadVideoList(targetPage);
    input.value = '';
}

// 修改loadVideoList函数，确保页码输入框的值正确更新
async function loadVideoList(targetPage = page) {
    try {
        const res = await fetch(
        `${API_BASE_URL}/videos?page=${targetPage}&pageSize=${PAGE_SIZE}`,
        {
            headers: { Accept: 'application/json' }  // 关键
        }
        );
        const data = await res.json();
        const videos = data.videos || data;
        const total = data.total || videos.length;

        totalPages = Math.ceil(total / PAGE_SIZE) || 1;
        page = targetPage;

        // 渲染列表
        const box = document.getElementById('videoList');
        if (!videos.length) {
            box.innerHTML = '<div class="loading">暂无视频，请上传一些视频！</div>';
        } else {
            box.innerHTML = videos.map(v => `
                <div class="video-card" onclick="playVideo('${v.id}','${v.title}','${v.filename}')">
                <div class="video-thumbnail">🎥</div>
                <div class="video-info">
                    <div class="video-title">${v.title}</div>
                    <div class="video-duration">时长: ${v.duration||'未知'}</div>
                </div>
                </div>`).join('');
        }

        // 更新分页栏
        document.getElementById('curPage').textContent = page;
        document.getElementById('totalPages').textContent = totalPages;
        document.getElementById('btnPrev').disabled = page <= 1;
        document.getElementById('btnNext').disabled = page >= totalPages;
        
        // 更新跳转输入框的最大值
        document.getElementById('gotoPageInput').max = totalPages;
    } catch (e) {
        console.error('加载视频列表失败:', e);
        showMessage('加载失败: ' + (e.message||e), 'error');
    }
}
// 添加在现有 script 标签内
async function handleBatchUpload(files) {
    const progressBar = document.getElementById('batchProgress');
    const progressText = document.getElementById('batchProgressText');
    
    progressBar.style.display = 'block';
    progressText.style.width = '100%';
    
    let completed = 0;
    const total = files.length;
    progressText.textContent = `${completed}/${total}`;
    
    for (const file of files) {
        if (!file.type.startsWith('video/')) continue;
        
        const formData = new FormData();
        formData.append('file', file);
        // 使用文件名作为标题（去除扩展名）
        formData.append('title', file.name.replace(/\.[^/.]+$/, ""));
        
        try {
            const response = await fetch(`${API_BASE_URL}/upload`, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                console.error(`上传 ${file.name} 失败`);
            }
        } catch (error) {
            console.error(`上传 ${file.name} 失败:`, error);
        }
        
        completed++;
        progressText.textContent = `${completed}/${total}`;
    }
    
    progressBar.style.display = 'none';
    showMessage(`批量上传完成！成功上传 ${completed} 个视频`);
    loadVideoList();
}

// 添加文件夹选择事件监听
document.getElementById('folderInput').addEventListener('change', async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;
    
    if (!confirm(`确定要上传 ${files.length} 个视频文件吗？`)) {
        e.target.value = '';
        return;
    }
    
    await handleBatchUpload(files);
    e.target.value = '';
});

/* 翻页按钮 */
function changePage(delta) {
    const next = page + delta;
    if (next < 1 || next > totalPages) return;
    loadVideoList(next);
}

// 显示消息
function showMessage(message, type = 'success') {
    console.log(message);
    const messageEl = document.getElementById('message');
    messageEl.textContent = message;
    messageEl.className = `message ${type}`;
    messageEl.style.display = 'block';
    setTimeout(() => {
        messageEl.style.display = 'none';
    }, 3000);
}

// 播放视频
function playVideo(id, title, filename) {
    currentVideoId = id;
    const playerContainer = document.getElementById('videoPlayerContainer');
    const player = document.getElementById('videoPlayer');
    const titleEl = document.getElementById('currentVideoTitle');
    
    titleEl.textContent = title;
    player.src = `${API_BASE_URL}/videos/${filename}`;
    playerContainer.style.display = 'block';
    
    // 滚动到播放器
    playerContainer.scrollIntoView({ behavior: 'smooth' });
}

// 关闭播放器
function closePlayer() {
    const playerContainer = document.getElementById('videoPlayerContainer');
    const player = document.getElementById('videoPlayer');
    
    player.pause();
    player.src = '';
    playerContainer.style.display = 'none';
    currentVideoId = null;
}

// 删除当前视频
async function deleteCurrentVideo() {
    if (!currentVideoId) return;
    
    if (!confirm('确定要删除这个视频吗？')) return;
    
    // 先停播并释放文件句柄
    const willRemovId =  currentVideoId;

    const player = document.getElementById('videoPlayer');
    player.pause();
    player.src = '';
    player.load();          // 关键：让浏览器释放文件占用
    closePlayer();

    try {
        const response = await fetch(`${API_BASE_URL}/videos/${willRemovId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showMessage('视频删除成功');
            closePlayer();
            await loadVideoList(); // 确保列表更新完成
        } else {
            throw new Error('删除请求失败');
        }
    } catch (error) {
        console.error('删除视频失败:', error);
        showMessage('删除视频失败', 'error');
        // 如果删除失败，尝试恢复播放
        if (player.src) {
            player.load();
        }
    }
}

// 上传视频
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const fileInput = document.getElementById('videoFile');
    const titleInput = document.getElementById('videoTitle');
    const file = fileInput.files[0];
    const title = titleInput.value;
    
    if (!file || !title) {
        showMessage('请选择视频文件并输入标题', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);

    const progressBar = document.getElementById('progressBar');
    const progress = document.getElementById('progress');
    
    progressBar.style.display = 'block';
    progress.style.width = '0%';
    progress.textContent = '0%';

    try {
        const xhr = new XMLHttpRequest();
        
        // 监听上传进度
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progress.style.width = percentComplete + '%';
                progress.textContent = Math.round(percentComplete) + '%';
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status === 200) {
                showMessage('视频上传成功！');
                fileInput.value = '';
                titleInput.value = '';
                progressBar.style.display = 'none';
                loadVideoList();
            } else {
                showMessage('视频上传失败', 'error');
                progressBar.style.display = 'none';
            }
        });

        xhr.addEventListener('error', () => {
            showMessage('视频上传失败', 'error');
            progressBar.style.display = 'none';
        });

        xhr.open('POST', `${API_BASE_URL}/upload`);
        xhr.send(formData);
    } catch (error) {
        console.error('上传失败:', error);
        showMessage('视频上传失败', 'error');
        progressBar.style.display = 'none';
    }
});

// 页面加载完成后加载视频列表
window.addEventListener('load', () => {
    loadVideoList();
});