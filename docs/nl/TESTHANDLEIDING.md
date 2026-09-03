# Compatibiliteitstesthandleiding voor Codex Lifeboat 3.4.4

[English](../TESTING-GUIDE.md)

Versie 3.4.4 is stabiel na geautomatiseerde tests en een geslaagde echte Windows 11-
route tussen twee computers. Verdere gebruikerstests voegen dekking toe voor
Windows 10, andere hardware, USB-onderbreking en meer computercombinaties.

## Voor het testen

- Bewaar ieder onvervangbaar project ook onafhankelijk op een andere plek.
- Begin waar mogelijk met niet-kritieke of tijdelijke testgegevens.
- Publiceer nooit een back-uppakket: dit kan broncode, `.env`-bestanden,
  API-sleutels, Git-geschiedenis en chatinhoud bevatten.
- Download `Codex-Lifeboat-Windows-x64-Portable.zip`, pak het volledig uit en
  controleer `SHA256.txt`.
- Sluit Codex volledig vóór iedere back-up-, herstel- of controlehandeling.

## Aanbevolen test met twee computers

1. Noteer op computer A de Windows-versie, gebruikersnaam, Codex-versie,
   projectlocaties, het aantal chats en eventuele OneDrive-omleiding.
2. Maak en controleer een back-up.
3. Installeer Codex op computer B, open het eenmaal, meld aan en sluit het volledig.
4. Herstel de back-up, controleer alle voorgestelde paden en conflictkeuzes en voer
   **Herstel controleren** uit.
5. Open Codex en controleer recente, gearchiveerde, vastgemaakte, projectgebonden
   en projectloze chats en de geselecteerde projectbestanden.
6. Maak op computer B een kleine herkenbare wijziging in een project en chat.
7. Maak en controleer een back-up van computer B.
8. Ga terug naar computer A, controleer het vergelijkingsplan zorgvuldig, herstel,
   verifieer en controleer dat geen dubbele chats, projecten of oude bestanden bestaan.
9. Open **Herstelpunten beheren**. Het lokale punt van vóór herstel moet zichtbaar
   zijn; USB-back-ups horen niet in deze lijst.

## Extra nuttige scenario's

- Verschillende Windows-gebruikersnamen op A en B.
- Windows 10 naar Windows 11 en andersom.
- OneDrive-omleiding van Documenten of Bureaublad.
- Projecten onder `C:\git`, een ander station, USB of een UNC-netwerkpad.
- Chats en projecten die alleen op de doelcomputer bestaan.
- Hetzelfde project onafhankelijk op beide computers gewijzigd.
- Een project bewust uitsluiten in de back-upinventaris.

## Resultaat melden

Gebruik op GitHub het formulier **Compatibility test result**. Zowel successen
als fouten zijn waardevol. Vermeld versie, beide Windows-versies, opslagtype,
afwijkende gebruikersnamen/paden, de geslaagde handelingen en een exacte maar
opgeschoonde foutmelding.

Verwijder gebruikersnamen, projectnamen, chatinhoud, sleutels, tokens en privépaden
uit schermafbeeldingen en logs. Voeg nooit een echte back-up, `auth.json`, `.env`,
SQLite-database, herstelpunt of projectarchief toe.
