# Testresultaten 3.0.0

Datum: 22 augustus 2026
Platform: Windows 11 buildomgeving; doelcompatibiliteit Windows 10/11 x64

## Geautomatiseerde systeemtest

Dezelfde test is eerst tegen de broncode en daarna tegen de zelfstandige EXE
uitgevoerd. De EXE-test gebruikte geen externe Python-runtime.

| Controle | Resultaat |
|---|---|
| Geldige pakketopbouw en onafhankelijke validatie | Geslaagd |
| Bronbestanden vóór/na back-up identiek | Geslaagd |
| Bron-`auth.json` niet in back-up | Geslaagd |
| `.git`, `.env` en niet-gecommitte projectbestanden exact | Geslaagd |
| Skills en draagbare Codex-configuratie hersteld | Geslaagd |
| Andere bron- en doelgebruikersnaam automatisch vertaald | Geslaagd |
| Oudere bron naar nieuwer doelschema | Geslaagd |
| Nieuwere bronvelden naar ouder doelschema | Geslaagd |
| Bestaand doelproject veiliggesteld en vervangen | Geslaagd |
| Lokale doelaanmelding ongewijzigd | Geslaagd |
| Beschadigd pakket afgekeurd | Geslaagd |
| Geforceerde fout na database-opbouw | Rollback geslaagd |
| Veiligheidskopie na succesvol herstel bewaard | Geslaagd |
| Vier GUI-functies in Nederlands en Engels | Geslaagd |
| Zelfstandige EXE start zonder directe crash | Geslaagd |

De testfixture bevat één database-thread, actieve rollout, project met `.git` en
`.env`, een skill, een draagbaar configuratiebestand, bestaande doeldata en twee
verschillende doeldatabaseschema's.
