from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "backend/app/services/analyzer.py"
SIGEF_ODS = ROOT / "backend/app/services/sigef_ods.py"


def patch_analyzer() -> None:
    s = ANALYZER.read_text()

    old = '''                overlap=0.0
                if subject.geom_type!="Point" and matched:
                    overlap=float(db.scalar(
                        select(func.coalesce(func.sum(
                            func.ST_Area(_geography(func.ST_Intersection(GeoFeature.geom,db_geom)))/10000.0
                        ),0)).where(filter_version,intersects)
                    ) or 0)
'''

    new = '''                overlap=0.0
                if subject.geom_type!="Point" and matched:
                    # A sobreposição territorial de uma fonte deve representar
                    # a área ÚNICA ocupada dentro do imóvel. Somar a interseção
                    # de cada feição individualmente duplica áreas quando duas
                    # ou mais feições da mesma fonte se sobrepõem entre si.
                    # Primeiro coletamos/dissolvemos as interseções e somente
                    # depois calculamos a área geodésica do resultado.
                    intersection_geom = func.ST_Intersection(
                        GeoFeature.geom,
                        db_geom,
                    )
                    dissolved_overlap = func.ST_UnaryUnion(
                        func.ST_Collect(intersection_geom)
                    )
                    overlap=float(db.scalar(
                        select(
                            func.coalesce(
                                func.ST_Area(
                                    _geography(dissolved_overlap)
                                ) / 10000.0,
                                0,
                            )
                        ).where(filter_version,intersects)
                    ) or 0)
'''

    if old in s:
        s = s.replace(old, new, 1)
        print("OK [analyzer] - soma bruta substituída por união espacial única")
    elif "dissolved_overlap = func.ST_UnaryUnion" in s:
        print("OK [analyzer] - união espacial única já estava aplicada")
    else:
        raise SystemExit("ERRO [analyzer]: bloco de cálculo de overlap não localizado")

    old_percent = '        percent=(overlap/area_ha*100) if area_ha else 0.0\n'
    new_percent = '''        # Tolerâncias geométricas de ponto flutuante não podem produzir
        # percentuais acima de 100% para uma interseção contida no imóvel.
        percent=min(100.0, (overlap/area_ha*100)) if area_ha else 0.0
'''
    if old_percent in s:
        s = s.replace(old_percent, new_percent, 1)
        print("OK [analyzer] - percentual limitado ao domínio territorial 0-100%")
    elif "percent=min(100.0" in s:
        print("OK [analyzer] - limite percentual já estava aplicado")
    else:
        raise SystemExit("ERRO [analyzer]: cálculo percentual não localizado")

    s = s.replace(
        '"calculation":"POSTGIS_VECTOR"',
        '"calculation":"POSTGIS_VECTOR_UNIQUE_UNION"',
    )

    ANALYZER.write_text(s)


