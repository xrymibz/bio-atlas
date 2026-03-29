#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""动植物图鉴 - 升级版（动物+植物）"""
import os, io, json, hashlib
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
import pymysql
from PIL import Image
from datetime import datetime as dt

app = Flask(__name__, template_folder='/root/.openclaw/workspace/bio_templates')
app.secret_key = 'bio_guide_secret_2026'
UPLOAD_FOLDER = '/root/.openclaw/workspace/bio_photos'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_CONFIG = dict(host='localhost', user='root', password='OpenClaw@2026',
                 database='openclaw_db', charset='utf8mb4',
                 cursorclass=pymysql.cursors.DictCursor)

PLANTS_DATA = json.load(open('/root/.openclaw/workspace/plants_data.json', encoding='utf-8'))

def get_db():
    return pymysql.connect(**DB_CONFIG)

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def compress_image(stream, max_size=(1200, 1200), quality=78):
    img = Image.open(stream)
    if img.mode in ('RGBA', 'P', 'LA'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail(max_size, Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=quality, optimize=True)
    out.seek(0)
    return out

# Make ICONS available in all templates
app.jinja_env.globals['ICONS'] = {
    "哺乳动物":"🐯","鸟类":"🦅","爬行动物":"🦎","两栖动物":"🐸","鱼类":"🐟","昆虫":"🦋",
    "裸子植物":"🌲","被子植物·乔木":"🌳","被子植物·灌木":"🌿","被子植物·草本":"🌱"
}

ICONS = {
    "哺乳动物":"🐯","鸟类":"🦅","爬行动物":"🦎","两栖动物":"🐸","鱼类":"🐟","昆虫":"🦋",
    "裸子植物":"🌲","被子植物·乔木":"🌳","被子植物·灌木":"🌿","被子植物·草本":"🌱"
}

@app.template_filter('icon')
def icon_filter(cat):
    return ICONS.get(cat, '')

@app.template_global()
def global_icons():
    return ICONS

# =====================================================================
# 路由
# =====================================================================

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (u,))
        user = cur.fetchone()
        cur.close(); conn.close()
        if user and user['password_hash'] == hash_password(p):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/')
        return render_template('login.html', e='用户名或密码错误')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')
    page = int(request.args.get('p', 1))
    per_page = 10
    kw = request.args.get('kw', '')
    ct = request.args.get('ct', '')
    ed = request.args.get('ed', '')
    org = request.args.get('org', 'animal')  # animal or plant
    uid = session['user_id']

    # 我见过的ID集合
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT organism_id FROM user_sightings WHERE user_id=%s", (uid,))
    seen_ids = {str(row['organism_id']) for row in cur.fetchall()}

    items = []
    cats = []

    if org == 'animal':
        # 动物：从数据库
        cond, params = [], []
        if kw:
            cond.append("(name_cn LIKE %s OR name_en LIKE %s OR scientific_name LIKE %s)")
            params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%'])
        if ct: cond.append("category=%s"); params.append(ct)
        if ed: cond.append("is_endangered=%s"); params.append(int(ed))
        whr = ' AND '.join(cond) if cond else '1=1'
        cur.execute(f"SELECT COUNT(*) as c FROM animal WHERE {whr}", params)
        total = cur.fetchone()['c']
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(max(1, page), pages)
        offset = (page - 1) * per_page
        cur.execute(f"SELECT * FROM animal WHERE {whr} ORDER BY id LIMIT {per_page} OFFSET {offset}", params)
        for row in cur.fetchall():
            row = dict(row)
            row['org_type'] = 'animal'
            row['is_seen'] = str(row['id']) in seen_ids
            items.append(row)
        cur.execute("SELECT DISTINCT category FROM animal ORDER BY category")
        cats = [r['category'] for r in cur.fetchall()]

    else:
        # 植物：从数据库 plants 表
        cond, params = [], []
        if kw:
            cond.append("(name_cn LIKE %s OR name_en LIKE %s OR scientific_name LIKE %s)")
            params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%'])
        if ct: cond.append("category=%s"); params.append(ct)
        if ed: cond.append("is_endangered=%s"); params.append(int(ed))
        whr = ' AND '.join(cond) if cond else '1=1'
        cur.execute(f"SELECT COUNT(*) as c FROM plants WHERE {whr}", params)
        total = cur.fetchone()['c']
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(max(1, page), pages)
        offset = (page - 1) * per_page
        cur.execute(f"SELECT * FROM plants WHERE {whr} ORDER BY class_name, family, genus LIMIT {per_page} OFFSET {offset}", params)
        for row in cur.fetchall():
            row = dict(row)
            row['org_type'] = 'plant'
            row['id'] = row['name_cn']
            row['is_seen'] = row['name_cn'] in seen_ids
            items.append(row)
        cur.execute("SELECT DISTINCT category FROM plants ORDER BY category")
        cats = [r['category'] for r in cur.fetchall()]

    sc = len(seen_ids)
    cur.close(); conn.close()
    return render_template('index.html', items=items, p=page, pg=pages, kw=kw, ct=ct, ed=ed, org_type=org, cats=cats, sc=sc)

