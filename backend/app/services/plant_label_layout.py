"""Deterministic cartographic label placement in PDF point coordinates.

All labels use measured glyph widths. Bounding rectangles (conservative for
rotated labels) are checked against previously reserved labels and furniture.
If a label cannot be placed at legible size, use a leader line and callout.
When neither fits, raise rather than emit an overlapping/cropped PDF.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    def intersects(self, other: "Box", gap: float = 2.0) -> bool:
        return not (self.x+self.w+gap <= other.x or other.x+other.w+gap <= self.x
                    or self.y+self.h+gap <= other.y or other.y+other.h+gap <= self.y)

    def inside(self, region: "Box", pad: float=3.0) -> bool:
        return (self.x >= region.x+pad and self.y >= region.y+pad
                and self.x+self.w <= region.x+region.w-pad
                and self.y+self.h <= region.y+region.h-pad)


def _rotated_bounds(cx, cy, width, height, angle):
    theta = math.radians(angle)
    w = abs(width*math.cos(theta)) + abs(height*math.sin(theta))
    h = abs(width*math.sin(theta)) + abs(height*math.cos(theta))
    return Box(cx-w/2, cy-h/2, w, h)


class LabelLayout:
    def __init__(self, viewport):
        self.bounds = Box(*viewport)
        self.reserved: list[Box] = []
        self.callouts: list[tuple[float,float,float,float]] = []

    def reserve(self, box: Box) -> bool:
        if not box.inside(self.bounds) or any(box.intersects(o) for o in self.reserved):
            return False
        self.reserved.append(box)
        return True

    def available(self, box: Box) -> bool:
        return box.inside(self.bounds) and not any(box.intersects(o) for o in self.reserved)

    def place(self, pdf, lines: list[str], anchor: tuple[float,float],
              *, angle=0, font="Helvetica-Bold", color=None,
              desired=7.3, minimum=6.0, offsets=None, allow_callout=True,
              white_background=True):
        lines = [str(s) for s in lines if str(s).strip()]
        if not lines:
            return True
        # Preserve o nome completo do confrontante, quebrando em linhas
        # antes de tentar posicionamento ou líder de chamada.
        max_text_width=max(40.,self.bounds.w*0.38)
        wrapped=[]
        for line in lines:
            if stringWidth(line,font,minimum)<=max_text_width:
                wrapped.append(line)
                continue
            words=line.split()
            current=""
            for word in words:
                if stringWidth(word,font,minimum)>max_text_width:
                    raise ValueError(
                        "Rótulo contém palavra maior que o espaço cartográfico disponível. "
                        "Utilize folha maior ou abreviação técnica validada."
                    )
                candidate=(current+" "+word).strip()
                if current and stringWidth(candidate,font,minimum)>max_text_width:
                    wrapped.append(current)
                    current=word
                else:
                    current=candidate
            if current:
                wrapped.append(current)
        lines=wrapped
        ax,ay = anchor
        if abs(angle)>90:
            angle = (angle+180)%360
        if offsets is None:
            offsets = [(0,14),(0,-14),(16,0),(-16,0),
                       (23,23),(-23,23),(23,-23),(-23,-23)]
        sizes = [round(desired-i*.25,2) for i in range(int((desired-minimum)/.25)+1)]
        for size in sizes:
            if size<minimum-.01:continue
            widths = [stringWidth(t,font,size) for t in lines]
            width=max(widths)+8
            line_height=size+2.2
            height=len(lines)*line_height+5
            # Rotated labels have a conservative axis-aligned bounding rectangle.
            for ox,oy in offsets:
                cx,cy=ax+ox,ay+oy
                box=_rotated_bounds(cx,cy,width,height,angle)
                if not self.available(box):
                    continue
                self.reserved.append(box)
                pdf.saveState()
                pdf.translate(cx,cy)
                pdf.rotate(angle)
                if white_background:
                    pdf.setFillColor(colors.white)
                    pdf.rect(-width/2,-height/2,width,height,stroke=0,fill=1)
                pdf.setFillColor(color or colors.HexColor("#23342A"))
                pdf.setFont(font,size)
                for n,value in enumerate(lines):
                    pdf.drawCentredString(0,height/2-3-size-n*line_height,value)
                pdf.restoreState()
                return True
        if not allow_callout:
            return False
        # Leaders route information outside clusters, while retaining an exact
        # endpoint at the originating vertex/segment.
        size=max(minimum,6.2)
        width=max(stringWidth(t,font,size) for t in lines)+9
        height=len(lines)*(size+2.4)+5
        region=self.bounds
        # Search a deterministic perimeter/ring of callouts, nearest anchor first.
        options=[]
        step=max(11.0,height+4)
        for y in (region.y+height/2+6, region.y+region.h-height/2-6):
            for x in range(int(region.x+width/2+6),int(region.x+region.w-width/2-5),max(10,int(step))):
                options.append((float(x),y))
        for x in (region.x+width/2+6,region.x+region.w-width/2-6):
            for y in range(int(region.y+height/2+5),int(region.y+region.h-height/2-4),max(10,int(step))):
                options.append((x,float(y)))
        options.sort(key=lambda pt:(math.hypot(pt[0]-ax,pt[1]-ay),pt[0],pt[1]))
        for cx,cy in options:
            box=Box(cx-width/2,cy-height/2,width,height)
            if not self.available(box):
                continue
            self.reserved.append(box)
            edge_x = min(max(ax,box.x),box.x+box.w)
            edge_y = min(max(ay,box.y),box.y+box.h)
            pdf.saveState()
            pdf.setStrokeColor(colors.HexColor("#516E60"))
            pdf.setLineWidth(.45)
            pdf.line(ax,ay,edge_x,edge_y)
            pdf.setFillColor(colors.white)
            pdf.circle(ax,ay,1.3,stroke=1,fill=1)
            if white_background:
                pdf.rect(box.x,box.y,box.w,box.h,stroke=1,fill=1)
            pdf.setFillColor(color or colors.HexColor("#23342A"))
            pdf.setFont(font,size)
            for n,value in enumerate(lines):
                pdf.drawCentredString(cx,box.y+box.h-3-size-n*(size+2.4),value)
            pdf.restoreState()
            self.callouts.append((ax,ay,cx,cy))
            return True
        raise ValueError(
            "Não foi possível distribuir todos os rótulos sem sobreposição "
            "e mantendo fonte legível. Aumente a folha, amplie a escala "
            "ou desative algumas informações opcionais da planta."
        )
