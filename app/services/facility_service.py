import math
from app.db.database import connection

def haversine_km(lat1,lon1,lat2,lon2):
    r=6371.0; p1,p2=math.radians(lat1),math.radians(lat2)
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*r*math.asin(math.sqrt(a))

def search_facilities(area: str|None=None, latitude: float|None=None, longitude: float|None=None):
    with connection() as c:
        rows=c.execute("SELECT * FROM facilities WHERE verification_status='verified'").fetchall()
    if area:
        needle=area.casefold(); rows=[r for r in rows if needle in ((r['state'] or '')+' '+(r['lga'] or '')+' '+r['address']).casefold()]
    if latitude is not None and longitude is not None:
        rows=[r for r in rows if r['latitude'] is not None and r['longitude'] is not None]
        rows=sorted(rows,key=lambda r:haversine_km(latitude,longitude,r['latitude'],r['longitude']))
    return rows[:5]

def format_facilities(rows):
    if not rows: return "I don't have verified participating facilities for that area yet. Please contact your local health authority or antenatal provider for a current referral."
    return "Verified facilities:\n"+"\n".join(f"{r['name']} — {r['address']}; phone: {r['phone'] or 'not listed'}; last verified: {r['last_verified_at'] or 'date not recorded'}; source: {r['source']}. Please call to confirm current availability." for r in rows)