@app.route('/my-sightings')
def my_sightings():
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    # 动物 sighting
    cur.execute("""
        SELECT s.id as sid, s.organism_id, s.photo_path, s.note, s.seen_at, 'animal' as organism_type,
               a.name_cn, a.scientific_name, a.kingdom, a.phylum, a.class,
               a.order_name, a.family, a.genus, a.species, a.category
        FROM user_sightings s
        JOIN animal a ON s.organism_type='animal' AND s.organism_id=a.id
        WHERE s.user_id=%s
    """, (uid,))
    animal_rows = cur.fetchall()
    # 植物 sighting：从数据库 plants 表
    cur.execute("""
        SELECT s.id as sid, s.organism_id, s.photo_path, s.note, s.seen_at, 'plant' as organism_type,
               p.name_cn, p.scientific_name, p.kingdom, p.phylum, p.class_name as class,
               p.order_name, p.family, p.genus, p.species, p.category
        FROM user_sightings s
        JOIN plants p ON s.organism_id = p.name_cn
        WHERE s.user_id=%s AND s.organism_type='plant'
    """, (uid,))
    plant_rows = cur.fetchall()
    all_rows = animal_rows + plant_rows

    sjs = {}
    ttree = {}
    KINGDOM_ICON = {"动物界":"🐾","植物界":"🌱"}

    for r in all_rows:
        seen_at = r['seen_at'].strftime('%Y年%m月%d日') if isinstance(r['seen_at'], dt) else str(r['seen_at'])
        sid = r['sid']
        name_cn = r['name_cn'] or '未知'
        sjs[sid] = {'name_cn': name_cn, 'scientific_name': r.get('scientific_name',''),
                     'seen_at': seen_at, 'note': r['note'] or '', 'photo': bool(r['photo_path']),
                     'category': r.get('category') or '动物', 'org_type': r.get('organism_type') or 'animal'}
        # 植物 kingdom 归一为"植物界"
        phylum = r.get('phylum') or ''
        if phylum in ('松柏门','被子植物门','苏铁门','银杏门'):
            kingdom = '植物界'
        else:
            kingdom = '动物界'
        phylum = phylum or '未知门'
        cls     = (r.get('class') or '未知纲').replace('被子植物·','')
        order   = r.get('order_name') or '未知目'
        family  = r.get('family') or '未知科'
        genus   = r.get('genus') or '未知属'
        species = name_cn

        ttree.setdefault(kingdom, {}).setdefault(phylum, {}).setdefault(cls, {}).setdefault(order, {}).setdefault(family, {}).setdefault(genus, []).append({
            'sid': sid, 'name_cn': species,
            'scientific_name': r.get('scientific_name',''),
            'photo': bool(r['photo_path']), 'seen_at': seen_at,
            'category': r.get('category') or '动物',
            'org_type': r.get('organism_type') or 'animal'
        })

    # 构建前端树
    def build_tree():
        result = []
        for kingdom in sorted(ttree.keys(), key=lambda x: ('动物' in x, x)):
            children1 = []
            for phylum in sorted(ttree[kingdom].keys()):
                children2 = []
                for cls in sorted(ttree[kingdom][phylum].keys()):
                    children3 = []
                    for order in sorted(ttree[kingdom][phylum][cls].keys()):
                        children4 = []
                        for family in sorted(ttree[kingdom][phylum][cls][order].keys()):
                            genus_dict = ttree[kingdom][phylum][cls][order][family]
                            genus_nodes = []
                            for genus in sorted(genus_dict.keys()):
                                items = genus_dict[genus]
                                leaf_nodes = [{'type':'sighting','name':it['name_cn'],'category':it['category'],
                                               'sid':it['sid'],'photo':it['photo'],
                                               'seen_at':it['seen_at'],'org_type':it['org_type']} for it in items]
                                genus_nodes.append({'type':'genus','name':genus,
                                                    'count':len(items),'children':leaf_nodes})
                            children4.append({"type":"family","name":family,
                                              "count":sum(g["count"] for g in genus_nodes),"children":genus_nodes})
                        children3.append({'type':'order','name':order,'count':sum(c['count'] for c in children4),'children':children4})
                    children2.append({'type':'order','name':cls,'count':sum(c['count'] for c in children3),'children':children3})
                children1.append({'type':'phylum','name':phylum,'count':sum(c['count'] for c in children2),'children':children2})
            result.append({'type':'kingdom','name':kingdom,'icon':KINGDOM_ICON.get(kingdom,'📂'),'count':sum(c['count'] for c in children1),'children':children1})
        return result

    tree_list = build_tree()
    total = len(all_rows)
    cur.close(); conn.close()
    return render_template('seen.html', tree=tree_list, sjs=json.dumps(sjs), total=total)


