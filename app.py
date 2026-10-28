"""
Plateforme de flexibilité locale – zone industrielle Sanital, Châtellerault
Lancer :  streamlit run app.py
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import flex_core as fc

st.set_page_config(page_title="Flexibilité Châtellerault", layout="wide")

# Couleurs lisibles par les personnes daltoniennes (palette Okabe-Ito)
BLEU, ORANGE, VERT, JAUNE, VIOLET, GRIS = "#0072B2", "#E69F00", "#009E73", "#F0E442", "#CC79A7", "#555555"
VERMILLON = "#D55E00"
COUL = {"Industrie": BLEU, "Tertiaire": ORANGE, "VE": VERT, "Batterie": VIOLET}
NOM_CAT = {"Industrie": "Usine", "Tertiaire": "Commerce ou bureau", "VE": "Recharge de véhicules", "Batterie": "Batterie"}
TAUX, VIE, FIXES = 0.05, 40, 5000  # hypothèses fixes, détaillées dans le rapport

SRC_IRIS = "Enedis Open Data, « Consommation électrique par secteur d'activité à la maille IRIS », année 2025"
SRC_ADR = "Enedis Open Data, « Consommation annuelle d'électricité des entreprises par adresse », année 2025"
SRC_POSTES = "Enedis Open Data, « Postes électriques HTA/BT »"
SRC_COURBE = "Enedis Open Data, « Puissances électriques au pas 15 minutes », journée du 20 janvier 2026"
SRC_AO = "Enedis, appel d'offres « Flexibilités locales » du 1er semestre 2026"
SRC_CRE = "Barème de raccordement Enedis approuvé par la CRE (délibération n° 2026-160)"


def pc(x):
    return f"{x * 100:.0f} %"


def fr(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def intro(texte):
    st.markdown(f"<p style='font-size:1.1rem;color:#222;margin-bottom:1rem'>{texte}</p>", unsafe_allow_html=True)


def source(texte):
    st.caption(f"Source : {texte}")


def chiffre(col, titre, valeur, detail=""):
    col.markdown(
        f"<div style='background:#f2f2f2;border-radius:10px;padding:14px 16px;height:100%'>"
        f"<div style='font-size:.9rem;color:#444'>{titre}</div>"
        f"<div style='font-size:1.9rem;font-weight:600;color:#111;line-height:1.2'>{valeur}</div>"
        f"<div style='font-size:.85rem;color:#555'>{detail}</div></div>", unsafe_allow_html=True)


def style(fig, titre, h=420):
    fig.update_layout(title=dict(text=titre, font=dict(size=17)), height=h, plot_bgcolor="white",
                      margin=dict(l=10, r=10, t=60, b=10), legend_title=None,
                      legend=dict(orientation="h", y=-0.25))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e6e6e6")
    return fig


@st.cache_data
def donnees():
    return fc.load_postes(), fc.load_conso_iris(), fc.load_sites_za(), fc.profil_zone(), fc.profil_zone(pas="15")


postes, iris, sites, prof, prof15 = donnees()
pointe_auto = fc.fenetre_pointe(prof)

# ------------------------------------------------------------------ Réglages
with st.sidebar:
    st.header("Réglages")
    st.caption("Toutes les pages se mettent à jour quand une valeur change.")
    depassement = st.number_input("Puissance en trop à supprimer (kW)", 100, 3000, 500, 50)
    marge = st.slider("Marge de sécurité (%)", 0, 50, 10)  / 100
    duree = st.slider("Durée de la saturation (heures)", 1, 4, 2)
    debut = st.slider("Heure de début de la saturation", 0, 23, pointe_auto)
    st.divider()
    long_km = st.slider("Longueur du câble à construire (km)", 0.5, 10.0, 4.0, 0.5)
    cout_m = st.select_slider("Prix du câble (€ par mètre)", [107, 145, 202], 145)
    nb_evt = st.slider("Nombre de saturations par an", 1, 400, 20)

capex = fc.capex_renforcement(long_km, cout_m)
heures = [h for h in range(debut, debut + duree) if h < 24]
p, besoin = fc.scenario_congestion(prof, debut, len(heures), depassement, marge)
fen = f"{heures[0]}h-{heures[-1] + 1}h"

if "offres" not in st.session_state:
    st.session_state.offres = fc.generer_offres(postes=postes)

st.title("Plateforme de flexibilité – zone industrielle Sanital, Châtellerault")
st.markdown(
    f"**Situation étudiée.** Entre **{fen}**, le réseau électrique de la zone doit supporter **{depassement} kW de plus** "
    f"que ce qu'il peut transporter : on parle de **saturation**. Deux solutions existent : construire un nouveau câble, "
    f"ou payer des entreprises de la zone pour qu'elles consomment moins pendant ces heures-là. "
    f"Cette plateforme étudie la deuxième solution. Avec la marge de sécurité de {pc(marge)}, il faut trouver "
    f"**{besoin:.0f} kW** de baisse de consommation, au coût le plus bas.")

T = st.tabs(["1 · La zone", "2 · La saturation", "3 · Les offres", "4 · Le choix des offres",
             "5 · Flexibilité ou nouveau câble ?", "6 · Conclusion"])

# ------------------------------------------------------------------ 1. La zone
with T[0]:
    intro("La zone industrielle Sanital est le quartier de Châtellerault qui consomme le plus d'électricité. "
          "C'est pour cette raison qu'elle a été choisie.")
    serie = fc.load_serie_commune()
    total = serie[serie.annee == 2025]["conso_MWh"].sum()
    za = iris[iris.code_iris == fc.IRIS_ZA]["conso_MWh"].sum()
    c = st.columns(3)
    chiffre(c[0], "Consommation de Châtellerault en 2025", f"{fr(total / 1000, 1)} GWh", "tous quartiers confondus")
    chiffre(c[1], "Consommation de la zone Sanital", f"{fr(za / 1000, 1)} GWh", f"soit {pc(za / total)} de la ville")
    chiffre(c[2], "Entreprises dans la zone", f"{fr(sites.nb_sites.sum())}", "sites de plus de 36 kVA")
    source(SRC_IRIS + " ; " + SRC_ADR)
    st.write("")
    a, b = st.columns(2)
    with a:
        z = iris.pivot_table(index="nom_iris", columns="secteur", values="conso_MWh", aggfunc="sum").fillna(0) / 1000
        z = z.loc[z.sum(axis=1).sort_values().index].reset_index()
        z = z.melt(id_vars="nom_iris", value_vars=["INDUSTRIE", "TERTIAIRE", "RESIDENTIEL"], var_name="Type", value_name="GWh")
        z["Type"] = z.Type.map({"INDUSTRIE": "Industrie", "TERTIAIRE": "Commerces et bureaux", "RESIDENTIEL": "Logements"})
        fig = px.bar(z, y="nom_iris", x="GWh", color="Type", orientation="h",
                     color_discrete_map={"Industrie": BLEU, "Commerces et bureaux": ORANGE, "Logements": VIOLET})
        fig.update_yaxes(title=None)
        fig.update_xaxes(title="Consommation en 2025 (GWh)")
        st.plotly_chart(style(fig, "Consommation par quartier", 500), use_container_width=True)
        source(SRC_IRIS)
    with b:
        pz = postes.assign(Zone=postes.zone_indus.map({True: "Zone Sanital", False: "Reste de la ville"}))
        fig = px.scatter_map(pz, lat="lat", lon="lon", color="Zone", hover_name="nom_iris", zoom=11.3,
                             center=dict(lat=46.82, lon=0.55), hover_data={"lat": False, "lon": False, "Zone": False},
                             color_discrete_map={"Zone Sanital": "#e34948", "Reste de la ville": "#1f4fd1"})
        fig.update_traces(marker=dict(size=7))
        fig.update_layout(map_style="open-street-map", height=500, margin=dict(l=0, r=0, t=60, b=0),
                          title=dict(text="Postes électriques de la ville", font=dict(size=17)),
                          legend=dict(y=.02, x=.01, title=None, bgcolor="rgba(255,255,255,.85)"))
        st.plotly_chart(fig, use_container_width=True)
        source(SRC_POSTES)
    with st.expander("Voir la liste des entreprises de la zone"):
        s = sites.assign(Activité=sites.naf2.map(fc.NAF).fillna(sites.naf2)).sort_values("conso_MWh", ascending=False)
        s = s.rename(columns={"adresse": "Adresse", "conso_MWh": "Consommation 2025 (MWh)"})
        st.dataframe(s[["Adresse", "Activité", "Consommation 2025 (MWh)"]], hide_index=True, use_container_width=True)
        source(SRC_ADR)

# ------------------------------------------------------------------ 2. La saturation
with T[1]:
    intro(f"Le graphique montre la consommation de la zone heure par heure, un jour d'hiver. "
          f"Elle est la plus forte le matin, entre 9h et 11h. La saturation de {depassement} kW est placée à ce moment-là.")
    cap = p.capacite_kW.iloc[0] / 1000
    c = st.columns(3)
    chiffre(c[0], "Consommation la plus forte", f"{fr(prof.charge_kW.max() / 1000, 1)} MW", f"vers {pointe_auto}h")
    chiffre(c[1], "Limite du réseau", f"{fr(cap, 1)} MW", "hypothèse : égale à la consommation la plus forte")
    chiffre(c[2], "Baisse à trouver", f"{besoin:.0f} kW", f"de {fen}")
    st.write("")
    fig = go.Figure()
    for col, lab, cc in [("hta_kW", "Usines et grands sites", BLEU), ("pro_kW", "Petits commerces et artisans", ORANGE),
                         ("residentiel_kW", "Logements", VIOLET)]:
        fig.add_scatter(x=prof15.h, y=prof15[col] / 1000, stackgroup="a", name=lab, line=dict(width=0.5, color=cc),
                        hovertemplate="%{y:.1f} MW<extra>" + lab + "</extra>")
    fig.add_bar(x=[h + .5 for h in heures], y=[depassement / 1000] * len(heures), base=cap,
                name=f"Puissance en trop ({depassement} kW)", marker_color=VERMILLON, width=.9)
    fig.add_hline(y=cap, line_dash="dash", line_color="black", annotation_text="Limite du réseau",
                  annotation_position="top left")
    fig.update_xaxes(title="Heure de la journée", dtick=3, range=[0, 24])
    fig.update_yaxes(title="Puissance consommée (MW)")
    st.plotly_chart(style(fig, "Consommation de la zone sur une journée d'hiver", 470), use_container_width=True)
    source(f"{SRC_IRIS} ; {SRC_COURBE} ; calcul du groupe")
    with st.expander("Comment cette courbe a été obtenue"):
        st.write("Enedis publie la quantité d'électricité consommée par la zone sur l'année (environ 80 GWh en 2025), "
                 "mais pas la consommation heure par heure. Cette quantité a donc été répartie sur la journée en suivant "
                 "la consommation moyenne, quart d'heure par quart d'heure, des usines, des commerces et des logements "
                 "en France le 20 janvier 2026, publiée par Enedis. La quantité totale est donc réelle ; "
                 "la répartition dans la journée est une estimation.")
        st.write("La limite du réseau n'est pas publique. On suppose qu'elle est égale à la consommation la plus forte "
                 f"d'aujourd'hui, et que {depassement} kW de consommation supplémentaire arrivent (agrandissement d'une usine, "
                 "nouvelle entreprise, etc.).")

# ------------------------------------------------------------------ 3. Les offres
with T[2]:
    intro("Une offre est la proposition d'une entreprise : « je peux baisser ma consommation de tant de kW, "
          "à tel prix, à telles heures ». La plateforme dispose de 18 offres.")
    cols = ["id", "acteur", "categorie", "puissance_kW", "prix_EUR_MWh", "duree_max_h", "dispo_debut", "dispo_fin"]
    ed = st.data_editor(
        st.session_state.offres[cols], hide_index=True, use_container_width=True, key="ed", disabled=["id", "categorie"],
        column_config={"id": "N°", "acteur": "Entreprise", "categorie": "Type", "puissance_kW": "Baisse possible (kW)",
                       "prix_EUR_MWh": "Prix demandé (€/MWh)", "duree_max_h": "Durée maximale (h)",
                       "dispo_debut": "Disponible à partir de (h)", "dispo_fin": "jusqu'à (h)"})
    offres = st.session_state.offres.copy()
    for col in cols:
        offres[col] = ed[col].values
    with st.expander("D'où viennent ces offres"):
        st.markdown(f"""
