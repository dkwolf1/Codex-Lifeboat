# Codex Portable Backup Package 2.0

Status: **bevroren voor fase 1**
Formaat-id: `codex-portable-backup`
Versie: `2.0`

## Doel en veiligheidsmodel

Het pakket bewaart projecten en lokale Codex-werkgeschiedenis zonder credentials
of installatie-identiteit mee te nemen. Herstel is later altijd een import in een
werkende doelinstallatie, nooit vervanging van de volledige `.codex`-map.

De generator leest de bron, maakt een consistente SQLite-snapshot, bouwt alles in
een tijdelijke `.building-*`-map, hasht ieder inhoudsbestand en laat daarna een
apart validatorprogramma draaien. Alleen daarna wordt `backupComplete` waar en
krijgt de map zijn definitieve naam.

## Vaste indeling

```text
Codex-PortableBackup-YYYYMMDD-HHMMSS/
├── manifest/
│   ├── package.json
│   ├── package.json.sha256
│   ├── projects.json
│   ├── threads.json
│   ├── path-mappings.json
│   └── sha256.csv
├── projects/project-<stabiele-id>/...
├── codex/
│   ├── state.snapshot.sqlite
│   ├── sessions/**/*.jsonl
│   ├── archived_sessions/**/*.jsonl
│   ├── session_index.jsonl
│   └── portable-global-state.json
├── attachments/attachment-<id>/...
├── extra/<naam>/...
├── tools/
├── spec/
└── reports/backup-report.json
```

## Manifestregels

- Alle JSON is UTF-8 zonder BOM.
- Alle interne paden gebruiken `/` en zijn relatief aan de pakketroot.
- `manifest/sha256.csv` bevat `relative_path,size,sha256` en dekt ieder bestand,
  behalve zichzelf, `package.json` en `package.json.sha256`.
- `package.json` bevat de SHA-256 van `sha256.csv`.
- `package.json.sha256` bevat alleen de hex-hash van `package.json` plus newline.
- Onverwachte, niet in `sha256.csv` genoemde bestanden maken validatie ongeldig.
- Een project-id is de eerste 16 hextekens van SHA-256 over het genormaliseerde
  oorspronkelijke pad; daardoor is de indeling binnen dezelfde bron stabiel en
  kunnen gelijke mapnamen uit verschillende bronpaden niet botsen.

## Padmapping

`path-mappings.json` registreert per project en bijlage:

- het oorspronkelijke absolute bronpad;
- het relatieve pad in de back-up;
- `mappingKind` (`project`, `attachment` of `extra`);
- een optioneel voorgesteld doelpad;
- of het bronbestand tijdens de back-up aanwezig was.

Absolute paden in chats en de SQLite-snapshot worden tijdens fase 1 niet
herschreven. Daardoor blijven de bronbytes bewijsbaar intact. Fase 2 gebruikt dit
manifest om uitsluitend bekende padvelden op de doelcomputer te vertalen.

## Thread- en rolloutregels

- Iedere rij in de snapshottabel `threads` moet één item in `threads.json` hebben.
- Een thread met een geldig bron-rolloutpad moet exact één gekopieerde JSONL hebben.
- De eerste JSONL-regel moet geldige JSON van type `session_meta` zijn.
- `payload.id` moet gelijk zijn aan de database-thread-id.
- Een database-thread zonder rollout blokkeert voltooiing.
- Losse rolloutbestanden mogen worden opgenomen, maar worden als orphan gemeld.

## Ontbrekende bijlagen

Een historische lokale bijlage kan al door Windows zijn verwijderd. Dat maakt de
chat zelf niet ongeldig. Elk gevonden pad krijgt daarom status `copied` of
`missing`. Ontbrekende bijlagen leveren een waarschuwing op en worden geteld in
`package.json`; hash-, rollout- en databasefouten blijven blokkerend.

## Projectdetectie

De generator combineert, in deze volgorde:

1. expliciete `projects` uit `backup-config.json`;
2. `project_roots` uit de consistente database-snapshot;
3. `local-projects[*].rootPaths` uit de draagbare globale status.

Thread-`cwd`-waarden worden geïnventariseerd en aan projecten gekoppeld, maar niet
blind als nieuwe projectroot gekopieerd. Dit voorkomt dat een brede map zoals een
heel gebruikersprofiel onbedoeld in de back-up terechtkomt. Ongekoppelde bestaande
cwd's staan als waarschuwing in het rapport en kunnen expliciet aan de configuratie
worden toegevoegd.

## Acceptatiecriteria fase 0 en 1

- De bron wordt nooit gewijzigd.
- Credentials en installatie-identiteit komen niet in het pakket voor.
- Een onderbroken run blijft herkenbaar als `.building-*` en is nooit `complete`.
- `PRAGMA quick_check` van bron en snapshot retourneert `ok`.
- Iedere database-thread heeft een geldige, id-passende rollout.
- Iedere inhoudsfile heeft een SHA-256-hash en bestandsgrootte.
- De onafhankelijke validator controleert schema, hashes, onverwachte bestanden,
  SQLite, threads, projecten en bijlage-inventaris.
- De generator promoveert het pakket alleen na een geslaagde controle.
- Het pakket bevat zijn eigen validator en specificatie.
- Herstel vereist nooit credentials van de broncomputer.
