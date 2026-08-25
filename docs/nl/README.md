# Codex Lifeboat

**Codex met één programma back-uppen, herstellen en overzetten naar een andere Windows-pc.**

[English](../../README.md) · [Beveiliging](../../SECURITY.md) · [Documentatie](IMPLEMENTATION-ROADMAP.md)

> **Openbare testrelease:** versie 3.4.2 is een bèta/release candidate. De
> geautomatiseerde bron-, EXE- en ZIP-tests slagen, maar praktijkresultaten van
> Windows 10 en echte overdrachten tussen meerdere computers worden nog verzameld.
> Bewaar onvervangbare gegevens ook apart en lees de [testhandleiding](TESTHANDLEIDING.md).

## Downloaden voor Windows

### [Download Codex Lifeboat 3.4.2](https://github.com/dkwolf1/Codex-Lifeboat/releases/tag/v3.4.2)

Download op de releasepagina uitsluitend dit bestand:

```text
Codex-Lifeboat-Windows-x64-Portable.zip
```

Pak de ZIP uit en start `Codex-Lifeboat.exe`. Installatie, Python en
administratorrechten zijn niet nodig. Windows 10/11 x64 wordt ondersteund.

> Download niet de automatisch door GitHub gemaakte bestanden **Source code
> (zip)** of **Source code (tar.gz)**. Die zijn alleen voor ontwikkelaars.

Windows SmartScreen kan waarschuwen omdat deze communitybuild niet commercieel
is ondertekend. Controleer voor gebruik het meegeleverde `SHA256.txt`.

## Back-up maken

1. Sluit Codex volledig af.
2. Plaats de USB-stick.
3. Start `Codex-Lifeboat.exe`.
4. Kies **Volledige back-up maken**.
5. Controleer de inventaris. Alles staat standaard aan; sluit een project alleen uit
   als de bestanden niet vanuit deze back-up hersteld hoeven te kunnen worden.
6. Kies daarna **Back-up controleren**.

Bij het aanmaken wordt iedere payload eenmaal gelezen om de SHA-256 vast te leggen,
gevolgd door snelle controles van database, manifesten, paden, omvang en back-uplijn.
**Back-up controleren** is de aparte volledige onafhankelijke herlezing, zodat het
langzaamste leeswerk niet direct dubbel wordt uitgevoerd.

## Herstellen op een nieuwe computer

1. Installeer Codex, open het eenmaal en meld je aan.
2. Sluit Codex volledig af.
3. Start `Codex-Lifeboat.exe` vanaf de USB-stick.
4. Kies **Volledig herstellen**.
5. Controleer desgevraagd de locaties van externe projecten.
6. Controleer het volledige vergelijkingsplan. Los ieder chat- of projectconflict
   op en controleer doel-only projecten; die blijven behouden tenzij u ze expliciet
   archiveert of naar herstelquarantaine verwijdert.
7. Controleer de locatie van de veiligheidskopie en bevestig.
8. Kies daarna **Herstel controleren**.

Een chat wordt alleen automatisch uitgebreid als de volledige lokale geschiedenis
aantoonbaar een ongewijzigde prefix van de langere back-upchat is. Ieder ander
verschil blijft een expliciet conflict met een gebruikerskeuze.

Gebruik **Herstelpunten beheren** om lokale herstelopslag te bekijken of alleen
oudere gecontroleerde punten veilig op te ruimen. De twee nieuwste geldige punten,
onvolledig bewijs, zichtbare projectarchieven en alle USB-back-ups blijven staan.

Herstelpunten worden op de doelcomputer gemaakt vlak vóór een herstelactie. Het
zijn lokale terugrolkopieën en geen gewone USB-back-ups. De lijst blijft daarom
leeg totdat op deze computer een back-up is teruggezet.

## Wat wordt meegenomen

- Projectmappen, inclusief `.git`, `.env` en niet-gecommitte bestanden
- Actieve en gearchiveerde lokale chats
- Project- en chatkoppelingen en beschikbare lokale bijlagen
- Skills en overdraagbare Codex-instellingen
- Een consistente SQLite-snapshot en SHA-256-controle
- Een alleen-lezen vergelijkingsplan met conflicten, acties en vrije-ruimtecontrole
- Per chat kiezen voor back-up, deze computer, beide, overslaan of annuleren
- Doel-only projecten standaard behouden, met expliciet archiveren of herstelbaar verwijderen
- Per project kiezen voor back-up, computer, archiveren-en-vervangen, overslaan of annuleren
- Transactionele, met hashes gecontroleerde projectvervanging zonder oude restbestanden
- Een veiligheidskopie en automatische rollback bij fouten
- Een visueel resultaat dat toont wat beschermd en gecontroleerd is
- Een inventaris vóór de back-up met locatie, bestandenaantal, omvang en grootste
  mappen per project; alle projecten zijn standaard geselecteerd
