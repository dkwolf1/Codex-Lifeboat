# Implementatieroadmap voor universeel heen-en-weer herstellen

[English](../IMPLEMENTATION-ROADMAP.md) · [Goedgekeurde specificatie](ROUND-TRIP-RESTORE-SPEC.md)

Deze roadmap bouwt een veilige overdracht van één volledige Codex-werktoestand
tussen willekeurige Windows 10/11-computers. Een fase start pas nadat de
automatische testpoort van de vorige fase slaagt. Gevaarlijk herstelgedrag blijft
uitgeschakeld totdat alle benodigde fundamenten aantoonbaar werken.

## Fase 0 — Specificatie en veiligheidsgrens

**Status:** Compleet in 3.3.0

- Beheerde inhoud, conflicten, opruimen en begrippen vastleggen.
- Lineaire snapshot-overdracht onderscheiden van gelijktijdige cloudsync.
- Alleen schrijven naar gecontroleerde Codex-data en goedgekeurde projectroots.
- Aanmelding en computeridentiteit van het doel behouden.
- Iedere herstelwijziging automatisch kunnen terugrollen.

**Poort:** Engelse en Nederlandse specificaties bestaan en alle bestaande tests
voor back-up, validatie, herstel, rollback en GUI slagen.

## Fase 1 — Universeel locatiemodel

**Status:** Compleet in 3.3.0

- Profiel- en Known Folder-paden zonder gebruikersnaam beschrijven.
- Externe schijven, USB en UNC-roots registreren zonder stilzwijgend doelpad.
- Universele locaties voor projecten, bijlagen en extra paden vastleggen.
- Pakketformaat 2.1 toevoegen met blijvende ondersteuning voor 2.0.

**Poort:** Tests voor andere gebruikersnamen, omgeleide mappen, profielpaden,
externe roots, UNC, schemavalidatie en formaat 2.0 slagen.

## Fase 2 — Permanente projectidentiteit

**Status:** Compleet in 3.4.0

- Ieder logisch project krijgt een padonafhankelijke UUID.
- Een lokaal register buiten projectmappen bewaren.
- Identiteiten in de back-up meenemen en op het doel installeren.
- Oude padgebaseerde ID's migreren zonder projectbestanden toe te voegen.
- Codex-ID's en Git-metadata alleen als herkenningsbewijs gebruiken.

**Poort:** Dezelfde project-ID blijft bestaan na gebruikersnaam- en padwijziging,
projecten met dezelfde naam blijven verschillend en een volgende back-up hergebruikt de ID.

## Fase 3 — Volledige Codex-inventaris

**Status:** Compleet in 3.4.0

- Recent, projectloze, vastgemaakte en gearchiveerde chats inventariseren.
- Rollouts, indexen, relaties, koppelingen en beschikbare bijlagen meenemen.
- Alle aantoonbaar aan Codex gekoppelde projecten vinden.
- Dubbele, overlappende, geneste, ontbrekende en gekoppelde roots detecteren.
- Eén onafhankelijk gevalideerd inventarismanifest schrijven en pakketformaten
  2.0, 2.1 en 2.2 leesbaar houden.

**Poort:** Iedere testchat en ieder beheerd project staat exact één keer in de
back-up en ieder manifestonderdeel verwijst naar gecontroleerde back-updata.

## Fase 4 — Back-uplijn en wijzigingsgeschiedenis

**Status:** Compleet in 3.4.0

- Back-up-ID, ouder-ID, anonieme computer-ID en onderdeelstatus toevoegen.
- Nieuw, gewijzigd, verwijderd, gelijk en onafhankelijk gewijzigd onderscheiden.
- De route B → A → B als één doorlopende lijn herkennen.
- Anonieme apparaat- en lijnstatus buiten Codex en projectmappen bewaren en bij
  een mislukte restore automatisch terugrollen.

**Poort:** Driewegvergelijking herkent normale opvolging en conflicterende aftakkingen.

## Fase 5 — Project Location Mapper

**Status:** Compleet in 3.4.0

- Universele locaties op de doelcomputer oplossen.
- Externe rootkoppelingen vragen en per computer onthouden.
- Gebruiken, aanmaken, andere map kiezen of overslaan aanbieden.
- Onveilige, ontbrekende, botsende en offline doelen weigeren.
- Bij overslaan veilig stoppen zonder iets te herstellen; selectief herstel per
  project wordt onderdeel van het plan in fase 6.

**Poort:** Geen extern project wordt hersteld voordat het doel expliciet is gecontroleerd.

## Fase 6 — Vergelijkings- en herstelplan