- **Entreprises (offres O01 à O12)** : ce sont de vraies entreprises de la zone, avec leur adresse et leur consommation
  réelle ({SRC_ADR}).
- **Baisse possible** : estimée à partir de la consommation réelle de chaque entreprise (une part de sa puissance moyenne),
  puis ramenée dans les fourchettes du sujet : usines 100 à 300 kW, commerces et bureaux 20 à 100 kW,
  recharge de véhicules 20 à 150 kW, batteries 50 à 200 kW.
- **Prix** : tirés au hasard dans les fourchettes du sujet (50 à 300 €/MWh). Les prix réels ne sont pas publics.
- **Horaires** : hypothèses selon l'activité. Usines 6h-22h (deux équipes), commerces et bureaux 8h-19h,
  bornes des salariés 8h-18h, flotte de camionnettes 18h-7h (la nuit, au dépôt), batteries 24h/24.
- **Offres O13 à O18** (recharge de véhicules et batteries) : fictives, aucune donnée publique n'existe pour la zone.
""")
    dispo = offres[[all(fc._dispo(o, h) for h in heures) for _, o in offres.iterrows()]]
    c = st.columns(3)
    chiffre(c[0], "Baisse proposée au total", f"{fr(offres.puissance_kW.sum())} kW", "par les 18 offres")
    chiffre(c[1], f"Baisse disponible de {fen}", f"{fr(dispo.puissance_kW.sum())} kW", f"{len(dispo)} offres disponibles")
    chiffre(c[2], "Baisse à trouver", f"{besoin:.0f} kW",
            "les offres suffisent" if dispo.puissance_kW.sum() >= besoin else "les offres ne suffisent pas")
    st.write("")
    g = offres.copy()
    g["fin"] = g.apply(lambda r: r.dispo_fin if r.dispo_fin > r.dispo_debut else r.dispo_fin + 24, axis=1)
    g["label"] = g.id + "  " + g.acteur.str.split(" – ").str[0]
    fig = go.Figure()
    for cat in COUL:
        sub = g[g.categorie == cat]
        fig.add_bar(y=sub.label, x=sub.fin - sub.dispo_debut, base=sub.dispo_debut, orientation="h",
                    marker_color=COUL[cat], name=NOM_CAT[cat], hovertext=sub.acteur)
    fig.add_vrect(x0=heures[0], x1=heures[-1] + 1, fillcolor="black", opacity=.12, line_width=0,
                  annotation_text="saturation", annotation_position="top")
    fig.update_xaxes(title="Heure (au-delà de 24 : lendemain matin)", range=[0, 31], dtick=3)
    fig.update_yaxes(autorange="reversed", title=None)
    st.plotly_chart(style(fig, "Heures de disponibilité de chaque offre (zone grise : saturation)", 560),
                    use_container_width=True)
    source("hypothèses du groupe (voir « D'où viennent ces offres »)")

# ------------------------------------------------------------------ 4. Le choix
r_mo = fc.selection_preseance(offres, heures, besoin, depassement)
r_or = fc.selection_ortools(offres, heures, besoin, depassement)
k_mo, k_or = fc.indicateurs(r_mo, offres), fc.indicateurs(r_or, offres)

with T[3]:
    intro(f"Il faut choisir, parmi les 18 offres, lesquelles activer pour obtenir au moins {besoin:.0f} kW "
          f"de baisse à chaque heure de la saturation, en payant le moins possible.")
    st.markdown("#### Méthode utilisée : l'optimisation avec OR-Tools")
    st.markdown(f"""
