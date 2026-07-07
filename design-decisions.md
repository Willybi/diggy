# Décisions design system — 2026-07

1. Grille de spacing : base 4px. Échelle : 2, 4, 8, 12, 16, 20, 24, 32, 40, 60.
   Le 14px (81 occ.) migre vers : [12 / 16 / au cas par cas selon contexte].

2. Demi-pixels de table (12.5 / 14.5px) : [conservés comme tokens
   explicites --fs-table-sm / --fs-table] OU [normalisés vers 13/14px].
   
3. Densité [data-density] : [feature conservée → les 16px en dur des
   contextes de padding de composant migrent vers var(--pad)] OU
   [abandonnée → --pad devient --space-4, suppression des surcharges
   data-density].