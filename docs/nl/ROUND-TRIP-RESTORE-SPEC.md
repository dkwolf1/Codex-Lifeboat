# Specificatie voor universeel heen-en-weer herstellen

[English](../ROUND-TRIP-RESTORE-SPEC.md)

## Doel

Codex Lifeboat moet een lineaire overdracht tussen willekeurige Windows
10/11-computers ondersteunen: computer B back-uppen, verder werken op computer
A en daarna de nieuwere toestand terugbrengen naar B zonder handmatig
verwijderen, dubbele gegevens, restbestanden of afhankelijkheid van
gebruikersnamen, stationsletters en mapindelingen.

Dit is gecontroleerde snapshot-overdracht, geen gelijktijdige cloudsync.

## Beheerde inhoud

Lifeboat neemt automatisch gegevens mee die aantoonbaar bij Codex horen:

- iedere chat uit de database, inclusief Recent, projectloze, vastgemaakte en
  gearchiveerde chats;
- sessierollouts, indexen, projectkoppelingen, relaties en beschikbare
  gekoppelde bijlagen;
- overdraagbare instellingen, skills en instructies;
- projecten die in Codex staan, door een chat worden gebruikt, als werkmap zijn
  gebruikt of handmatig zijn toegevoegd;
- alle bytes binnen beheerde projecten, waaronder `.git`, `.env`, verborgen
  bestanden en niet-gecommitte werk.

Lifeboat doorzoekt geen volledige schijven naar niet aan Codex gekoppelde
projecten.

## Locatieregels

- Windows Known Folders en profielrelatieve paden worden logisch opgeslagen,
  zonder afhankelijkheid van de gebruikersnaam op het doel.
- Externe, verwisselbare en netwerklocaties vereisen een expliciete koppeling
  voordat exact spiegelen ze mag wijzigen.
- Een ontbrekende externe root wordt nooit stilzwijgend naar een herstelmap
  omgeleid.
- De identiteit van een project mag niet van het huidige pad afhangen. Een
  latere fase introduceert permanente project-ID's.
- Interne Codex-paden mogen worden vertaald; projectbestanden blijven exact.

## Herstelregels

- Op een bestaande doelcomputer hoeft Codex niet opnieuw te worden geïnstalleerd
  of aangemeld. Codex moet alleen volledig worden afgesloten.
- Aanmelding en computeridentiteit blijven van de doelcomputer.
- Voor iedere schrijfactie verschijnt een volledig vergelijkings- en herstelplan.
- Beheerde projectroots worden als geheel gespiegeld en nooit bestand voor
  bestand over bestaande mappen gelegd.
- Bestaande doelen worden vóór vervanging veiliggesteld en gecontroleerd.
- Iedere fout activeert automatische rollback.
- Dezelfde back-up opnieuw herstellen geeft dezelfde actieve toestand zonder
  duplicaten.

## Conflicten en gegevens die alleen op het doel bestaan

- Wijzigingen op beide computers blokkeren automatisch herstel en vereisen een
  expliciete keuze per onderdeel.
- Projecten die alleen op het doel bestaan blijven standaard bewaard en worden
  gemeld. De gebruiker kan ze archiveren of expliciet verwijderen.
- Verwijderde en gearchiveerde chatstatus reist met de actieve back-uplijn mee.
- Een nieuwe chat die alleen op het doel bestaat is een conflict en wordt niet
  stilzwijgend verwijderd.
- Lifeboat voegt inhoud nooit automatisch samen.

## Opruimen en herstelpunten

- Actieve Codex-gegevens krijgen geen gegenereerde `-old`, `-backup`, `mislukt`
  of dubbele herstelmappen.
- Tijdelijke staginggegevens verdwijnen na gecontroleerde voltooiing.
- Herstelpunten staan buiten actieve Codex-data in één beheerde locatie.
- Het toekomstige standaardbeleid bewaart de twee nieuwste geldige
  herstelpunten en verwijdert nooit automatisch het nieuwste bruikbare punt.
- Back-uppakketten op USB worden nooit automatisch verwijderd.

## Veiligheidsgrens

Lifeboat mag alleen paden verwijderen of vervangen die in het gecontroleerde
herstelplan staan en aantoonbaar onder goedgekeurde beheerde roots vallen. Het
programma mag nooit een volledig profiel, station, netwerkshare of willekeurige
map scannen en opschonen.

## Huidige afbakening van 3.4.3

Release 3.4.3 bevat fasen 0–10.1 en betrouwbaarheidsfasen 13.1–13.5: draagbare
paden, permanente projectidentiteit, volledige lokale inventaris, back-uplijn,
gecontroleerde locatiekoppeling, alleen-lezen vergelijking, transactionele
projectspiegels, expliciete conflictkeuzes, diagnose, padaudit, Git-bewuste uitleg,
atomische metadata en strikte prefix-chatuitbreiding. De automatische fase-11-
matrix slaagt voor broncode, EXE en uitgepakte ZIP; praktijkbewijs en de stabiele-
releasepoort staan nog open.
