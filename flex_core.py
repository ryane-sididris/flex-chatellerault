"""
Cœur du modèle – Projet 4 : Flexibilité territoriale (ZA Sanital, Châtellerault)

  1. Données réelles      : Enedis Open Data (conso 2025 par IRIS / secteur / site, courbes
                            nationales du 20/01/2026), RTE eCO2mix, postes HTA/BT
  2. Profil de la zone    : énergie annuelle réelle × forme horaire réelle par catégorie
  3. Congestion simulée   : +500 kW pendant 2 h sur la pointe, besoin = 550 kW (marge 10 %)
  4. Offres               : 18 offres, dont 12 adossées aux sites réels de la ZA
  5. Sélection            : (a) préséance économique (prix croissant), (b) OR-Tools CP-SAT
  6. Indicateurs          : puissance, coût total, coût moyen, marge, offres non retenues
  7. Robustesse           : Monte-Carlo sur les défaillances + comparaison des solveurs
  8. Flex vs renforcement : barème Enedis/CRE 2026, annuité, valeur du report d'investissement
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
IRIS_ZA = "860660303"  # Zones Industrielles Sanital et Nord

# ---------------------------------------------------------------------------
# 1. Données
# ---------------------------------------------------------------------------

def load_eco2mix(path: Path = DATA / "eco2mix_2026-01-20.csv") -> pd.DataFrame:
    """Consommation régionale Nouvelle-Aquitaine (MW, pas 30 min) – RTE eCO2mix."""
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", usecols=[2, 3, 4],
                     names=["date", "heure", "conso_MW"], header=0)
    df = df.dropna(subset=["conso_MW"])
    df = df[df["heure"].astype(str).str.match(r"^\d{2}:\d{2}$")].copy()
    df["conso_MW"] = df["conso_MW"].astype(float)
    df["h"] = df["heure"].str.slice(0, 2).astype(int) + df["heure"].str.slice(3, 5).astype(int) / 60
    return df.reset_index(drop=True)


def load_postes(path: Path = DATA / "postes.csv") -> pd.DataFrame:
    """Postes HTA/BT (Enedis) avec coordonnées."""
    df = pd.read_csv(path)
    coords = df["geometry"].str.extract(r"\[([-\d.]+),([-\d.]+)\]").astype(float)
    df["lon"], df["lat"] = coords[0], coords[1]
    df["zone_indus"] = df["code_iris"].astype(str) == IRIS_ZA
    return df


def load_conso_iris() -> pd.DataFrame:
    """Consommation 2025 par IRIS et grand secteur (Enedis)."""
    return pd.read_csv(DATA / "conso_iris_2025.csv", sep=";", dtype={"code_iris": str})


def load_serie_commune() -> pd.DataFrame:
    return pd.read_csv(DATA / "conso_commune_serie.csv", sep=";")


def load_sites_za() -> pd.DataFrame:
    """Sites 'entreprises' (> 36 kVA) de la ZA Sanital, conso 2025 par adresse (Enedis)."""
    return pd.read_csv(DATA / "sites_sanital_2025.csv", sep=";", dtype={"naf2": str})


def load_bilan() -> pd.DataFrame:
    """Puissances nationales Enedis au pas 15 min le 20/01/2026, par catégorie (MW)."""
    df = pd.read_csv(DATA / "bilan_enedis_20260120.csv", sep=";")
    df["h"] = df["heure"].str.slice(0, 2).astype(int) + df["heure"].str.slice(3, 5).astype(int) / 60
    return df


# Moyennes annuelles 2025 des mêmes séries (Enedis, bilan électrique 15 min) en MW
MOY_2025_MW = {"residentiel": 15844.1, "pro": 4158.6, "hta": 11661.3}

NAF = {
    "10": "Agroalimentaire", "13": "Textile", "14": "Habillement", "18": "Imprimerie",
    "22": "Plasturgie", "23": "Minéraux non métalliques", "25": "Produits métalliques",
    "27": "Équipements électriques", "28": "Machines", "29": "Automobile",
    "31": "Meubles", "32": "Autres industries", "33": "Maintenance industrielle",
    "35": "Énergie", "42": "Génie civil", "45": "Commerce auto", "46": "Commerce de gros",
    "47": "Commerce de détail", "49": "Transport", "52": "Entreposage", "53": "Courrier",
    "55": "Hébergement", "56": "Restauration", "64": "Finance", "68": "Immobilier",
    "71": "Ingénierie", "82": "Services aux entreprises", "84": "Administration",
    "85": "Enseignement", "86": "Santé", "88": "Action sociale", "93": "Sport-loisirs",
}

# ---------------------------------------------------------------------------
# 2. Profil de charge de la zone
# ---------------------------------------------------------------------------

def energies_zone(iris: str = IRIS_ZA) -> dict:
    """Énergie annuelle (MWh) de la zone répartie par forme de courbe.

    - Gros sites (ENT, souvent HTA)     -> forme 'hta'
    - Petits professionnels (PRO ≤36kVA) -> forme 'pro'
    - Résidentiel                        -> forme 'residentiel'
    Pour la ZA Sanital (Enedis 2025) : PRO industrie 396,9 MWh, PRO tertiaire 1 680,5 MWh.
    """
    c = load_conso_iris()
    z = c[c["code_iris"] == iris].set_index("secteur")["conso_MWh"]
    pro = 396.9 + 1680.5 if iris == IRIS_ZA else 0.15 * z.get("TERTIAIRE", 0)
    res = z.get("RESIDENTIEL", 0)
    ent = z.sum() - pro - res
    return {"hta": ent, "pro": pro, "residentiel": res, "total": z.sum()}


def profil_zone(iris: str = IRIS_ZA, pas: str = "h") -> pd.DataFrame:
    """Profil de la zone un jour froid de semaine (20/01/2026), en kW.

    P_zone(t) = Σ_catégories  E_annuelle / 8760 h × P_nationale(t) / P_nationale_moyenne_2025
    → énergie réelle de la zone, forme réelle (Enedis) de chaque type de client.
    """
    b = load_bilan()
    e = energies_zone(iris)
    comp = {}
    for cat, col in [("hta", "hta_MW"), ("pro", "pro_MW"), ("residentiel", "residentiel_MW")]:
        comp[cat] = e[cat] * 1000 / 8760 * b[col] / MOY_2025_MW[cat]
    df = pd.DataFrame({"h": b["h"], **{f"{k}_kW": v for k, v in comp.items()}})
    df["charge_kW"] = df[[f"{k}_kW" for k in comp]].sum(axis=1)
    if pas == "h":
        df = df.assign(heure=df["h"].astype(int)).groupby("heure", as_index=False).mean(numeric_only=True)
        df = df.drop(columns="h")
    return df


def fenetre_pointe(prof: pd.DataFrame, duree: int = 2) -> int:
    """Heure de début de la fenêtre de `duree` heures la plus chargée."""
    roll = prof["charge_kW"].rolling(duree).mean().shift(-(duree - 1))
    return int(prof.loc[roll.idxmax(), "heure"])


def scenario_congestion(prof: pd.DataFrame, debut: int, duree: int = 2,
                        depassement_kW: float = 500, marge: float = 0.10) -> tuple[pd.DataFrame, float]:
    """Capacité = charge horaire maximale actuelle. On simule une hausse (nouveau
    raccordement, électrification d'un process…) qui porte la charge à capacité + 500 kW
    pendant la fenêtre. Besoin de flexibilité = dépassement × (1 + marge)."""
    p = prof.copy()
    fen = (p["heure"] >= debut) & (p["heure"] < debut + duree)
    capacite = float(p["charge_kW"].max())
    p["charge_congestion_kW"] = np.where(fen, capacite + depassement_kW, p["charge_kW"])
    p["capacite_kW"] = capacite
    p["en_congestion"] = fen
    return p, depassement_kW * (1 + marge)


# ---------------------------------------------------------------------------
# 3. Offres
# ---------------------------------------------------------------------------

BORNES = {  # bornes du sujet
    "Industrie": dict(p=(100, 300), prix=(50, 150), dmax=(1, 4)),
    "Tertiaire": dict(p=(20, 100), prix=(80, 200), dmax=(1, 2)),
    "VE":        dict(p=(20, 150), prix=(100, 250), dmax=(1, 3)),
    "Batterie":  dict(p=(50, 200), prix=(150, 300), dmax=(1, 2)),
}
CATEGORIES = BORNES  # compat

# Hypothèses de gisement par site (part de la puissance moyenne effaçable)
H_UTIL = {"Industrie": 5000, "Tertiaire": 2800}       # heures d'utilisation équivalentes
PART_FLEX = {"Industrie": (0.06, 0.12), "Tertiaire": (0.15, 0.25)}
FIABILITE = {"Industrie": 0.95, "Tertiaire": 0.90, "VE": 0.85, "Batterie": 0.97}


def _clip(x, lo, hi):
    return int(round(min(max(x, lo), hi) / 5) * 5)


def generer_offres(seed: int = 42, n_indus: int = 7, n_tert: int = 5, n_ve: int = 3, n_batt: int = 3,
                   postes: pd.DataFrame | None = None) -> pd.DataFrame:
    """18 offres par défaut. Industrie et tertiaire = sites réels de la ZA (conso Enedis 2025) ;
    puissance offerte = P_moyenne × part flexible, bornée par le sujet. VE et batteries = synthétiques.
    Prix tirés aléatoirement dans les fourchettes du sujet (graine fixée)."""
    rng = np.random.default_rng(seed)
    sites = load_sites_za()
    rows = []

    ind = sites[(sites["secteur"] == "INDUSTRIE") | (sites["naf2"] == "33")].nlargest(n_indus, "conso_MWh")
    ter = sites[(sites["secteur"] == "TERTIAIRE") & (sites["naf2"] != "33")
                & sites["naf2"].isin(["47", "56", "84", "88", "68", "52", "55", "85"])]
    ter = ter.sort_values("conso_MWh", ascending=False).drop_duplicates("naf2").head(n_tert)

    for cat, df_ in (("Industrie", ind), ("Tertiaire", ter)):
        b = BORNES[cat]
        for _, s in df_.iterrows():
            p_moy = s["conso_MWh"] * 1000 / H_UTIL[cat]
            p = _clip(p_moy * rng.uniform(*PART_FLEX[cat]), *b["p"])
            rows.append(dict(acteur=f"{NAF.get(s['naf2'], 'NAF ' + s['naf2'])} – {s['adresse'].title()}",
                             categorie=cat, naf2=s["naf2"], conso_site_MWh=round(s["conso_MWh"]),
                             puissance_kW=p, source="Site réel Enedis 2025",
                             dispo_debut=6 if cat == "Industrie" else 8,
                             dispo_fin=22 if cat == "Industrie" else 19))

    ve = [("Bornes salariés ZA (charge pilotée)", 8, 18), ("Flotte utilitaires logistique", 18, 7),
          ("Bornes publiques Espace d'Argenson", 7, 22)]
    batt = [("Batterie couplée PV toiture industrielle", 0, 24), ("Batterie de site agroalimentaire", 0, 24),
            ("Stockage mutualisé ZA (projet)", 0, 24)]
    for cat, lst in (("VE", ve[:n_ve]), ("Batterie", batt[:n_batt])):
        for nom, d, f in lst:
            rows.append(dict(acteur=nom, categorie=cat, naf2="", conso_site_MWh=np.nan,
                             puissance_kW=_clip(rng.uniform(*BORNES[cat]["p"]), *BORNES[cat]["p"]),
                             source="Synthétique", dispo_debut=d, dispo_fin=f))

    df = pd.DataFrame(rows)
    df["prix_EUR_MWh"] = [int(round(rng.uniform(*BORNES[c]["prix"]) / 5) * 5) for c in df["categorie"]]
    df["duree_min_h"] = 1
    df["duree_max_h"] = [int(rng.integers(BORNES[c]["dmax"][0], BORNES[c]["dmax"][1] + 1)) for c in df["categorie"]]
    df["fiabilite"] = df["categorie"].map(FIABILITE)
    df.insert(0, "id", [f"O{i + 1:02d}" for i in range(len(df))])
    if postes is not None:  # position indicative : un poste de la ZA (VE/batt. aussi dans la ZA)
        za = postes[postes["zone_indus"]].reset_index(drop=True)
        idx = rng.choice(len(za), size=len(df), replace=len(df) > len(za))
        df["lat"], df["lon"] = za.loc[idx, "lat"].values, za.loc[idx, "lon"].values
    cols = ["id", "acteur", "categorie", "puissance_kW", "prix_EUR_MWh", "duree_min_h", "duree_max_h",
            "dispo_debut", "dispo_fin", "fiabilite", "naf2", "conso_site_MWh", "source"]
    return df[cols + [c for c in df.columns if c not in cols]]


def generer_offres_aleatoires(seed: int, n_par_cat=(4, 4, 4, 4)) -> pd.DataFrame:
    """Jeu d'offres purement synthétique (pour les tests statistiques des solveurs)."""
    rng = np.random.default_rng(seed)
    dispo = {"Industrie": (6, 22), "Tertiaire": (8, 19), "VE": (17, 24), "Batterie": (0, 24)}
    rows = []
    for cat, n in zip(BORNES, n_par_cat):
        b = BORNES[cat]
        for _ in range(n):
            rows.append(dict(categorie=cat, puissance_kW=_clip(rng.uniform(*b["p"]), *b["p"]),
                             prix_EUR_MWh=int(rng.uniform(*b["prix"])), duree_min_h=1,
                             duree_max_h=int(rng.integers(b["dmax"][0], b["dmax"][1] + 1)),
                             dispo_debut=dispo[cat][0], dispo_fin=dispo[cat][1]))
    df = pd.DataFrame(rows)
    df.insert(0, "id", [f"O{i + 1:02d}" for i in range(len(df))])
    return df


# ---------------------------------------------------------------------------
# 4. Sélection
# ---------------------------------------------------------------------------

@dataclass
class Resultat:
    methode: str
    activation: pd.DataFrame          # lignes = offres, colonnes = heures (kW activés)
    besoin_kW: float
    depassement_kW: float
    heures: list[int]
    statut: str = "OK"
    notes: list[str] = field(default_factory=list)


def _dispo(o, h) -> bool:
    d, f = int(o["dispo_debut"]), int(o["dispo_fin"])
    return d <= h < f if d <= f else (h >= d or h < f)   # gère les plages de nuit (ex. 18h → 7h)


def selection_preseance(offres: pd.DataFrame, heures: list[int], besoin: float, depassement: float) -> Resultat:
    """Préséance économique : à chaque heure, empilement des offres disponibles par prix
    croissant jusqu'à couvrir le besoin (offres indivisibles, durée max respectée)."""
    act = pd.DataFrame(0.0, index=list(offres["id"]), columns=heures)
    restant = dict(zip(offres["id"], offres["duree_max_h"]))
    tri = offres.sort_values(["prix_EUR_MWh", "puissance_kW"], ascending=[True, False])
    notes, statut = [], "OK"
    for h in heures:
        cumul = 0.0
        for _, o in tri.iterrows():
            if cumul >= besoin:
                break
            if _dispo(o, h) and restant[o["id"]] > 0:
                act.loc[o["id"], h] = o["puissance_kW"]
                restant[o["id"]] -= 1
                cumul += o["puissance_kW"]
        if cumul < besoin:
            statut = "INSUFFISANT"
            notes.append(f"{h}h : {cumul:.0f} kW mobilisés < besoin {besoin:.0f} kW")
    return Resultat("Préséance économique", act, besoin, depassement, heures, statut, notes)


def selection_ortools(offres: pd.DataFrame, heures: list[int], besoin: float, depassement: float,
                      temps_max_s: float = 10, puissance_garantie: bool = False) -> Resultat:
    """Programme linéaire en nombres entiers (CP-SAT) :
        min  Σ_o Σ_h  P_o · prix_o · x_oh                      (coût total)
        s.c. Σ_o P_o · x_oh ≥ besoin                ∀h        (couverture + marge)
             x_oh = 0 si o indisponible à h                    (disponibilité)
             dmin_o · y_o ≤ Σ_h x_oh ≤ dmax_o · y_o            (durées)
             une seule plage contiguë par offre                (pas de fractionnement)
             x_oh, y_o ∈ {0,1}                                 (offre sélectionnée une fois)
    Variante `puissance_garantie` : chaque offre compte pour P_o × fiabilité_o dans la
    couverture (puissance « espérée ») – le portefeuille devient plus robuste aux défaillances.
    """
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    ids = list(offres["id"])
    ob = offres.set_index("id")
    x = {(i, h): m.NewBoolVar(f"x_{i}_{h}") for i in ids for h in heures}
    y = {i: m.NewBoolVar(f"y_{i}") for i in ids}
    s = {(i, h): m.NewBoolVar(f"s_{i}_{h}") for i in ids for h in heures}
    for i in ids:
        o = ob.loc[i]
        n = sum(x[i, h] for h in heures)
        for h in heures:
            if not _dispo(o, h):
                m.Add(x[i, h] == 0)
            m.AddImplication(x[i, h], y[i])
        m.Add(n <= int(o["duree_max_h"]) * y[i])
        m.Add(n >= int(o["duree_min_h"]) * y[i])
        for k, h in enumerate(heures):
            prev = x[i, heures[k - 1]] if k > 0 else 0
            m.Add(s[i, h] >= x[i, h] - prev)
        m.Add(sum(s[i, h] for h in heures) <= 1)
    def p_eff(i):
        f = float(ob.loc[i, "fiabilite"]) if (puissance_garantie and "fiabilite" in ob) else 1.0
        return int(round(ob.loc[i, "puissance_kW"] * f))
    for h in heures:
        m.Add(sum(p_eff(i) * x[i, h] for i in ids) >= int(np.ceil(besoin)))
    m.Minimize(sum(int(round(ob.loc[i, "puissance_kW"] * ob.loc[i, "prix_EUR_MWh"] / 10)) * x[i, h]
                   for i in ids for h in heures))
    nom = "OR-Tools (puissance garantie)" if puissance_garantie else "Optimisation OR-Tools"
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = temps_max_s
    solver.parameters.num_workers = 4
    st = solver.Solve(m)
    act = pd.DataFrame(0.0, index=ids, columns=heures)
    if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i in ids:
            for h in heures:
                if solver.Value(x[i, h]):
                    act.loc[i, h] = ob.loc[i, "puissance_kW"]
        return Resultat(nom, act, besoin, depassement, heures,
                        "OPTIMAL" if st == cp_model.OPTIMAL else "RÉALISABLE")
    return Resultat(nom, act, besoin, depassement, heures, "INFAISABLE",
                    ["Le gisement ne permet pas de couvrir le besoin sur toute la fenêtre."])


# ---------------------------------------------------------------------------
# 5. Indicateurs
# ---------------------------------------------------------------------------

def indicateurs(res: Resultat, offres: pd.DataFrame) -> dict:
    o = offres.set_index("id")
    act = res.activation
    p_h = act.sum(axis=0)
    energie = float(act.values.sum() / 1000)
    cout = float((act.sum(axis=1) * o.loc[act.index, "prix_EUR_MWh"]).sum() / 1000)
    retenues = act.index[act.sum(axis=1) > 0].tolist()
    return {
        "methode": res.methode, "statut": res.statut,
        "P_min_mobilisee_kW": float(p_h.min()), "P_max_mobilisee_kW": float(p_h.max()),
        "P_par_heure": {int(k): float(v) for k, v in p_h.items()},
        "energie_MWh": energie, "cout_total_EUR": cout,
        "cout_moyen_EUR_MWh": cout / energie if energie else float("nan"),
        "marge_vs_depassement_kW": float(p_h.min() - res.depassement_kW),
        "marge_vs_depassement_pct": float((p_h.min() - res.depassement_kW) / res.depassement_kW * 100),
        "surplus_vs_besoin_kW": float(p_h.min() - res.besoin_kW),
        "nb_retenues": len(retenues), "retenues": retenues,
        "non_retenues": [i for i in o.index if i not in retenues], "notes": res.notes,
    }


def detail_activation(res: Resultat, offres: pd.DataFrame) -> pd.DataFrame:
    act = res.activation
    d = offres.set_index("id").loc[act.index, ["acteur", "categorie", "puissance_kW", "prix_EUR_MWh"]].copy()
    for h in act.columns:
        d[f"{h}h-{h + 1}h"] = act[h].astype(int)
    d["heures_activees"] = (act > 0).sum(axis=1)
    d["cout_EUR"] = (act.sum(axis=1) * d["prix_EUR_MWh"] / 1000).round(1)
    d["retenue"] = d["heures_activees"] > 0
    d.index.name = "id"
    return d.reset_index().sort_values(["retenue", "prix_EUR_MWh"], ascending=[False, True])


def raison_non_retenue(oid: str, res: Resultat, offres: pd.DataFrame) -> str:
    o = offres.set_index("id").loc[oid]
    if not any(_dispo(o, h) for h in res.heures):
        return "Indisponible sur la fenêtre"
    return "Trop chère / non nécessaire"


# ---------------------------------------------------------------------------
# 6. Robustesse
# ---------------------------------------------------------------------------

def monte_carlo(res: Resultat, offres: pd.DataFrame, n: int = 5000, seed: int = 0) -> dict:
    """Chaque offre retenue répond avec une probabilité = sa fiabilité. On mesure la probabilité
    que la puissance réellement livrée couvre le dépassement (500 kW) à chaque heure."""
    rng = np.random.default_rng(seed)
    act = res.activation
    rel = offres.set_index("id").loc[act.index, "fiabilite"].to_numpy() if "fiabilite" in offres else np.full(len(act), .9)
    ok = rng.random((n, len(act))) < rel                       # (tirages, offres)
    livre = ok @ act.to_numpy()                                 # (tirages, heures)
    couvert = (livre >= res.depassement_kW).all(axis=1)
    return {"proba_couverture": float(couvert.mean()), "P_livree_moy_kW": float(livre.min(axis=1).mean()),
            "P_livree_p5_kW": float(np.percentile(livre.min(axis=1), 5))}


def sensibilite_marge(offres, heures, depassement=500, marges=(0, .05, .10, .15, .20, .30), n=4000):
    rows = []
    for mg in marges:
        r = selection_ortools(offres, heures, depassement * (1 + mg), depassement)
        if r.statut == "INFAISABLE":
            rows.append(dict(marge_pct=mg * 100, cout_EUR=np.nan, proba_couverture=np.nan)); continue
        k = indicateurs(r, offres)
        rows.append(dict(marge_pct=mg * 100, cout_EUR=k["cout_total_EUR"],
                         proba_couverture=monte_carlo(r, offres, n)["proba_couverture"]))
    return pd.DataFrame(rows)


def comparer_solveurs(n_instances: int = 200, heures=(18, 19), besoin=550, depassement=500) -> pd.DataFrame:
    """Compare les deux méthodes sur n jeux d'offres aléatoires (mêmes bornes que le sujet)."""
    rows = []
    for s in range(n_instances):
        o = generer_offres_aleatoires(s)
        a, b = selection_preseance(o, list(heures), besoin, depassement), selection_ortools(o, list(heures), besoin, depassement, 5)
        ka, kb = indicateurs(a, o), indicateurs(b, o)
        rows.append(dict(seed=s, statut_mo=a.statut, statut_or=b.statut,
                         cout_mo=ka["cout_total_EUR"] if a.statut == "OK" else np.nan,
                         cout_or=kb["cout_total_EUR"] if b.statut != "INFAISABLE" else np.nan,
                         surplus_mo=ka["surplus_vs_besoin_kW"], surplus_or=kb["surplus_vs_besoin_kW"]))
    df = pd.DataFrame(rows)
    df["surcout_mo_pct"] = (df["cout_mo"] / df["cout_or"] - 1) * 100
    return df


# ---------------------------------------------------------------------------
# 7. Flexibilité vs renforcement
# ---------------------------------------------------------------------------

# Barème de raccordement Enedis v8 (CRE, délibération 2026-160, 17/07/2026) :
#   extension HTA souterraine : 145 €/m (zone A, ≤ 400 m), 107 €/m au-delà, 202 €/m (zone B)
#   poste HTA/BT neuf ≤ 250 kVA : 21 898 à 42 545 € HT
COUT_HTA_EUR_M = (107, 145, 202)


def capex_renforcement(longueur_km: float = 4.0, cout_m: float = 145, cellule_depart: float = 80_000,
                       divers: float = 0.15) -> float:
    """Nouveau départ HTA depuis le poste source : câble + cellule + aléas/ingénierie."""
    return (longueur_km * 1000 * cout_m + cellule_depart) * (1 + divers)


def annuite(capex: float, taux: float, n_ans: int) -> float:
    return capex * taux / (1 - (1 + taux) ** -n_ans) if taux else capex / n_ans


def comparaison_renforcement(cout_evenement: float, nb_evenements_an: int, capex_renfo: float,
                             taux: float = 0.05, duree_vie: int = 40,
                             frais_fixes_flex_an: float = 0.0, report_ans: int = 5) -> dict:
    flex_an = cout_evenement * nb_evenements_an + frais_fixes_flex_an
    renfo_an = annuite(capex_renfo, taux, duree_vie)
    seuil = (renfo_an - frais_fixes_flex_an) / cout_evenement if cout_evenement else float("inf")
    gain_report = capex_renfo * (1 - (1 + taux) ** -report_ans)              # valeur du report
    cout_flex_report = sum(flex_an / (1 + taux) ** (t + 1) for t in range(report_ans))
    return {"flex_EUR_an": flex_an, "renfo_EUR_an": renfo_an, "nb_evenements_seuil": seuil,
            "flex_moins_cher": flex_an < renfo_an, "gain_report_EUR": gain_report,
            "cout_flex_report_EUR": cout_flex_report, "report_ans": report_ans}


if __name__ == "__main__":
    prof = profil_zone()
    deb = fenetre_pointe(prof)
    prof2, besoin = scenario_congestion(prof, deb)
    print(energies_zone(), "pointe", round(prof["charge_kW"].max()), "kW à", deb, "h")
    offres = generer_offres(postes=load_postes())
    print(offres[["id", "acteur", "categorie", "puissance_kW", "prix_EUR_MWh", "duree_max_h", "dispo_debut", "dispo_fin"]].to_string())
    heures = [deb, deb + 1]
    for f in (selection_preseance, selection_ortools):
        r = f(offres, heures, besoin, 500)
        k = indicateurs(r, offres)
        print(f"\n== {k['methode']} [{k['statut']}] P={k['P_par_heure']} coût={k['cout_total_EUR']:.1f} € "
              f"moy={k['cout_moyen_EUR_MWh']:.0f} €/MWh retenues={k['retenues']}  MC={monte_carlo(r, offres)}")
