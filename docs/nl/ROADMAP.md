# Roadmap: betrouwbare Codex-back-up en herstel

> Dit is de oorspronkelijke architectuurroadmap. Gebruik voor de actuele status
> de [implementatieroadmap voor fasen 0–13](IMPLEMENTATION-ROADMAP.md).

[Specificatie voor universeel heen-en-weer herstellen](ROUND-TRIP-RESTORE-SPEC.md)

[Implementatieroadmap: fases 0–13](IMPLEMENTATION-ROADMAP.md)

## 1. Doel

Een vaste, herhaalbare werkwijze bouwen waarmee een volledige Codex-werkomgeving veilig van computer A naar computer B kan worden overgezet, zonder de aanmelding, installatie-identiteit of machinegebonden instellingen van computer B te beschadigen.

De oplossing moet:

- projectbestanden, Git-repositories en aanvullende projectdata meenemen;
- lokale Codex-chats, gearchiveerde chats, titels en projectkoppelingen meenemen;
- bestaande chats en projecten op de doelcomputer behouden;
- verschillende Windows-gebruikersnamen en projectpaden ondersteunen;
- verschillende Codex-appversies veilig verwerken;
- onderbreekbaar, hervatbaar en zonder schade opnieuw uitvoerbaar zijn;
- vóór en na iedere bewerking controleerbaar bewijs opleveren;
- een volledige terugrolmogelijkheid bieden.

## 2. Belangrijkste ontwerpbeslissing

De `.codex`-map mag nooit meer als één geheel van computer A naar computer B worden gekopieerd.

De inhoud wordt voortaan gesplitst in twee categorieën.

### Draagbare gegevens

- projectmappen en Git-repositories;
- `sessions` en `archived_sessions`;
- een consistente SQLite-snapshot met threadgegevens;
- `session_index.jsonl`;
- alleen de overdraagbare project- en threadvelden uit `.codex-global-state.json`;
- beschikbare bijlagen waarnaar chats verwijzen;
- optionele skills, instructies en andere expliciet geselecteerde gebruikersbestanden.

### Machinegebonden gegevens

Deze worden nooit vanaf de broncomputer teruggezet:

- `auth.json` en andere aanmeldgegevens;
- `installation_id` en `cap_sid`;
- sandboxmappen, caches en tijdelijke bestanden;
- actieve SQLite `-shm`-bestanden;
- browsercookies, lokale appcache en Windows-packagegegevens;
- machinegebonden processen, locks en runtimebestanden;
- lokale permissie- en accountstatus van de doelcomputer.

Herstel betekent daarom altijd **importeren in een werkende lokale installatie**, nooit een volledige profielvervanging.

## 3. Beoogde pakketindeling

Elke back-up krijgt een zelfstandig, versieerbaar pakket:

```text
Codex-PortableBackup-YYYYMMDD-HHMMSS/
├── manifest/
│   ├── package.json
│   ├── projects.json
│   ├── threads.json
│   ├── path-mappings.json
│   └── sha256.csv
├── projects/
│   ├── project-001/
│   ├── project-002/
│   └── ...
├── codex/
│   ├── state.snapshot.sqlite
│   ├── sessions/
│   ├── archived_sessions/
│   ├── session_index.jsonl
│   └── portable-global-state.json
├── attachments/
├── tools/
│   ├── Backup-Codex.ps1
│   ├── Controleer-CodexBackup.ps1
│   ├── Herstel-Codex.ps1
│   └── Merge-CodexData.py
└── reports/
```

`package.json` bevat minimaal:

- formaat- en scriptversie;
- datum, broncomputer en bronprofiel;
- Codex-appversie en databaseschemaversie;
- lijst met projecten en oorspronkelijke paden;
- aantallen chats, sessiebestanden en bijlagen;
- totale grootte en vrije-ruimtevereiste;
- resultaat van SQLite `quick_check`;
- status `complete` of `incomplete`;
- gebruikte hashmanifesten.

## 4. Standaardwerkwijze

### Back-up maken

1. Start `MAAK-Codex-backup.cmd`.
2. Het programma inventariseert projecten, chats, bijlagen, versies en vrije ruimte.
3. Codex moet volledig worden afgesloten voordat de definitieve snapshot begint.
4. SQLite wordt via de SQLite Backup API naar een consistente snapshot geschreven. Database-, WAL- en SHM-bestanden worden niet blind gekopieerd.
5. Projectbestanden en sessiebestanden worden naar een tijdelijke pakketmap gekopieerd.
6. Voor ieder bestand wordt een SHA-256-hash vastgelegd.
7. De tijdelijke pakketmap krijgt een snelle structuur-, database- en manifestcontrole.
8. Alleen na een geslaagde controle krijgt het pakket `BackupComplete: true` en zijn definitieve naam.
9. Er verschijnt een kort rapport met `GESLAAGD`, aantallen en pakketlocatie.

