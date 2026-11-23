"""Controle explícito da ressalva opcional de croqui.

Textos legados de documentos anteriormente gerados podem estar salvos no
campo memorial_edited. Quando a ressalva é desmarcada, elimina apenas os
dois avisos padronizados do sistema, sem modificar observações particulares.
"""
from __future__ import annotations

import re

from app.services.plant_memorial_v2 import DISCLAIMER

# Redação automática antiga do memorial simples (não é uma ressalva obrigatória).
LEGACY_PRECISION_NOTICE = (
    "Coordenadas referenciadas ao SIRGAS 2000; azimutes e distâncias "
    "geodésicos calculados sobre o elipsóide GRS80. "
    "A precisão depende da fonte da geometria; a emissão não corresponde "
    "a certificação fundiária."
)
PROFESSIONAL_PRECISION_NOTICE = (
    "Coordenadas referenciadas ao SIRGAS 2000; azimutes e distâncias "
    "geodésicos calculados sobre o elipsóide GRS80. A precisão depende "
    "da fonte da geometria; esta emissão não constitui certificação fundiária."
)


def _flexible_phrase(value: str) -> str:
    return r"\s+".join(re.escape(part) for part in value.split())


def remove_optional_warnings(text: str | None, include_croqui_warning: bool) -> str | None:
    """Retira SOMENTE os textos automáticos conhecidos quando desmarcado.

    Não elimina uma observação criada manualmente pelo usuário nem muda
    as informações geométricas. Preserva None como pedido de geração automática.
    """
    if text is None or include_croqui_warning:
        return text
    cleaned = text
    for phrase in (DISCLAIMER, LEGACY_PRECISION_NOTICE,
                   PROFESSIONAL_PRECISION_NOTICE):
        cleaned = re.sub(_flexible_phrase(phrase), "", cleaned,
                         flags=re.IGNORECASE)

    # Elimina o cabeçalho órfão APENAS quando ele antecede um aviso legado
    # do sistema e ficou vazio. Preserva demais observações pessoais.
    cleaned = re.sub(
        r"(?im)^[ \t]*OBSERVA[ÇC][ÃA]O\s*:\s*(?=\n\s*(?:\n|$))",
        "", cleaned,
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
