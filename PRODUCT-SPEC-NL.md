# Productspecificatie 3.0

## Ondersteund

- Windows 10 en Windows 11, 64-bit;
- lokale Codex/ChatGPT-desktopinstallatie;
- verschillende Windows-gebruikersnamen en bekende-maplocaties;
- herstel van ouder naar nieuwer én nieuwer naar ouder schema op basis van
  gemeenschappelijke SQLite-kolommen;
- offline uitvoering met waarschuwing wanneer versiecontrole niet mogelijk is;
- online best-effortcontrole via Microsoft Store/winget;
- Nederlands en Engels;
- uitvoering zonder administratorrechten, Python of installatieprogramma.

## Gebruikersbelofte

Na een geslaagde eindcontrole bevat de doelcomputer dezelfde meegenomen
projectbytes, chats, archieven, projectkoppelingen, beschikbare bijlagen, skills
en draagbare instellingen als de broncomputer. Paden worden naar het nieuwe
Windows-profiel vertaald. Aanmelding en computeridentiteit blijven van het doel.

## Vier operaties

1. Back-up: consistente snapshot, volledige projectkopie en SHA-256-manifest.
2. Back-upcontrole: read-only controle van hashes, SQLite, threads en projecten.
3. Herstel: eerst veiligheidskopie en toestemming, daarna vervanging met rollback.
4. Herstelcontrole: SQLite, thread-rollouts en projectbytes/hashes controleren.

## Foutgedrag

- Een onderbroken back-up blijft `.building-*` en wordt nooit compleet genoemd.
- Een beschadigde back-up wordt vóór herstel geweigerd.
- Een niet-schoon doel wordt eerst veiliggesteld en expliciet gemeld.
- Iedere fout tijdens herstel activeert automatische rollback.
- Een veiligheidskopie wordt na succes niet automatisch verwijderd.
