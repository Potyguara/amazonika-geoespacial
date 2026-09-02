from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGEF_ODS = ROOT / "backend/app/services/sigef_ods.py"

s = SIGEF_ODS.read_text()
backup = SIGEF_ODS.with_suffix(SIGEF_ODS.suffix + ".bak-unlimited-municipalities-v2-20260902")
if not backup.exists():
    backup.write_text(s)

old = '''        municipalities = _municipalities_for_analysis(db, analysis)
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

new = '''        municipalities = _municipalities_for_analysis(db, analysis)
        if not municipalities:
            raise ValueError(
                "Malha municipal IBGE 2025 não carregada ou imóvel sem município identificado."
            )

        # O SIGEF aceita múltiplos municípios na linha Município(s).
        # Preenche um município por célula, sem limite de quantidade.
        # Quando houver apenas um município, repetimos A/B para manter
        # compatibilidade com o modelo já validado no simulador.
        municipality_values = list(municipalities)
        if len(municipality_values) == 1:
            municipality_values.append(municipality_values[0])

        identification_rows = identification.findall(f"{TABLE}table-row")
        if len(identification_rows) < 17:
            raise ValueError("Linha Município(s) não encontrada no modelo SIGEF.")

        municipality_row = identification_rows[16]
        municipality_cells = _expand_row_cells(municipality_row)
        if not municipality_cells:
            raise ValueError("A linha Município(s) não possui células utilizáveis.")

        # Expande a própria linha se a quantidade de municípios exceder
        # o número de células originalmente existentes no modelo.
        while len(municipality_cells) < len(municipality_values):
            template_cell = deepcopy(municipality_cells[-1])
            _set_string(template_cell, "")
            municipality_row.append(template_cell)
            municipality_cells.append(template_cell)

        for index, municipality in enumerate(municipality_values):
            _set_string(municipality_cells[index], municipality)

        # Limpa células remanescentes da linha para não carregar conteúdo
        # residual do modelo quando houver menos municípios que células.
        for index in range(len(municipality_values), len(municipality_cells)):
            _set_string(municipality_cells[index], "")
'''

if new in s:
    print("OK [sigef-ods] - múltiplos municípios ilimitados já aplicados")
elif old in s:
    s = s.replace(old, new, 1)
    SIGEF_ODS.write_text(s)
    print("OK [sigef-ods] - trava de dois municípios removida")
    print("OK [sigef-ods] - linha Município(s) agora aceita quantidade dinâmica")
else:
    raise SystemExit(
        "ERRO [sigef-ods] - bloco antigo de municípios não localizado. "
        "Nenhum arquivo foi alterado."
    )

print("SIGEF_UNLIMITED_MUNICIPALITIES_V2_OK")