**Status:** Compleet in 3.4.0

- Bron, doel, status, actie, omvang en vrije ruimte tonen.
- Gelijke, inkomende, doel-only, verwijderde en conflicterende data onderscheiden.
- Herstellen blokkeren zolang koppelingen of conflicten openstaan.
- Alleen projecten selecteren die volgens het gecontroleerde plan moeten worden
  aangemaakt of vervangen; gelijke en doel-only projecten blijven ongemoeid.

**Poort:** Het plan voorspelt alle schrijfacties en schrijft zelf niets.

## Fase 7 — Transactioneel exact spiegelen

**Status:** Compleet in 3.4.0

- Elk geselecteerd project naast het uiteindelijke doel op hetzelfde volume opbouwen.
- De volledige bestandsset, byteomvang en alle SHA-256-hashes controleren voordat
  de actieve projectmap verandert.
- Het vorige doel atomair in quarantaine plaatsen en de gecontroleerde spiegel
  activeren; verouderde bestanden verdwijnen door mapvervanging, nooit door overlap.
- Elke transactiestap in het hersteljournaal vastleggen en voltooide wijzigingen
  bij een fout in omgekeerde volgorde terugrollen.
- Gelijke projecten bij herhaling overslaan zonder tijdelijke of dubbele actieve mappen.

**Poort:** Herhalen geeft hetzelfde resultaat; onderbreking maakt geen duplicaten
en laat de oorspronkelijke toestand herstelbaar.

## Fase 8 — Chats spiegelen en conflicten

**Status:** Compleet in 3.4.0

- Recent, vastgemaakt, archief, verwijdering, projectkoppeling, projectloos,
  dynamische tools en chatrelaties spiegelen.
- Eén actief databaserecord en één geldige rollout per chat-ID behouden.
- Doel-only chats en onafhankelijke wijzigingen op beide computers blokkeren tot
  de gebruiker per chat een keuze maakt.
- Back-up, computer, beide, overslaan of annuleren als expliciete keuzes aanbieden.
- Een bewaarde doelkopie een voorspelbaar nieuw chat-ID geven, de rollout-ID
  herschrijven, Recent zonder dubbelen opbouwen en de exacte ID-set controleren.
- Na een geïnjecteerde chatfout de volledige Codex-toestand van vóór herstel terugzetten.

**Poort:** Codex toont exact de verwachte chats zonder dubbelen of teruggekeerde verwijderingen.

## Fase 9 — Projecten en data die alleen op het doel bestaan

**Status:** Compleet in 3.4.0

- Standaard behouden en rapporteren.
- Onafhankelijk gewijzigde projectroots oplossen zonder bestanden stil samen te voegen.
- Bij onafhankelijk gewijzigde projectroots kiezen voor back-up, computer,
  archiveren-en-vervangen, overslaan of annuleren.
- Voor doel-only projecten zichtbaar archiveren of apart bevestigd naar
  herstelquarantaine verplaatsen; projectbytes worden niet vernietigd.
- Database-, global-state- en Lifeboat-identiteitsregistraties volgens de
  gecontroleerde keuze behouden of verwijderen.
- Iedere verplaatsing journaliseren en na een latere fout automatisch terugrollen.

**Poort:** Geslaagd. Behouden, archiveren, herstelbaar verwijderen, registratie-
opschoning en rollback zijn getest; zonder aparte toestemming verdwijnen geen bytes.

## Fase 10 — Bewaarbeleid voor herstelpunten

**Status:** Compleet in 3.4.0

- Geïndexeerde herstelpunten bewaren onder de lokale Lifeboat-datamap, buiten
  actieve Codex-data en gebruikersprojecten.
- Standaard de twee nieuwste onafhankelijk geldige punten bewaren; onvolledige of
  ongeldige punten blijven voor handmatige inspectie staan.
- Alleen oudere gecontroleerde punten en hun exacte gejournaliseerde verborgen
  projectdata verwijderen; zichtbare gebruikersarchieven blijven ongemoeid.
- Gecontroleerde achtergebleven stagingmappen verwijderen en status, schijfgebruik,
  bewaarbeleid en bevestigde handmatige opschoning in de GUI tonen.
- USB-back-uppakketten nooit scannen of automatisch verwijderen.

**Poort:** Geslaagd. Vier geldige testpunten worden tot de twee nieuwste beperkt,
ongeldige data en USB-back-ups blijven staan, staging wordt verwijderd, herhalen is
idempotent en herstel gebruikt de beheerde locatie.

## Fase 10.1 — Back-upinventaris en projectselectie