@app.route('/mindmap')
def mindmap():
    """脑图模式 - XMind风格展示我见过的动植物"""
    if 'user_id' not in session:
        return redirect('/login')
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    # 动物 sighting
    cur.execute("""
        SELECT s.id as sid, s.organism_id, s.photo_path, s.note, s.seen_at, 'animal' as organism_type,
               a.name_cn, a.scientific_name, a.kingdom, a.phylum, a.class,
               a.order_name, a.family, a.genus, a.species, a.category
        FROM user_sightings s
        JOIN animal a ON s.organism_type='animal' AND s.organism_id=a.id
        WHERE s.user_id=%s
    """, (uid,))
    animal_rows = cur.fetchall()
    # 植物 sighting
    cur.execute("""
        SELECT s.id as sid, s.organism_id, s.photo_path, s.note, s.seen_at, 'plant' as organism_type,
               p.name_cn, p.scientific_name, p.kingdom, p.phylum, p.class_name as class,
               p.order_name, p.family, p.genus, p.species, p.category
        FROM user_sightings s
        JOIN plants p ON s.organism_id = p.name_cn
        WHERE s.user_id=%s AND s.organism_type='plant'
    """, (uid,))
    plant_rows = cur.fetchall()
    all_rows = animal_rows + plant_rows

    sjs = {}
    ttree = {}
    KINGDOM_ICON = {"动物界":"🐾","植物界":"🌱"}

    for r in all_rows:
        seen_at = r['seen_at'].strftime('%Y年%m月%d日') if isinstance(r['seen_at'], dt) else str(r['seen_at'])
        sid = r['sid']
        name_cn = r['name_cn'] or '未知'
        sjs[sid] = {'name_cn': name_cn, 'scientific_name': r.get('scientific_name',''),
                     'seen_at': seen_at, 'note': r['note'] or '', 'photo': bool(r['photo_path']),
                     'category': r.get('category') or '动物', 'org_type': r.get('organism_type') or 'animal'}
        phylum = r.get('phylum') or ''
        if phylum in ('松柏门','被子植物门','苏铁门','银杏门'):
            kingdom = '植物界'
        else:
            kingdom = '动物界'
        phylum = phylum or '未知门'
        cls = (r.get('class') or '未知纲').replace('被子植物·','')
        order = r.get('order_name') or '未知目'
        family = r.get('family') or '未知科'
        genus = r.get('genus') or '未知属'

        ttree.setdefault(kingdom, {}).setdefault(phylum, {}).setdefault(cls, {}).setdefault(order, {}).setdefault(family, {}).setdefault(genus, []).append({
            'sid': sid, 'name_cn': name_cn,
            'scientific_name': r.get('scientific_name',''),
            'photo': bool(r['photo_path']), 'seen_at': seen_at,
            'category': r.get('category') or '动物',
            'org_type': r.get('organism_type') or 'animal'
        })

    def build_tree():
        result = []
        for kingdom in sorted(ttree.keys(), key=lambda x: ('动物' in x, x)):
            children1 = []
            for phylum in sorted(ttree[kingdom].keys()):
                children2 = []
                for cls in sorted(ttree[kingdom][phylum].keys()):
                    children3 = []
                    for order in sorted(ttree[kingdom][phylum][cls].keys()):
                        children4 = []
                        for family in sorted(ttree[kingdom][phylum][cls][order].keys()):
                            genus_dict = ttree[kingdom][phylum][cls][order][family]
                            genus_nodes = []
                            for genus in sorted(genus_dict.keys()):
                                items = genus_dict[genus]
                                leaf_nodes = [{'type':'sighting','name':it['name_cn'],'category':it['category'],'sid':it['sid'],'photo':it['photo'],'seen_at':it['seen_at'],'org_type':it['org_type']} for it in items]
                                genus_nodes.append({'type':'genus','name':genus,'count':len(items),'children':leaf_nodes})
                            children4.append({"type":"family","name":family,"count":sum(g["count"] for g in genus_nodes),"children":genus_nodes})
                        children3.append({'type':'order','name':order,'count':sum(c['count'] for c in children4),'children':children4})
                    children2.append({'type':'class','name':cls,'count':sum(c['count'] for c in children3),'children':children3})
                children1.append({'type':'phylum','name':phylum,'count':sum(c['count'] for c in children2),'children':children2})
            result.append({'type':'kingdom','name':kingdom,'icon':KINGDOM_ICON.get(kingdom,'📂'),'count':sum(c['count'] for c in children1),'children':children1})
        return result

    tree_list = build_tree()
    total = len(all_rows)
    cur.close(); conn.close()
    return render_template('mindmap.html', tree=tree_list, tree_json=json.dumps(tree_list), sjs=json.dumps(sjs), total=total)


