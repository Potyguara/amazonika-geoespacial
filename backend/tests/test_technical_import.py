"""Testes mínimos do importador SIGEF ODS, sem arquivo privado de terceiros."""
import io
import unittest
import zipfile

from app.services.technical_import import parse_sigef_ods, _dms


def _make_ods():
    ns = "urn:oasis:names:tc:opendocument:xmlns:"
    def cell(value):
        return f'<table:table-cell><text:p>{value}</text:p></table:table-cell>'
    def row(*values):
        return "<table:table-row>" + "".join(cell(v) for v in values) + "</table:table-row>"
    def table(name, rows):
        return f'<table:table table:name="{name}">' + "".join(rows) + "</table:table>"
    ident = table("identificacao", [
        row("Nome:", "TESTADOR"),
        row("CPF:", "000.000.000-00"),
        row("Denominação:", "LOTE TESTE"),
        row("Situação:", "Área não Titulada"),
        row("Município(s):", ""),
        row("Município Exemplo-AP"),
    ])
    perim = table("perimetro_1", [
        row("Denominação:", "LOTE TESTE"),
        row("Parcela número:", "001"),
        row("Lado:", "Externo"),
        row("Tipo de Coordenada:", "Geográfica"),
        row("Vértice","E/Long","Sigma long","N/Lat","Sigma lat","h","Sigma h","Método Posicionamento","Tipo Limite","CNS","Matrícula","Descritivo"),
        row("EQGV-V-502", "50 52 40,069 W","0,01","01 05 20,821 N","0,01","1,11","0,02","PA2","LA6","","","Ramal Exemplo"),
        row("EQGV-V-503", "50 52 38,682 W","0,01","01 05 20,149 N","0,01","1,05","0,02","PA2","LA6","","","Ramal Exemplo"),
        row("EQGV-M-0305", "50 52 13,917 W","0,02","01 05 14,041 N","0,02","18,55","0,03","PG1","LA6","","","Vizinho"),
    ])
    xml = f'<office:document-content xmlns:office="{ns}office:1.0" xmlns:table="{ns}table:1.0" xmlns:text="{ns}text:1.0"><office:body><office:spreadsheet>{ident}{perim}</office:spreadsheet></office:body></office:document-content>'
    out = io.BytesIO()
    with zipfile.ZipFile(out,"w") as z:
        z.writestr("mimetype","application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml",xml)
    return out.getvalue()


class TestSigefODS(unittest.TestCase):
    def test_dms(self):
        self.assertAlmostEqual(_dms("50 52 40,069 W", False), -50.87779694444, places=7)
        self.assertAlmostEqual(_dms("01 05 20,821 N", True), 1.08911694444, places=7)

    def test_preserves_real_names_and_confrontants(self):
        result = parse_sigef_ods(_make_ods())
        self.assertEqual(result["vertex_count"], 3)
        self.assertEqual(len(result["features"]), 1)
        feature = result["features"][0]
        props = feature["properties"]
        self.assertEqual(props["vertexNames"], ["EQGV-V-502", "EQGV-V-503", "EQGV-M-0305"])
        self.assertEqual(props["confrontants"], ["Ramal Exemplo", "Ramal Exemplo", "Vizinho"])
        self.assertEqual(props["altitudes"], ["1.11", "1.05", "18.55"])
        self.assertEqual(props["sigef_vertex_details"][2]["positioning_method"], "PG1")
        self.assertEqual(len(feature["geometry"]["coordinates"][0]), 4)
        self.assertEqual(result["metadata"]["owner"], "TESTADOR")
        self.assertEqual(result["metadata"]["municipality"], "Município Exemplo-AP")

    def test_rejects_invalid_file(self):
        with self.assertRaises(ValueError):
            parse_sigef_ods(b"invalid")


if __name__ == "__main__":
    unittest.main()