def patch_sigef_ods() -> None:
    s = SIGEF_ODS.read_text()

    # Precisamos de text() para consultar a malha municipal estrutural do IBGE.
    if "from sqlalchemy import func, select, text" not in s:
        if "from sqlalchemy import func, select" in s:
            s = s.replace(
                "from sqlalchemy import func, select",
                "from sqlalchemy import func, select, text",
                1,
            )
        else:
            raise SystemExit("ERRO [sigef_ods]: import sqlalchemy não localizado")

    helper_anchor = "\ndef _write_perimeter(\n"
    if "def _decimal_to_dms(" not in s:
        if helper_anchor not in s:
            raise SystemExit("ERRO [sigef_ods]: _write_perimeter não localizado")
        helper = r'''
def _decimal_to_dms(value: float, axis: str) -> str:
    """Converte grau decimal para o texto geográfico aceito pelo SIGEF.

    Exemplo do modelo validado:
        longitude: 51 13 27,694 W
        latitude:  01 04 59,070 N
    """
    absolute = abs(float(value))
    degrees = int(absolute)
    minutes_float = (absolute - degrees) * 60.0
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60.0, 3)

    # Corrige eventual transporte de arredondamento.
    if seconds >= 60.0:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1

    axis = axis.lower()
    if axis == "lon":
        hemisphere = "W" if value < 0 else "E"
    elif axis == "lat":
        hemisphere = "S" if value < 0 else "N"
    else:
        raise ValueError("Eixo inválido para conversão GMS.")

    degree_text = f"{degrees:02d}"
    second_text = f"{seconds:06.3f}".replace(".", ",")
    return f"{degree_text} {minutes:02d} {second_text} {hemisphere}"


def _municipalities_for_analysis(db: Session, analysis: Analysis) -> list[str]:
    """Retorna os municípios efetivamente interceptados pelo imóvel.

    A tabela ibge_municipios_2025 é uma referência estrutural do sistema,
    independente das camadas que o usuário liga/desliga para a análise.
    Interseções meramente lineares/de fronteira (<= 1 m²) são descartadas.
    """
    exists = db.scalar(text("SELECT to_regclass('public.ibge_municipios_2025')"))
    if not exists:
        return []

    rows = db.execute(
        text(
            """
            SELECT
                m.nm_mun,
                m.sigla_uf,
                ST_Area(
                    ST_Intersection(m.geom, a.input_geom)::geography
                ) AS intersection_area_m2
            FROM ibge_municipios_2025 AS m
            JOIN analyses AS a
              ON a.id = :analysis_id
            WHERE ST_Intersects(m.geom, a.input_geom)
              AND ST_Area(
                    ST_Intersection(m.geom, a.input_geom)::geography
                  ) > 1.0
            ORDER BY intersection_area_m2 DESC, m.nm_mun
            """
        ),
        {"analysis_id": str(analysis.id)},
    ).all()

    result: list[str] = []
    seen: set[str] = set()
    for name, uf, _area in rows:
        label = f"{str(name).strip()}-{str(uf).strip().upper()}"
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result

'''
        s = s.replace(helper_anchor, "\n" + helper + "def _write_perimeter(\n", 1)
        print("OK [sigef_ods] - conversor GMS e resolvedor municipal adicionados")
    else:
        print("OK [sigef_ods] - helpers GMS/município já estavam presentes")

    # O tipo de coordenada deve ser explicitamente Geográfica.
    marker = '''    # Cabeçalho do perímetro.
    _set_identification_value(
        sheet,
        3,
        2,
'''
    if marker in s and '"Geográfica"' not in s[s.find("def _write_perimeter("):s.find("def build_sigef_simulation_ods(")]:
        insertion = '''    # O modelo SIGEF validado usa coordenadas geográficas em GMS.
    _set_identification_value(
        sheet,
        9,
        2,
        "Geográfica",
    )

'''
        s = s.replace(marker, insertion + marker, 1)
        print("OK [sigef_ods] - tipo de coordenada definido como Geográfica")

    old_coords = '''        _set_number(cells[1], longitude)
        _set_number(cells[2], 0.0)
        _set_number(cells[3], latitude)
        _set_number(cells[4], 0.0)
'''
    new_coords = '''        _set_string(cells[1], _decimal_to_dms(longitude, "lon"))
        _set_number(cells[2], 0.0)
        _set_string(cells[3], _decimal_to_dms(latitude, "lat"))
        _set_number(cells[4], 0.0)
'''
    if old_coords in s:
        s = s.replace(old_coords, new_coords, 1)
        print("OK [sigef_ods] - longitude/latitude decimal substituídas por GMS")
    elif '_decimal_to_dms(longitude, "lon")' in s:
        print("OK [sigef_ods] - escrita GMS já estava aplicada")
    else:
        raise SystemExit("ERRO [sigef_ods]: escrita das coordenadas não localizada")

    # Preenche Município(s) imediatamente antes do perímetro. A linha 17 é a
    # utilizada pelo validador SIGEF. O modelo validado aceita um município em
    # cada célula A/B da linha 17; com um único município repetimos o valor,
    # exatamente como na ODS válida fornecida como referência.
    call_anchor = '''        _write_perimeter(
            perimeter,
            polygon,
        )
'''
    if "municipalities = _municipalities_for_analysis" not in s:
        municipal_block = '''        municipalities = _municipalities_for_analysis(db, analysis)
        if not municipalities:
            raise ValueError(
                "Malha municipal IBGE 2025 não carregada ou imóvel sem município identificado."
            )
        if len(municipalities) > 2:
            raise ValueError(
                "A área intercepta mais de dois municípios; revise a geometria antes da simulação SIGEF: "
                + ", ".join(municipalities)
            )

        first_municipality = municipalities[0]
        second_municipality = (
            municipalities[1]
            if len(municipalities) > 1
            else first_municipality
        )
        _set_identification_value(
            identification,
            17,
            1,
            first_municipality,
        )
        _set_identification_value(
            identification,
            17,
            2,
            second_municipality,
        )

'''
        if call_anchor not in s:
            raise SystemExit("ERRO [sigef_ods]: chamada _write_perimeter não localizada")
        s = s.replace(call_anchor, municipal_block + call_anchor, 1)
        print("OK [sigef_ods] - Município(s) preenchido(s) por interseção espacial")
    else:
        print("OK [sigef_ods] - preenchimento municipal já estava aplicado")

    SIGEF_ODS.write_text(s)


patch_analyzer()
patch_sigef_ods()
print("UNIQUE_OVERLAP_AND_SIGEF_ODS_OK")
