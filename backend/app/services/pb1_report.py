from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from xml.sax.saxutils import escape
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw
from pyproj import Transformer
import json
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from pyproj import Geod

def build_pb1_report(title, piece_id, snapshot, paths):
    top = snapshot.get("topcon") or {}
    pb = snapshot.get("pb1") or {}
    source = top.get("pb1_source") or {}
    vertices = top.get("pb1_draft") or []
    if not vertices:
        raise ValueError("Nenhum vértice PB1 salvo.")
    preview = pb.get("partial_preview") or pb.get("technical_preview") or {}
    assets = pb.get("assets") or {}
    calculated = {p["vertex_id"]:p for p in preview.get("points",[]) if p.get("vertex_id")}
    if preview.get("color_sha256") != (assets.get("pb1_color") or {}).get("sha256") or preview.get("dtm_sha256") != (assets.get("pb1_dtm") or {}).get("sha256"):
        calculated = {}
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize=9
    styles["Normal"].leading=13
    story=[]
    def p(value, style="Normal"):
        story.append(Paragraph(escape(str(value)),styles[style]))
        story.append(Spacer(1,6))
    def val(x):
        return "Não informado" if x is None or x=="" else str(x)
    def num(x):
        return "—" if x is None else f"{float(x):.3f}"
    def table(rows,widths):
        t=LongTable([[Paragraph(escape(str(v)),styles["Normal"]) for v in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dcece5")),("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,-1),.25,colors.lightgrey)]))
        story.append(t);story.append(Spacer(1,10))
    p("AMAZÔNIKA GEOESPACIAL","Heading2")
    p("Relatório técnico do cálculo de vértices — PB1","Title")
    p("PRELIMINAR — sujeito à revisão do responsável técnico")
    p(f"Imóvel: {title} | Peça: {piece_id}")
    p("Emissão UTC: "+datetime.now(timezone.utc).isoformat())
    p("1. Origem e parâmetros declarados","Heading2")
    for k,label in [("product","Produto"),("sheet","Folhas INOM/MI"),("scale","Escala"),("pec","PEC"),("accuracy_reference","Documento de exatidão"),("vertical_kind","Tipo de altitude"),("vertical_datum","Datum vertical"),("source_model","Modelo original"),("vertical_reference","Documento vertical")]:
        p(label+": "+val(source.get(k)))
    p("2. Insumos e rastreabilidade","Heading2")
    for kind in ("pb1_color","pb1_dtm"):
        a=assets.get(kind) or {}; m=a.get("metadata") or {}
        p(kind+" | SHA-256: "+val(a.get("sha256")))
        for k in ("filename","size_bytes"):
            p(k+": "+val(a.get(k)))
        for k in ("width","height","crs_authority","vertical_crs_name","geo_transform","bands"):
            p(k+": "+val(m.get(k)))
    p("3. Metodologia e fórmulas","Heading2")
    p("Digitalização manual sobre ORIXP georreferenciado; leitura da cota do MDT numérico. Coordenadas geográficas preservadas. A cota original não comprova o datum.")
    p("Quando há conversão válida: h = HN + eta (altura normal) ou h = H + N (ortométrica). Se a origem for elipsoidal, h = Z. Propagação sob independência: sigma_h = sqrt(sigma_MDT² + sigma_fator²). Precisão horizontal declarada: sqrt(sigma_E² + sigma_N²).")
    p("Distâncias e azimutes do trecho abaixo: solução geodésica inversa no elipsoide GRS80 (pyproj.Geod.inv), não distância plana UTM.")
    model=preview.get("local_height_model") if calculated else None
    if model:
        p("Ajustamento vertical local exploratório","Heading3")
        p("C_i = h_GNSS,i - Z_MDT,i; C = média(C_i); h_V = Z_MDT,V + C. HN estimada = h_V - eta quando houver fator IBGE compatível. O modelo não identifica o datum original.")
        p("Validação cruzada: para cada referência i, e_i = C_i - média dos demais C. RMSE_LOO = raiz da média dos quadrados de e_i. Não é validação independente nem sigma h aprovado.")
        p("Amostra: "+str(model["count"])+" | Correção média: "+num(model["offset_m"])+" m | Desvio padrão amostral: "+num(model["sample_std_m"])+" m | RMSE_LOO: "+num(model["rmse_loo_m"])+" m")
        controls=[["Marco","h GNSS","Cota MDT","Correção","Resíduo LOO"]]
        for r in model["controls"]:
            controls.append([r["name"],num(r["h_gnss_m"]),num(r["mdt_m"]),num(r["correction_m"]),num(r["loo_residual_m"])])
        table(controls,[120,85,85,85,108])
        p("Sem avaliação planimétrica independente; valores de precisão não aprovados.")
    p("4. Resultados dos vértices","Heading2")
    rows=[["Vértice","Latitude","Longitude","MDT (m)","h (m)","Sigma h"]]
    sigmas=[["Vértice","Tipo de altitude original","Fator (m)","Sigma E","Sigma N"]]
    for v in vertices:
        r=calculated.get(v["name"],{})
        if r.get("latitude")!=v.get("latitude") or r.get("longitude")!=v.get("longitude"): r={}
        rows.append([v["name"],f'{v["latitude"]:.8f}',f'{v["longitude"]:.8f}',num(r.get("source_value_m",v.get("source_elevation_m"))),num(r.get("h_ellipsoidal_m")),num(r.get("sigma_h_m"))])
        sigmas.append([v["name"],val(r.get("source_vertical_kind")),num(r.get("conversion_factor_m")),num(r.get("sigma_e_m")),num(r.get("sigma_n_m"))])
    table(rows,[98,82,82,76,76,69]);table(sigmas,[100,155,76,76,76])
    p("5. Trecho M–V–M","Heading2")
    closure=top.get("pb1_closure") or {}
    boundary=[v for v in (top.get("boundary") or []) if not v.get("derived_calculation")]
    start=next((i for i,v in enumerate(boundary) if closure.get("start") in (v.get("name"),v.get("sigef_vertex_code"))),None)
    chain=list(vertices)
    if closure.get("confirmed") and start is not None and len(boundary)>=2:
        ends=[boundary[start],boundary[(start+1)%len(boundary)]]
        if all(isinstance(v.get("longitude"),(int,float)) and isinstance(v.get("latitude"),(int,float)) for v in ends):
            chain=[ends[0],*vertices,ends[1]]
    def name(v): return v.get("sigef_vertex_code") or v["name"]
    geod=Geod(ellps="GRS80"); rows=[["Inicial","Final","Azimute (graus)","Distância (m)"]]
    total=0
    for a,b in zip(chain,chain[1:]):
        az,_,d=geod.inv(a["longitude"],a["latitude"],b["longitude"],b["latitude"])
        total+=d
        rows.append([name(a),name(b),num(az%360),num(d)])
    table(rows,[130,130,110,113])
    p("Comprimento geodésico do trecho apresentado: "+num(total)+" m.")
    p("Fechamento declarado: "+("confirmado" if closure.get("confirmed") else "pendente"))
    p("Trecho apresentado: "+("M–V–M" if len(chain)>len(vertices) else "somente V, marcos inicial/final não determinados")+". Não representa o perímetro integral.")
    p("6. Evidências raster","Heading2")
    images=[]
    with tempfile.TemporaryDirectory() as tmp:
        for kind,path in paths.items():
            try:
                out=Path(tmp)/(kind+".png")
                cmd=["gdal_translate","-of","PNG","-outsize","480","0","-ot","Byte"]
                if kind=="pb1_dtm":cmd+=["-b","1","-scale"]
                else:cmd+=["-b","1","-b","2","-b","3","-scale"]
                subprocess.run(cmd+[str(path),str(out)],capture_output=True,check=True,timeout=30)
                im=Image(BytesIO(out.read_bytes()));im._restrictSize(470,320)
                p(kind+" — recorte original, contraste apenas ilustrativo")
                story.append(im);story.append(Spacer(1,8))
                # GDAL output geotransform gives the actual thumbnail pixel locations.
                try:
                    info=json.loads(subprocess.run(["gdalinfo","-json",str(out)],capture_output=True,check=True,timeout=15).stdout)
                    gt=info["geoTransform"]
                    crs=info["coordinateSystem"]["wkt"]
                    tr=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
                    det=gt[1]*gt[5]-gt[2]*gt[4]
                    if not det: raise ValueError("Transformação singular")
                    canvas=PILImage.open(out).convert("RGB");draw=ImageDraw.Draw(canvas)
                    coords=[]
                    for v in chain:
                        x,y=tr.transform(v["longitude"],v["latitude"])
                        px=((x-gt[0])*gt[5]-(y-gt[3])*gt[2])/det
                        py=((y-gt[3])*gt[1]-(x-gt[0])*gt[4])/det
                        coords.append((px,py))
                    if len(coords)>1: draw.line(coords,fill="#ff375e",width=3)
                    for v,(x,y) in zip(chain,coords):
                        if 0<=x<canvas.width and 0<=y<canvas.height:
                            draw.ellipse((x-4,y-4,x+4,y+4),fill="#ffffff",outline="#ad1740",width=2)
                            draw.text((x+6,y-8),name(v),fill="#ffffff",stroke_width=2,stroke_fill="#20382f")
                    overlay=BytesIO();canvas.save(overlay,format="PNG");overlay.seek(0)
                    im2=Image(overlay);im2._restrictSize(470,320)
                    p("Trecho digitalizado sobre o recorte — visualização de apoio, sem escala de impressão")
                    story.append(im2);story.append(Spacer(1,8))
                except (OSError,subprocess.SubprocessError,ValueError,KeyError,ZeroDivisionError):
                    p("Sobreposição indisponível: georreferência da miniatura não recuperada.")

            except (OSError,subprocess.SubprocessError,ValueError):
                p(kind+": miniatura indisponível.")
        p("7. Revisão e responsabilidade técnica","Heading2")
        p("Resultados disponíveis: "+str(len(calculated))+" conversões na prévia vinculada aos rasters. A exatidão deve ser fundamentada por documentação ou avaliação técnica adequada. Ajustes empíricos sem validação externa permanecem preliminares. Não equivale a aprovação RT ou certificação SIGEF.")
        p("Referência do cálculo: "+val(preview.get("calculated_at")))
        p("Responsável técnico: __________________________________")
        p("Registro profissional / ART: ____________________________")
        p("Assinatura e data: _____________________________________")
        buf=BytesIO()
        def footer(c,d):
            c.setFont("Helvetica",8);c.drawString(56,32,"Amazônika Geoespacial | PB1 | PRELIMINAR")
            c.drawRightString(539,32,str(d.page))
        SimpleDocTemplate(buf,pagesize=A4,leftMargin=56,rightMargin=56,topMargin=45,bottomMargin=48).build(story,onFirstPage=footer,onLaterPages=footer)
        return buf.getvalue()
