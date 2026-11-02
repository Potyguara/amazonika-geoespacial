"""Professional static thematic mapping with GeoPandas/Matplotlib (Agg).

Only plots the GIS features provided; never synthesizes geographic features.
The source geometries are in SIRGAS 2000 geographic coordinates (EPSG:4674).
"""
from __future__ import annotations

import io
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator
from shapely.geometry import Polygon, MultiPolygon, Point, MultiPoint, LineString, MultiLineString, GeometryCollection
from pyproj import Transformer
from shapely.ops import transform as shp_transform
from .thematic_maps import _projected, _color

def _plot(ax, geom, color, outline=False, opacity=1):
    if geom.is_empty:
        return
    if isinstance(geom, (MultiPolygon, MultiLineString, MultiPoint, GeometryCollection)):
        for part in geom.geoms:
            _plot(ax, part, color, outline, opacity)
    elif isinstance(geom, Polygon):
        # Explicitly preserve polygon holes.
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        verts, codes = [], []
        for ring in (geom.exterior, *geom.interiors):
            points = list(ring.coords)
            if len(points)<3: continue
            verts.extend(points)
            codes.extend([Path.MOVETO] + [Path.LINETO]*(len(points)-2) + [Path.CLOSEPOLY])
        if verts:
            patch=PathPatch(Path(verts,codes), facecolor="none" if outline else color,
                            edgecolor="#c52828" if outline else "#587a68",
                            linewidth=1.8 if outline else .22, alpha=1 if outline else opacity)
            ax.add_patch(patch)
    elif isinstance(geom, LineString):
        x,y=geom.xy
        ax.plot(x,y,color=color,linewidth=1.05,zorder=7)
    elif isinstance(geom, Point):
        ax.plot(geom.x,geom.y,marker="o",color=color,markersize=3.5,zorder=8)