@app.route("/api/seen", methods=["POST"])
def api_seen():
    if 'user_id' not in session:
        return jsonify({'error': '请先登录'}), 401
    organism_id = request.form.get('organism_id', '')
    org_type = request.form.get('organism_type', 'animal')
    note = request.form.get('note', '')
    photo = request.files.get('photo')
    path = None
    if photo and allowed_file(photo.filename):
        c = compress_image(photo.stream)
        fn = f"{session['user_id']}_{org_type}_{organism_id}_{int(dt.now().timestamp())}.jpg"
        with open(os.path.join(UPLOAD_FOLDER, fn), 'wb') as f:
            f.write(c.read())
        path = fn
    conn = get_db()
    cur = conn.cursor()
    # 防止重复记录：同用户在同一天的同一种生物只保留一条
    today = dt.now().strftime('%Y-%m-%d')
    oid = str(organism_id) if org_type == 'plant' else str(int(organism_id))
    cur.execute(
        "SELECT id FROM user_sightings WHERE user_id=%s AND organism_type=%s AND organism_id=%s AND DATE(seen_at)=%s",
        (session['user_id'], org_type, oid, today))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({'ok': True, 'duplicate': True})
    if org_type == 'plant':
        cur.execute("INSERT INTO user_sightings (user_id, organism_type, organism_id, photo_path, note) VALUES (%s,%s,%s,%s,%s)",
                    (session['user_id'], org_type, oid, path, note))
    else:
        cur.execute("INSERT INTO user_sightings (user_id, organism_type, organism_id, photo_path, note) VALUES (%s,%s,%s,%s,%s)",
                    (session['user_id'], org_type, int(organism_id), path, note))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/unseen/<id>/<org_type>', methods=['POST'])
