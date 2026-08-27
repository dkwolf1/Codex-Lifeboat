# Productspecificatie 3.4

[English](../PRODUCT-SPEC.md)

## Ondersteunde omgeving

- Windows 10 en Windows 11, x64.
- Lokale Codex-desktopinstallatie.
- Verschillende Windows-gebruikersnamen, omgeleide bekende mappen, stationsletters,
  externe schijven, USB-doelen en expliciet gekoppelde UNC-roots.
- Offline gebruik met waarschuwing als online versiecontrole niet beschikbaar is.
- Engels als hoofdtaal met volledige Nederlandse vertaling.
- Gebruik zonder administratorrechten, Python of installatieprogramma.

Versie 3.4.2 is een openbare bèta/release candidate totdat de resterende fysieke
fase-11-tests zijn afgerond.

## Gebruikersbelofte

Na een geslaagde eindcontrole bevat de doelcomputer de geselecteerde projectbytes,
lokale chats, archieven, projectkoppelingen, beschikbare bijlagen, skills en draagbare
instellingen uit het bronpakket. Draagbare paden worden naar de doelcomputer vertaald.
Aanmelding en computeridentiteit van het doel blijven ongewijzigd. Conflicterende of
doel-only gegevens worden nooit stil overschreven.

## Handelingen

1. **Back-up maken:** alleen-lezen inventaris, expliciete projectselectie,
   consistente snapshot, volledige kopie, SHA-256-manifest en snelle structuurcontrole.
2. **Back-up controleren:** alleen-lezen pakket-, hash-, SQLite-, inventaris- en lijncontrole.
3. **Back-up herstellen:** locatiekoppeling, vergelijkingsplan, conflictkeuzes,
   herstelpunt vooraf, transactionele vervanging en automatische rollback.
4. **Herstel controleren:** exacte controle van database, chats, projecten en keuzes.
5. **Herstelpunten beheren:** lokale terugrolopslag bekijken en alleen oudere,
   onafhankelijk geldige punten volgens het bewaarbeleid verwijderen.

## Inhoud van de back-up

Draagbare gegevens omvatten geselecteerde complete projectmappen, recente en
gearchiveerde rollouts, een consistente SQLite-snapshot, draagbare globale status,
beschikbare bijlagen, skills, instructies en draagbare gebruikersconfiguratie.

Aanmelding, installatie-ID's, computeridentiteit, sandboxes, caches, gedownloade
plugin-runtimes, tijdelijke bestanden, locks, actieve SQLite-sidecars en
runtimegegevens worden uitgesloten. Plugininstellingen en eigen skills blijven
overdraagbaar.

## Conflict- en opschoningsmodel

- De vergelijking is alleen-lezen en voorspelt alle schrijfacties.
- Chatconflicten vereisen back-up, computer, beide, overslaan of annuleren.
- Projectconflicten vereisen back-up, computer, archiveren-en-vervangen, overslaan of annuleren.
- Doel-only projecten blijven staan tenzij de gebruiker ze expliciet archiveert
  of naar herstelquarantaine verplaatst.
- Beheerde projecten worden vóór atomische activering opgebouwd en met hashes gecontroleerd.
- Opschoning blijft voorzichtig: USB-back-ups, zichtbare archieven, onvolledig bewijs
  en de twee nieuwste geldige lokale punten worden niet automatisch verwijderd.

## Gedrag bij fouten

- Een onderbroken back-up blijft `.building-*` en wordt nooit compleet genoemd.
- Een beschadigde back-up wordt vóór wijzigingen geweigerd.
- Onvoldoende ruimte en onopgeloste paden of conflicten blokkeren schrijven.
- Herstelwijzigingen worden gejournaliseerd en bij fouten omgekeerd teruggerold.
- Een geslaagd herstel bewaart het beheerde herstelpunt van vóór die actie.

## Definitie van een stabiele release

De bron-, verpakte-EXE- en portable-ZIP-matrices moeten slagen; echte Windows
10/11- en A-naar-B-naar-A-tests leveren opgeschoond bewijs; er blijft geen kritisch
veiligheidsprobleem open; Engelse en Nederlandse documentatie, hashes, licentie,
notices, beperkingen en beveiligingsmelding worden samen gepubliceerd.