def render_matplotlib(title, subtitle, layers, source, style=None, branding=False, fmt="pdf"):
    style=style or {}
    projected,epsg=_projected(layers)
    property_parts=[g for l,g in zip(layers,projected) if l.role=="property"]
    if not property_parts: raise ValueError("Propriedade obrigatória.")
    prop=property_parts[0]
    xmin,ymin,xmax,ymax=prop.bounds
    span=max(xmax-xmin,ymax-ymin,200)
    context=style.get("context","balanced")
    margin=span*{"close":.13,"balanced":.35,"regional":.65}.get(context,.35)
    if style.get("buffer_m") is not None: margin=float(style["buffer_m"])
    if not math.isfinite(margin) or margin<0 or margin>1e6: raise ValueError("Margem inválida.")
    cx,cy=(xmin+xmax)/2,(ymin+ymax)/2
    width,height=(xmax-xmin)+margin*2,(ymax-ymin)+margin*2

    # A3 in landscape: fixed 11.69 x 16.54 inches.
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    ax=fig.add_axes([.052,.14,.705,.74])
    fig.text(.5,.952,title.upper()[:105],ha="center",fontsize=18,fontweight="bold",color="#173b32")
    if subtitle:fig.text(.5,.926,subtitle[:140],ha="center",fontsize=10,color="#52685e")
    ax.set_facecolor("#fafcf9")
    ratio=(16.54*.705)/(11.69*.74)
    width=max(width,height*ratio)
    height=max(height,width/ratio)
    denominator=style.get("scale")
    # Choose print scale from true map width; 1 inch = .0254 m.
    raw=width/(16.54*.705*.0254)
    standards=[1000,2500,5000,10000,25000,50000,100000,250000,500000,1000000,2500000,5000000]
    if denominator is None:
        denominator=next((v for v in standards if v>=raw),5000000)
    else:
        denominator=float(denominator)
        if denominator<raw: raise ValueError("Escala manual não comporta o mapa A3.")
    width=denominator*(16.54*.705)*.0254
    height=width/ratio
    ax.set_xlim(cx-width/2,cx+width/2)
    ax.set_ylim(cy-height/2,cy+height/2)
    ax.set_aspect("equal",adjustable="box")
    mode=style.get("mode","minimalista")
    grid=style.get("grid","border")
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.ticklabel_format(style="plain",useOffset=False)
    ax.tick_params(labelsize=7,top=True,labeltop=True,right=True,labelright=True,
                   bottom=True,left=True,length=3,pad=3)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x,p: f"{x:,.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,p: f"{x:,.0f}"))
    if grid=="off":
        ax.set_xticks([]);ax.set_yticks([])
    elif grid in ("subtle","full"):
        ax.grid(True,color="#dae2db" if grid=="subtle" else "#a3b4a8",
                linewidth=.4 if grid=="subtle" else .65,zorder=0)
    for spine in ax.spines.values():
        spine.set_color("#8a9b91");spine.set_linewidth(.7)

    # Polygons -> lines -> point markers -> property contour.
    rank=lambda item: (2 if item[0].role=="property" else
                       0 if item[1].geom_type in ("Polygon","MultiPolygon") else 1)
    entries=sorted(zip(layers,projected),key=rank)
    handles=[]
    for layer,geom in entries:
        c=layer.color
        _color(c)
        if layer.role=="property":
            prop_mode=style.get("property","outline")
            if prop_mode=="transparent":_plot(ax,geom,c,opacity=.15)
            elif prop_mode=="fill":_plot(ax,geom,c,opacity=.85)
            _plot(ax,geom,c,outline=True)
            handles.append(Patch(facecolor="none",edgecolor="#c52828",linewidth=1.8,label="Propriedade"))
        else:
            _plot(ax,geom,c)
            label=layer.name.split(": ",1)[-1]
            if geom.geom_type in ("LineString","MultiLineString"):
                handles.append(Line2D([0],[0],color=c,linewidth=2,label=label))
            elif geom.geom_type in ("Point","MultiPoint"):
                handles.append(Line2D([0],[0],marker="o",linestyle="none",color=c,label=label))
            else:
                handles.append(Patch(facecolor=c,edgecolor="#587a68",linewidth=.4,label=label))
    fig.text(.79,.865,"LEGENDA",fontsize=11,fontweight="bold",color="#173b32")
    # No invented classes; direct legend from supplied vector attributes.
    ax_leg=fig.add_axes([.79,.36,.19,.48]);ax_leg.axis("off")
    ax_leg.legend(handles=handles,loc="upper left",frameon=False,fontsize=8,
                  handlelength=1.7,handleheight=1,alignment="left",borderaxespad=0)
    fig.text(.79,.325,"N",fontsize=13,fontweight="bold")
    fig.text(.79,.295,"↑",fontsize=24)
    fig.text(.79,.246,"REFERÊNCIA CARTOGRÁFICA",fontsize=9,fontweight="bold")
    fig.text(.79,.218,f"SIRGAS 2000 · UTM · EPSG:{epsg}\nCoordenadas em metros",fontsize=8,va="top")
    fig.text(.79,.145,"FONTES",fontsize=9,fontweight="bold")
    fig.text(.79,.123,(source or "; ".join(dict.fromkeys(l.source for l in layers)))[:100],
             fontsize=7,va="top",wrap=True)
    # Grounded printed scale and 2-section proportional bar.
    fig.text(.055,.095,f"ESCALA 1:{denominator:,.0f}".replace(",","."),fontsize=9,fontweight="bold")
    length=max(100,round(denominator*.0254*1.2/100)*100)
    bar_inches=length/(denominator*.0254)
    bar_frac=bar_inches/16.54
    x0=.31; y0=.098
    for n in range(2):
        from matplotlib.patches import Rectangle
        fig.add_artist(Rectangle((x0+n*bar_frac/2,y0),bar_frac/2,.007,transform=fig.transFigure,
                       facecolor="#1f2825" if n==0 else "white",edgecolor="#1f2825",linewidth=.8))
    fig.text(x0,.085,"0",fontsize=7)
    fig.text(x0+bar_frac,.085,f"{length:,} m",ha="right",fontsize=7)
    if branding:fig.text(.05,.025,"AMAZÔNIKA GEOESPACIAL",fontsize=8,color="#315347")
    out=io.BytesIO()
    fig.savefig(out,format=fmt,dpi=180,facecolor="white")
    plt.close(fig)
    return out.getvalue()
