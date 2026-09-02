from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Source, SourceKind

OFFICIAL_SOURCES = (
    {
        "slug": "funai-terras-indigenas", "name": "Terras indígenas", "institution": "FUNAI",
        "kind": SourceKind.WFS, "service_url": "https://cmr.funai.gov.br/geoserver/ows",
        "layer_name": "CMR-PUBLICO:lim_terra_indigena_a", "update_frequency": "MENSAL",
        "metadata_json": {"provider": "FUNAI/CMR via INDE", "crs": "EPSG:4674", "wfs_version": "1.0.0", "stale_after_days": 15,
            "portal_url": "https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas"},
    },
    {
        "slug": "iphan-sitios", "name": "Sítios arqueológicos", "institution": "IPHAN",
        "kind": SourceKind.WFS, "service_url": "https://geoserver.iphan.gov.br/geoserver/ows",
        "layer_name": "SICG:sitios", "update_frequency": "MENSAL",
        "metadata_json": {"provider": "IPHAN/SICG", "geometry_role": "POINT", "crs": "EPSG:4674", "wfs_version": "1.0.0", "stale_after_days": 15,
            "portal_url": "https://www.gov.br/iphan/pt-br/patrimonio-cultural/patrimonio-arqueologico/cadastro-de-sitios-arqueologicos"},
    },
    {
        "slug": "iphan-sitios-poligonos", "name": "Áreas de sítios arqueológicos", "institution": "IPHAN",
        "kind": SourceKind.WFS, "service_url": "https://geoserver.iphan.gov.br/geoserver/ows",
        "layer_name": "SICG:sitios_pol", "update_frequency": "MENSAL",
        "metadata_json": {"provider": "IPHAN/SICG", "geometry_role": "POLYGON", "crs": "EPSG:4674", "wfs_version": "1.0.0", "stale_after_days": 15,
            "portal_url": "https://www.gov.br/iphan/pt-br/patrimonio-cultural/patrimonio-arqueologico/cadastro-de-sitios-arqueologicos"},
    },
    {
        "slug": "spu-imoveis-uniao", "name": "Patrimônio imobiliário da União", "institution": "SPU",
        "kind": SourceKind.WFS, "service_url": "https://geoservicos.inde.gov.br/geoserver/SPU/ows",
        "layer_name": "SPU:qualificageo_2026_jul_779088_rips_painel_brasil_filtro_sigilo", "update_frequency": "MENSAL",
        "metadata_json": {"provider": "SPU via INDE", "crs": "EPSG:4674", "wfs_version": "2.0.0", "stale_after_days": 31,
            "portal_url": "https://inde.gov.br/CatalogoGeoservicos", "access_mode": "PUBLIC_SERVICE", "service_role": "VECTOR_ANALYSIS",
            "wfs_layers": ["SPU:qualificageo_2026_jul_779088_rips_painel_brasil_filtro_sigilo", "SPU:vw_app_espelho_dagua_federal_a_04082026", "SPU:vw_app_ilha_federal_a_04082026", "SPU:vw_app_manguezal_federal_a_04082026", "SPU:vw_app_praia_federal_a_04082026", "SPU:vw_app_trecho_terreno_acrescido_marginal_a_04082026", "SPU:vw_app_trecho_terreno_acrescido_marinha_a_04082026", "SPU:vw_app_trecho_terreno_marginal_a_11082026", "SPU:vw_app_trecho_terreno_marinha_a_04082026"],
            "wms_enabled": True, "wms_theme": "spu_patrimonio", "wms_fixed_layer": "SPU:qualificageo_2026_jul_779088_rips_painel_brasil_filtro_sigilo,SPU:vw_app_espelho_dagua_federal_a_04082026,SPU:vw_app_ilha_federal_a_04082026,SPU:vw_app_manguezal_federal_a_04082026,SPU:vw_app_praia_federal_a_04082026,SPU:vw_app_trecho_terreno_acrescido_marginal_a_04082026,SPU:vw_app_trecho_terreno_acrescido_marinha_a_04082026,SPU:vw_app_trecho_terreno_marginal_a_11082026,SPU:vw_app_trecho_terreno_marinha_a_04082026",
            "wms_url": "https://geoservicos.inde.gov.br/geoserver/SPU/ows"},
    },
    {
        "slug": "sicar-imoveis-rurais", "name": "Cadastro Ambiental Rural (CAR)", "institution": "SICAR",
        "kind": SourceKind.WFS, "service_url": "https://geoserver.car.gov.br/geoserver/sicar/ows",
        "layer_name": "sicar:sicar_imoveis_ap", "update_frequency": "CONFORME_FONTE",
        "metadata_json": {"provider": "Serviço Florestal Brasileiro/SICAR", "crs": "EPSG:4674", "wfs_version": "2.0.0",
            "portal_url": "https://consultapublica.car.gov.br/publico/imoveis/index", "access_mode": "PUBLIC_SERVICE",
            "service_role": "WMS_REFERENCE_WITH_WFS_ON_DEMAND", "wfs_on_demand": True, "stale_after_days": 1,
            "wms_enabled": True, "wms_theme": "sicar:sicar_imoveis", "wms_url": "https://geoserver.car.gov.br/geoserver/sicar/wms",
            "allow_legacy_tls": True},
    },
    {
        "slug": "anm-processos-minerarios", "name": "Poligonais de processos minerários", "institution": "ANM",
        "kind": SourceKind.ARCGIS_FEATURE,
        "service_url": "https://geo.anm.gov.br/arcgis/rest/services/SIGMINE/dados_anm/MapServer",
        "layer_name": "0", "update_frequency": "DIARIA",
        "metadata_json": {"provider": "ANM/SIGMINE", "crs": "EPSG:4674", "stale_after_days": 1,
            "portal_url": "https://geo.anm.gov.br/arcgis/rest/services/SIGMINE/dados_anm/MapServer/0",
            "access_mode": "PUBLIC_SERVICE", "service_role": "WMS_REFERENCE_WITH_ARCGIS_REST_ON_DEMAND",
            "arcgis_on_demand": True, "arcgis_where": "FID >= 0", "wms_enabled": True, "wms_theme": "anm_processos", "wms_fixed_layer": "0",
            "wms_url": "https://geo.anm.gov.br/arcgis/services/SIGMINE/dados_anm/MapServer/WMSServer"},
    },
)

def main():
    configured = 0
    with SessionLocal() as db:
        for item in OFFICIAL_SOURCES:
            source = db.scalar(select(Source).where(Source.slug == item["slug"]))
            if source is None:
                source = Source(is_official=True, is_active=True, **item)
                db.add(source)
            else:
                for field, value in item.items(): setattr(source, field, value)
                source.is_official = True
            configured += 1
        db.commit()
    print(f"FUNAI, IPHAN, SPU, SICAR e ANM configurados: {configured} fonte(s) oficial(is).")

if __name__ == "__main__": main()
