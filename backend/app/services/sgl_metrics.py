"""MTGIR 2ª edição, 3.8.1, 3.8.3, 3.8.4. Sem substituir h ausente por zero."""
from math import radians, sin, cos, sqrt, fsum, isfinite
from pyproj import Transformer

_TO_XYZ = Transformer.from_crs("EPSG:4893", "EPSG:4892", always_xy=True)
_TO_LLH = Transformer.from_crs("EPSG:4892", "EPSG:4893", always_xy=True)

def sgl_metrics(points, heights):
    if len(points)<3 or len(points)!=len(heights):
        raise ValueError("SGL: coordenadas e alturas incompatíveis.")
    if any(not isinstance(h,(float,int)) or isinstance(h,bool) or not isfinite(h) for h in heights):
        raise ValueError("SGL: todas as alturas elipsoidais devem estar disponíveis.")
    xyz = [_TO_XYZ.transform(lon,lat,h,errcheck=True) for (lon,lat),h in zip(points,heights)]
    origin = tuple(fsum(p[k] for p in xyz)/len(xyz) for k in range(3))
    lon,lat,_ = _TO_LLH.transform(*origin,errcheck=True)
    l,p = radians(lon),radians(lat)
    local=[]
    for X,Y,Z in xyz:
        x,y,z=X-origin[0],Y-origin[1],Z-origin[2]
        e=-sin(l)*x+cos(l)*y
        n=-sin(p)*cos(l)*x-sin(p)*sin(l)*y+cos(p)*z
        u=cos(p)*cos(l)*x+cos(p)*sin(l)*y+sin(p)*z
        local.append((e,n,u))
    n=len(xyz)
    area=abs(fsum(local[i][0]*local[(i+1)%n][1]-local[(i+1)%n][0]*local[i][1] for i in range(n)))/2
    distances=[]
    for i in range(n):
        j=(i+1)%n
        squared=fsum((xyz[j][k]-xyz[i][k])**2 for k in range(3))-(heights[j]-heights[i])**2
        if squared < -1e-6:
            raise ValueError("SGL: distância horizontal inválida.")
        distances.append(sqrt(max(0.,squared)))
    return {"area_ha":area/10000,"perimeter_m":fsum(distances),"distances_m":distances,
            "origin_xyz":origin,"local_coordinates":local,"area_method":"SGL_GRS80",
            "distance_method":"MTGIR_3_8_4"}
