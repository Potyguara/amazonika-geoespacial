from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Source,SourceKind

INCRA_WMS={
    "incra-sigef-particular":("Parcelas SIGEF particulares","certificada_sigef_particular","QUINZENAL",False),
    "incra-sigef-publico":("Parcelas SIGEF públicas","certificada_sigef_publico","QUINZENAL",False),
    "incra-imoveis-certificados-privados":("Imóveis certificados privados","imoveiscertificados_privado","QUINZENAL",False),
    "incra-imoveis-certificados-publicos":("Imóveis certificados públicos","imoveiscertificados_publico","QUINZENAL",False),
    "incra-fundiario":("Parcelas georreferenciadas","parcelageo","QUINZENAL",True),
    "incra-assentamentos":("Assentamentos rurais","assentamentos","QUINZENAL",True),
    "incra-reconhecimento":("Áreas de reconhecimento territorial","reconhecimento","QUINZENAL",False),
    "incra-quilombolas":("Territórios quilombolas","quilombolas","QUINZENAL",True),
}

INCRA_UFS=("ac","al","ap","am","ba","ce","df","es","go","ma","mt","ms","mg","pa","pb","pr","pe","pi","rj","rn","rs","ro","rr","sc","sp","se","to")
INCRA_THEME_EXCLUSIONS={"quilombolas":{"ac","df","rr"}}

def state_urls(theme:str)->dict[str,str]:
    unavailable=INCRA_THEME_EXCLUSIONS.get(theme,set())
    return {uf:f"http://acervofundiario.incra.gov.br/i3geo/ogc.php?tema={theme}_{uf}" for uf in INCRA_UFS if uf not in unavailable}

def main():
    updated=0
    with SessionLocal() as db:
        for slug,(name,theme,frequency,default_active) in INCRA_WMS.items():
            source=db.scalar(select(Source).where(Source.slug==slug))
            if not source:
                source=Source(slug=slug,name=name,institution="INCRA",kind=SourceKind.DOWNLOAD,is_official=True,is_active=default_active,update_frequency=frequency,metadata_json={})
                db.add(source)
            metadata=dict(source.metadata_json or {})
            layer=f"{theme}_ap"
            official_url=f"http://acervofundiario.incra.gov.br/i3geo/ogc.php?tema={layer}"
            urls=state_urls(theme)
            metadata.update({"provider":"INCRA","crs":"EPSG:4674","access_mode":"PUBLIC_WMS_WFS","requires_auth":False,"service_role":"WMS_REFERENCE_WITH_WFS_ON_DEMAND","wms_enabled":True,"wfs_on_demand":True,"wfs_version":"1.1.0","wms_theme":theme,"wms_state":"ap","wms_url":official_url,"wms_urls":urls,"wms_available_ufs":sorted(urls),"wms_layer":layer,"allow_insecure_tls":True,"stale_after_days":15,"portal_url":"https://acervofundiario.incra.gov.br/i3geo/geodownload/geodados.php"})
            source.name=name
            source.kind=SourceKind.DOWNLOAD
            source.service_url=None
            source.layer_name=None
            source.update_frequency=frequency
            source.metadata_json=metadata
            updated+=1
        db.commit()
    print(f"Configuração WMS pública do INCRA aplicada a {updated} fonte(s).")

if __name__=="__main__": main()
