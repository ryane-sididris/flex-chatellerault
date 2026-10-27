"""
Plateforme de flexibilité locale – ZA Sanital, Châtellerault
Lancer :  streamlit run app.py
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import flex_core as fc

st.set_page_config(page_title="Flexibilité Châtellerault", layout="wide")

COUL = {"Industrie": "#2a78d6", "Tertiaire": "#eb6834", "VE": "#1baf7a", "Batterie": "#eda100"}
NOM_CAT = {"Industrie": "Usine", "Tertiaire": "Commerce / bureau", "VE": "Recharge de véhicules", "Batterie": "Batterie"}
ROUGE, VERT, GRIS = "#e34948", "#1baf7a", "#52514e"
TAUX, VIE, FIXES = 0.05, 40, 5000          # hypothèses fixes (voir rapport)


def pc(x):
    return f"{x * 100:.0f} %"


def fr(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def intro(texte):
    st.markdown(f"<p style='font-size:1.1rem;color:#333;margin-bottom:1.2rem'>{texte}</p>", unsafe_allow_html=True)


def chiffre(col, titre, valeur, detail=""):
    col.markdown(
        f"<div style='background:#f4f3ef;border-radius:10px;padding:14px 16px;height:100%'>"
        f"<div style='font-size:.9rem;color:#555'>{titre}</div>"
        f"<div style='font-size:1.9rem;font-weight:600;color:#14213d;line-height:1.2'>{valeur}</div>"
        f"<div style='font-size:.85rem;color:#666'>{detail}</div></div>", unsafe_allow_html=True)


def style(fig, titre, h=400):
    fig.update_layout(title=dict(text=titre, font=dict(size=17)), height=h, plot_bgcolor="white",
                      margin=dict(l=10, r=10, t=60, b=10), legend_title=None,
                      legend=dict(orientation="h", y=-0.28))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#eeeeee")
    return fig


@st.cache_data
def donnees():
    return (fc.load_postes(), fc.load_conso_iris(), fc.load_sites_za(),
            fc.profil_zone(), fc.profil_zone(pas="15"))


postes, iris, sites, prof, prof15 = donnees()
pointe_auto = fc.fenetre_pointe(prof)

# ------------------------------------------------------------------ Réglages
with st.sidebar:
    st.header("Réglages")
    st.caption("Tout le tableau de bord se recalcule quand vous changez une valeur.")
    depassement = st.number_input("Surplus à effacer (kW)", 100, 3000, 500, 50)
    marge = st.slider("Marge de sécurité (%)", 0, 50, 10) / 100
    duree = st.slider("Durée du problème (heures)", 1, 4, 2)
    debut = st.slider("Heure de début", 0, 23, pointe_auto)
    st.divider()
    long_km = st.slider("Longueur du câble à construire (km)", 0.5, 10.0, 4.0, 0.5)
    cout_m = st.select_slider("Prix du câble (€ par mètre)", [107, 145, 202], 145)
    nb_evt = st.slider("Nombre de fois par an où le problème arrive", 1, 400, 20)

capex = fc.capex_renforcement(long_km, cout_m)
heures = [h for h in range(debut, debut + duree) if h < 24]
p, besoin = fc.scenario_congestion(prof, debut, len(heures), depassement, marge)
fen = f"{heures[0]}h-{heures[-1] + 1}h"

if "offres" not in st.session_state:
    st.session_state.offres = fc.generer_offres(postes=postes)

st.title("Plateforme de flexibilité – zone industrielle Sanital, Châtellerault")
st.markdown(
    f"**Le problème :** le réseau électrique de la zone va être saturé de **{depassement} kW** entre **{fen}**. "
    f"Plutôt que de construire un nouveau câble, on demande à des entreprises de la zone de consommer moins à ce moment-là, "
    f"contre rémunération. Il faut trouver **{besoin:.0f} kW** ({depassement} kW + {pc(marge)} de marge), au prix le plus bas.")

T = st.tabs(["1 · La zone", "2 · Le problème", "3 · Les offres", "4 · Le choix des offres",
             "5 · Et si une entreprise ne répond pas ?", "6 · Flexibilité ou nouveau câble ?", "7 · Conclusion"])

# ------------------------------------------------------------------ 1. La zone
with T[0]:
    intro("On a choisi la zone industrielle Sanital parce que c'est là que Châtellerault consomme le plus d'électricité.")
    s25 = iris["conso_MWh"].sum()
    za = iris[iris.code_iris == fc.IRIS_ZA]["conso_MWh"].sum()
    c = st.columns(3)
    chiffre(c[0], "Consommation de Châtellerault (2025)", f"{fr(s25 / 1000, 1)} GWh", "source : Enedis")
    chiffre(c[1], "dont la zone Sanital", f"{fr(za / 1000, 1)} GWh", f"{pc(za / s25)} de la ville, sur un seul quartier")
    chiffre(c[2], "Entreprises dans la zone", f"{fr(sites.nb_sites.sum())}", "sites de plus de 36 kVA")
    st.write("")
    a, b = st.columns([1, 1])
    with a:
        z = iris.pivot_table(index="nom_iris", columns="secteur", values="conso_MWh", aggfunc="sum").fillna(0) / 1000
        z = z.loc[z.sum(axis=1).sort_values().index].reset_index()
        z = z.melt(id_vars="nom_iris", value_vars=["INDUSTRIE", "TERTIAIRE", "RESIDENTIEL"], var_name="Type", value_name="GWh")
        z["Type"] = z.Type.map({"INDUSTRIE": "Industrie", "TERTIAIRE": "Commerces et bureaux", "RESIDENTIEL": "Logements"})
        fig = px.bar(z, y="nom_iris", x="GWh", color="Type", orientation="h",
                     color_discrete_map={"Industrie": "#2a78d6", "Commerces et bureaux": "#eb6834", "Logements": "#6250d6"})
        fig.update_yaxes(title=None); fig.update_xaxes(title="GWh consommés en 2025")
        st.plotly_chart(style(fig, "Consommation par quartier : Sanital loin devant", 480),
                        use_container_width=True)
    with b:
        pz = postes.assign(Zone=postes.zone_indus.map({True: "Zone Sanital", False: "Reste de la ville"}))
        fig = px.scatter_map(pz, lat="lat", lon="lon", color="Zone", hover_name="nom_iris", zoom=11.3,
                             center=dict(lat=46.82, lon=0.55),
                             color_discrete_map={"Zone Sanital": ROUGE, "Reste de la ville": "#9bb7d4"})
        fig.update_layout(map_style="open-street-map", height=480, margin=dict(l=0, r=0, t=60, b=0),
                          title=dict(text="Les 935 postes électriques de la ville (zone Sanital en rouge)", font=dict(size=17)),
                          legend=dict(y=.02, x=.01, title=None))
        st.plotly_chart(fig, use_container_width=True)
    with st.expander("Voir la liste des entreprises de la zone"):
        s = sites.assign(Activité=sites.naf2.map(fc.NAF).fillna(sites.naf2)).sort_values("conso_MWh", ascending=False)
        s = s.rename(columns={"adresse": "Adresse", "conso_MWh": "Consommation 2025 (MWh)"})
        st.dataframe(s[["Adresse", "Activité", "Consommation 2025 (MWh)"]], hide_index=True, use_container_width=True)
        st.caption("Source : Enedis Open Data, consommation annuelle des entreprises par adresse.")

# ------------------------------------------------------------------ 2. Le problème
with T[1]:
    intro(f"Voici la consommation de la zone sur une journée d'hiver. Elle est la plus forte le matin. "
          f"C'est là qu'on simule le problème : {depassement} kW de trop pendant {len(heures)} h.")
    cap = p.capacite_kW.iloc[0] / 1000
    c = st.columns(3)
    chiffre(c[0], "Pic de consommation", f"{fr(prof.charge_kW.max() / 1000, 1)} MW", f"vers {pointe_auto}h")
    chiffre(c[1], "Limite du réseau (hypothèse)", f"{fr(cap, 1)} MW", "le réseau est déjà au maximum")
    chiffre(c[2], "À effacer", f"{besoin:.0f} kW", f"de {fen}")
    st.write("")
    fig = go.Figure()
    for col, lab, cc in [("hta_kW", "Usines et gros sites", "#2a78d6"), ("pro_kW", "Petits commerces et artisans", "#eb6834"),
                         ("residentiel_kW", "Logements", "#6250d6")]:
        fig.add_scatter(x=prof15.h, y=prof15[col] / 1000, stackgroup="a", name=lab, line=dict(width=0.5, color=cc),
                        hovertemplate="%{y:.1f} MW<extra>" + lab + "</extra>")
    fig.add_bar(x=[h + .5 for h in heures], y=[depassement / 1000] * len(heures), base=cap,
                name=f"Surplus de {depassement} kW (le problème)", marker_color=ROUGE, width=.9)
    fig.add_hline(y=cap, line_dash="dash", line_color="black", annotation_text="Limite du réseau",
                  annotation_position="top left")
    fig.update_xaxes(title="Heure de la journée", dtick=3, range=[0, 24])
    fig.update_yaxes(title="Puissance consommée (MW)")
    st.plotly_chart(style(fig, f"Consommation de la zone sur une journée d'hiver : le surplus (en rouge) dépasse la limite à {fen}", 460),
                    use_container_width=True)
    with st.expander("D'où vient cette courbe ?"):
        st.write("Enedis publie la consommation annuelle de la zone (80 GWh en 2025), mais pas sa courbe heure par heure. "
                 "On a donc réparti ces 80 GWh sur la journée en suivant la forme de consommation moyenne des usines, "
                 "des commerces et des logements en France, mesurée par Enedis le 20 janvier 2026. "
                 "La quantité est celle de la zone ; la forme de la journée est la moyenne nationale.")

# ------------------------------------------------------------------ 3. Les offres
with T[2]:
    intro("18 entreprises proposent de baisser leur consommation. Chacune dit combien de kW, à quel prix et à quelles heures. "
          "12 sont de vraies entreprises de la zone, 6 sont fictives (recharge de véhicules et batteries). "
          "Vous pouvez modifier les valeurs du tableau.")
    cols = ["id", "acteur", "categorie", "puissance_kW", "prix_EUR_MWh", "duree_max_h", "dispo_debut", "dispo_fin"]
    ed = st.data_editor(
        st.session_state.offres[cols], hide_index=True, use_container_width=True, key="ed", disabled=["id", "categorie"],
        column_config={"id": "N°", "acteur": "Entreprise", "categorie": "Type", "puissance_kW": "Peut baisser de (kW)",
                       "prix_EUR_MWh": "Prix demandé (€/MWh)", "duree_max_h": "Pendant max (h)",
                       "dispo_debut": "Disponible de (h)", "dispo_fin": "jusqu'à (h)",
                       "fiabilite": st.column_config.NumberColumn("Fiabilité", format="%.2f", min_value=0., max_value=1.,
                                                                  help="Probabilité que l'entreprise réponde vraiment")})
    offres = st.session_state.offres.copy()
    for col in cols:
        offres[col] = ed[col].values
    dispo = offres[[all(fc._dispo(o, h) for h in heures) for _, o in offres.iterrows()]]
    c = st.columns(3)
    chiffre(c[0], "Total proposé", f"{fr(offres.puissance_kW.sum())} kW", "les 18 offres")
    chiffre(c[1], f"Disponible à {fen}", f"{fr(dispo.puissance_kW.sum())} kW", f"{len(dispo)} offres")
    chiffre(c[2], "Besoin", f"{besoin:.0f} kW", "il y a largement assez" if dispo.puissance_kW.sum() > besoin else "pas assez !")
    st.write("")
    g = offres.copy()
    g["fin"] = g.apply(lambda r: r.dispo_fin if r.dispo_fin > r.dispo_debut else r.dispo_fin + 24, axis=1)
    g["label"] = g.id + "  " + g.acteur.str.split(" – ").str[0]
    fig = go.Figure()
    for cat in COUL:
        sub = g[g.categorie == cat]
        fig.add_bar(y=sub.label, x=sub.fin - sub.dispo_debut, base=sub.dispo_debut, orientation="h",
                    marker_color=COUL[cat], name=NOM_CAT[cat], hovertext=sub.acteur)
    fig.add_vrect(x0=heures[0], x1=heures[-1] + 1, fillcolor=ROUGE, opacity=.15, line_width=0,
                  annotation_text="le problème", annotation_position="top")
    fig.update_xaxes(title="Heure (au-delà de 24 = lendemain matin)", range=[0, 31], dtick=3)
    fig.update_yaxes(autorange="reversed", title=None)
    st.plotly_chart(style(fig, "Qui est disponible au moment du problème ? (barres qui touchent la zone rouge)", 560),
                    use_container_width=True)

# ------------------------------------------------------------------ 4. Le choix
r_mo = fc.selection_preseance(offres, heures, besoin, depassement)
r_or = fc.selection_ortools(offres, heures, besoin, depassement)
k_mo, k_or = fc.indicateurs(r_mo, offres), fc.indicateurs(r_or, offres)
mc_or = fc.monte_carlo(r_or, offres, 5000)

with T[3]:
    intro(f"Parmi les offres disponibles, le programme choisit la combinaison <b>la moins chère</b> qui efface "
          f"au moins {besoin:.0f} kW à chaque heure du problème, en respectant les horaires de chaque entreprise.")
    if k_or["statut"] == "INFAISABLE":
        st.error("Pas assez d'offres disponibles pour couvrir le besoin.")
    c = st.columns(4)
    chiffre(c[0], "Puissance obtenue", f"{k_or['P_min_mobilisee_kW']:.0f} kW", f"objectif : {besoin:.0f} kW")
    chiffre(c[1], "Coût total", f"{fr(k_or['cout_total_EUR'])} €", "payé aux entreprises")
    chiffre(c[2], "Prix moyen", f"{fr(k_or['cout_moyen_EUR_MWh'])} €/MWh", "par MWh effacé")
    chiffre(c[3], "Marge", f"{k_or['marge_vs_depassement_kW']:+.0f} kW", f"au-dessus des {depassement} kW")
    st.write("")
    rows = []
    det = fc.detail_activation(r_or, offres)
    for h in r_or.heures:
        for _, r in det[det[f"{h}h-{h + 1}h"] > 0].iterrows():
            rows.append(dict(Heure=f"{h}h-{h + 1}h", kW=r[f"{h}h-{h + 1}h"], Type=NOM_CAT[r.categorie],
                             Offre=r.id, Entreprise=r.acteur))
    if rows:
        fig = px.bar(pd.DataFrame(rows), x="Heure", y="kW", color="Type", text="Offre", hover_name="Entreprise",
                     color_discrete_map={NOM_CAT[k]: v for k, v in COUL.items()})
        fig.add_hline(y=besoin, line_dash="dot", line_color=VERT, annotation_text=f"objectif {besoin:.0f} kW")
        fig.update_traces(textposition="inside", insidetextanchor="middle", width=.5)
        fig.update_xaxes(title=None); fig.update_yaxes(title="kW effacés")
        a, _ = st.columns([3, 2])
        a.plotly_chart(style(fig, "Qui est activé, heure par heure (un bloc = une entreprise)", 460),
                       use_container_width=True)
        if True:
            st.markdown("**Liste des offres : choisies ou non, et pourquoi**")
            det["Choisie"] = det.retenue.map({True: "Oui", False: "Non"})
            det["Pourquoi"] = [("Pas chère, disponible" if r.retenue else fc.raison_non_retenue(r.id, r_or, offres))
                               for _, r in det.iterrows()]
            det = det.rename(columns={"id": "N°", "acteur": "Entreprise", "puissance_kW": "kW",
                                      "prix_EUR_MWh": "Prix (€/MWh)", "cout_EUR": "Payé (€)"})
            st.dataframe(det[["N°", "Entreprise", "kW", "Prix (€/MWh)", "Choisie", "Payé (€)", "Pourquoi"]],
                         hide_index=True, use_container_width=True)
    if r_mo.statut == "OK" and k_or["statut"] != "INFAISABLE":
        st.caption(f"Pour comparaison : en prenant simplement les offres les moins chères d'abord jusqu'à avoir assez, "
                   f"on paierait {fr(k_mo['cout_total_EUR'])} € au lieu de {fr(k_or['cout_total_EUR'])} €, "
                   f"car on prendrait trop de kW ({k_mo['P_max_mobilisee_kW']:.0f} kW à une heure).")

# ------------------------------------------------------------------ 5. Robustesse
with T[4]:
    intro("Une entreprise peut ne pas répondre le jour J (panne, commande urgente…). On suppose qu'une usine répond "
          "95 fois sur 100, un commerce 90, une borne de recharge 85, une batterie 97. "
          "On rejoue la situation des milliers de fois pour voir combien de fois le surplus est vraiment effacé.")
    c = st.columns(2)
    chiffre(c[0], "Chances que le surplus soit vraiment effacé", pc(mc_or["proba_couverture"]), f"avec {pc(marge)} de marge")
    st.write("")
    st.write("La marge de sécurité augmente les chances de réussite. Cliquez pour voir combien elle coûte "
             "(calcul d'environ 10 secondes).")
    if st.button("Comparer plusieurs marges"):
        sens = fc.sensibilite_marge(offres, heures, depassement, n=3000)
        t = pd.DataFrame({"Marge": [f"{m:.0f} %" for m in sens.marge_pct],
                          "Chances de réussir": [pc(x) for x in sens.proba_couverture],
                          "Coût par problème": [f"{fr(x)} €" for x in sens.cout_EUR]})
        a, _ = st.columns([2, 3])
        a.dataframe(t, hide_index=True, use_container_width=True)
        st.markdown("**À retenir :** passer de 10 % à 30 % de marge fait passer les chances de réussite d'environ 7 sur 10 "
                    "à 9 sur 10, pour quelques dizaines d'euros de plus.")

# ------------------------------------------------------------------ 6. Flex vs câble
best = k_or if k_or["statut"] != "INFAISABLE" else k_mo
cmp = fc.comparaison_renforcement(best["cout_total_EUR"], nb_evt, capex, TAUX, VIE, FIXES)
with T[5]:
    intro("L'autre solution est de construire un nouveau câble pour augmenter la limite du réseau. "
          "On compare ce que coûte chaque solution par an.")
    c = st.columns(3)
    chiffre(c[0], "Nouveau câble", f"{fr(cmp['renfo_EUR_an'])} €/an",
            f"{fr(capex / 1000)} k€ à construire, remboursés sur {VIE} ans")
    chiffre(c[1], "Flexibilité", f"{fr(cmp['flex_EUR_an'])} €/an",
            f"{nb_evt} problèmes × {fr(best['cout_total_EUR'])} € + {fr(FIXES)} € de frais")
    gagnant = "la flexibilité" if cmp["flex_moins_cher"] else "le câble"
    chiffre(c[2], "Le moins cher aujourd'hui", gagnant.capitalize(),
            f"la flexibilité gagne tant qu'il y a moins de {fr(cmp['nb_evenements_seuil'])} problèmes par an")
    st.write("")
    n = list(range(0, 1001, 10))
    df = pd.DataFrame({"n": n, "Flexibilité": [best["cout_total_EUR"] * x + FIXES for x in n],
                       "Nouveau câble": [cmp["renfo_EUR_an"]] * len(n)})
    fig = px.line(df, x="n", y=["Flexibilité", "Nouveau câble"],
                  color_discrete_map={"Flexibilité": VERT, "Nouveau câble": "#eda100"})
    fig.update_traces(line_width=3)
    fig.add_vline(x=nb_evt, line_dash="dot", line_color=GRIS, annotation_text="aujourd'hui")
    fig.add_vline(x=cmp["nb_evenements_seuil"], line_dash="dash", line_color=GRIS,
                  annotation_text=f"seuil : {fr(cmp['nb_evenements_seuil'])}/an", annotation_position="bottom right")
    fig.update_xaxes(title="Nombre de problèmes par an")
    fig.update_yaxes(title="Coût par an (€)")
    st.plotly_chart(style(fig, "Plus le problème est fréquent, plus la flexibilité coûte cher. "
                               "Tant que la ligne verte est sous la jaune, la flexibilité gagne.", 420),
                    use_container_width=True)
    st.caption("Prix du câble : barème officiel Enedis 2026 (107 à 202 € par mètre), plus 80 k€ d'équipement et 15 % d'imprévus. "
               "Ce sont des ordres de grandeur.")

# ------------------------------------------------------------------ 7. Conclusion
with T[6]:
    cats = offres.set_index("id").loc[best["retenues"], "categorie"].map(NOM_CAT).value_counts()
    verdict = (f"La flexibilité est moins chère que le nouveau câble tant que le problème arrive moins de "
               f"{fr(cmp['nb_evenements_seuil'])} fois par an." if cmp["flex_moins_cher"]
               else "Avec un problème aussi fréquent, le nouveau câble devient moins cher.")
    st.subheader("Ce qu'on recommande à l'agrégateur")
    st.markdown(f"""
1. **Ça marche :** {best['nb_retenues']} offres de la zone ({", ".join(f"{v} {c.lower()}" for c, v in cats.items())})
suffisent à effacer le surplus, pour {fr(best['cout_total_EUR'])} € à chaque fois.
2. **Recruter d'abord les grosses usines :** 10 entreprises font 70 % de la consommation de la zone, et ce sont les moins chères.
3. **Regrouper les entreprises :** Enedis n'accepte que des offres d'au moins 500 kW. Aucune entreprise seule n'y arrive.
4. **Choisir les offres par optimisation** plutôt qu'en prenant simplement les moins chères d'abord : on évite de payer des kW en trop.
5. **Prendre 20 à 30 % de marge** : avec {pc(marge)}, le surplus n'est vraiment effacé que {pc(mc_or['proba_couverture'])} du temps.
6. **{verdict}**

**Attention :** aujourd'hui, peu d'entreprises répondent aux appels d'offres d'Enedis, et la zone dépend de quelques grosses usines.
""")
