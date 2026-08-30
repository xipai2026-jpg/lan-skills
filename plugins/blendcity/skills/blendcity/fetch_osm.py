#!/usr/bin/env python3
"""
从 OpenStreetMap 拉一块地方的建筑/道路/水系/公园，投影成局部米制坐标，写出 scene.json。

    python3 fetch_osm.py --center 30.6572,104.0658 --radius 1700 --out scene.json

产物 scene.json 的契约（build_city.py 只认这个）：
    buildings [{"pts": [[x,y],...], "h": 楼高米}]
    roads     [{"pts": [[x,y],...], "w": 路宽米}]
    waters    [{"pts": [...], "w": 宽, "line": true}]   线状河流
              [{"pts": [...]}]                          面状水体
    parks     [{"pts": [[x,y],...]}]
坐标原点 = --center，X 东、Y 北，单位米。
"""
import argparse, hashlib, json, math, sys, time, urllib.parse, urllib.request

# 按顺序试，一个失败换下一个。主站只要用 urlencode 提交就正常（裸 POST 才 406）；
# 镜像 kumi 有时整站 500，所以两个都留着互为兜底。
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# 只取主干路，支路会把画面糊成一团麻
ROAD_WIDTH = {"motorway": 24, "trunk": 20, "primary": 16,
              "secondary": 12, "tertiary": 9}
LEVEL_HEIGHT = 3.2          # 没有 height 标签时，一层按 3.2m 估
FALLBACK_RANGE = (9, 30)    # 连层数都没有时的确定性随机区间


def overpass(query, retries=3):
    """Overpass 必须用 urlencode 的 data= 提交，裸 POST 会 406。"""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(retries):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=body, headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "blendcity/1.0 (OSM massing)"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    return json.loads(r.read().decode())
            except Exception as e:
                last = "%s -> %s: %s" % (url, type(e).__name__, str(e)[:120])
                print("  [重试] %s" % last, file=sys.stderr)
        time.sleep(10)
    raise SystemExit("Overpass 三轮都失败，最后一次：%s" % last)


def make_projector(lat0, lon0):
    """等距圆柱投影：小范围内够用，省掉 pyproj 依赖。"""
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    m_lat = 110540.0
    def proj(lat, lon):
        return ((lon - lon0) * m_lon, (lat - lat0) * m_lat)
    return proj


def ring(geometry, proj):
    """OSM way 的 geometry → 局部坐标点列；闭合环要去掉重复的收尾点。"""
    pts = [proj(p["lat"], p["lon"]) for p in geometry]
    if len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
        pts = pts[:-1]          # ← 不去掉会多出一个退化面
    return [[round(x, 2), round(y, 2)] for x, y in pts]


def building_height(el):
    """height → levels×3.2 → 按 id 哈希给确定性随机值（同一栋楼每次跑都一样高）。"""
    t = el.get("tags", {})
    for key in ("height", "building:height"):
        raw = t.get(key)
        if raw:
            try:
                return max(3.0, float(str(raw).replace("m", "").strip()))
            except ValueError:
                pass
    for key in ("building:levels", "levels"):
        raw = t.get(key)
        if raw:
            try:
                return max(3.0, float(str(raw).strip()) * LEVEL_HEIGHT)
            except ValueError:
                pass
    lo, hi = FALLBACK_RANGE
    seed = int(hashlib.md5(str(el.get("id", 0)).encode()).hexdigest()[:8], 16)
    return float(lo + seed % (hi - lo + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--center", required=True, help="纬度,经度  例 30.6572,104.0658")
    ap.add_argument("--radius", type=float, default=1500, help="半径（米），默认 1500")
    ap.add_argument("--out", default="scene.json")
    ap.add_argument("--no-roads", action="store_true", help="只要建筑，跳过路网/水系/公园")
    a = ap.parse_args()

    lat0, lon0 = [float(v) for v in a.center.split(",")]
    proj = make_projector(lat0, lon0)
    dlat = a.radius / 110540.0
    dlon = a.radius / (111320.0 * math.cos(math.radians(lat0)))
    bbox = "%f,%f,%f,%f" % (lat0 - dlat, lon0 - dlon, lat0 + dlat, lon0 + dlon)
    print("bbox = %s  (半径 %.0fm)" % (bbox, a.radius), file=sys.stderr)

    scene = {"buildings": [], "roads": [], "waters": [], "parks": []}

    print("[1/2] 拉建筑…", file=sys.stderr)
    data = overpass('[out:json][timeout:240];(way["building"](%s););out geom;' % bbox)
    for el in data.get("elements", []):
        pts = ring(el.get("geometry") or [], proj)
        if len(pts) >= 3:
            scene["buildings"].append({"pts": pts, "h": building_height(el)})
    print("      建筑 %d 栋" % len(scene["buildings"]), file=sys.stderr)

    if not a.no_roads:
        print("[2/2] 拉路网/水系/公园…", file=sys.stderr)
        q = ('[out:json][timeout:240];('
             'way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"](%s);'
             'way["waterway"~"^(river|canal)$"](%s);'
             'way["natural"="water"](%s);'
             'way["leisure"="park"](%s););out geom;') % (bbox, bbox, bbox, bbox)
        data = overpass(q)
        for el in data.get("elements", []):
            t = el.get("tags", {})
            geom = el.get("geometry") or []
            if t.get("highway"):
                pts = [[round(x, 2), round(y, 2)] for x, y in
                       (proj(p["lat"], p["lon"]) for p in geom)]
                if len(pts) >= 2:
                    scene["roads"].append({"pts": pts, "w": ROAD_WIDTH.get(t["highway"], 9)})
            elif t.get("waterway"):
                pts = [[round(x, 2), round(y, 2)] for x, y in
                       (proj(p["lat"], p["lon"]) for p in geom)]
                if len(pts) >= 2:
                    scene["waters"].append({"pts": pts, "w": 30, "line": True})
            elif t.get("natural") == "water":
                pts = ring(geom, proj)
                if len(pts) >= 3:
                    scene["waters"].append({"pts": pts})
            elif t.get("leisure") == "park":
                pts = ring(geom, proj)
                if len(pts) >= 3:
                    scene["parks"].append({"pts": pts})
        print("      道路 %d / 水系 %d / 公园 %d" % (
            len(scene["roads"]), len(scene["waters"]), len(scene["parks"])), file=sys.stderr)

    with open(a.out, "w") as f:
        json.dump(scene, f)
    print("写出 %s" % a.out, file=sys.stderr)


if __name__ == "__main__":
    main()
