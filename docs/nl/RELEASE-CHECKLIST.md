# Releasechecklist

[English](../RELEASE-CHECKLIST.md)

Deze checklist publiceert Codex Lifeboat 3.4.3 als **pre-release voor openbare
tests**. De tag-workflow bouwt en controleert nieuwe releasebestanden, maakt de
checksums en herkomstverklaringen en publiceert de GitHub-release.

## Vóór het pushen

- Controleer dat `git status --short` alleen bedoelde 3.4.3-wijzigingen bevat.
- Stage geen echte back-up, database, token, `.env`, EXE, ZIP of bouwmap.
- De lokale map `dist` hoort niet in Git en wordt bewust genegeerd.
- Maak tag `v3.4.3` pas nadat de CI-run van `main` groen is.

## Publiceren met PowerShell

Voer in de repositorymap uit:

```powershell
git add -A
git status --short
git diff --cached --check
git commit -m "Prepare Codex Lifeboat 3.4.3 public testing release"
git push origin main
```

Wacht tot de `main`-CI groen is op
<https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/ci.yml>. Voer dan uit:

```powershell
git tag -a v3.4.3 -m "Codex Lifeboat 3.4.3 public testing release"
git push origin v3.4.3
```

De tag start `.github/workflows/release.yml`. Maak niet daarnaast handmatig een
release met dezelfde tag: de workflow maakt deze en markeert hem als pre-release.
Volg de uitvoering op
<https://github.com/dkwolf1/Codex-Lifeboat/actions/workflows/release.yml> en open
daarna <https://github.com/dkwolf1/Codex-Lifeboat/releases/tag/v3.4.3>.

## Gepubliceerde release controleren

Naast GitHubs automatische bronarchieven moeten precies deze drie
projectbestanden aanwezig zijn:

- `Codex-Lifeboat.exe`
- `Codex-Lifeboat-Windows-x64-Portable.zip`
- `SHA256.txt`

Controleer dat de workflow groen is, de release **Pre-release** vermeldt, de
Engelse releasetekst zichtbaar is en de ZIP ook de licentie, het beveiligingsbeleid,
de testhandleidingen, releaseteksten, notices en bekende beperkingen bevat. Gebruik
de `SHA256.txt` van de releaseworkflow; lokaal gebouwde bestanden kunnen andere
hashes hebben.

Controleer na downloaden eventueel de GitHub-herkomstverklaring:

```powershell
gh attestation verify .\Codex-Lifeboat-Windows-x64-Portable.zip --repo dkwolf1/Codex-Lifeboat
```

Maak 3.4.3 pas stabiel nadat de nog ontbrekende fysieke Windows 10- en
twee-computer-tests in de fase-11-matrix staan. Testers mogen nooit echte
back-ups of niet-opgeschoonde logs uploaden.
