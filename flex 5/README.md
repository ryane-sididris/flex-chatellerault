# Projet 4 – Flexibilité territoriale (ZA Sanital, Châtellerault)

## Lancer le dashboard
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    streamlit run app.py

`python analyse.py` régénère tous les chiffres et figures du rapport dans `resultats/`.

## Fichiers
- `flex_core.py` : modèle (données, profil, congestion, offres, 2 solveurs, indicateurs, Monte-Carlo, flex vs renforcement)
- `app.py` : interface Streamlit (7 onglets)
- `analyse.py` : résultats chiffrés + figures PNG
- `data/` : données réelles
  - `conso_iris_2025.csv` – Enedis, conso par IRIS × secteur, 2025
  - `conso_commune_serie.csv` – Enedis, conso de Châtellerault 2018-2025
  - `sites_sanital_2025.csv` – Enedis, conso annuelle des entreprises par adresse, ZA Sanital 2025
  - `bilan_enedis_20260120.csv` – Enedis, puissances nationales au pas 15 min par catégorie, 20/01/2026
  - `eco2mix_2026-01-20.csv` – RTE eCO2mix Nouvelle-Aquitaine
  - `postes.csv` – Enedis, postes HTA/BT
  - `flex_regions.csv` – Enedis, flexibilités déclarées sur les mécanismes de marché par région

## Hypothèses principales
- Forme de courbe nationale Enedis par type de client, énergie réelle de la zone
- Capacité = pointe actuelle ; +500 kW pendant 2 h sur la pointe (9h-11h)
- Offres industrie/tertiaire : P_moy du site (5 000 h / 2 800 h) × part effaçable (6-12 % / 15-25 %), bornée par le sujet
- Prix aléatoires dans les fourchettes du sujet (graine 42)
- Fiabilités : industrie 95 %, tertiaire 90 %, VE 85 %, batterie 97 %
- Renforcement : nouveau départ HTA 4 km × 145 €/m (barème CRE 2026) + cellule 80 k€ + 15 % aléas ; annuité 40 ans à 5 %