Le choix est fait par un petit programme Python qui utilise **OR-Tools**, un outil gratuit de Google spécialisé
dans ce type de problème. Le programme reçoit les 18 offres et applique les règles suivantes :

1. à chaque heure de la saturation ({fen}), le total des baisses doit atteindre au moins **{besoin:.0f} kW** ;
2. une offre ne peut être activée que pendant ses heures de disponibilité ;
3. une offre ne peut pas être activée plus longtemps que sa durée maximale ;
4. une offre est prise en entier ou pas du tout.

Parmi toutes les combinaisons d'offres qui respectent ces règles, OR-Tools retient **celle qui coûte le moins cher**.
Le coût d'une offre se calcule ainsi : prix (€/MWh) × baisse (MW) × nombre d'heures.
""")
    if k_or["statut"] == "INFAISABLE":
        st.error("Les offres disponibles ne suffisent pas à couvrir le besoin.")
    st.markdown("#### Résultat")
    c = st.columns(4)
    chiffre(c[0], "Baisse obtenue", f"{k_or['P_min_mobilisee_kW']:.0f} kW", f"objectif : {besoin:.0f} kW")
    chiffre(c[1], "Coût total", f"{fr(k_or['cout_total_EUR'])} €", "payé aux entreprises par saturation")
    chiffre(c[2], "Prix moyen", f"{fr(k_or['cout_moyen_EUR_MWh'])} €/MWh", "par MWh non consommé")
    chiffre(c[3], "Marge disponible", f"{k_or['marge_vs_depassement_kW']:+.0f} kW",
            f"au-delà des {depassement} kW en trop")
    st.write("")
    det = fc.detail_activation(r_or, offres)
    rows = []
    for h in r_or.heures:
        for _, r in det[det[f"{h}h-{h + 1}h"] > 0].iterrows():
            rows.append(dict(Heure=f"{h}h-{h + 1}h", kW=r[f"{h}h-{h + 1}h"], Type=NOM_CAT[r.categorie],
                             Offre=r.id, Entreprise=r.acteur))
    if rows:
        fig = px.bar(pd.DataFrame(rows), x="Heure", y="kW", color="Type", text="Offre", hover_name="Entreprise",
                     color_discrete_map={NOM_CAT[k]: v for k, v in COUL.items()})
        fig.add_hline(y=besoin, line_dash="dot", line_color="black", annotation_text=f"objectif {besoin:.0f} kW")
        fig.update_traces(textposition="inside", insidetextanchor="middle", width=.5)
        fig.update_xaxes(title=None)
        fig.update_yaxes(title="Baisse de consommation (kW)")
        a, _ = st.columns([3, 2])
        a.plotly_chart(style(fig, "Offres activées à chaque heure (un bloc = une entreprise)", 460),
                       use_container_width=True)
    st.markdown("**Offres retenues et offres non retenues**")
    det["Retenue"] = det.retenue.map({True: "Oui", False: "Non"})
    det["Raison"] = [("Disponible et parmi les moins chères" if r.retenue else fc.raison_non_retenue(r.id, r_or, offres))
                     for _, r in det.iterrows()]
    det["Raison"] = det["Raison"].replace({"Trop chère / non nécessaire": "Plus chère, ou inutile une fois le besoin atteint",
                                           "Indisponible sur la fenêtre": "Pas disponible pendant la saturation"})
    det = det.rename(columns={"id": "N°", "acteur": "Entreprise", "puissance_kW": "Baisse (kW)",
                              "prix_EUR_MWh": "Prix (€/MWh)", "cout_EUR": "Montant payé (€)"})
    st.dataframe(det[["N°", "Entreprise", "Baisse (kW)", "Prix (€/MWh)", "Retenue", "Montant payé (€)", "Raison"]],
                 hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ 5. Flex vs câble
best = k_or if k_or["statut"] != "INFAISABLE" else k_mo
cmp = fc.comparaison_renforcement(best["cout_total_EUR"], nb_evt, capex, TAUX, VIE, FIXES)
with T[4]:
    intro("L'autre solution consiste à construire un nouveau câble pour augmenter la limite du réseau. "
          "Les deux solutions sont comparées sur leur coût par an.")
    c = st.columns(3)
    chiffre(c[0], "Nouveau câble", f"{fr(cmp['renfo_EUR_an'])} €/an",
            f"{fr(capex / 1000)} k€ de travaux, répartis sur {VIE} ans")
    chiffre(c[1], "Flexibilité", f"{fr(cmp['flex_EUR_an'])} €/an",
            f"{nb_evt} saturations × {fr(best['cout_total_EUR'])} € + {fr(FIXES)} € de frais fixes")
    chiffre(c[2], "Solution la moins chère", "Flexibilité" if cmp["flex_moins_cher"] else "Nouveau câble",
            f"la flexibilité reste moins chère en dessous de {fr(cmp['nb_evenements_seuil'])} saturations par an")
    st.write("")
    n = list(range(0, 1001, 10))
    df = pd.DataFrame({"n": n, "Flexibilité": [best["cout_total_EUR"] * x + FIXES for x in n],
                       "Nouveau câble": [cmp["renfo_EUR_an"]] * len(n)})
    fig = px.line(df, x="n", y=["Flexibilité", "Nouveau câble"],
                  color_discrete_map={"Flexibilité": BLEU, "Nouveau câble": VERMILLON})
    fig.update_traces(line_width=3)
    fig.data[1].line.dash = "dash"
    fig.add_vline(x=nb_evt, line_dash="dot", line_color=GRIS, annotation_text="situation étudiée")
    fig.add_vline(x=cmp["nb_evenements_seuil"], line_dash="dot", line_color=GRIS,
                  annotation_text=f"seuil : {fr(cmp['nb_evenements_seuil'])} par an", annotation_position="bottom right")
    fig.update_xaxes(title="Nombre de saturations par an")
    fig.update_yaxes(title="Coût par an (€)")
    st.plotly_chart(style(fig, "Coût par an des deux solutions selon le nombre de saturations", 430),
                    use_container_width=True)
    st.markdown("Le coût de la flexibilité augmente avec le nombre de saturations, alors que celui du câble est fixe. "
                "Tant que la ligne bleue est sous la ligne rouge, la flexibilité est moins chère.")
    source(f"prix du câble : {SRC_CRE} (107 à 202 € par mètre de câble), plus 80 k€ d'équipement et 15 % d'imprévus "
           f"(hypothèses du groupe) ; coût réparti sur {VIE} ans avec un taux de {pc(TAUX)}. Ordres de grandeur.")

# ------------------------------------------------------------------ 6. Conclusion
with T[5]:
    PLURIEL = {"Usine": "usines", "Commerce ou bureau": "commerces ou bureaux",
               "Recharge de véhicules": "bornes de recharge", "Batterie": "batteries"}
    cats = offres.set_index("id").loc[best["retenues"], "categorie"].map(NOM_CAT).value_counts()
    mix = ", ".join(f"{v} {PLURIEL[c] if v > 1 else c.lower()}" for c, v in cats.items())
    verdict = (f"Avec {nb_evt} saturations par an, la flexibilité coûte environ {fr(cmp['flex_EUR_an'])} € par an, "
               f"contre {fr(cmp['renfo_EUR_an'])} € pour un nouveau câble. Elle reste la solution la moins chère "
               f"tant que la saturation se produit moins de {fr(cmp['nb_evenements_seuil'])} fois par an."
               if cmp["flex_moins_cher"] else
               f"Avec {nb_evt} saturations par an, le nouveau câble devient moins cher que la flexibilité.")
    st.subheader("Recommandations à l'agrégateur")
    st.caption("L'agrégateur est l'entreprise qui regroupe les offres de plusieurs sites et les propose au gestionnaire "
               "du réseau (Enedis).")
    st.markdown(f"""
