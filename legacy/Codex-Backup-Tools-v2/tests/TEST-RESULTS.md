# Fase 1 — testresultaten

Datum: 22 augustus 2026
Platform: Windows, Windows PowerShell 5.1, Python 3.14

De generator is end-to-end uitgevoerd tegen een wegwerp-Codexprofiel met één
project, één SQLite-thread en één rolloutbestand.

| Test | Resultaat |
|---|---|
| Python-helpers compileren | Geslaagd |
| Beide PowerShell-scripts parseren in Windows PowerShell 5.1 | Geslaagd |
| Consistente SQLite Backup API-snapshot | Geslaagd, `quick_check=ok` |
| Automatische projectdetectie uit database en globale status | Geslaagd |
| Generator → onafhankelijke voorcontrole → definitieve controle | Geslaagd |
| Geldig proefpakket opnieuw los controleren | Geslaagd |
| Projectbestand na voltooiing wijzigen | Correct afgekeurd op grootte én projecttotaal |
| Rolloutbestand uit de bron laten ontbreken | Generator stopt; alleen `.building-*`, niet complete |
| Hashes van alle bronbestanden vóór/na een volledige run vergelijken | 0 gewijzigd, 0 toegevoegd |

Proefpakket: 1 thread, 1 project, 2 projectbestanden en 22 gehashte
pakketbestanden. De foutinjectietest retourneerde exitcode 1 zoals vereist.