### Back-up controleren

1. Start `CONTROLEER-Codex-backup.cmd` op de USB-schijf.
2. Alle manifesten, hashes, aantallen en databaseverwijzingen worden gecontroleerd.
3. Iedere thread moet exact één bestaand rolloutbestand hebben.
4. Iedere rollout moet geldige JSON-metadata en de juiste thread-id bevatten.
5. SQLite `quick_check` moet `ok` retourneren.
6. De controle wijzigt niets.

### Herstellen op een andere computer

1. Installeer en open Codex eenmaal op de doelcomputer.
2. Meld aan en maak eventueel één testchat.
3. Sluit Codex volledig.
4. Start `CONTROLEER-Codex-herstel.cmd`.
5. Kies of bevestig nieuwe projectpaden; gebruikersprofielpaden worden automatisch voorgesteld.
6. Start `HERSTEL-Codex.cmd`.
7. Maak eerst een consistente terugrolkopie van de huidige database en UI-status.
8. Kopieer project- en sessiebestanden zonder afwijkende bestaande bestanden te overschrijven.
9. Importeer ontbrekende threads transactief in de huidige databaseschema-versie.
10. Voeg projecten en projectroots toe en koppel threads op basis van expliciete metadata en `cwd`.
11. Vertaal alleen padvelden; chatinhoud blijft ongewijzigd.
12. Voeg de overdraagbare delen van de UI-status samen.
13. Voer de volledige eindcontrole uit.
14. Start Codex pas opnieuw nadat het rapport `GESLAAGD` meldt.

## 5. Roadmap per fase

### Fase 0 — Specificatie en nulmeting

Doel: het back-upformaat en alle grenzen formeel vastleggen.

Werk:

- draagbare en machinegebonden Codex-bestanden classificeren;
- huidige SQLite-tabellen en relevante kolommen documenteren;
- projectdetectie baseren op `projects`, `project_roots`, thread-`cwd` en globale projectstatus;
- padmapping als expliciet onderdeel van het manifest ontwerpen;
- regels vastleggen voor ontbrekende historische bijlagen;
- pakketversie `2.0` definiëren.

Acceptatie:

- ieder opgenomen bestand heeft een reden;
- ieder uitgesloten bestand heeft een veiligheidsreden;
- herstellen vereist nooit broncomputercredentials.

### Fase 1 — Back-upgenerator 2.0

Doel: met één starter een consistente, zelfcontrolerende back-up maken.

Werk:

- automatische projectinventarisatie;
- aanvullende mappen via een configuratiebestand;
- veilige Codex-procescontrole;
- consistente SQLite Backup API-snapshot;
- export van overdraagbare globale status;
- sessie- en attachment-inventarisatie;
- SHA-256-manifest;
- tijdelijke opbouw en atomische voltooiing;
- duidelijke voortgang, rapporten en foutlogs.

Acceptatie:

- een onderbroken back-up krijgt nooit status `complete`;
- de bronbestanden worden niet gewijzigd;
- een voltooide back-up slaagt direct voor de structuurcontrole;
- **Back-up controleren** kan ieder payloadbestand daarna onafhankelijk herlezen
  en via SHA-256 controleren.

### Fase 2 — Herstel/importeur 2.0

Doel: veilig importeren in een bestaande, werkende Codex-installatie.

Werk:

- interactieve of configureerbare padmapping;
- vrije-ruimte- en versiecontrole;
- controle op afwijkende bestaande projectbestanden;
- transactieve, schema-bewuste SQLite-merge;
- idempotente thread-, project- en sessie-import;
- importjournal met statussen per stap;
- hervatten vanaf de laatste volledig afgeronde stap;
- consistente rollbackdatabase;
- geen Python via `python -c`; altijd een echt `.py`-helperbestand;
- eindrapport met aantallen en ontbrekende verwijzingen.

Acceptatie:

- tweemaal uitvoeren veroorzaakt geen duplicaten;
- bestaande chats blijven behouden;
- authenticatie en installatie-identiteit blijven behouden;
- iedere database-thread heeft een bestaand rolloutbestand;
- alle vier projectgroepen zijn zichtbaar en te openen;
- afbreken op ieder testpunt laat een hervatbare toestand achter.

### Fase 3 — Geautomatiseerde testmatrix

Doel: “werkt op mijn computer” vervangen door aantoonbare compatibiliteit.

Minimale tests:

