#!/usr/bin/env python3
"""中国动物查询HTTP服务 - 完整版"""
import os, io, json
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, send_from_directory
import pymysql, hashlib
from PIL import Image
from datetime import datetime as dt

app = Flask(__name__)
app.secret_key = 'animal_server_secret_key_2026'
UPLOAD_FOLDER = '/root/.openclaw/workspace/animal_photos'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    return pymysql.connect(host='localhost', user='root', password='OpenClaw@2026', database='openclaw_db', charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in {'png','jpg','jpeg','gif','webp'}

def compress_image(stream, max_size=(1200,1200), quality=75):
    img = Image.open(stream)
    if img.mode in ('RGBA','P','LA'):
        bg = Image.new('RGB', img.size, (255,255,255))
        bg.paste(img, mask=img.split()[-1] if img.mode=='RGBA' else None)
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail(max_size, Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=quality, optimize=True)
    out.seek(0)
    return out

# ==================== 登录页 ====================
LOGIN_HTML = '''<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>登录</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(135deg,#1a73e8,#0d47a1);min-height:100vh;display:flex;align-items:center;justify-content:center}
.b{background:white;border-radius:20px;padding:40px;width:90%;max-width:360px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}
.b h1{text-align:center;color:#1a73e8;font-size:24px;margin-bottom:8px}
.b>p{text-align:center;color:#666;font-size:14px;margin-bottom:30px}
.g{margin-bottom:20px}
.g label{display:block;font-size:14px;color:#333;margin-bottom:8px;font-weight:500}
.g input{width:100%;padding:14px 16px;border:1px solid #ddd;border-radius:12px;font-size:15px}
.g input:focus{outline:none;border-color:#1a73e8;box-shadow:0 0 0 3px rgba(26,115,232,0.1)}
.btn{width:100%;padding:14px;background:#1a73e8;color:white;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer}
.btn:hover{background:#1557b0}
.e{color:#d32f2f;font-size:13px;text-align:center;margin-bottom:15px}
</style></head>
<body>
<div class="b"><h1>🐼 中国动物查询</h1><p>请登录后查询</p>
{%if e%}<div class="e">{{e}}</div>{%endif%}
<form method="POST">
<div class="g"><label>用户名</label><input name="username" placeholder="请输入用户名" required></div>
<div class="g"><label>密码</label><input type="password" name="password" placeholder="请输入密码" required></div>
<button type="submit" class="btn">登 录</button>
</form>
</div></body></html>'''

# ==================== 主页 ====================
LIST_HTML = '''<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>中国动物查询</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f5f5f5;min-height:100vh}
h1{font-size:18px}a{text-decoration:none}
.hd{background:linear-gradient(135deg,#1a73e8,#0d47a1);color:white;padding:14px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,0.15)}
.hd h1{font-weight:600}
.abtn{padding:8px 14px;background:rgba(255,255,255,0.2);color:white;border:none;border-radius:20px;font-size:13px}
.sch{padding:12px;background:white}
.sch input{width:100%;padding:12px 16px;border:1px solid #ddd;border-radius:24px;font-size:15px;outline:none;background:#f8f9fa}
.fil{display:flex;gap:8px;padding:12px;overflow-x:auto;background:white;-webkit-overflow-scrolling:touch}
.fil::-webkit-scrollbar{display:none}
.tag{flex-shrink:0;padding:8px 16px;border-radius:20px;font-size:13px;border:1px solid #ddd;background:white;color:#333}
.tag.active{background:#1a73e8;color:white;border-color:#1a73e8}
.lst{padding:12px}
.card{background:white;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.cn{font-size:17px;font-weight:600;color:#1a1a1a}
.lt{font-size:12px;color:#999;font-style:italic;margin-top:2px}
.bd{display:flex;gap:6px;margin-top:4px}
.bl{padding:4px 10px;border-radius:12px;font-size:11px}
.rd{background:#ffebee;color:#d32f2f}
.gr{background:#e8f5e9;color:#388e3c}
.bl2{background:#e3f2fd;color:#1565c0}
.info{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;color:#666;margin-top:10px}
.info span{color:#333;font-weight:500}
.ft{margin-top:10px;padding-top:10px;border-top:1px solid #f0f0f0;font-size:13px;color:#666}
.btns{display:flex;gap:8px;margin-top:12px}
.btn1{flex:1;padding:10px;background:#1a73e8;color:white;border:none;border-radius:24px;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px}
.btn1:hover{background:#1557b0}
.btn2{flex:1;padding:10px;background:#4caf50;color:white;border:none;border-radius:24px;font-size:14px;cursor:pointer}
.btn2:hover{background:#388e3c}
.pg{display:flex;justify-content:center;gap:8px;padding:16px;flex-wrap:wrap}
.pg a{min-width:44px;height:36px;display:flex;align-items:center;justify-content:center;background:white;border-radius:8px;font-size:14px;color:#333;text-decoration:none;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
.pg a.cur{background:#1a73e8;color:white}
.pg a.off{opacity:0.4;pointer-events:none}
@media(min-width:768px){.wrap{max-width:600px;margin:0 auto;background:#f5f5f5;min-height:100vh}}
</style></head>
<body>
<div class="wrap">
<div class="hd"><h1>🐼 中国动物查询</h1><a href="/my-sightings" class="abtn">📋 我见过({{sc}})</a></div>
<div class="sch"><input id="kw" placeholder="搜索名称或学名..." value="{{kw or ''}}"></div>
<div class="fil">
<a class="tag {{'active' if not ct else ''}}" href="/?page=1&kw={{kw}}&ct=&ed={{ed}}">全部</a>
<a class="tag {{'active' if ct=='哺乳动物' else ''}}" href="/?page=1&kw={{kw}}&ct=哺乳动物&ed={{ed}}">哺乳</a>
<a class="tag {{'active' if ct=='鸟类' else ''}}" href="/?page=1&kw={{kw}}&ct=鸟类&ed={{ed}}">鸟类</a>
<a class="tag {{'active' if ct=='爬行动物' else ''}}" href="/?page=1&kw={{kw}}&ct=爬行动物&ed={{ed}}">爬行</a>
<a class="tag {{'active' if ct=='两栖动物' else ''}}" href="/?page=1&kw={{kw}}&ct=两栖动物&ed={{ed}}">两栖</a>
<a class="tag {{'active' if ed=='1' else ''}}" href="/?page=1&kw={{kw}}&ct={{ct}}&ed=1">⚠️濒危</a>
</div>
<div class="lst">
{%if animals%}
{%for a in animals%}
<div class="card">
<div class="cn">{{a.name_cn}}</div>
<div class="lt">{{a.scientific_name or ''}}</div>
<div class="bd">
{%if a.is_seen%}<span class="bl bl2">✓已见过</span>{%endif%}
<span class="bl {{'rd' if a.is_endangered else 'gr'}}">{{'⚠️濒危' if a.is_endangered else '✅安全'}}</span>
</div>
<div class="info">
<div>纲：<span>{{a.class or '-'}}</span></div><div>目：<span>{{a.order_name or '-'}}</span></div>
<div>科：<span>{{a.family or '-'}}</span></div><div>属：<span>{{a.genus or '-'}}</span></div>
<div>种：<span>{{a.species or '-'}}</span></div><div>亚种：<span>{{a.subspecies or '-'}}</span></div>
</div>
<div class="ft">📍 {{a.region or '分布未知'}}</div>
<div class="btns">
<button class="btn1" onclick="showDetail({{a.id}},'{{a.name_cn}}','{{a.scientific_name or ''}}','{{a.class or ''}}','{{a.order_name or ''}}','{{a.family or ''}}','{{a.genus or ''}}','{{a.species or ''}}','{{a.subspecies or ''}}','{{a.category or ''}}','{{(a.feature or '')|replace("'","\\'")}}','{{(a.region or '')|replace("'","\\'")}}','{{(a.description or '')|replace("'","\\'")}}','{{'⚠️濒危' if a.is_endangered else '✅安全'}}')">🔍 查看详情</button>
<button class="{{'btn2' if a.is_seen else 'btn1'}}" onclick="toggleSeen({{a.id}},'{{a.name_cn}}',this)">{{'✓ 已见过' if a.is_seen else '📍 标记见过'}}</button>
</div>
</div>
{%endfor%}
{%else%}
<div style="text-align:center;padding:60px 20px;color:#999;font-size:15px;">
<div style="font-size:48px;margin-bottom:16px;">🔍</div>
<div>没查到"{{kw or ''}}"相关的动物</div>
<div style="font-size:13px;margin-top:8px;color:#bbb;">试试其他关键词</div>
</div>
{%endif%}
</div>
{%if pg>1%}
<div class="pg">
<a class="{{'off' if p<=1 else ''}}" href="/?page={{p-1 if p>1 else 1}}&kw={{kw}}&ct={{ct}}&ed={{ed}}">‹</a>
{%for i in range(1,pg+1)%}{%if i>=p-2 and i<=p+2%}<a class="{{'cur' if i==p else ''}}" href="/?page={{i}}&kw={{kw}}&ct={{ct}}&ed={{ed}}">{{i}}</a>{%endif%}{%endfor%}
<a class="{{'off' if p>=pg else ''}}" href="/?page={{p+1 if p<pg else pg}}&kw={{kw}}&ct={{ct}}&ed={{ed}}">›</a>
</div>
{%endif%}
</div>

<!--详情弹窗-->
<div id="detailModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:200;align-items:center;justify-content:center;overflow-y:auto;padding:20px;">
<div style="background:white;border-radius:16px;padding:24px;width:100%;max-width:480px;max-height:90vh;overflow-y:auto;">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
<h3 id="detTitle" style="font-size:18px;font-weight:600;color:#1a1a1a"></h3>
<span onclick="closeDetail()" style="font-size:24px;color:#999;cursor:pointer;padding:5px;">×</span>
</div>
<div id="detBody" style="font-size:14px;color:#333;line-height:1.8;"></div>
</div></div>

<!--上传弹窗-->
<div id="upModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:200;align-items:center;justify-content:center;">
<div style="background:white;border-radius:16px;padding:24px;width:90%;max-width:400px;">
<h3 id="upTitle" style="margin-bottom:16px;font-size:17px;">📸 标记见过</h3>
<form id="upForm" enctype="multipart/form-data">
<div style="margin-bottom:16px;">
<label style="display:block;padding:20px;border:2px dashed #ddd;border-radius:12px;text-align:center;cursor:pointer;background:#f8f9fa;">
<input type="file" id="upPhoto" name="photo" accept="image/*" style="display:none;">
<span id="upLabel" style="font-size:14px;color:#666;">📷 点击选择照片（支持拍照或相册）</span>
</label></div>
<textarea name="note" placeholder="写点什么..." style="width:100%;height:60px;border:1px solid #ddd;border-radius:8px;padding:10px;font-size:14px;resize:none;margin-bottom:12px;box-sizing:border-box;"></textarea>
<input type="hidden" id="upId" name="animal_id" value="">
<div style="display:flex;gap:10px;">
<button type="button" onclick="closeUp()" style="flex:1;padding:12px;border:1px solid #ddd;border-radius:8px;background:white;cursor:pointer;">取消</button>
<button type="submit" style="flex:1;padding:12px;background:#1a73e8;color:white;border:none;border-radius:8px;cursor:pointer;">确认</button>
</div></form>
</div></div>

<script>
var st;
var searchInput=document.getElementById('kw');searchInput.addEventListener('input',function(){var v=this.value;clearTimeout(st);st=setTimeout(function(){location.href='/?page=1&kw='+encodeURIComponent(v)+'&ct={{ct}}&ed={{ed}}'},600);searchInput.value=v;});
document.getElementById('upPhoto').addEventListener('change',function(){var f=this.files[0];document.getElementById('upLabel').textContent=f?'✓ '+f.name:'📷 点击选择照片（支持拍照或相册）';});
function showDetail(id,cn,ln,cl,od,fa,ge,sp,sb,ct,ft,rg,ds,st2){
var h='<div style="margin-bottom:12px;"><span style="font-size:24px;font-weight:600">'+cn+'</span> <span style="color:'+(st2=='⚠️濒危'?'#d32f2f':'#388e3c')+';font-size:13px">'+st2+'</span></div>';
h+='<div style="font-size:13px;color:#999;font-style:italic;margin-bottom:16px;">'+ln+'</div>';
h+='<div style="background:#f8f9fa;border-radius:10px;padding:14px;margin-bottom:12px;">';
h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">';
h+='<div><b>界：</b>动物界</div><div><b>门：</b>脊索动物门</div>';
h+='<div><b>纲：</b>'+cl+'</div><div><b>目：</b>'+od+'</div>';
h+='<div><b>科：</b>'+fa+'</div><div><b>属：</b>'+ge+'</div>';
h+='<div><b>种：</b>'+sp+'</div><div><b>亚种：</b>'+sb+'</div>';
h+='<div><b>大类：</b>'+ct+'</div></div></div>';
if(ft&&ft!='None')h+='<div style="margin-bottom:12px;"><b style="color:#1a73e8">特征：</b>'+ft+'</div>';
if(rg&&rg!='None')h+='<div style="margin-bottom:12px;"><b style="color:#1a73e8">分布：</b>'+rg+'</div>';
if(ds&&ds!='None')h+='<div style="margin-bottom:12px;"><b style="color:#1a73e8">描述：</b>'+ds+'</div>';
document.getElementById('detTitle').textContent=cn;
document.getElementById('detBody').innerHTML=h;
document.getElementById('detailModal').style.display='flex';
}
function closeDetail(){document.getElementById('detailModal').style.display='none';}
function toggleSeen(id,cn,btn){
if(btn.classList.contains('btn2')){if(confirm('取消见过标记？'))fetch('/api/unseen/'+id,{method:'POST'}).then(r=>r.json()).then(d=>{if(d.ok)location.reload()});}
else{document.getElementById('upTitle').textContent='📸 标记见过 "'+cn+'"';document.getElementById('upId').value=id;document.getElementById('upLabel').textContent='📷 点击选择照片（支持拍照或相册）';document.getElementById('upModal').style.display='flex';}}
function closeUp(){document.getElementById('upModal').style.display='none';}
document.getElementById('upForm').addEventListener('submit',function(e){e.preventDefault();var fd=new FormData(this);fetch('/api/seen',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{if(d.ok){alert('已记录！');location.reload();}else alert(d.error||'失败')});});
</script></body></html>'''

# ==================== 我见过的页面(树状图) ====================
SEEN_HTML = '''<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>我见过的动物</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f5f5f5;min-height:100vh}
h1{font-size:18px}a{text-decoration:none}
.hd{background:linear-gradient(135deg,#1a73e8,#0d47a1);color:white;padding:14px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,0.15)}
.hd h1{font-weight:600}
.bk{padding:8px 14px;background:rgba(255,255,255,0.2);color:white;border:none;border-radius:20px;font-size:13px}
.tr{padding:12px}
.nd{margin-bottom:6px}
.nh{display:flex;align-items:center;padding:11px 14px;background:white;border-radius:10px;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,0.06);user-select:none}
.nh:hover{background:#f8f9fa}
.ar{font-size:11px;margin-right:8px;transition:transform .2s;display:inline-block}
.ar.o{transform:rotate(90deg)}
.ico{margin-right:8px;font-size:16px}
.lb{flex:1;font-size:15px;font-weight:600;color:#1a1a1a}
.cnt{background:#e3f2fd;color:#1565c0;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:500}
.ch{padding-left:18px;margin-top:4px}
.ch.o{display:block}
.sub{display:flex;align-items:center;padding:9px 14px;background:#fafafa;border-radius:8px;margin-bottom:3px;cursor:pointer;font-size:14px;transition:background .15s}
.sub:hover{background:#eee}
.dot{width:7px;height:7px;border-radius:50%;margin-right:9px;flex-shrink:0;background:#4caf50}
.dot.no{background:#ccc}
.nm{flex:1;font-size:14px;font-weight:normal}
.has{margin-left:auto;margin-right:8px;font-size:12px;color:#4caf50}
.tm{font-size:12px;color:#999}
.det{display:none;padding:16px;background:white;border-radius:12px;margin-bottom:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1)}
.det.o{display:block}
.det-h{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.dn{font-size:17px;font-weight:600;color:#1a1a1a}
.dlt{font-size:12px;color:#999;font-style:italic;margin-top:2px}
.dtm{font-size:12px;color:#666}
.dnt{font-size:14px;color:#555;margin:8px 0;line-height:1.5}
.dph{width:100%;border-radius:8px;margin-top:8px;cursor:pointer}
.dac{display:flex;gap:10px;margin-top:12px}
.dab{flex:1;padding:10px;border:1px solid #ddd;border-radius:8px;background:white;font-size:13px;cursor:pointer;text-align:center}
.dab.dl{color:#d32f2f;border-color:#ffcdd2;background:#fff5f5}
.x{font-size:22px;color:#999;cursor:pointer;padding:5px;float:right}
.empty{text-align:center;padding:60px 20px;color:#999}
.empty-e{font-size:48px;margin-bottom:16px}
#viewer{position:fixed;inset:0;background:rgba(0,0,0,0.9);z-index:300;display:none;align-items:center;justify-content:center;flex-direction:column}
#viewer img{max-width:95%;max-height:80vh;border-radius:8px}
#viewer .xv{position:absolute;top:15px;right:20px;color:white;font-size:32px;cursor:pointer;width:40px;height:40px;text-align:center;line-height:40px}
@media(min-width:768px){.wrap{max-width:600px;margin:0 auto;background:#f5f5f5;min-height:100vh}}
</style>
</head>
<body>
<div class="wrap">
<div class="hd"><h1>🌳 我见过的动物({{total}})</h1><a href="/" class="bk">返回</a></div>
{%if tree%}
<div class="tr">
{%for cls_name, orders_list in tree.items()%}
<div class="nd">
<div class="nh" onclick="t(this)"><span class="ar">▶</span><span class="ico">🐾</span><span class="lb">{{cls_name}}</span><span class="cnt">{{orders_list|length}}</span></div>
<div class="ch">
{%for od in orders_list%}
<div class="nd">
<div class="nh" onclick="t(this)"><span class="ar">▶</span><span class="ico">📂</span><span class="lb">{{od.order_name}}</span><span class="cnt">{{od.count}}</span></div>
<div class="ch">
{%for fa in od.families%}
<div class="nd">
<div class="nh" onclick="t(this)"><span class="ar">▶</span><span class="ico">📁</span><span class="lb">{{fa.family}}</span><span class="cnt">{{fa.count}}</span></div>
<div class="ch">
{%for ge in fa.genera%}
<div class="nd">
<div class="nh" onclick="t(this)"><span class="ar">▶</span><span class="ico">📄</span><span class="lb">{{ge.genus}}</span><span class="cnt">{{ge.count}}</span></div>
<div class="ch">
{%for an in ge.animals%}
<div class="sub" onclick="show({{an.sid}})"><span class="dot{{' no' if not an.photo else ''}}"></span><span class="nm">{{an.name_cn}}</span>{%if an.photo%}<span class="has">📷</span>{%endif%}<span class="tm">{{an.seen_at}}</span></div>
{%endfor%}
</div>
</div>
{%endfor%}
</div>
</div>
{%endfor%}
</div>
</div>
{%endfor%}
</div>
</div>
{%endfor%}
</div>
{%else%}
<div class="empty"><div class="empty-e">🦁</div><div>还没有见过记录</div><div style="font-size:13px;margin-top:8px">去列表页标记吧～</div></div>
{%endif%}
</div>
<div id="det" class="det"></div>
<div id="viewer" onclick="clV()"><span class="xv">×</span><img id="vImg" src=""></div>
<script>
var s={{sjs | safe}};
function t(el){var a=el.querySelector('.ar');var c=el.nextElementSibling;a.classList.toggle('o');c.classList.toggle('o');}
function show(id){var x=s[id];var h='<span class="x" onclick="clDet()">×</span><div class="det-h"><div><div class="dn">'+x.name_cn+'</div><div class="dlt">'+(x.sn||'')+'</div></div><div class="dtm">'+x.seen_at+'</div></div>';if(x.note)h+='<div class="dnt">'+x.note+'</div>';if(x.photo)h+='<img class="dph" src="/photos/'+id+'" onclick="v(\\/photos\\/'+id+'\\/)">';h+='<div class="dac"><button class="dab dl" onclick="del('+id+')">🗑️ 删除</button></div>';document.getElementById('det').innerHTML=h;document.getElementById('det').classList.add('o');document.getElementById('det').scrollIntoView();}
function clDet(){document.getElementById('det').classList.remove('o');}
function v(src){document.getElementById('vImg').src=src;document.getElementById('viewer').style.display='flex';}
function clV(){document.getElementById('viewer').style.display='none';}
function del(id){if(confirm('删除这条记录？'))fetch('/api/sighting/'+id,{method:'DELETE'}).then(r=>r.json()).then(d=>{if(d.ok)location.reload();else alert('失败')});}
</script>
</body></html>'''

@app.route('/login', methods=['GET','POST'])
def login():
    kw = request.args.get('kw', '')
    ct = request.args.get('ct', '')
    ed = request.args.get('ed', '')
    next_page = '/?page=1'
    if kw: next_page += '&kw=' + kw
    if ct: next_page += '&ct=' + ct
    if ed: next_page += '&ed=' + ed
    
    if request.method=='POST':
        u=request.form.get('username','').strip()
        p=request.form.get('password','')
        conn=get_db()
        cur=conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s",(u,))
        user=cur.fetchone()
        cur.close();conn.close()
        if user and user['password_hash']==hash_password(p):
            session['user_id']=user['id']
            session['username']=user['username']
            session['nickname']=user['nickname']
            return redirect(next_page)
        return render_template_string(LOGIN_HTML, e='用户名或密码错误')
    return render_template_string(LOGIN_HTML, e=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session:
        kw = request.args.get('kw', '')
        ct = request.args.get('ct', '')
        ed = request.args.get('ed', '')
        args = ''
        if kw: args += '&kw=' + kw
        if ct: args += '&ct=' + ct
        if ed: args += '&ed=' + ed
        return redirect(url_for('login') + '?page=1' + args if args else url_for('login'))
    page=int(request.args.get('page',1))
    per_page=10
    kw=request.args.get('kw','')
    ct=request.args.get('ct','')
    ed=request.args.get('ed','')
    conn=get_db()
    uid=session['user_id']
    cur=conn.cursor()
    cur.execute("SELECT animal_id FROM user_sightings WHERE user_id=%s",(uid,))
    seen_ids={row['animal_id'] for row in cur.fetchall()}
    sc=len(seen_ids)
    cond,params=[],[]
    if kw:
        cond.append("(name_cn LIKE %s OR name_en LIKE %s OR scientific_name LIKE %s)")
        params.extend([f'%{kw}%',f'%{kw}%',f'%{kw}%'])
    if ct:cond.append("category=%s");params.append(ct)
    if ed:cond.append("is_endangered=%s");params.append(int(ed))
    whr=' AND '.join(cond) if cond else '1=1'
    cur.execute(f"SELECT COUNT(*) as c FROM animal WHERE {whr}",params)
    total=cur.fetchone()['c']
    pages=max(1,(total+per_page-1)//per_page)
    page=min(max(1,page),pages)
    offset=(page-1)*per_page
    cur.execute(f"SELECT * FROM animal WHERE {whr} ORDER BY id LIMIT {per_page} OFFSET {offset}",params)
    animals=[]
    for row in cur.fetchall():
        row['is_seen']=row['id'] in seen_ids
        animals.append(row)
    cur.close();conn.close()
    return render_template_string(LIST_HTML,animals=animals,p=page,pg=pages,kw=kw,ct=ct,ed=ed,sc=sc)

@app.route('/my-sightings')
def my_sightings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn=get_db()
    uid=session['user_id']
    cur=conn.cursor()
    cur.execute("""
        SELECT s.id as sid,s.animal_id,s.photo_path,s.note,s.seen_at,
               a.name_cn,a.scientific_name,a.class,a.order_name,a.family,a.genus
        FROM user_sightings s JOIN animal a ON s.animal_id=a.id
        WHERE s.user_id=%s ORDER BY a.class,a.order_name,a.family,a.genus,a.name_cn
    """,(uid,))
    rows=cur.fetchall()
    tree={}
    sjs={}
    for r in rows:
        seen_at=r['seen_at'].strftime('%Y年%m月%d日') if isinstance(r['seen_at'],dt) else str(r['seen_at'])
        an={'sid':r['sid'],'name_cn':r['name_cn'],'photo':bool(r['photo_path']),'seen_at':seen_at}
        sjs[r['sid']]={'name_cn':r['name_cn'],'sn':r['scientific_name'],'seen_at':seen_at,'note':r['note'] or '','photo':bool(r['photo_path'])}
        cls=r['class'] or '未知纲'
        if cls not in tree:tree[cls]=[]
        orders=tree[cls]
        od_name=r['order_name'] or '未知目'
        od=next((x for x in orders if x['order_name']==od_name),None)
        if not od:od={'order_name':od_name,'count':0,'families':[]};orders.append(od)
        od['count']+=1
        families=od['families']
        fa_name=r['family'] or '未知科'
        fa=next((x for x in families if x['family']==fa_name),None)
        if not fa:fa={'family':fa_name,'count':0,'genera':[]};families.append(fa)
        fa['count']+=1
        genera=fa['genera']
        ge_name=r['genus'] or '未知属'
        ge=next((x for x in genera if x['genus']==ge_name),None)
        if not ge:ge={'genus':ge_name,'count':0,'animals':[]};genera.append(ge)
        ge['count']+=1
        ge['animals'].append(an)
    cur.close();conn.close()
    return render_template_string(SEEN_HTML,tree=tree,sjs=json.dumps(sjs),total=len(rows))

@app.route('/api/seen', methods=['POST'])
def api_seen():
    if 'user_id' not in session:return jsonify({'error':'请先登录'}),401
    aid=request.form.get('animal_id',type=int)
    note=request.form.get('note','')
    photo=request.files.get('photo')
    path=None
    if photo and allowed_file(photo.filename):
        c=compress_image(photo.stream)
        fn=f"{session['user_id']}_{aid}_{int(dt.now().timestamp())}.jpg"
        with open(os.path.join(UPLOAD_FOLDER,fn),'wb') as f:f.write(c.read())
        path=fn
    conn=get_db()
    cur=conn.cursor()
    cur.execute("INSERT INTO user_sightings (user_id,animal_id,photo_path,note) VALUES (%s,%s,%s,%s)",(session['user_id'],aid,path,note))
    conn.commit()
    cur.close();conn.close()
    return jsonify({'ok':True})

@app.route('/api/unseen/<int:aid>', methods=['POST'])
def api_unseen(aid):
    if 'user_id' not in session:return jsonify({'error':'请先登录'}),401
    conn=get_db()
    cur=conn.cursor()
    cur.execute("SELECT photo_path FROM user_sightings WHERE user_id=%s AND animal_id=%s",(session['user_id'],aid))
    row=cur.fetchone()
    if row and row['photo_path']:
        p=os.path.join(UPLOAD_FOLDER,row['photo_path'])
        if os.path.exists(p):os.remove(p)
    cur.execute("DELETE FROM user_sightings WHERE user_id=%s AND animal_id=%s",(session['user_id'],aid))
    conn.commit()
    cur.close();conn.close()
    return jsonify({'ok':True})

@app.route('/api/sighting/<int:sid>', methods=['DELETE'])
def api_delete(sid):
    if 'user_id' not in session:return jsonify({'error':'请先登录'}),401
    conn=get_db()
    cur=conn.cursor()
    cur.execute("SELECT photo_path FROM user_sightings WHERE id=%s AND user_id=%s",(sid,session['user_id']))
    row=cur.fetchone()
    if row and row['photo_path']:
        p=os.path.join(UPLOAD_FOLDER,row['photo_path'])
        if os.path.exists(p):os.remove(p)
    cur.execute("DELETE FROM user_sightings WHERE id=%s AND user_id=%s",(sid,session['user_id']))
    conn.commit()
    cur.close();conn.close()
    return jsonify({'ok':True})

@app.route('/photos/<int:sid>')
def get_photo(sid):
    conn=get_db()
    cur=conn.cursor()
    cur.execute("SELECT photo_path FROM user_sightings WHERE id=%s AND user_id=%s",(sid,session.get('user_id')))
    row=cur.fetchone()
    cur.close();conn.close()
    if row and row['photo_path']:
        return send_from_directory(UPLOAD_FOLDER,row['photo_path'])
    return 'not found',404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