def api_unseen(id, org_type):
    if 'user_id' not in session:
        return jsonify({'error': '请先登录'}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT photo_path FROM user_sightings WHERE user_id=%s AND organism_type=%s AND organism_id=%s",
                (session['user_id'], org_type, id))
    row = cur.fetchone()
    if row and row['photo_path']:
        p = os.path.join(UPLOAD_FOLDER, row['photo_path'])
        if os.path.exists(p): os.remove(p)
    cur.execute("DELETE FROM user_sightings WHERE user_id=%s AND organism_type=%s AND organism_id=%s",
                (session['user_id'], org_type, id))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/sighting/<int:sid>', methods=['DELETE'])
def api_delete(sid):
    if 'user_id' not in session:
        return jsonify({'error': '请先登录'}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT photo_path FROM user_sightings WHERE id=%s AND user_id=%s", (sid, session['user_id']))
    row = cur.fetchone()
    if row and row['photo_path']:
        p = os.path.join(UPLOAD_FOLDER, row['photo_path'])
        if os.path.exists(p): os.remove(p)
    cur.execute("DELETE FROM user_sightings WHERE id=%s AND user_id=%s", (sid, session['user_id']))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/photos/<int:sid>')
def get_photo(sid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT photo_path FROM user_sightings WHERE id=%s AND user_id=%s", (sid, session.get('user_id')))
    row = cur.fetchone()
    cur.close(); conn.close()
    if row and row['photo_path']:
        return send_from_directory(UPLOAD_FOLDER, row['photo_path'])
    return 'not found', 404

# =====================================================================
# =====================================================================
# iNaturalist 缩略图接口
# =====================================================================
INAT_CACHE = {}

@app.route('/api/thumb/<path:name>')
def thumb(name):
    """Search iNaturalist for species photo by scientific/common name."""
    import urllib.request, urllib.parse, ssl
    if not name:
        return jsonify({'url': None})
    # Try cache first
    if name in INAT_CACHE:
        return jsonify({'url': INAT_CACHE[name]})
    ctx = ssl._create_unverified_context()
    try:
        url = f'https://api.inaturalist.org/v1/observations?taxon_name={urllib.parse.quote(name)}&per_page=3&locale=en'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
            data = json.loads(r.read())
        results = data.get('results', [])
        for obs in results:
            photos = obs.get('photos', [])
            for p in photos:
                img_url = p.get('url', '')
                # Skip copyright infringement placeholders
                if img_url and 'copyright-infringement' not in img_url:
                    INAT_CACHE[name] = img_url
                    return jsonify({'url': img_url})
    except:
        pass
    INAT_CACHE[name] = None
    return jsonify({'url': None})




@app.route('/api/sighting-photo/<id>/<org_type>')
def sighting_photo(id, org_type):
    """返回用户对该物种上传的照片URL"""
    if 'user_id' not in session:
        return jsonify({'error': '请先登录'}), 401
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    # 动物用INT id，植物用中文学名
    if org_type == 'plant':
        cur.execute("""
            SELECT photo_path FROM user_sightings
            WHERE user_id=%s AND organism_type='plant' AND organism_id=%s AND photo_path IS NOT NULL
            ORDER BY seen_at DESC LIMIT 1
        """, (uid, id))
    else:
        try:
            int_id = int(id)
            cur.execute("""
                SELECT photo_path FROM user_sightings
                WHERE user_id=%s AND organism_type='animal' AND organism_id=%s AND photo_path IS NOT NULL
                ORDER BY seen_at DESC LIMIT 1
            """, (uid, int_id))
        except:
            return jsonify({'photo': None})
    row = cur.fetchone()
    cur.close(); conn.close()
    if row and row['photo_path']:
        return jsonify({'photo': row['photo_path']})
    return jsonify({'photo': None})



@app.route('/p/<path:filename>')
def serve_photo(filename):
    """提供用户上传的照片"""
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)