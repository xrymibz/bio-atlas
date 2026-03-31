import pymysql, json
conn = pymysql.connect(host='localhost', user='root', password='OpenClaw@2026', database='openclaw_db', charset='utf8mb4')
cur = conn.cursor()

# Load existing plants from JSON first
existing_plants = json.load(open('/root/.openclaw/workspace/plants_data.json', encoding='utf-8'))
print(f'JSON plants: {len(existing_plants)}')

cols = '(name_cn,name_en,scientific_name,kingdom,phylum,class_name,order_name,family,genus,species,subspecies,category,feature,is_endangered,region,description,flower_color,leaf_type,fruit_type,habitat)'
sql = 'INSERT IGNORE INTO plants %s VALUES ' % cols

vals = []
for p in existing_plants:
    vals.append('(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)')
values_sql = ','.join(vals)
all_vals = []
for p in existing_plants:
    all_vals.extend([
        p.get('name_cn',''),p.get('name_en',''),p.get('scientific_name',''),
        p.get('kingdom','植物界'),p.get('phylum',''),p.get('class',''),
        p.get('order_name',''),p.get('family',''),p.get('genus',''),
        p.get('species',''),p.get('subspecies',''),
        p.get('category',''),p.get('feature',''),
        int(p.get('is_endangered',0)),
        p.get('region',''),p.get('description',''),
        p.get('flower_color',''),p.get('leaf_type',''),
        p.get('fruit_type',''),p.get('habitat','')
    ])

cur.execute(sql + values_sql, all_vals)
conn.commit()
print(f'Inserted: {cur.rowcount}')
cur.execute('SELECT COUNT(*) FROM plants')
print(f'Total plants in DB: {cur.fetchone()[0]}')
conn.close()