**Status:** Compleet in 3.4.0

- Voor de back-up ieder gevonden project scannen en huidige locatie, logisch aantal
  bestanden, logische omvang en grootste directe submappen tonen.
- Codex-chats, instellingen en beschikbare bijlagen vergrendeld ingeschakeld houden;
  ieder bestaand project is standaard geselecteerd.
- Het geschatte geselecteerde bestandenaantal en de omvang direct herberekenen bij
  het aan- of uitzetten van een project.
- Bij uitgesloten projectbestanden een tweede expliciete bevestiging vragen en de
  volledige selectie in het back-uprapport vastleggen.
- Chats van een uitgesloten project als projectloze geschiedenis bewaren, terwijl
  de actieve database- en global-state-registraties van dat project niet meegaan.
- Dependency-, cache-, build-, Git-, omgevings- of andere projectmappen nooit stil
  automatisch uitsluiten; de gebruiker beslist op basis van het grootteoverzicht.

**Poort:** Geslaagd. De alleen-lezen inventaris verandert de bron niet, alles start
geselecteerd, totalen reageren op de selectie, een uitgesloten project heeft geen
payload of actieve registratie, de chats blijven aanwezig en onafhankelijke
pakketvalidatie slaagt.

## Fase 11 — Universele Windows-testmatrix

**Status:** Automatische poort compleet in 3.4.0; praktijktests staan open

- Windows 10/11, accounts, OneDrive, stationsletters, USB/UNC, lange en Unicode-paden,
  reparsepunten, geneste roots, weinig ruimte, onderbreking en corruptie testen.
- Losse en gearchiveerde chats, wijzigingen op beide pc's, formaat 2.0 en herhaalde
  heen-en-weer-routes testen.

**Automatische poort:** Broncode, portable EXE en opnieuw uitgepakte release
candidate slagen voor de complete simulatiematrix. De praktijktestpoort blijft open.

De geautomatiseerde matrix met twaalf gesimuleerde tweepc-scenario's en twee
Windows-CI-profielen is actief. Praktijktests op echte Windows 10/11-computers,
USB-verwijdering tijdens schrijven en de release-candidate heen-en-weer-route
staan nog open.
De broncode, verpakte EXE en opnieuw uitgepakte portable ZIP slagen lokaal op
Windows 11 voor alle 75 controles en 12/12 geautomatiseerde scenario's.

## Fase 12 — Publieke release en bewijs voor stabiele release

**Status:** Openbare testrelease voorbereid in 3.4.0

- Engelse hoofddocumentatie en volledige Nederlandse vertaling afronden.
- Ondertekende bestanden waar mogelijk, SHA-256, meldingen, beperkingen en een
  eenvoudige migratiehandleiding publiceren.
- Een Windows-release candidate door meerdere gebruikers laten testen en
  opgeschoonde resultaten verzamelen.

**Poort:** v4.0.0 verschijnt pas met onafhankelijk bewijs van volledige heen-en-weer-herstelbaarheid.

Versie 3.4.0 verschijnt daarom als transparante pre-release met Engelse
hoofddocumentatie, Nederlandse vertaling, SHA-256-bestanden, beveiligingsmelding,
bekende grenzen en een vast formulier voor compatibiliteitsresultaten.

## Fase 13 — Vervolg voor betrouwbaarheid en overdraagbaarheid

### Fase 13.1 — Diagnosecentrum en geanonimiseerd rapport

**Status:** Geïmplementeerd in 3.4.1

- Eén alleen-lezen GUI-actie voor systeemdiagnose toevoegen.
- Windows 10/11, uitgepakte startlocatie, Codex-map en SQLite-integriteit,
  Codex-processtatus, geïnstalleerde versie, verwisselbare opslag, lokale vrije
  ruimte, herstelpunten en lokale Lifeboat-status controleren.
- Geslaagd-, let-op- en foutresultaten in Engels en Nederlands tonen.
- Een gestructureerd JSON-supportrapport kopiëren of opslaan.
- Gebruikers- en computernamen, stationsletters, absolute paden, project- en
  bestandsnamen, chattitels/-inhoud, aanmeldgegevens en omgevingswaarden uitsluiten.
- Zowel onveranderde brongegevens als anonimisering automatisch blijven testen.

**Poort:** De volledige zelftest slaagt, de diagnose verandert het gecontroleerde
profiel niet en bekende synthetische identiteitswaarden komen niet in het rapport voor.

### Fase 13.2 — Schemabewuste audit van overdraagbare paden

**Status:** Geïmplementeerd in 3.4.1

