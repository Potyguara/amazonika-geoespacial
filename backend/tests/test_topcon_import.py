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

DISTÂNCIA, SOLUÇÃO, ÓRBITA E PDOP
Nome        Distancia (m)      Tipo Solução   Órbita    PDOP    HDOP    VDOP
0304−Base   1104,165          Fixo,L1        Preciso   1,977   0,825   1,796
0305−Base   365,120           Fixo,L1        Preciso   2,219   0,913   2,023

DURAÇÃO E INTERVALO
Nome Ponto   Nome Original     Hora Início            Hora Fim              Duração    Método     Interval (msec) Tipo Antena
Base         Base              28/10/2026 06:30:00    28/10/2026 17:22:15   10:52:15   Estático    15000           HiPer SR
0304         0304              28/10/2026 06:40:00    28/10/2026 07:25:15   00:45:15   Estático    15000           HiPer SR
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
        self.assertEqual(len(result["solution"]), 2)
        self.assertEqual(result["solution"][0]["baseline"], "0304−Base")
        self.assertAlmostEqual(result["solution"][0]["pdop"], 1.977)
        self.assertEqual(len(result["sessions"]), 2)
        self.assertEqual(result["sessions"][1]["method"], "Estático")
        self.assertFalse(result["ready_for_sigef"])
        self.assertFalse(result["checks"]["errors"],result["checks"])

    def test_native_topcon_point_summary_and_observations(self):
        report = """AMAZONIKA - PROCESSAMENTO GNSS
Project
Project name: Teste.ttp
Projection: UTMNorth-Zone_22 : 54W to 48W
Datum: SIRGAS

Point Summary
Nome         Código       Malha Norte (m)     Malha Este (m)        Elevação (m)          Latitude WGS84           Longitude WGS84         Alt Elip WGS84 (m)
B1                       44727,941           513780,836           -14,850               0°24'16,80009815"N       50°52'34,14768533"W     -14,850
M578                     45165,067           513957,616           -17,695               0°24'31,03731751"N       50°52'28,42808961"W     -17,695
M581                     43983,336           514425,360           -20,882               0°23'52,54780377"N       50°52'13,29576794"W     -20,882

Observações GPS
Nome         dN (m)     dE (m)      dZ (m)       Horz RMS (m)    Vert RMS (m)    SigmaX (m)    SigmaY (m)    SigmaZ (m)    Tipo Solução
B1−M578      437,126    176,780     -2,845      0,002           0,005           0,003         0,004         0,002         Fixo
B1−M581      -744,605   644,524     -6,032      0,004           0,011           0,007         0,008         0,003         Fixo

Ocupações GPS
Nome Ponto      Hora Início              Hora Fim                 Duração     receptor     Interval (msec)
B1              24/10/2026 08:23:40      24/10/2026 11:11:15      02:47:35    RECEPTOR-1   5000
M578            24/10/2026 09:54:46      24/10/2026 10:00:14      00:05:28    RECEPTOR-2   1000
M581            24/10/2026 09:01:44      24/10/2026 09:08:04      00:06:20    RECEPTOR-2   1000

Ajustamento
Control Tie Analysis: success
"""
        raw = "<html><body>" + report.replace("\n", "<br>") + "</body></html>"
        result = parse_topcon_report(raw.encode("utf-8"), "relatorio.htm")
        self.assertEqual(result["point_count"], 3)
        self.assertEqual(result["project"]["name"], "Teste.ttp")
        self.assertEqual(result["project"]["utm_zone"], 22)
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(len(result["sessions"]), 3)
        self.assertAlmostEqual(result["observations"][0]["horizontal_rms_m"], 0.002)
        b1 = next(p for p in result["points"] if p["name"] == "B1")
        m578 = next(p for p in result["points"] if p["name"] == "M578")
        self.assertEqual(b1["point_role"], "CONTROL")
        self.assertAlmostEqual(m578["easting_m"], 513957.616)
        self.assertIsNone(m578["sigma_hz_m"])
        self.assertIsNone(m578["ellipsoidal_height_m"])
        self.assertAlmostEqual(m578["ellipsoidal_height_reported_m"], -17.695)
        self.assertTrue(any("WGS84" in w for w in result["checks"]["warnings"]))
        self.assertFalse(result["ready_for_sigef"])

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
