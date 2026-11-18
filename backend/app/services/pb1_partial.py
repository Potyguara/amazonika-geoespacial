from math import hypot, sqrt, isfinite

def partial_parameters(source, inputs):
    def positive(x):
        return isinstance(x,(int,float)) and not isinstance(x,bool) and isfinite(x) and x>0
    e,n,z=(inputs.get(k) for k in ("sigma_e_m","sigma_n_m","source_sigma_m"))
    e,n,z=(v if positive(v) else None for v in (e,n,z))
    origin="DECLARED" if e is not None or n is not None else "MISSING"
    if e is None and n is None:
        mm={"PEC A":.3,"PEC B":.5,"PEC C":.6}.get(source.get("pec"))
        try: scale=float(source.get("scale") or 0)
        except (ValueError,TypeError): scale=0
        if mm and isfinite(scale) and 0<scale<=1000000:
            e=n=mm*scale/1000/sqrt(2)
            origin="PEC_REFERENCE_ISOTROPIC_ESTIMATE"
    return {"sigma_e_m":e,"sigma_n_m":n,"source_sigma_m":z,
            "horizontal_sigma_m":hypot(e,n) if e is not None and n is not None else None,
            "sigma_origin":origin}

def partial_vertex(point,z,params,factor,source):
    # Only use documented normal height compatible with the declared model and grid.
    # The declaration is not proof of accuracy or RT approval.
    datum=str(source.get("vertical_datum") or "").casefold()
    model=str(source.get("source_model") or "").upper()
    kind=source.get("vertical_kind")
    factor_ok= isinstance(factor,(list,tuple)) and len(factor)==2 and all(isinstance(v,(int,float)) and isfinite(v) for v in factor) and factor[1]>=0
    documented=bool(str(source.get("vertical_reference") or "").strip())
    h=None; sigma=None; status="VERTICAL_PENDING"
    if z is not None and documented:
        if kind=="ELLIPSOIDAL" and model=="NONE" and ("sirgas" in datum or "grs80" in datum):
            h=z; sigma=params["source_sigma_m"];status="DECLARED_REFERENCE"
        elif kind=="NORMAL" and model=="HGEOHNOR2020" and factor_ok and "santana" in datum:
            h=z+factor[0];status="DECLARED_REFERENCE"
            if params["source_sigma_m"] is not None: sigma=hypot(params["source_sigma_m"],factor[1])
    pending=[]
    if h is None:
        if z is None: pending.append("Cota MDT indisponível.")
        if not documented: pending.append("Informe o documento que comprova o referencial vertical do MDT.")
        if kind not in ("NORMAL","ELLIPSOIDAL"): pending.append("Tipo de altitude original não identificado ou não suportado na conversão parcial.")
        elif kind=="NORMAL":
            if model!="HGEOHNOR2020": pending.append("Modelo original não confirmado como hgeoHNOR2020.")
            if "santana" not in datum: pending.append("Datum vertical compatível com Santana não confirmado.")
            if not factor_ok: pending.append("Fator IBGE válido e compatível ausente para este vértice.")
        elif model!="NONE" or not ("sirgas" in datum or "grs80" in datum):
            pending.append("Referencial elipsoidal SIRGAS 2000/GRS80 não confirmado.")
    if params["sigma_origin"]!="DECLARED" or params["sigma_e_m"] is None or params["sigma_n_m"] is None:
        pending.append("Precisão planimétrica individual por eixo ainda não fundamentada.")
    if sigma is None: pending.append("Sigma h pendente: confira a precisão vertical da fonte e a conversão.")
    return {"pending_reasons":pending,"vertex_id":point["name"],"latitude":point["latitude"],"longitude":point["longitude"],
            "source_value_m":z,"source_vertical_kind":kind,"source_vertical_datum":source.get("vertical_datum"),
            "h_ellipsoidal_m":h,"sigma_h_m":sigma,"sigma_e_m":params["sigma_e_m"],"sigma_n_m":params["sigma_n_m"],
            "conversion_factor_m":factor[0] if factor_ok else None,"factor_sigma_m":factor[1] if factor_ok else None,
            "status":status}
