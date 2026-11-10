"""Regressão Topcon: valores reais do exemplo e bloqueios de inferência SIGEF."""
import unittest

from app.services.topcon_import import parse_topcon_report

REPORT = """INCRA
CABEÇALHO DO PROJETO
Nome do Projeto: PROCESSAMENTO.ttp
Unidade Linear: Meters
Unidade Angular: DMS
Projeção: UTMNorth-Zone_22 : 54W to 48W
Datum: SIRGAS
Geóide:

AJUSTAMENTO
Tipo de Ajustamento: Plano + Altura, Minimal constraint
Nivel de Confiança: 95 %
Numero de pontos Ajustados: 5

COORDENADAS UTM
Nome      Malha Norte (m)    Malha Este (m)     Elevação (m)
0304      120268,227         513406,376         18,730
0305      120168,534         514407,275         18,547
0306      119837,022         514641,039          0,077
0307      118621,291         514374,233         -0,355
Base      119803,968         514407,559          1,277

COORDENADAS GEOGRÁFICAS
Nome       Latitude                   Longitude                  Elevação (m)
0304       1°05'17,16230436"N          50°52'46,19565222"W          18,730
0305       1°05'13,91393911"N          50°52'13,80868335"W          18,547
0306       1°05'03,11624600"N          50°52'06,24502495"W           0,077
0307       1°04'23,52010296"N          50°52'14,87998580"W          -0,355
Base       1°05'02,04000025"N          50°52'13,80000009"W           1,277

DESVIO PADRÃO
Nome      Desv Padrão n (m)   Desv Padrão e (m)   Desv Padrão Hz (m)    Desv Padrão u (m)
0304      0,005              0,006              0,008                0,016
0305      0,015              0,021              0,026                0,058
0306      0,017              0,016              0,023                0,054
0307      0,006              0,007              0,009                0,016
Base      0,000              0,000              0,000                0,000

FATOR DE ESCALA
Nome      Fator de Escala Combinado Proj ao Terr    Convergência
0304      1,000400874590                          0°00'08,2379"
0305      1,000400500982                          0°00'08,8456"
"""


class TopconParsingTests(unittest.TestCase):
    def test_html_report_with_real_topcon_values(self):
        html="<html><body>"+REPORT.replace("\n", "<br>")+"</body></html>"
        result=parse_topcon_report(html.encode(), "PROCESSAMENTO.htm")
        self.assertEqual(result["point_count"],5)
        self.assertEqual(result["project"]["utm_zone"],22)
        self.assertEqual(result["project"]["hemisphere"],"N")
        self.assertEqual(result["project"]["datum"],"SIRGAS")
        point=next(p for p in result["points"] if p["name"]=="0304")
        self.assertAlmostEqual(point["northing_m"],120268.227)
        self.assertAlmostEqual(point["easting_m"],513406.376)
        self.assertAlmostEqual(point["sigma_hz_m"],0.008)
        self.assertAlmostEqual(point["scale_combined"],1.000400874590)
        self.assertIsNone(point["ellipsoidal_height_m"])
        self.assertIsNone(point["sigef_vertex_code"])
        base=next(p for p in result["points"] if p["name"]=="Base")
        self.assertEqual(base["point_role"],"CONTROL")
        self.assertFalse(result["ready_for_sigef"])
        self.assertFalse(result["checks"]["errors"],result["checks"])

    def test_invalid_reference_blocks_sirgas_assumption(self):
        raw=REPORT.replace("Datum: SIRGAS","Datum: Desconhecido")
        result=parse_topcon_report(raw.encode(), "PROCESSAMENTO.html")
        self.assertTrue(any("Datum" in x for x in result["checks"]["errors"]))

    def test_invalid_file_rejected_without_fabricating_coordinates(self):
        with self.assertRaises(ValueError):
            parse_topcon_report(b"sem tabela" * 100,"relatorio.html")

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            parse_topcon_report(b"A"*(12*1024*1024+1),"x.html")


if __name__=="__main__":
    unittest.main()