1. **Le besoin peut être couvert par les entreprises de la zone.** {best['nb_retenues']} offres
({mix}) suffisent pour baisser la consommation de
{best['P_min_mobilisee_kW']:.0f} kW, pour un coût de {fr(best['cout_total_EUR'])} € par saturation.
2. **Les grosses usines sont à recruter en priorité.** Dix entreprises représentent 70 % de la consommation de la zone
et proposent les prix les plus bas.
3. **Les entreprises doivent être regroupées.** Enedis n'accepte que des offres d'au moins 500 kW ; aucune entreprise
de la zone n'atteint ce seuil seule.
4. **Le choix des offres doit être fait par optimisation (OR-Tools).** Il évite d'acheter des kW en trop :
{fr(k_mo['cout_total_EUR'] - k_or['cout_total_EUR'])} € d'économie par saturation dans le cas étudié.
5. **{verdict}**

**Limites.** Les baisses possibles, les prix et les horaires des offres sont des hypothèses, car ces informations
ne sont pas publiques. La courbe de consommation de la zone est une estimation. Enfin, peu d'entreprises répondent
aujourd'hui aux appels d'offres d'Enedis : le recrutement des sites sera la principale difficulté.
""")
    source(f"{SRC_ADR} ; {SRC_AO} ; résultats des onglets précédents")
