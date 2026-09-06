/** Champs métier attendus par la Direction (miroir de `storage.CHAMPS_METIER`). */
export const CHAMPS_METIER = [
  { cle: "reference_dossier", libelle: "Référence du dossier" },
  { cle: "numero_parcelle", libelle: "Numéro de parcelle" },
  { cle: "section_cadastrale", libelle: "Section cadastrale" },
  { cle: "quartier", libelle: "Quartier / secteur" },
  { cle: "demandeur", libelle: "Demandeur" },
  { cle: "date_depot", libelle: "Date de dépôt" },
  { cle: "date_decision", libelle: "Date de décision" },
  { cle: "type_acte", libelle: "Type d'acte" },
  { cle: "statut_instruction", libelle: "Statut de l'instruction" },
] as const;
