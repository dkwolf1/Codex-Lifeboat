# Codex Overzetassistent 3.0

Een zelfstandige tweetalige Windows 10/11-app voor:

1. een volledige Codex-back-up naar USB;
2. onafhankelijke controle van die back-up;
3. functioneel 1-op-1 herstel op een andere Windows-pc;
4. controle van het herstelde resultaat.

## Gebruik

### Op de broncomputer

1. Sluit Codex volledig af.
2. Plaats de USB-stick.
3. Start `Codex-Overzetassistent.exe`.
4. Kies **Volledige back-up maken**.
5. Laat daarna **Back-up controleren** uitvoeren.

### Op de nieuwe computer

1. Installeer Codex, open het eenmaal en meld aan.
2. Sluit Codex volledig af.
3. Start `Codex-Overzetassistent.exe` vanaf de USB-stick of vanuit de back-upmap.
4. Kies **Volledig herstellen**.
5. De app maakt eerst een lokale veiligheidskopie en vraagt daarna toestemming.
6. Kies na afloop **Herstel controleren**.

Windows SmartScreen kan bij deze niet-commercieel ondertekende testrelease een
waarschuwing tonen. Controleer eerst de meegeleverde SHA-256 en kies alleen bij
de ongewijzigde release eventueel **Meer informatie** → **Toch uitvoeren**.

## Wat wordt meegenomen

- alle automatisch gevonden projectmappen, inclusief `.git`, `.env` en niet-gecommitte bestanden;
- actieve en gearchiveerde lokale chats;
- project- en threadkoppelingen;
- beschikbare lokale chatbijlagen;
- Codex-configuratie, skills en overige gebruikersgegevens;
- een consistente SQLite-snapshot en SHA-256-hash van ieder pakketbestand.

## Wat lokaal blijft

- `auth.json` en de actieve aanmelding;
- installatie-id en computeridentiteit;
- caches, locks, sandboxgeheimen en actieve runtimebestanden.

Deze gegevens worden op de doelcomputer behouden. Dat voorkomt de fout waarbij
een volledige `.codex`-map van een andere computer de lokale installatie breekt.

## Versies

De app probeert online de geïnstalleerde Microsoft Store-versie te controleren.
Als dat niet lukt, als de computer offline is of als een andere versie wordt
gevonden, verschijnt een waarschuwing. De gebruiker mag daarna doorgaan. De
database-import gebruikt alleen kolommen die bron en doel begrijpen en vult
nieuwe verplichte doelvelden veilig aan. Bij iedere fout volgt automatische rollback.

## Beveiliging

De back-up is bewust niet versleuteld en kan `.env`-bestanden of andere geheimen
bevatten. Bewaar de USB-stick daarom fysiek veilig.

Deze app is een onafhankelijke migratiehulp en geen officieel OpenAI-product.
