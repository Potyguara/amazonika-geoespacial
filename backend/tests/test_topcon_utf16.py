import unittest
from app.services.topcon_import import parse_topcon_report


class TopconUTF16Tests(unittest.TestCase):
    def test_extended_point_summary(self):
        headers = ["Nome","Código","Malha Norte (m)","Malha Este (m)","Elevação (m)",
                   "Latitude WGS84","Longitude WGS84","Alt Elip WGS84 (m)",
                   "Latitude","Longitude","Alt Elip (m)","Controle","Desv Padrão n (m)",
                   "Desv Padrão e (m)","Desv Padrão Hz (m)","Desv Padrão u (m)","Geoid Separation (m)"]
        from pyproj import Transformer
        lon,lat = Transformer.from_crs(31976,4674,always_xy=True).transform(459208.404,24719.545)
        def dms(v, hemi):
            v=abs(v); d=int(v); m=int((v-d)*60); s=((v-d)*60-m)*60
            return f'{d}°{m:02d}\'{s:.8f}"{hemi}'
        la,lo=dms(lat,"N"),dms(lon,"W")
        base=["REF","","24719,545","459208,404","-6,339",la,lo,"-6,339",la,lo,"-6,339","Ambos","0,000","0,000","0,000","0,000",""]
        mark=["M−0001","","24719,545","459208,404","-2,501",la,lo,"-2,501",la,lo,"-2,501","Nenhum","0,002","0,001","0,002","0,004",""]
        def row(values,tag):
            return "<TR>\n"+"\n".join(f"<{tag}>{v} </{tag}>" for v in values)+"</TR>"
        html="<html><body><div>Projection: UTMNorth-Zone_22</div><div>Datum: SIRGAS</div><table><caption>Point Summary</caption>"+row(headers,"TH")+row(base,"TD")+row(mark,"TD")+"</table></body></html>"
        for encoding in ("utf-16","utf-8-sig","cp1252"):
            with self.subTest(encoding=encoding):
                # Windows-1252 cannot represent the U+2212 typographic minus.
                source=html.replace("−","-") if encoding=="cp1252" else html
                result=parse_topcon_report(source.encode(encoding),"report.htm")
                self.assertEqual(result["point_count"],2)
                self.assertEqual(result["points"][0]["point_role"],"CONTROL")
                p=result["points"][1]
                self.assertEqual(p["name"],"M-0001")
                self.assertEqual(p["sigma_n_m"],.002)
                self.assertEqual(p["sigma_e_m"],.001)
                self.assertEqual(p["sigma_hz_m"],.002)
                self.assertEqual(p["sigma_u_m"],.004)
                self.assertEqual(p["ellipsoidal_height_reported_m"],-2.501)
                self.assertFalse(result["ready_for_sigef"])
                self.assertFalse(any("não precisões individuais" in w for w in result["checks"]["warnings"]))

    def test_two_control_bases_with_space_in_name(self):
        """Relatório com duas bases VRS ("BASE" e "BASE 1") não deve ser rejeitado."""
        headers = ["Nome","Código","Malha Norte (m)","Malha Este (m)","Elevação (m)",
                   "Latitude WGS84","Longitude WGS84","Alt Elip WGS84 (m)",
                   "Latitude","Longitude","Alt Elip (m)","Controle","Desv Padrão n (m)",
                   "Desv Padrão e (m)","Desv Padrão Hz (m)","Desv Padrão u (m)"]
        from pyproj import Transformer
        lon,lat = Transformer.from_crs(31976,4674,always_xy=True).transform(459208.163,24719.561)
        def dms(v, hemi):
            v=abs(v); d=int(v); m=int((v-d)*60); s=((v-d)*60-m)*60
            return f'{d}°{m:02d}\'{s:.8f}"{hemi}'
        la,lo=dms(lat,"N"),dms(lon,"W")
        def point(name, control, sigma):
            return [name,"","24719,561","459208,163","-8,830",la,lo,"-8,830",la,lo,"-8,830",control,sigma,sigma,sigma,sigma]
        def row(values,tag):
            return "<TR>\n"+"\n".join(f"<{tag}>{v} </{tag}>" for v in values)+"</TR>"
        occ_headers=["Nome Ponto","Hora Início","Hora Fim","Duração","receptor","Interval (msec)"]
        occ=["BASE 1","19/08/2026 09:05:36","19/08/2026 15:33:06","06:27:30","3487273","1000"]
        html=("<html><body><table><caption>Point Summary</caption>"+row(headers,"TH")
              +row(point("BASE","Ambos","0,000"),"TD")+row(point("BASE 1","Ambos","0,000"),"TD")
              +row(point("p1","Nenhum","0,001"),"TD")+"</table>"
              +"<table><caption>Ocupações GPS</caption>"+row(occ_headers,"TH")+row(occ,"TD")+"</table></body></html>")
        result=parse_topcon_report(html.encode("utf-16"),"report.htm")
        self.assertEqual(result["point_count"],3)
        names=[p["name"] for p in result["points"]]
        self.assertEqual(names,["BASE","BASE_1","p1"])
        self.assertEqual(result["points"][1]["point_role"],"CONTROL")
