# Bouwen en testen

Vereisten voor ontwikkelaars: Windows 10/11 en Python 3.11 of nieuwer. De
vastgezette versie van PyInstaller wordt automatisch in een lokale virtuele
omgeving geïnstalleerd.

## Zelftest

```powershell
.\test.ps1
```

## Volledige release bouwen

```powershell
.\build.ps1
```

Het buildscript voert eerst de volledige zelftest uit. Alleen daarna bouwt het de
zelfstandige `.exe`, maakt het een portable zip en schrijft het SHA-256-checksums.
Tijdelijke bestanden komen onder `.build` en worden niet door Git gevolgd.

De eindgebruiker heeft Python en PyInstaller niet nodig.
