"""Diagnóstico de prontidão da ODS PB1, sem aprovação nem certificação."""
from math import isfinite
from app.services.topcon_perimeter_review import review_topcon_perimeter

def _positive(v):
    return isinstance(v, (int,float)) and not isinstance(v,bool) and isfinite(v) and v>0

def audit_pb1_ods(snapshot, vertices, profile=None):
    top=snapshot.get("topcon") or {}
    pb=snapshot.get("pb1") or {}
    source=top.get("pb1_source") or {}
    draft=top.get("pb1_draft") or []
    preview=pb.get("partial_preview") or {}
    rows={r.get("vertex_id"):r for r in preview.get("points",[]) if isinstance(r,dict)}
    controls={p.get("name"):p for p in top.get("boundary") or [] if isinstance(p,dict)}
    points={p.get("name"):p for p in draft if isinstance(p,dict)}
    global_errors=[]
    if not (top.get("pb1_closure") or {}).get("confirmed"):
        global_errors.append("Fechamento geométrico PB1 não confirmado.")
    if not (pb.get("assets") or {}).get("pb1_dtm"):
        global_errors.append("MDT numérico não vinculado.")
    if not preview:
        global_errors.append("Processamento PB1 ainda não registrado no servidor.")
    if len(vertices)<3:
        global_errors.append("Perímetro com menos de três vértices.")
    if len({v.get("name") for v in vertices}) != len(vertices):
        global_errors.append("Nomes internos duplicados no perímetro.")
    if len({v.get("sigef_vertex_code") for v in vertices}) != len(vertices):
        global_errors.append("Códigos SIGEF duplicados.")
    missing_doc=[k for k in ("product","accuracy_reference","vertical_reference") if not str(source.get(k) or "").strip()]
    if missing_doc:
        global_errors.append("Fonte cartográfica sem identificação/referências técnicas: "+", ".join(missing_doc)+".")
    if preview.get("sigma_origin")!="DECLARED":
        global_errors.append("Precisões planimétricas PB1 não fundamentadas por avaliação/documentação.")
    if len(points)!=sum(v.get("sigef_method")=="PB1" for v in vertices):
        global_errors.append("Número de vértices PB1 divergente do registro de construção.")
    checks=review_topcon_perimeter(vertices)
    global_errors.extend(checks.get("errors",[]))
    global_errors.extend(checks.get("ods_errors",[]))
    full=[]
    for v in vertices:
        name=str(v.get("name") or "")
        code=str(v.get("sigef_vertex_code") or name)
        is_virtual=v.get("sigef_method")=="PB1"
        reason=[]
        if not code.strip():reason.append("Código SIGEF ausente")
        if not v.get("sigef_method"):reason.append("Método ausente")
        if not v.get("boundary_type"):reason.append("Tipo de limite ausente")
        if not v.get("confrontant"):reason.append("Confrontante ausente")
        if v.get("height_reference_confirmed") is not True or not isinstance(v.get("ellipsoidal_height_m"),(int,float)) or not isfinite(v["ellipsoidal_height_m"]):
            reason.append("Altura elipsoidal h não confirmada")
        for field,label in (("sigma_lon_m","σE"),("sigma_lat_m","σN"),("sigma_h_m","σh")):
            if not _positive(v.get(field)):reason.append(label+" ausente/inválido")
        if is_virtual:
            original=points.get(name)
            row=rows.get(name)
            if not original or not row:
                reason.append("Vértice não vinculado ao processamento PB1 salvo")
            else:
                for k in ("latitude","longitude"):
                    v0=v.get(k)
                    if not isinstance(v0,(int,float)) or not isfinite(v0) or abs(v0-row.get(k,1e20))>5.1e-10 or abs(v0-original.get(k,1e20))>5.1e-10:
                        reason.append("Coordenadas divergentes do cálculo");break
                if row.get("status")!="DECLARED_REFERENCE":
                    reason.append("Altura PB1 não validada: "+str(row.get("status") or "sem cálculo"))
                for out,inner in (("ellipsoidal_height_m","h_ellipsoidal_m"),("sigma_lon_m","sigma_e_m"),("sigma_lat_m","sigma_n_m"),("sigma_h_m","sigma_h_m")):
                    if v.get(out)!=row.get(inner):
                        reason.append("Atributo "+out+" divergente ou pendente no servidor")
        elif name not in controls:
            reason.append("Marco M não identificado na divisa GNSS original")
        full.append({"name":name,"code":code,"method":v.get("sigef_method"),"ready":not reason,"reasons":list(dict.fromkeys(reason))})
    verified=sum(row["ready"] for row in full)
    count_pb1=sum(v.get("sigef_method")=="PB1" for v in vertices)
    ready=verified==len(full) and not global_errors and count_pb1==len(points) and bool(points)
    return {
        "status":"READY_FOR_RT_REVIEW" if ready else "PENDING",
        "vertex_count":len(vertices),"original_count":len(vertices)-count_pb1,
        "pb1_count":count_pb1,"complete_count":verified,
        "global_issues":list(dict.fromkeys(global_errors)),
        "vertices":full,
        "notice":"Verificação técnica local. Mesmo quando completa, requer avaliação documental do RT e não substitui a validação SIGEF.",
    }