| Scenario | Verwacht resultaat |
|---|---|
| Zelfde computer, lege installatie | Volledige import |
| Andere Windows-gebruikersnaam | Alle profielpaden vertaald |
| Andere projectschijf of hoofdmap | Mapping correct toegepast |
| Nieuwere Codex-versie op doelcomputer | Import in het nieuwe schema |
| Bestaande chats op doelcomputer | Behouden en samengevoegd |
| Herstel tweemaal uitvoeren | Geen duplicaten |
| Stroomonderbreking na projectkopie | Hervatten bij database-import |
| Onderbreking tijdens database-import | Transactierollback |
| Beschadigd sessiebestand | Vooraf blokkeren met duidelijke melding |
| Ontbrekende historische bijlage | Waarschuwing, chats blijven bruikbaar |
| Afwijkend bestaand projectbestand | Niet overschrijven; menselijke keuze vereist |
| Onvoldoende schijfruimte | Stoppen vóór wijzigingen |

Acceptatie:

- alle tests draaien tegen een wegwerpomgeving;
- iedere release van de scripts doorloopt dezelfde tests;
- testresultaten worden als JSON en leesbaar rapport opgeslagen.

### Fase 4 — Gebruiksgemak

Doel: de handeling geschikt maken voor normaal dagelijks gebruik.

Oplevering:

- `MAAK-Codex-backup.cmd`;
- `CONTROLEER-Codex-backup.cmd`;
- `HERSTEL-Codex.cmd`;
- `HERVAT-Codex-herstel.cmd`;
- `CONTROLEER-Codex-herstel.cmd`;
- één configuratiebestand voor extra projectmappen;
- één Nederlandstalige handleiding;
- vaste foutloglocatie;
- afsluitende samenvatting: projecten, chats, bestanden, hashes en waarschuwingen.

Acceptatie:

- de normale gebruiker hoeft geen PowerShell-commando te typen;
- iedere foutmelding noemt de stap, oorzaak en concrete vervolgactie;
- de gebruiker hoeft nooit `.codex`-mappen handmatig te hernoemen of verwijderen.

### Fase 5 — Codex-skill en beheer

Doel: de procedure duurzaam en vindbaar maken.

Werk:

- na stabilisatie een persoonlijke `codex-backup-herstel`-skill maken;
- de skill laat Codex eerst inventariseren en daarna uitsluitend de geteste tools gebruiken;
- versienummering en changelog toevoegen;
- elk kwartaal een proefherstel naar een lege testmap uitvoeren;
- oude back-ups volgens een retentiebeleid verwijderen;
- minimaal twee back-ups bewaren op verschillende fysieke locaties.

De officiële OpenAI-workflows noemen zowel herhaalbare skills als geverifieerde operaties als geschikte patronen voor terugkerende werkprocessen: https://learn.chatgpt.com/use-cases

## 6. Veiligheidsregels

1. Nooit herstellen terwijl Codex draait.
2. Nooit de volledige `.codex`-map van een andere computer over de lokale map kopiëren.
3. Nooit `auth.json`, installatie-id's of caches migreren.
4. Nooit een actieve SQLite-database alleen als los `.sqlite`-bestand kopiëren.
5. Nooit bestaande afwijkende projectbestanden stil overschrijven.
6. Nooit doorgaan na een mislukte hash- of databasecontrole.
7. Nooit een back-up `complete` noemen vóór de onafhankelijke eindcontrole.
8. Nooit een veiligheidskopie verwijderen voordat Codex meerdere keren correct is gestart.

## 7. Definition of Done

De oplossing is pas definitief wanneer:

- back-up, controle, herstel en hervatten afzonderlijke commando's zijn;
- de back-up een versieerbaar en gedocumenteerd formaat heeft;
- alle bestanden een hash hebben;
- SQLite-snapshots consistent zijn;
- herstel idempotent en transactief is;
- bron- en doelgebruikersnaam mogen verschillen;
- bestaande doelcomputerdata behouden blijft;
- rollback aantoonbaar werkt;
- alle testmatrixscenario's slagen;
- een niet-technische gebruiker alleen de `.cmd`-starters nodig heeft;
- een proefherstelrapport alle verwachte chats en projecten bevestigt.

## 8. Aanbevolen uitvoeringsvolgorde

1. Fase 0 afronden en pakketformaat 2.0 bevriezen.
2. Back-upgenerator en onafhankelijke validator bouwen.
3. Eerst testfixtures en foutinjectietests toevoegen.
4. Herstel/importeur bouwen op basis van de bewezen merge-aanpak.
5. Hervatten en rollback testen door geforceerde onderbrekingen.
6. Eén volledige migratie van hoofdcomputer naar laptop uitvoeren.
7. Pas daarna de eenvoudige starters en persoonlijke Codex-skill publiceren.

De eerstvolgende concrete oplevering hoort dus **Back-upgenerator 2.0 + onafhankelijke validator** te zijn. Een hersteltool is alleen betrouwbaar wanneer het bronpakket vooraf aantoonbaar consistent is.