- Padbevattende SQLite- en global-state-velden onderzoeken zonder de bron te wijzigen.
- Bekende vertaalde paden, bewust uitgesloten computerspecifieke status, bekende
  velden met niet-gekoppelde externe paden en onbekende toekomstige velden onderscheiden.
- Het resultaat vóór de back-up en in het diagnosecentrum tonen.
- In iedere back-up een afzonderlijk gehasht `reports/portability-audit.json` opslaan.
- Alleen aantallen, classificaties, redencodes en stabiele vingerafdrukken vastleggen;
  nooit paden, projectnamen, gebruikersidentiteit of chatinhoud.
- Bij benodigde controle waarschuwen en doorgaan; nooit een vertaling gokken of een
  onbekend veld stil verwijderen.
- Bevindingen lokaal uitleggen met echte schemaveldnaam, padsoort, bestaansstatus,
  bewaar-/vertaalgedrag en lage, middelhoge of hoge impact. Volledige paden standaard
  verbergen en lokale details uit gekopieerde of opgeslagen supportrapporten verwijderen.
- De audit tijdens de herstelcontrole opnieuw uitvoeren en bewaarde verwijzingen naar
  een oude bronlocatie apart melden zonder een waarschuwing als corruptie te behandelen.

**Poort:** Geslaagd. Synthetische bekende en toekomstige velden worden correct
geclassificeerd, de scan is alleen-lezen, rapporten bevatten geen echte paden, de
audit wordt in het pakket met hashes gecontroleerd en de volledige broncode-test slaagt.

### Fase 13.3 — Git-bewuste conflictuitleg

**Status:** Geïmplementeerd in 3.4.1

- Beide projectwerkmappen zonder locks of wijzigingen onderzoeken wanneer Git beschikbaar is.
- Dezelfde commit, back-up loopt voor, computer loopt voor, uiteengelopen of niet-
  verwante geschiedenis, lokale wijzigingen en onvoldoende bewijs onderscheiden.
- De uitleg tonen zodra in het herstelplan een project wordt geselecteerd.
- De volledige Lifeboat-bestandshashes leidend houden en alle bestaande expliciete
  conflictkeuzes behouden.
- Nooit mergen, committen, resetten, rebasen, fetchen, pushen of een werkmap wijzigen.

**Poort:** Geslaagd. Synthetische geschiedenis test voortgang, divergentie en lokale
wijzigingen; er lekt geen pad en Git-bewijs verandert nooit een herstelactie.

### Fase 13.4 — Duurzame atomische metadataopslag

**Status:** Geïmplementeerd in 3.4.1

- Kritieke JSON- en checksummetadata via één schrijver in dezelfde map opslaan.
- Het tijdelijke bestand volledig flushen, teruglezen, parseren en eventueel
  valideren, daarna atomisch vervangen en tijdelijke resten bij fouten verwijderen.
- Configuratie, manifesten, rapporten, hersteljournalen, projectidentiteiten,
  back-uplijn/apparaatstatus, externe-rootkoppelingen en checksums afdekken.
- Bij onderbreking vóór vervanging de vorige volledige waarde behouden.

**Poort:** Geslaagd. Een geïnjecteerde vervangingsfout behoudt de oude leesbare
waarde, een nieuwe poging plaatst de volledige nieuwe waarde en laat geen tempbestand achter.

### Fase 13.5 — Strikte prefix-synchronisatie van chats

**Status:** Geïmplementeerd in 3.4.1

- Bron- en doelrollout als genormaliseerde semantische JSONL-records in volgorde
  vergelijken, zonder een van beide bestanden te wijzigen.
- Alleen automatisch doorgaan wanneer een niet-lege doelchat exact de prefix van
  een langere back-upchat is en alle relevante databasemetadata ongewijzigd zijn.
- De bestaande transactionele herstelroute gebruiken om de volledige bewezen
  voortzetting te plaatsen; nooit direct aan een actieve rollout toevoegen.
- Gewijzigde records of metadata, ongeldige data, lege doelen, langere doelchats en
  andere afwijkingen als expliciete conflicten laten staan.
- De veilige uitbreiding en recordaantallen in Engels en Nederlands tonen.

**Poort:** Geslaagd. Semantische paden met andere gebruikersnamen, divergentie,
metadatawijzigingen, ongeldige JSONL, alleen-lezen planning, transactioneel herstel
en herhaald idempotent herstel vallen onder de volledige 75 bron- en pakketcontroles.

Fase 13.6 (optionele back-upversleuteling) blijft afzonderlijk vervolgwerk.
