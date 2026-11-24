from app.services.ps1_persistence import same_perimeter_cyclic


def _v(code, lat, lon):
    return {"sigef_vertex_code": code, "latitude": lat, "longitude": lon}


BASE = [_v("A-M-0001", 0.23, -51.36), _v("A-V-0001", 0.22, -51.37), _v("A-M-0002", 0.21, -51.36)]


def test_rotacao_do_vertice_inicial_e_aceita():
    assert same_perimeter_cyclic(BASE, BASE[1:] + BASE[:1])


def test_inversao_do_sentido_nao_e_aceita():
    assert not same_perimeter_cyclic(BASE, list(reversed(BASE)))


def test_coordenada_alterada_nao_e_aceita():
    changed = [dict(BASE[0], latitude=0.2301)] + BASE[1:]
    assert not same_perimeter_cyclic(BASE, changed)


def test_codigo_duplicado_nao_e_aceito():
    assert not same_perimeter_cyclic(BASE, [BASE[0], BASE[0], BASE[2]])
