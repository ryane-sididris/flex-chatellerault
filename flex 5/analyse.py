"""Produit les résultats chiffrés et les figures du rapport / des diapos (dossier resultats/)."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import flex_core as fc

OUT = Path(__file__).parent / "resultats"; OUT.mkdir(exist_ok=True)
C = {"Industrie": "#2a78d6", "Tertiaire": "#eb6834", "VE": "#1baf7a", "Batterie": "#eda100",
     "Résidentiel": "#6250d6", "Agriculture": "#008300"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": .8, "axes.axisbelow": True,
                     "figure.dpi": 160, "savefig.bbox": "tight", "axes.titleweight": "bold",
                     "axes.titlesize": 13, "axes.titlelocation": "left", "legend.frameon": False})
R = {}

# --- 1. Territoire
serie = fc.load_serie_commune()
s25 = serie[serie.annee == 2025].set_index("secteur")["conso_MWh"]
R["commune_2025_GWh"] = {k: round(v / 1000, 1) for k, v in s25.items()}
R["commune_total_GWh"] = round(s25.sum() / 1000, 1)
iris = fc.load_conso_iris()
tot_iris = iris.groupby(["code_iris", "nom_iris"])["conso_MWh"].sum().sort_values()
R["za_GWh"] = round(tot_iris.xs(fc.IRIS_ZA, level=0).iloc[0] / 1000, 1)
R["za_part_commune_pct"] = round(tot_iris.xs(fc.IRIS_ZA, level=0).iloc[0] / s25.sum() * 100, 1)
e = fc.energies_zone(); R["za_energies_MWh"] = {k: round(float(v)) for k, v in e.items()}
sites = fc.load_sites_za(); R["za_nb_sites_ent"] = int(sites.nb_sites.sum())
R["za_top10_part_pct"] = round(sites.nlargest(10, "conso_MWh").conso_MWh.sum() / e["total"] * 100, 1)

fig, ax = plt.subplots(figsize=(7, 3.6))
piv = serie[serie.secteur != "INCONNU"].pivot(index="annee", columns="secteur", values="conso_MWh") / 1000
for sec, lab in [("TERTIAIRE", "Tertiaire"), ("INDUSTRIE", "Industrie"), ("RESIDENTIEL", "Résidentiel")]:
    ax.plot(piv.index, piv[sec], lw=2, color=C[lab], marker="o", ms=4)
    ax.annotate(f"{lab} {piv[sec].iloc[-1]:.0f}", (piv.index[-1], piv[sec].iloc[-1]), xytext=(6, 0),
                textcoords="offset points", va="center", color=INK, fontsize=10)
ax.set_title("Châtellerault : consommation électrique par secteur (GWh/an)")
ax.set_ylim(0, 95); ax.set_xlim(2017.7, 2026.3); ax.set_ylabel("GWh")
fig.savefig(OUT / "fig1_serie_commune.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 4.2))
z = iris.pivot_table(index="nom_iris", columns="secteur", values="conso_MWh", aggfunc="sum").fillna(0) / 1000
z = z.loc[z.sum(axis=1).sort_values().index]
left = np.zeros(len(z))
for sec, lab in [("INDUSTRIE", "Industrie"), ("TERTIAIRE", "Tertiaire"), ("RESIDENTIEL", "Résidentiel")]:
    ax.barh(z.index, z[sec], left=left, color=C[lab], label=lab, height=.7, edgecolor="white", linewidth=1)
    left += z[sec].values
ax.set_title("Consommation 2025 par quartier IRIS (GWh)"); ax.legend(loc="lower right")
ax.grid(axis="y", visible=False); ax.tick_params(axis="y", labelsize=9)
fig.savefig(OUT / "fig2_iris.png"); plt.close(fig)

# --- 2. Profil et congestion
prof15 = fc.profil_zone(pas="15")
prof = fc.profil_zone()
deb = fc.fenetre_pointe(prof); heures = [deb, deb + 1]
p, besoin = fc.scenario_congestion(prof, deb)
R.update(pointe_kW=round(prof.charge_kW.max()), creux_kW=round(prof.charge_kW.min()),
         fenetre=f"{deb}h-{deb + 2}h", capacite_kW=round(p.capacite_kW.iloc[0]), besoin_kW=besoin)
fig, ax = plt.subplots(figsize=(8, 3.8))
ax.stackplot(prof15.h, prof15.hta_kW / 1000, prof15.pro_kW / 1000, prof15.residentiel_kW / 1000,
             colors=[C["Industrie"], C["Tertiaire"], C["Résidentiel"]], alpha=.85,
             labels=["Gros sites (ENT/HTA)", "Petits pros", "Résidentiel"])
cap = p.capacite_kW.iloc[0] / 1000
ax.axhline(cap, color=INK, ls="--", lw=1.2); ax.text(0.2, cap + .25, f"Capacité {cap:.1f} MW", color=INK, fontsize=9)
ax.bar([h + .5 for h in heures], [.5, .5], bottom=cap, width=.95, color="#e34948", label="Dépassement +500 kW")
ax.axvspan(deb, deb + 2, color="#e34948", alpha=.07)
ax.set_xlim(0, 24); ax.set_ylim(0, cap + 1.6); ax.set_xticks(range(0, 25, 3))
ax.set_xlabel("Heure (20 janvier 2026)"); ax.set_ylabel("MW")
ax.set_title("ZA Sanital : profil de charge reconstitué et congestion simulée")
ax.legend(loc="lower right", ncol=2, fontsize=9)
fig.savefig(OUT / "fig3_profil.png"); plt.close(fig)

eco = fc.load_eco2mix(); b = fc.load_bilan()
fig, ax = plt.subplots(figsize=(8, 3.4))
for col, lab, c in [("hta_MW", "HTA (industrie, gros tertiaire)", C["Industrie"]), ("pro_MW", "Professionnels", C["Tertiaire"]),
                    ("residentiel_MW", "Résidentiel", C["Résidentiel"])]:
    ax.plot(b.h, b[col] / b[col].max(), lw=2, color=c, label=lab)
ax.plot(eco.h, eco.conso_MW / eco.conso_MW.max(), lw=1.5, color=INK2, ls=":", label="Nouvelle-Aquitaine (RTE)")
ax.set_title("Formes de courbe le 20/01/2026 (normalisées)"); ax.set_xlim(0, 24); ax.set_xticks(range(0, 25, 3))
ax.legend(fontsize=9, ncol=2, loc="lower right"); ax.set_ylim(.55, 1.03)
fig.savefig(OUT / "fig4_formes.png"); plt.close(fig)

# --- 3. Offres et sélection
offres = fc.generer_offres(postes=fc.load_postes())
offres.drop(columns=["lat", "lon"]).to_csv(OUT / "offres.csv", index=False, sep=";")
res = {"mo": fc.selection_preseance(offres, heures, besoin, 500),
       "or": fc.selection_ortools(offres, heures, besoin, 500),
       "og": fc.selection_ortools(offres, heures, besoin, 500, puissance_garantie=True)}
K = {}
for k, r in res.items():
    ind = fc.indicateurs(r, offres); ind.update(fc.monte_carlo(r, offres, 20000)); K[k] = ind
    fc.detail_activation(r, offres).to_csv(OUT / f"selection_{k}.csv", index=False, sep=";")
R["selection"] = K
R["gisement_kW_fenetre"] = int(offres[[fc._dispo(o, deb) for _, o in offres.iterrows()]].puissance_kW.sum())
R["gisement_kW_total"] = int(offres.puissance_kW.sum())

fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True)
for ax, (k, titre) in zip(axes, [("mo", "Préséance économique"), ("or", "OR-Tools"), ("og", "OR-Tools + fiabilité")]):
    r = res[k]; act = r.activation; o = offres.set_index("id")
    for j, h in enumerate(heures):
        bottom = 0
        for oid in act.index[act[h] > 0]:
            v = act.loc[oid, h]; cat = o.loc[oid, "categorie"]
            ax.bar(j, v, bottom=bottom, color=C[cat], width=.6, edgecolor="white", linewidth=2)
            if v >= 45:
                ax.text(j, bottom + v / 2, oid, ha="center", va="center", color="white", fontsize=8)
            bottom += v
    ax.axhline(besoin, color="#1baf7a", ls=":", lw=1.5); ax.axhline(500, color="#e34948", ls="--", lw=1.2)
    ax.set_xticks([0, 1], [f"{h}h-{h + 1}h" for h in heures]); ax.grid(axis="x", visible=False)
    ax.set_title(f"{titre}\n{K[k]['cout_total_EUR']:.0f} € · couverture {K[k]['proba_couverture'] * 100:.0f} %", fontsize=11)
axes[0].set_ylabel("kW activés")
axes[2].text(1.4, 500, " 500 kW\n dépassement", color="#e34948", fontsize=8, va="top")
axes[2].text(1.4, besoin, " 550 kW besoin", color="#1baf7a", fontsize=8, va="bottom")
from matplotlib.patches import Patch
fig.legend(handles=[Patch(color=C[c], label=c) for c in ["Industrie", "Tertiaire", "VE", "Batterie"]],
           loc="lower center", ncol=4, bbox_to_anchor=(.5, -.04))
fig.savefig(OUT / "fig5_selection.png"); plt.close(fig)

# --- 4. Robustesse
sens = fc.sensibilite_marge(offres, heures, n=20000); sens.to_csv(OUT / "sensibilite_marge.csv", index=False, sep=";")
R["sensibilite_marge"] = sens.round(3).to_dict(orient="records")
fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
ax[0].plot(sens.marge_pct, sens.proba_couverture * 100, marker="o", color=C["Industrie"], lw=2)
ax[0].set_title("Probabilité de couvrir 500 kW (%)"); ax[0].set_xlabel("Marge de sécurité (%)"); ax[0].set_ylim(0, 100)
ax[1].bar(sens.marge_pct, sens.cout_EUR, width=3.2, color=C["Tertiaire"])
ax[1].set_title("Coût par événement (€)"); ax[1].set_xlabel("Marge de sécurité (%)"); ax[1].grid(axis="x", visible=False)
for a in ax: a.axvline(10, color=INK2, ls=":", lw=1)
fig.savefig(OUT / "fig6_marge.png"); plt.close(fig)

bench = fc.comparer_solveurs(200, heures=(9, 10)); bench.to_csv(OUT / "benchmark_solveurs.csv", index=False, sep=";")
ok = bench.dropna(subset=["cout_mo", "cout_or"])
R["benchmark"] = dict(n=len(bench), or_faisable=int((bench.statut_or != "INFAISABLE").sum()),
                      mo_ok=int((bench.statut_mo == "OK").sum()),
                      surcout_moyen_pct=round(ok.surcout_mo_pct.mean(), 1), surcout_median_pct=round(ok.surcout_mo_pct.median(), 1),
                      surcout_max_pct=round(ok.surcout_mo_pct.max(), 1), egalite_pct=round((ok.surcout_mo_pct < .01).mean() * 100, 1),
                      surplus_mo_moy=round(ok.surplus_mo.mean()), surplus_or_moy=round(ok.surplus_or.mean()))
fig, ax = plt.subplots(figsize=(7, 3.2))
ax.hist(ok.surcout_mo_pct, bins=20, color=C["Industrie"], edgecolor="white")
ax.axvline(ok.surcout_mo_pct.mean(), color=INK, ls="--", lw=1.2)
ax.text(ok.surcout_mo_pct.mean(), ax.get_ylim()[1] * .9, f"  moyenne +{ok.surcout_mo_pct.mean():.0f} %", fontsize=9)
ax.set_title(f"Surcoût du tri par prix vs OR-Tools ({len(ok)} jeux d'offres aléatoires)"); ax.set_xlabel("Surcoût (%)"); ax.set_ylabel("Nb de jeux")
fig.savefig(OUT / "fig7_benchmark.png"); plt.close(fig)

# --- 5. Flex vs renforcement
capex_bas, capex_ref, capex_haut = fc.capex_renforcement(2, 107), fc.capex_renforcement(4, 145), fc.capex_renforcement(6, 202)
cev = K["og"]["cout_total_EUR"]
cmp = fc.comparaison_renforcement(cev, 20, capex_ref, .05, 40, 5000, 5)
R["renfo"] = dict(capex_bas=round(capex_bas), capex_ref=round(capex_ref), capex_haut=round(capex_haut),
                  annuite_ref=round(cmp["renfo_EUR_an"]), flex_an_20evts=round(cmp["flex_EUR_an"]),
                  seuil_evts=round(cmp["nb_evenements_seuil"]), gain_report_5ans=round(cmp["gain_report_EUR"]),
                  cout_flex_5ans=round(cmp["cout_flex_report_EUR"]), cout_evenement=round(cev, 1))
n = np.arange(0, 1001, 10)
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(n, (cev * n + 5000) / 1000, color=C["VE"], lw=2.2, label="Flexibilité")
for cx, ls, lab in [(capex_bas, ":", "bas"), (capex_ref, "-", "réf."), (capex_haut, ":", "haut")]:
    a = fc.annuite(cx, .05, 40) / 1000
    ax.axhline(a, color=C["Batterie"] if lab == "réf." else INK2, ls=ls, lw=2 if lab == "réf." else 1.2)
    ax.text(1005, a, f"Renforcement {lab}\n{cx / 1e3:.0f} k€", fontsize=8, va="center")
ax.axvline(20, color=INK2, ls="--", lw=1); ax.text(28, 118, "scénario :\n20 événements/an", fontsize=8, color=INK2)
ax.set_xlabel("Nombre d'événements de congestion par an"); ax.set_ylabel("k€ / an")
ax.set_title("Coût annuel : flexibilité vs renforcement (annuité 40 ans, 5 %)")
ax.set_xlim(0, 1000); ax.legend(loc="lower right")
ax.text(280, 50, f"seuil ≈ {cmp['nb_evenements_seuil']:.0f} évts/an", fontsize=9, color=INK)
fig.savefig(OUT / "fig8_renforcement.png"); plt.close(fig)

json.dump(R, open(OUT / "resultats.json", "w"), indent=1, ensure_ascii=False, default=float)
print(json.dumps(R, indent=1, ensure_ascii=False, default=float))
