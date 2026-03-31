#!/usr/bin/env python3
"""
Excel 文件上传服务
端口: 5100
上传的 Excel 文件保存到 ./excel/ 目录
"""

import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 配置
PORT = 5100
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'excel')
ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv', 'xlsm', 'xlsb'}

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """首页 - 上传界面 + 文件管理"""
    return '''
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Excel 文件服务</title>
        <style>
            * { box-sizing: border-box; }
            body { font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
            h1 { text-align: center; color: #333; }
            .container { display: flex; gap: 20px; }
            .panel { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .upload-box { flex: 1; border: 2px dashed #4CAF50; text-align: center; }
            .file-list-box { flex: 2; }
            .upload-box h2 { color: #4CAF50; margin-top: 0; }
            input[type="file"] { margin: 15px 0; }
            button { background: #4CAF50; color: white; padding: 10px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
            button:hover { background: #45a049; }
            button.download-btn { background: #2196F3; padding: 5px 15px; font-size: 14px; }
            button.download-btn:hover { background: #1976D2; }
            button.delete-btn { background: #f44336; padding: 5px 15px; font-size: 14px; }
            button.delete-btn:hover { background: #d32f2f; }
            .file-table { width: 100%; border-collapse: collapse; margin-top: 15px; }
            .file-table th, .file-table td { padding: 12px 8px; text-align: left; border-bottom: 1px solid #eee; }
            .file-table th { background: #f8f8f8; color: #666; font-weight: normal; }
            .file-table tr:hover { background: #f9f9f9; }
            .file-name { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .msg { margin-top: 15px; padding: 10px; border-radius: 5px; }
            .success { background: #d4edda; color: #155724; }
            .error { background: #f8d7da; color: #721c24; }
            .total-bar { background: #fff3cd; padding: 10px 15px; border-radius: 5px; margin-bottom: 15px; color: #856404; }
            .nav-links { text-align: center; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>📊 Excel 文件管理服务</h1>
        <div class="nav-links">
            <span>📁 存储路径: /root/.openclaw/workspace/excel/</span>
        </div>
        <div class="container">
            <div class="panel upload-box">
                <h2>⬆️ 上传文件</h2>
                <div>支持格式: xls, xlsx, csv, xlsm, xlsb</div>
                <form id="uploadForm" enctype="multipart/form-data" method="post" action="/upload">
                    <input type="file" name="file" id="fileInput" accept=".xls,.xlsx,.csv,.xlsm,.xlsb" required>
                    <br>
                    <button type="submit">上传</button>
                </form>
                <div id="message"></div>
            </div>
            <div class="panel file-list-box">
                <div class="total-bar">📋 共 <span id="totalCount">0</span> 个文件</div>
                <table class="file-table">
                    <thead>
                        <tr>
                            <th>文件名</th>
                            <th>大小</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="fileList"></tbody>
                </table>
            </div>
        </div>
        <script>
            async function loadFiles() {
                const res = await fetch('/files');
                const files = await res.json();
                document.getElementById('totalCount').textContent = files.length;
                const list = document.getElementById('fileList');
                if (!files.length) {
                    list.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#999;">暂无文件</td></tr>';
                    return;
                }
                list.innerHTML = files.map(f => `
                    <tr>
                        <td class="file-name" title="${f.name}">📄 ${f.name}</td>
                        <td>${f.size} KB</td>
                        <td>
                            <button class="download-btn" onclick="window.location.href='/download/${encodeURIComponent(f.name)}'">下载</button>
                            <button class="delete-btn" onclick="deleteFile('${encodeURIComponent(f.name)}')">删除</button>
                        </td>
                    </tr>
                `).join('');
            }
            document.getElementById('uploadForm').onsubmit = async (e) => {
                e.preventDefault();
                const formData = new FormData();
                formData.append('file', document.getElementById('fileInput').files[0]);
                const res = await fetch('/upload', { method: 'POST', body: formData });
                const msg = await res.json();
                const div = document.getElementById('message');
                div.className = 'msg ' + (res.ok ? 'success' : 'error');
                div.textContent = msg.message;
                if (res.ok) { loadFiles(); document.getElementById('fileInput').value = ''; }
            };
            async function deleteFile(name) {
                if (!confirm('确认删除 ' + name + '？')) return;
                const res = await fetch('/delete/' + name, { method: 'DELETE' });
                const msg = await res.json();
                alert(msg.message);
                if (res.ok) loadFiles();
            }
            loadFiles();
        </script>
    </body>
    </html>
    '''

@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传"""
    if 'file' not in request.files:
        return jsonify({'message': '没有文件'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'message': '没有选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'message': '不支持的文件类型，仅支持: xls, xlsx, csv, xlsm, xlsb'}), 400
    
    # 生成安全文件名（保留原名但加唯一前缀防止冲突）
    original_name = secure_filename(file.filename)
    ext = original_name.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex[:8]}_{original_name}"
    
    file_path = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(file_path)
    
    file_size = os.path.getsize(file_path) / 1024  # KB
    
    return jsonify({
        'message': f'上传成功！文件名: {unique_name} ({file_size:.1f} KB)',
        'filename': unique_name,
        'size': file_size
    })

@app.route('/files', methods=['GET'])
def list_files():
    """列出已上传的文件"""
    files = []
    for f in os.listdir(UPLOAD_FOLDER):
        fpath = os.path.join(UPLOAD_FOLDER, f)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath) / 1024
            files.append({'name': f, 'size': f'{size:.1f}'})
    return jsonify(files)

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """下载文件"""
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """删除文件"""
    import urllib.parse
    filename = urllib.parse.unquote(filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'message': f'已删除: {filename}'})
    return jsonify({'message': f'文件不存在: {filename}'}), 404

if __name__ == '__main__':
    print(f"""
╔════════════════════════════════════════════╗
║     Excel 上传服务已启动                    ║
╠════════════════════════════════════════════╣
║  地址: http://localhost:{PORT}               ║
║  保存路径: {UPLOAD_FOLDER}
║  支持格式: xls, xlsx, csv, xlsm, xlsb      ║
╚════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=PORT, debug=False)
