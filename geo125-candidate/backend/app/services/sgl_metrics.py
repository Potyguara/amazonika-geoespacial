"""MTGIR 2ª edição, 3.8.1, 3.8.3, 3.8.4. Sem substituir h ausente por zero."""
from math import radians, degrees, sin, cos, sqrt, fsum, isfinite, atan2, hypot
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

def puissant_azimuth(lon1, lat1, lon2, lat2):
    """Problema inverso, lados curtos, formulário UFPR pp. 1-2.
    https://cartografica.ufpr.br/wp-content/uploads/2011/10/transp-coordenadas-puissant.pdf
    Grandezas angulares em radianos (equivalentes aos segundos do formulário).
    """
    if not all(isfinite(v) for v in (lon1,lat1,lon2,lat2)):
        raise ValueError("Coordenadas não finitas.")
    if not (-90<lat1<90 and -90<lat2<90):
        raise ValueError("Puissant: latitude fora do domínio.")
    a=6378137.0
    f=1/298.257222101
    e2=f*(2-f)
    p1,p2=radians(lat1),radians(lat2)
    pm=(p1+p2)/2
    dp=p2-p1
    dl=radians((lon2-lon1+180)%360-180)
    w1,w2=(1-e2*sin(p)**2 for p in (p1,p2))
    nm=a*(1/sqrt(w1)+1/sqrt(w2))/2
    mm=a*(1-e2)*(w1**-1.5+w2**-1.5)/2
    x=dl*cos(pm)*nm
    y=dp*cos(dl/2)*mm
    if hypot(x,y)==0:
        raise ValueError("Puissant: vértices coincidentes.")
    if hypot(x,y)>80000:
        raise ValueError("Puissant: lado superior ao domínio de 80 km.")
    gamma=dl*sin(pm)/cos(dp/2)+sin(pm)*cos(pm)**2*dl**3/12
    return degrees(atan2(x,y)-gamma/2)%360
