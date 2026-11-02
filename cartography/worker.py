"""Isolated PyQGIS PDF renderer. Internal Docker network only; no user Python execution."""
import io
import json
import math
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsFillSymbol,
    QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap,
    QgsLayoutItemMapGrid, QgsLayoutItemPage, QgsLayoutItemScaleBar,
    QgsLayoutPoint, QgsLayoutSize, QgsMapLayer, QgsPrintLayout,
    QgsLayoutExporter, QgsProject, QgsRectangle, QgsSingleSymbolRenderer,
    QgsVectorLayer, QgsSimpleMarkerSymbolLayer, QgsLineSymbol,
    QgsMarkerSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsLegendStyle,
)
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtCore import Qt

qgs = QgsApplication([], False)
qgs.initQgis()
MAX_BODY = 12_000_000


def render(request):
    layers_in = request["layers"]
    if not isinstance(layers_in, list) or not 1 <= len(layers_in) <= 60:
        raise ValueError("Número inválido de camadas")
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4674"))
    layers, tmp = [], tempfile.TemporaryDirectory()
    try:
        for i, item in enumerate(layers_in):
            color = item.get("color", "#73c6ad")
            if not isinstance(color, str) or len(color) != 7 or QColor(color).isValid() is False:
                raise ValueError("Cor inválida")
            features = item.get("features")
            if features is None:
                features = [{"type":"Feature","properties":{},"geometry":item["geometry"]}]
            if not isinstance(features,list) or not features or len(features)>3000:
                raise ValueError("Quantidade inválida de feições")
            feature = {"type":"FeatureCollection","features":features}
            path = Path(tmp.name) / f"layer_{i}.geojson"
            path.write_text(json.dumps(feature), encoding="utf-8")
            layer = QgsVectorLayer(str(path), str(item.get("name", "Camada"))[:120], "ogr")
            layer.setCrs(QgsCoordinateReferenceSystem('EPSG:4674'))
            if not layer.isValid():
                raise ValueError("Geometria inválida na camada " + str(i))
            if layer.geometryType() == 2:
                symbol = QgsFillSymbol.createSimple({"color": color if item.get("role") != "property" else "transparent",
                     "outline_color": "#c52828" if item.get("role") == "property" else "#526d5d",
                     "outline_width": "0.55" if item.get("role") == "property" else "0.12"})
            elif layer.geometryType() == 1:
                symbol = QgsLineSymbol.createSimple({"line_color":color,"line_width":"0.45"})
            else:
                symbol = QgsMarkerSymbol.createSimple({"name":"circle","color":color,"size":"2"})
            field = item.get("class_field")
            classes = item.get("classes")
            if field and classes and layer.fields().indexFromName(field) >= 0:
                if not isinstance(classes,list) or len(classes)>40:
                    raise ValueError("Quantidade de classes inválida (máximo 40)")
                categories=[]
                for klass in classes:
                    class_color=klass.get("color",color)
                    if not isinstance(class_color,str) or not QColor(class_color).isValid():
                        raise ValueError("Cor de classe inválida")
                    class_symbol=symbol.clone()
                    class_symbol.setColor(QColor(class_color))
                    categories.append(QgsRendererCategory(klass["value"],class_symbol,str(klass.get("label",klass["value"]))[:70]))
                layer.setRenderer(QgsCategorizedSymbolRenderer(field,categories))
            else:
                layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            project.addMapLayer(layer)
            layers.append(layer)
        property_layers = [l for l, item in zip(layers,layers_in) if item.get("role")=="property"]
        if not property_layers:
            raise ValueError("Propriedade obrigatória")
        prop = property_layers[0]
        src = prop.crs()
        from qgis.core import QgsCoordinateTransform
        center = prop.extent()
        projected = QgsCoordinateReferenceSystem("EPSG:31982")
        lon = center.center().x()
        lat = center.center().y()
        # SIRGAS UTM zone selected from property's geographic center.
        zone = max(1, min(60, int((lon + 180)//6)+1))
        projected = QgsCoordinateReferenceSystem(f"EPSG:{31960+zone if lat<0 else 31954+zone}")
        project.setCrs(projected)
        transformed = QgsCoordinateTransform(src, projected, project)
        rect = transformed.transformBoundingBox(center)
        context = request.get("style",{}).get("context","balanced")
        m = max(rect.width(),rect.height(),200)*{"close":.13,"balanced":.35,"regional":.65}.get(context,.35)
        buffer_m = request.get("style",{}).get("buffer_m")
        if buffer_m is not None:
            m=float(buffer_m)
        if not math.isfinite(m) or not 0<=m<=1000000:
            raise ValueError("Margem inválida")
        w, h = max(rect.width()+2*m,10), max(rect.height()+2*m,10)
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        page = layout.pageCollection().pages()[0]
        page.setPageSize(QgsLayoutSize(420,297))
        def label(text,x,y,size=9,bold=False):
            obj=QgsLayoutItemLabel(layout)
            obj.setText(str(text))
            font=QFont("DejaVu Sans",size)
            font.setBold(bold)
            obj.setFont(font)
            obj.setFontColor(QColor("#173b32"))
            layout.addLayoutItem(obj)
            obj.attemptMove(QgsLayoutPoint(x,y))
            obj.attemptResize(QgsLayoutSize(95 if x>=320 else 300,10))
            return obj
        label(str(request.get("title","MAPA TEMÁTICO"))[:105].upper(),14,7,16,True)
        label(str(request.get("subtitle",""))[:140],14,18,9)
        map_item=QgsLayoutItemMap(layout)
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(14,32))
        map_item.attemptResize(QgsLayoutSize(296,232))
        map_item.setCrs(projected)
        map_item.setLayers(list(reversed(layers)))
        map_item.setKeepLayerSet(True)
        ratio=296/232
        w=max(w,h*ratio)
        h=max(h,w/ratio)
        scale=request.get("style",{}).get("scale")
        raw=w/(296/1000)
        if scale is None:
            standards=[1000,2500,5000,10000,25000,50000,100000,250000,500000,1000000,2500000,5000000,10000000,25000000]
            scale=next((v for v in standards if v>=raw), math.ceil(raw/1000000)*1000000)
        else:
            scale=float(scale)
            if not math.isfinite(scale) or scale<raw:
                raise ValueError("Escala manual não comporta o mapa")
        map_item.zoomToExtent(QgsRectangle(rect.center().x()-scale*.296/2,rect.center().y()-scale*.232/2,
                                           rect.center().x()+scale*.296/2,rect.center().y()+scale*.232/2))
        map_item.setFrameEnabled(True)
        grid_mode=request.get("style",{}).get("grid","border")
        if grid_mode in ("border","subtle","full"):
            grid=map_item.grid()
            grid.setEnabled(True)
            grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly if grid_mode=="border" else QgsLayoutItemMapGrid.Solid)
            grid.setAnnotationEnabled(True)
            grid.setAnnotationPrecision(0)
            grid.setIntervalX(max(100,round(scale*.05/100)*100))
            grid.setIntervalY(max(100,round(scale*.05/100)*100))
            grid.setAnnotationFont(QFont("DejaVu Sans",7))
        label("LEGENDA",321,36,11,True)
        legend=QgsLayoutItemLegend(layout)
        layout.addLayoutItem(legend)
        legend.setTitle("")
        legend.setLinkedMap(map_item)
        legend.setAutoUpdateModel(False)
        root=legend.model().rootGroup()
        root.clear()
        for layer in reversed(layers):
            root.addLayer(layer)
        legend.attemptMove(QgsLayoutPoint(319,49))
        legend.setSymbolWidth(7)
        legend.setSymbolHeight(4)
        legend.setStyleFont(QgsLegendStyle.SymbolLabel, QFont("DejaVu Sans",7))
        legend.setMaximumSize(QgsLayoutSize(91,132))
        label("N ↑",321,188,15,True)
        label("REFERÊNCIA CARTOGRÁFICA",321,210,9,True)
        label("SIRGAS 2000 / UTM  |  EPSG:"+projected.authid().split(":")[-1],321,220,7)
        label("FONTES: "+str(request.get("source",""))[:85],321,236,7)
        bar=QgsLayoutItemScaleBar(layout)
        bar.setStyle("Single Box")
        bar.setLinkedMap(map_item)
        bar.setUnits(projected.mapUnits())
        bar.setNumberOfSegments(2)
        bar.setNumberOfSegmentsLeft(0)
        bar.setUnitsPerSegment(max(100,round(scale*.025/100)*100))
        layout.addLayoutItem(bar)
        bar.attemptMove(QgsLayoutPoint(14,270))
        label("ESCALA 1:"+f"{scale:,.0f}".replace(",","."),125,268,9,True)
        if request.get("branding"):
            label("AMAZONIKA GEOESPACIAL",320,277,8,True)
        output=Path(tmp.name)/"result.pdf"
        exporter=QgsLayoutExporter(layout)
        status=exporter.exportToPdf(str(output),QgsLayoutExporter.PdfExportSettings())
        if status != QgsLayoutExporter.Success:
            raise ValueError("Falha na exportação PDF ("+str(status)+")")
        return output.read_bytes()
    finally:
        tmp.cleanup()
        project.clear()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        payload=b'{"ok":true,"engine":"pyqgis"}'
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path != "/render":
            self.send_error(404)
            return
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<1 or size>MAX_BODY:
                self.send_error(413)
                return
            payload=json.loads(self.rfile.read(size))
            result=render(payload)
            self.send_response(200)
            self.send_header("Content-Type","application/pdf")
            self.send_header("Content-Length",str(len(result)))
            self.end_headers()
            self.wfile.write(result)
        except (KeyError,ValueError,TypeError) as exc:
            self.send_error(422,str(exc)[:150])
        except Exception:
            self.send_error(500,"Falha na renderização cartográfica")

if __name__=="__main__":
    HTTPServer(("0.0.0.0",8090),Handler).serve_forever()