- Optioneel een heel project uitsluiten terwijl chats en Codex-instellingen meegaan
- Beheerde herstelpunten met schijfgebruik en behoud van twee geldige punten
- Een alleen-lezen diagnosecentrum met duidelijke geslaagd-, let-op- en foutstatus
- Een geanonimiseerd JSON-supportrapport zonder namen, paden, projectgegevens,
  chatinhoud, aanmeldgegevens of omgevingswaarden
- Een schemabewuste overdraagbaarheidsaudit die vertaalde paden, bewust uitgesloten
  computerstatus, niet-gekoppelde externe paden en nieuwe Codex-velden onderscheidt
- Een lokaal detailscherm met veldnaam, padsoort, bestaansstatus, verwerking,
  vertaalstatus en verwachte impact; volledige paden verschijnen alleen op verzoek
- Git-bewuste uitleg bij projectconflicten voor gelijke commits, voortgang,
  uiteengelopen geschiedenis en lokale wijzigingen, zonder Git te veranderen
- Duurzame atomische opslag voor manifesten, rapporten, registers, koppelingen,
  instellingen, back-uplijnen, apparaatstatus en hersteljournalen
- Strikte prefix-synchronisatie voor chats: alleen wanneer alle bestaande lokale
  chatrecords en metadata exact het begin van een langere back-upchat vormen,
  wordt de aantoonbaar nieuwe voortzetting automatisch overgenomen
- Begrensde analyse van zeer grote rollouts en honderden historische
  bijlageverwijzingen, zonder de betekenis van draagbare vingerafdrukken te wijzigen

De aanmelding, installatie-id, computeridentiteit, caches, locks en
sandboxgeheimen van de broncomputer worden bewust niet teruggezet.

Gebruik **Systeemcontrole en diagnose** wanneer de voorbereiding van een back-up
of herstelactie onduidelijk is. De functie controleert zonder wijzigingen onder
andere Windows, toegang tot Codex-gegevens, de SQLite-database, een nog draaiende
Codex-app, versiedetectie, verwisselbare opslag, vrije ruimte en herstelpunten.
Met **Rapport kopiëren** of **Rapport opslaan** deelt u een geanonimiseerd
JSON-resultaat met een tester of GitHub-issue.

Het projectkeuzescherm toont vóór de back-up ook het resultaat van de padaudit.
**Details bekijken** legt per groep uit wat het lokale veld is, of de locatie nog
bestaat, of de gegevens worden meegenomen, of het pad wordt vertaald en wat de
mogelijke impact is. Onbekende verwijzingen worden ongewijzigd bewaard: een
let-opmelding laat dus geen databasegegevens weg en blokkeert back-up of herstel
niet. Wel kan een bewaarde koppeling na herstel nog naar de oude locatie wijzen.
**Herstel controleren** meldt resterende oude bronverwijzingen afzonderlijk.

Echte veldnamen en optioneel volledige paden zijn alleen lokaal zichtbaar. Iedere
back-up bevat een afzonderlijk gehasht `reports/portability-audit.json`; gekopieerde
en opgeslagen diagnoserapporten bevatten alleen aantallen, classificaties,
redencodes en vingerafdrukken van onbekende schemavelden—nooit echte paden,
projectnamen of gebruikersidentiteit.

## Beveiliging

Back-ups zijn niet versleuteld en kunnen broncode, `.env`-bestanden, API-sleutels
en andere vertrouwelijke projectgegevens bevatten. Bewaar de USB-stick veilig.

Codex Lifeboat is een onafhankelijk communityproject en geen officieel OpenAI-product.

De broncode, verpakte EXE en opnieuw uitgepakte ZIP slagen voor 75/75 controles
en 12/12 geautomatiseerde Windows-scenario's.
Praktijktests staan in de [fase-11-matrix](../PHASE-11-TEST-MATRIX.md).

Ontwikkelaars vinden de publicatiestappen in de
[releasechecklist](RELEASE-CHECKLIST.md).
