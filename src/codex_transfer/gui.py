from __future__ import annotations

import argparse
import os
import queue
import tempfile
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import atomic_io, backup, diagnostics, location_mapper, recovery, restore, restore_plan, windows
from .validate import validate


TEXT = {
    "nl": {
        "title": "Codex Lifeboat",
        "subtitle": "Neem uw Codex-projecten, chats en instellingen veilig mee",
        "language": "Taal",
        "computer": "Deze computer",
        "codex_home": "Gevonden Codex-map",
        "usb": "Gevonden USB-schijven",
        "backup": "Back-up maken",
        "verify_backup": "Back-up controleren",
        "restore": "Back-up terugzetten",
        "verify_restore": "Herstel controleren",
        "overview": "Overzicht",
        "overview_subtitle": "Uw Codex-gegevens zijn klaar om veilig mee te nemen",
        "nav_backup": "Back-up",
        "nav_restore": "Herstellen",
        "backup_description": "Bewaar uw projecten, chats en instellingen",
        "restore_description": "Ga op deze computer verder vanuit een back-up",
        "latest_backup": "Laatste back-up",
        "included": "Inbegrepen",
        "storage": "Opslag",
        "no_backup_yet": "Nog geen back-up in deze sessie",
        "activity": "Activiteit",
        "last_result": "Laatste resultaat",
        "result_backup_title": "Back-up gereed",
        "result_verify_title": "Back-up gecontroleerd",
        "result_valid": "Volledig en gecontroleerd",
        "result_valid_warnings": "Geldig met aandachtspunten",
        "result_invalid": "Controle mislukt",
        "metric_chats": "Chats",
        "metric_projects": "Projecten",
        "metric_files": "Bestanden",
        "metric_size": "Omvang",
        "selection_title": "Kies wat in de back-up komt",
        "selection_intro": "Alles is standaard geselecteerd. Chats, instellingen en bijlagen blijven altijd beschermd; u kunt alleen projectbestanden uitsluiten.",
        "selection_include": "Meenemen",
        "selection_name": "Onderdeel",
        "selection_location": "Huidige locatie",
        "selection_folders": "Grootste mappen",
        "selection_total": "Geselecteerd: {projects}/{total} projecten · {files} bestanden · ongeveer {size}",
        "selection_locked": "Altijd inbegrepen",
        "selection_missing": "Niet gevonden",
        "selection_included": "Meegenomen",
        "selection_excluded": "Uitgesloten",
        "selection_codex_card": "Codex-gegevens beschermd",
        "selection_projects_card": "Projecten geselecteerd",
        "selection_files_card": "Geschat aantal bestanden",
        "selection_size_card": "Geschatte omvang",
        "selection_all": "Alle projecten selecteren",
        "selection_none": "Alle projecten uitsluiten",
        "selection_continue": "Doorgaan met back-up",
        "selection_cancel": "Annuleren",
        "selection_details": "Selecteer een regel om de grootste onderliggende mappen te bekijken.",
        "selection_exclusion_notice": "Uitgesloten projecten: {count}. De bijbehorende chatgeschiedenis blijft aanwezig, maar de projectbestanden kunnen niet vanuit deze back-up worden hersteld.",
        "selection_portability_ready": "✓ Overdraagbaarheidscontrole: alle {count} gevonden padverwijzingen vallen onder bekende vertaal- of uitsluitingsregels.",
        "selection_portability_attention": "● {count} padverwijzingen in {fields} veld(en) vragen aandacht. De gegevens worden wel meegenomen en de back-up en het herstel kunnen doorgaan.",
        "portability_details": "Details bekijken",
        "portability_title": "Details padverwijzingen",
        "portability_intro": "Onbekende verwijzingen worden ongewijzigd bewaard. U mist daardoor geen databasegegevens, maar een oude koppeling kan na herstel nog naar de vorige locatie wijzen.",
        "portability_covered": "Afgedekt",
        "portability_review": "Te controleren",
        "portability_field": "Lokaal veld",
        "portability_kind": "Soort pad",
        "portability_references": "Verwijzingen",
        "portability_exists": "Bestaat nu",
        "portability_handling": "Bij back-up/herstel",
        "portability_impact": "Impact",
        "portability_show_paths": "Lokale paden tonen (privé)",
        "portability_privacy": "Volledige paden blijven alleen in dit venster. Opgeslagen en gekopieerde rapporten blijven geanonimiseerd.",
        "portability_no_details": "Er zijn geen lokale details beschikbaar. Voer de controle opnieuw uit om details te verzamelen.",
        "portability_low": "Laag",
        "portability_medium": "Mogelijk merkbaar",
        "portability_high": "Belangrijk",
        "portability_present": "Ja",
        "portability_missing": "Nee / historisch",
        "portability_not_checked": "Niet gecontroleerd",
        "portability_profile_relative": "Gebruikersmap",
        "portability_project_relative": "Projectmap",
        "portability_external_or_unknown": "Extern of onbekend",
        "portability_old_source_location": "Oude bronlocatie",
        "portability_preserved_and_translated": "Meegenomen en vertaald",
        "portability_preserved_unchanged": "Meegenomen, niet vertaald",
        "portability_excluded_machine_state": "Computerspecifiek; uitgesloten",
        "portability_detail_text": "Veld: {field}\nBron: {source}\nAantal: {count}\nGegevens meegenomen: {included}\nAutomatisch vertaald: {translated}\nImpact: {impact}\n\nVoorbeelden:\n{paths}",
        "yes": "Ja",
        "no": "Nee",
        "details": "Wat is beschermd",
        "chat_details": "{active} actief · {archived} gearchiveerd · {pinned} vastgemaakt · {projectless} projectloos",
        "attachment_details": "Bijlagen: {copied} aanwezig · {missing} historisch niet meer beschikbaar",
        "identity_details": "{logical} logische projecten met {roots} permanente projectidentiteiten",
        "lineage_details": "Back-uplijn: {relation}",
        "lineage_root": "eerste back-up",
        "lineage_linear": "doorlopende overdracht",
        "lineage_divergent": "afwijkende tak gevonden",
        "assurance_hashes": "Alle pakketbestanden zijn met SHA-256 gecontroleerd",
        "assurance_database": "De SQLite-snapshot is consistent",
        "assurance_auth": "Aanmelding en computeridentiteit zijn niet uit de bron gekopieerd",
        "warnings_summary": "Aandachtspunten",
        "warning_missing_attachments": "{count} historische bijlagen zijn niet meer lokaal aanwezig",
        "warning_links": "{count} links of reparsepunten zijn veilig overgeslagen",
        "warning_missing_projects": "{count} geregistreerde projectlocaties bestaan niet meer",
        "warning_other": "{count} overige aandachtspunten staan in het volledige rapport",
        "full_report": "Volledig rapport: {path}",
        "result_location": "Back-uplocatie: {path}",
        "close": "Sluiten",
        "recovery": "Herstelpunten",
        "recovery_title": "Herstelpunten",
        "recovery_intro": "Codex Lifeboat bewaart standaard de twee nieuwste geldige herstelpunten. USB-back-ups worden nooit verwijderd.",
        "recovery_valid": "Geldig",
        "recovery_invalid": "Extra bewaard",
        "recovery_storage": "Opslag",
        "recovery_policy": "Bewaarbeleid",
        "recovery_keep": "nieuwste geldige punten",
        "recovery_date": "Datum",
        "recovery_status": "Status",
        "recovery_size": "Omvang",
        "recovery_location": "Locatie",
        "recovery_clean": "Oude herstelpunten veilig opruimen",
        "recovery_empty_title": "Nog geen herstelpunten",
        "recovery_empty_help": "Een herstelpunt wordt automatisch gemaakt vlak voordat u op deze computer een back-up terugzet.",
        "recovery_confirm": "Alleen oudere, volledig gecontroleerde herstelpunten worden verwijderd. De twee nieuwste geldige punten, ongeldige/onvolledige punten, zichtbare projectarchieven en USB-back-ups blijven bewaard. Doorgaan?",
        "recovery_cleaned": "Opschoning voltooid.\n\nVerwijderde herstelpunten: {points}\nVrijgemaakt: {size}\nGeldige herstelpunten bewaard: {retained}",
        "diagnostics": "Diagnose",
        "diagnostics_title": "Diagnosecentrum",
        "diagnostics_intro": "Controleert deze computer zonder bestanden of instellingen te wijzigen.",
        "diagnostics_ready": "Klaar voor gebruik",
        "diagnostics_attention": "Controleer de aandachtspunten",
        "diagnostics_blocked": "Actie vereist",
        "diagnostics_passed": "Geslaagd",
        "diagnostics_notices": "Aandachtspunten",
        "diagnostics_failed": "Mislukt",
        "diagnostics_check": "Controle",
        "diagnostics_status": "Status",
        "diagnostics_result": "Resultaat",
        "diagnostics_pass": "Goed",
        "diagnostics_notice": "Let op",
        "diagnostics_fail": "Actie nodig",
        "diagnostics_privacy": "Het supportrapport is geanonimiseerd: geen gebruikersnaam, computernaam, stationsletter, absoluut pad, projectnaam of chatinhoud.",
        "diagnostics_copy": "Rapport kopiëren",
        "diagnostics_save": "Rapport opslaan",
        "diagnostics_copy_done": "Het geanonimiseerde diagnoserapport staat op het klembord.",
        "diagnostics_save_done": "Het geanonimiseerde diagnoserapport is opgeslagen:\n\n{path}",
        "diagnostics_save_failed": "Het diagnoserapport kon niet worden opgeslagen:\n\n{error}",
        "diagnostics_save_title": "Geanonimiseerd diagnoserapport opslaan",
        "diagnostics_running": "Systeemcontroles uitvoeren…",
        "diagnostics_windows": "Windows-compatibiliteit",
        "diagnostics_launch_location": "Startlocatie toepassing",
        "diagnostics_codex_data": "Codex-gegevens",
        "diagnostics_codex_readable": "Toegang tot Codex-gegevens",
        "diagnostics_database": "Codex-database",
        "diagnostics_codex_closed": "Status Codex-toepassing",
        "diagnostics_installation": "Codex-installatie",
        "diagnostics_removable_storage": "Verwisselbare opslag",
        "diagnostics_local_space": "Lokale vrije ruimte",
        "diagnostics_recovery_points": "Herstelpunten",
        "diagnostics_local_state": "Lokale Lifeboat-status",
        "diagnostics_portability_audit": "Overdraagbaarheid van paden",
        "diagnostics_atomic_metadata": "Atomair opslaan van metadata",
        "ready": "Gereed",
        "working": "Bezig… sluit dit venster niet.",
        "choose_destination": "Kies USB-schijf of doelmap voor de back-up",
        "choose_backup": "Kies de Codex-PortableBackup-map",
        "confirm_backup": "Codex moet volledig zijn afgesloten. Wilt u een volledige back-up van uw projecten, chats en instellingen maken in:\n\n{path}?",
        "confirm_backup_selection": "Codex moet volledig zijn afgesloten. Maak de geselecteerde back-up in:\n\n{path}\n\nProjecten: {projects}\nBestanden: ongeveer {files}\nOmvang: ongeveer {size}?",
        "backup_done": "De back-up is voltooid:\n\n{path}",
        "backup_done_warnings": "De back-up is voltooid met {count} waarschuwing(en):\n\n{path}\n\n{details}\n\nVolledig rapport:\n{report}",
        "valid_backup": "De back-up is volledig en geldig.\n\nThreads: {threads}\nProjecten: {projects}\nHashes: {hashes}",
        "invalid_backup": "De back-up is ongeldig:\n\n{errors}",
        "restore_intro": "Codex moet op deze computer zijn geïnstalleerd. Open Codex één keer, meld u aan en sluit het programma daarna volledig af voordat u doorgaat.",
        "restore_confirm": "Er is een veiligheidskopie gemaakt:\n{safety}\n\nHuidige chats: {threads}\nHuidige projecten: {projects}\n\nWilt u de lokale Codex-gegevens vervangen door de volledige back-up?",
        "restore_cancelled": "Herstel geannuleerd. De veiligheidskopie is bewaard.",
        "restore_done": "Herstel en eindcontrole zijn geslaagd.\n\nVeiligheidskopie:\n{safety}",
        "restore_done_retention": "Herstel en eindcontrole zijn geslaagd.\n\nHerstelpunt:\n{safety}\n\nGeldige herstelpunten bewaard: {retained}\nTotale herstelopslag: {size}",
        "valid_restore": "Het herstel is geldig.\n\nThreads: {threads}\nProjecten: {projects}",
        "valid_restore_notice": "Het herstel is geldig.\n\nThreads: {threads}\nProjecten: {projects}\n\nPadcontrole: {paths} verwijzing(en) vragen nog aandacht; {old} verwijzing(en) wijzen nog naar een oude bronlocatie. Er ontbreken hierdoor geen databasegegevens.",
        "error": "Fout",
        "warning": "Waarschuwing",
        "version_warning": "Versiecontrole: {message}\n\nGeïnstalleerde versie: {installed}\nNieuwste online versie: {latest}\n\nWilt u toch doorgaan?",
        "no_usb": "Geen verwisselbare USB-schijf automatisch gevonden; kies handmatig een map.",
        "detected_backup": "Back-up automatisch gevonden:\n\n{path}\n\nDeze gebruiken?",
        "extract_required": "Codex Lifeboat is rechtstreeks vanuit het ZIP-bestand gestart.\n\nSluit dit venster, klik met rechts op de gedownloade ZIP, kies 'Alles uitpakken' en start Codex-Lifeboat.exe vanuit de uitgepakte map.",
        "extract_status": "Pak de ZIP eerst volledig uit; starten vanuit de ZIP is geblokkeerd.",
        "map_external_title": "Projectlocatie kiezen",
        "map_external_question": "Projecten uit deze externe bron:\n{source}\n\nJa: dezelfde locatie gebruiken of aanmaken\nNee: een andere hoofdmap kiezen\nAnnuleren: dit project overslaan en herstel stoppen",
        "map_external_invalid": "Deze projectlocatie kan niet veilig worden gebruikt:\n\n{errors}\n\nKies een andere hoofdmap.",
        "map_external_choose": "Kies of maak de hoofdmap voor deze externe projecten",
        "map_external_skipped": "De externe projectlocatie is overgeslagen. Er is niets hersteld.",
        "map_review": "Controleer waar de projecten worden teruggezet:\n\n{mappings}\n\nDeze locaties gebruiken en onthouden op deze computer?",
        "map_failed": "De projectlocaties zijn nog niet veilig opgelost:\n\n{errors}",
        "plan_title": "Herstelplan controleren",
        "plan_ready": "Het plan is volledig. Controleer alle acties voordat u verdergaat.",
        "plan_blocked": "Herstel is geblokkeerd totdat alle conflicten en locaties zijn opgelost.",
        "plan_restore": "Plan goedkeuren en doorgaan",
        "plan_close": "Sluiten zonder herstellen",
        "plan_kind": "Onderdeel",
        "plan_state": "Status",
        "plan_source": "Bron",
        "plan_target": "Doel",
        "plan_action": "Actie",
        "plan_size": "Omvang",
        "plan_disk": "Benodigde vrije ruimte: {required} · Beschikbaar: {free}",
        "plan_blockers": "Blokkeringen:\n{details}",
        "plan_decision_help": "Selecteer een chat of project en kies wat u wilt bewaren.",
        "plan_item_details": "Geselecteerd onderdeel:\n{reason}\n\nGit-uitleg: {git}",
        "plan_item_details_plain": "Geselecteerd onderdeel:\n{reason}",
        "plan_git_exact": "Dezelfde Git-commit en aan beide kanten geen lokale wijzigingen gevonden.",
        "plan_git_worktree": "Dezelfde Git-commit, maar lokale of niet-gevolgde bestanden verschillen.",
        "plan_git_backup_ahead": "De back-up bevat latere commits uit dezelfde Git-geschiedenis.",
        "plan_git_computer_ahead": "Deze computer bevat latere commits uit dezelfde Git-geschiedenis.",
        "plan_git_diverged": "Beide kanten hebben na een gemeenschappelijke Git-basis verschillende commits gekregen.",
        "plan_git_unrelated": "De commits hebben geen aantoonbare gemeenschappelijke Git-geschiedenis.",
        "plan_git_unavailable": "Geen voldoende Git-bewijs beschikbaar; de volledige bestandshashes blijven leidend.",
        "plan_git_changes": "Lokale wijzigingen: back-up {source}, computer {target}.",
        "plan_prefix_sync": (
            "Veilige chatuitbreiding: de {existing} bestaande records zijn exact "
            "ongewijzigd; {incoming} nieuw(e) record(s) uit de back-up worden toegevoegd."
        ),
        "keep_source": "Back-up bewaren",
        "keep_target": "Computer bewaren",
        "keep_both": "Beide bewaren",
        "skip": "Overslaan",
        "retain": "Project behouden",
        "archive": "Project archiveren",
        "delete": "Project verwijderen",
        "delete_project_confirm": "U staat op het punt dit project uit de actieve locatie te verwijderen:\n\n{path}\n\nDe gegevens gaan eerst naar een herstelquarantaine. Wilt u deze verwijdering expliciet goedkeuren?",
    },
    "en": {
        "title": "Codex Lifeboat",
        "subtitle": "Take your Codex projects, chats, and settings with you safely",
        "language": "Language",
        "computer": "This computer",
        "codex_home": "Detected Codex folder",
        "usb": "Detected USB drives",
        "backup": "Create backup",
        "verify_backup": "Verify backup",
        "restore": "Restore backup",
        "verify_restore": "Verify restore",
        "overview": "Overview",
        "overview_subtitle": "Your Codex data is ready to travel safely",
        "nav_backup": "Backup",
        "nav_restore": "Restore",
        "backup_description": "Protect your projects, chats, and settings",
        "restore_description": "Continue on this computer from a backup",
        "latest_backup": "Latest backup",
        "included": "Included",
        "storage": "Storage",
        "no_backup_yet": "No backup created in this session",
        "activity": "Activity",
        "last_result": "Latest result",
        "result_backup_title": "Backup ready",
        "result_verify_title": "Backup verified",
        "result_valid": "Complete and verified",
        "result_valid_warnings": "Valid with notices",
        "result_invalid": "Verification failed",
        "metric_chats": "Conversations",
        "metric_projects": "Projects",
        "metric_files": "Files",
        "metric_size": "Size",
        "selection_title": "Choose what goes into the backup",
        "selection_intro": "Everything is selected by default. Conversations, settings, and attachments always stay protected; only project files can be excluded.",
        "selection_include": "Include",
        "selection_name": "Item",
        "selection_location": "Current location",
        "selection_folders": "Largest folders",
        "selection_total": "Selected: {projects}/{total} projects · {files} files · approximately {size}",
        "selection_locked": "Always included",
        "selection_missing": "Not found",
        "selection_included": "Included",
        "selection_excluded": "Excluded",
        "selection_codex_card": "Codex data protected",
        "selection_projects_card": "Projects selected",
        "selection_files_card": "Estimated files",
        "selection_size_card": "Estimated size",
        "selection_all": "Select all projects",
        "selection_none": "Exclude all projects",
        "selection_continue": "Continue to backup",
        "selection_cancel": "Cancel",
        "selection_details": "Select a row to inspect its largest child folders.",
        "selection_exclusion_notice": "Excluded projects: {count}. Their conversation history remains available, but their project files cannot be restored from this backup.",
        "selection_portability_ready": "✓ Portability audit: all {count} detected path references are covered by known translation or exclusion rules.",
        "selection_portability_attention": "● {count} path references across {fields} field(s) need attention. The data is included and backup and restore can continue.",
        "portability_details": "View details",
        "portability_title": "Path reference details",
        "portability_intro": "Unknown references are preserved unchanged. No database data is omitted, but an old link may still point to its previous location after restore.",
        "portability_covered": "Covered",
        "portability_review": "Needs review",
        "portability_field": "Local field",
        "portability_kind": "Path type",
        "portability_references": "References",
        "portability_exists": "Exists now",
        "portability_handling": "Backup/restore handling",
        "portability_impact": "Impact",
        "portability_show_paths": "Show local paths (private)",
        "portability_privacy": "Full paths stay in this window only. Saved and copied reports remain anonymized.",
        "portability_no_details": "No local details are available. Run the check again to collect details.",
        "portability_low": "Low",
        "portability_medium": "Potentially noticeable",
        "portability_high": "Important",
        "portability_present": "Yes",
        "portability_missing": "No / historical",
        "portability_not_checked": "Not checked",
        "portability_profile_relative": "User profile",
        "portability_project_relative": "Project folder",
        "portability_external_or_unknown": "External or unknown",
        "portability_old_source_location": "Old source location",
        "portability_preserved_and_translated": "Included and translated",
        "portability_preserved_unchanged": "Included, not translated",
        "portability_excluded_machine_state": "Machine-specific; excluded",
        "portability_detail_text": "Field: {field}\nSource: {source}\nCount: {count}\nData included: {included}\nAutomatically translated: {translated}\nImpact: {impact}\n\nExamples:\n{paths}",
        "yes": "Yes",
        "no": "No",
        "details": "What is protected",
        "chat_details": "{active} active · {archived} archived · {pinned} pinned · {projectless} projectless",
        "attachment_details": "Attachments: {copied} available · {missing} historical files no longer available",
        "identity_details": "{logical} logical projects with {roots} permanent project identities",
        "lineage_details": "Backup lineage: {relation}",
        "lineage_root": "first backup",
        "lineage_linear": "continuous hand-off",
        "lineage_divergent": "divergent branch detected",
        "assurance_hashes": "Every package file passed SHA-256 verification",
        "assurance_database": "The SQLite snapshot is consistent",
        "assurance_auth": "Source authentication and machine identity were not copied",
        "warnings_summary": "Notices",
        "warning_missing_attachments": "{count} historical attachments are no longer available locally",
        "warning_links": "{count} links or reparse points were safely skipped",
        "warning_missing_projects": "{count} registered project locations no longer exist",
        "warning_other": "{count} other notices are recorded in the full report",
        "full_report": "Full report: {path}",
        "result_location": "Backup location: {path}",
        "close": "Close",
        "recovery": "Recovery points",
        "recovery_title": "Recovery points",
        "recovery_intro": "Codex Lifeboat keeps the two newest valid recovery points by default. USB backups are never deleted.",
        "recovery_valid": "Valid",
        "recovery_invalid": "Retained extra",
        "recovery_storage": "Storage",
        "recovery_policy": "Retention",
        "recovery_keep": "newest valid points",
        "recovery_date": "Date",
        "recovery_status": "Status",
        "recovery_size": "Size",
        "recovery_location": "Location",
        "recovery_clean": "Safely clean old recovery points",
        "recovery_empty_title": "No recovery points yet",
        "recovery_empty_help": "A recovery point is created automatically just before a backup is restored on this computer.",
        "recovery_confirm": "Only older, fully verified recovery points will be removed. The two newest valid points, invalid/incomplete points, visible project archives, and USB backups remain untouched. Continue?",
        "recovery_cleaned": "Cleanup complete.\n\nRecovery points removed: {points}\nSpace freed: {size}\nValid recovery points retained: {retained}",
        "diagnostics": "Diagnostics",
        "diagnostics_title": "Diagnostics center",
        "diagnostics_intro": "Checks this computer without changing files or settings.",
        "diagnostics_ready": "Ready for use",
        "diagnostics_attention": "Review the notices",
        "diagnostics_blocked": "Action required",
        "diagnostics_passed": "Passed",
        "diagnostics_notices": "Notices",
        "diagnostics_failed": "Failed",
        "diagnostics_check": "Check",
        "diagnostics_status": "Status",
        "diagnostics_result": "Result",
        "diagnostics_pass": "Good",
        "diagnostics_notice": "Notice",
        "diagnostics_fail": "Action needed",
        "diagnostics_privacy": "The support report is anonymized: no user name, computer name, drive letter, absolute path, project name, or conversation content.",
        "diagnostics_copy": "Copy report",
        "diagnostics_save": "Save report",
        "diagnostics_copy_done": "The anonymized diagnostic report is on the clipboard.",
        "diagnostics_save_done": "The anonymized diagnostic report was saved:\n\n{path}",
        "diagnostics_save_failed": "The diagnostic report could not be saved:\n\n{error}",
        "diagnostics_save_title": "Save anonymized diagnostic report",
        "diagnostics_running": "Running system checks…",
        "diagnostics_windows": "Windows compatibility",
        "diagnostics_launch_location": "Application launch location",
        "diagnostics_codex_data": "Codex data",
        "diagnostics_codex_readable": "Codex data access",
        "diagnostics_database": "Codex database",
        "diagnostics_codex_closed": "Codex application state",
        "diagnostics_installation": "Codex installation",
        "diagnostics_removable_storage": "Removable storage",
        "diagnostics_local_space": "Local free space",
        "diagnostics_recovery_points": "Recovery points",
        "diagnostics_local_state": "Lifeboat local state",
        "diagnostics_portability_audit": "Path portability",
        "diagnostics_atomic_metadata": "Atomic metadata storage",
        "ready": "Ready",
        "working": "Working… do not close this window.",
        "choose_destination": "Select USB drive or backup destination",
        "choose_backup": "Select the Codex-PortableBackup folder",
        "confirm_backup": "Codex must be completely closed. Create a full backup of your projects, chats, and settings in:\n\n{path}?",
        "confirm_backup_selection": "Codex must be completely closed. Create the selected backup in:\n\n{path}\n\nProjects: {projects}\nFiles: approximately {files}\nSize: approximately {size}?",
        "backup_done": "Backup completed successfully:\n\n{path}",
        "backup_done_warnings": "The backup completed with {count} warning(s):\n\n{path}\n\n{details}\n\nFull report:\n{report}",
        "valid_backup": "The backup is complete and valid.\n\nThreads: {threads}\nProjects: {projects}\nHashes: {hashes}",
        "invalid_backup": "The backup is invalid:\n\n{errors}",
        "restore_intro": "Codex must be installed on this computer. Open it once, sign in, and then close it completely before continuing.",
        "restore_confirm": "A safety copy has been created:\n{safety}\n\nCurrent chats: {threads}\nCurrent projects: {projects}\n\nReplace the local Codex data with the complete backup?",
        "restore_cancelled": "Restore cancelled. The safety copy has been kept.",
        "restore_done": "Restore and final verification succeeded.\n\nSafety copy:\n{safety}",
        "restore_done_retention": "Restore and final verification succeeded.\n\nRecovery point:\n{safety}\n\nValid recovery points retained: {retained}\nTotal recovery storage: {size}",
        "valid_restore": "The restore is valid.\n\nThreads: {threads}\nProjects: {projects}",
        "valid_restore_notice": "The restore is valid.\n\nThreads: {threads}\nProjects: {projects}\n\nPath check: {paths} reference(s) still need attention; {old} reference(s) still point to an old source location. No database data is omitted by this.",
        "error": "Error",
        "warning": "Warning",
        "version_warning": "Version check: {message}\n\nInstalled version: {installed}\nLatest online version: {latest}\n\nContinue anyway?",
        "no_usb": "No removable USB drive was detected automatically; select a folder manually.",
        "detected_backup": "Backup detected automatically:\n\n{path}\n\nUse this backup?",
        "extract_required": "Codex Lifeboat was started directly from the ZIP file.\n\nClose this window, right-click the downloaded ZIP, select 'Extract All', and start Codex-Lifeboat.exe from the extracted folder.",
        "extract_status": "Extract the ZIP completely first; running from inside the ZIP is blocked.",
        "map_external_title": "Choose project location",
        "map_external_question": "Projects use this external source root:\n{source}\n\nYes: use or create the same location\nNo: choose another root folder\nCancel: skip this project and stop the restore",
        "map_external_invalid": "This project location cannot be used safely:\n\n{errors}\n\nChoose another root folder.",
        "map_external_choose": "Choose or create the root folder for these external projects",
        "map_external_skipped": "The external project location was skipped. Nothing was restored.",
        "map_review": "Review where the projects will be restored:\n\n{mappings}\n\nUse these locations and remember them on this computer?",
        "map_failed": "The project locations have not been resolved safely:\n\n{errors}",
        "plan_title": "Review restore plan",
        "plan_ready": "The plan is complete. Review every action before continuing.",
        "plan_blocked": "Restore is blocked until every conflict and location is resolved.",
        "plan_restore": "Approve plan and continue",
        "plan_close": "Close without restoring",
        "plan_kind": "Item",
        "plan_state": "State",
        "plan_source": "Source",
        "plan_target": "Target",
        "plan_action": "Action",
        "plan_size": "Size",
        "plan_disk": "Required free space: {required} · Available: {free}",
        "plan_blockers": "Blocking issues:\n{details}",
        "plan_decision_help": "Select a conversation or project and choose what to keep.",
        "plan_item_details": "Selected item:\n{reason}\n\nGit explanation: {git}",
        "plan_item_details_plain": "Selected item:\n{reason}",
        "plan_git_exact": "The same Git commit is present and neither worktree reports local changes.",
        "plan_git_worktree": "The Git commit is the same, but local or untracked files differ.",
        "plan_git_backup_ahead": "The backup contains later commits from the same Git history.",
        "plan_git_computer_ahead": "This computer contains later commits from the same Git history.",
        "plan_git_diverged": "Both sides contain different commits after a shared Git base.",
        "plan_git_unrelated": "The commits have no provable shared Git history.",
        "plan_git_unavailable": "Insufficient Git evidence; complete file hashes remain authoritative.",
        "plan_git_changes": "Local changes: backup {source}, computer {target}.",
        "plan_prefix_sync": (
            "Safe chat extension: all {existing} existing records are exactly "
            "unchanged; {incoming} new backup record(s) will be added."
        ),
        "keep_source": "Keep backup",
        "keep_target": "Keep computer",
        "keep_both": "Keep both",
        "skip": "Skip",
        "retain": "Retain project",
        "archive": "Archive project",
        "delete": "Delete project",
        "delete_project_confirm": "You are about to remove this project from its active location:\n\n{path}\n\nThe data will first move to recovery quarantine. Explicitly approve this removal?",
    },
}

PLAN_VALUES = {
    "nl": {
        "identical": "Gelijk",
        "incoming": "Inkomend",
        "destination-only": "Alleen op doelcomputer",
        "removed": "Verwijderd in back-up",
        "conflicting": "Conflict",
        "none": "Geen wijziging",
        "create": "Aanmaken",
        "replace": "Vervangen",
        "retain": "Behouden",
        "resolve": "Eerst oplossen",
        "replace-managed-data": "Beheerde Codex-data vervangen",
        "delete": "Verwijderen volgens back-up",
        "keep-both": "Beide bewaren",
        "archive": "Archiveren",
        "archive-and-replace": "Archiveren en back-up gebruiken",
        "delete-project": "Actief project verwijderen",
    },
    "en": {
        "identical": "Identical",
        "incoming": "Incoming",
        "destination-only": "Destination only",
        "removed": "Removed in backup",
        "conflicting": "Conflict",
        "none": "No change",
        "create": "Create",
        "replace": "Replace",
        "retain": "Retain",
        "resolve": "Resolve first",
        "replace-managed-data": "Replace managed Codex data",
        "delete": "Delete to match backup",
        "keep-both": "Keep both",
        "archive": "Archive",
        "archive-and-replace": "Archive and use backup",
        "delete-project": "Remove active project",
    },
}


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TiB"


def _backup_result_model(
    package_root: Path, validation: dict | None = None
) -> dict:
    package_root = package_root.resolve(strict=False)
    package = backup.read_json(package_root / "manifest" / "package.json")
    inventory_path = package_root / "manifest" / "inventory.json"
    report_path = package_root / "reports" / "backup-report.json"
    inventory = backup.read_json(inventory_path) if inventory_path.is_file() else {}
    report = backup.read_json(report_path) if report_path.is_file() else {}
    counts = package.get("counts", {})
    conversations = inventory.get("conversations", {}).get("counts", {})
    warnings = [str(item) for item in report.get("warnings", [])]
    missing_attachments = int(counts.get("attachmentsMissing", 0))
    link_warnings = sum(
        "reparse" in item.casefold() or "symbolic link" in item.casefold()
        for item in warnings
    )
    missing_projects = sum(
        (
            "project root" in item.casefold()
            or "projectroot" in item.casefold()
        )
        and (
            "does not exist" in item.casefold()
            or "bestaat niet" in item.casefold()
        )
        for item in warnings
    )
    categorized = min(
        len(warnings), missing_attachments + link_warnings + missing_projects
    )
    valid = bool(
        validation.get("valid") if validation is not None else package.get("backupComplete")
    )
    return {
        "package": str(package_root),
        "report": str(report_path),
        "valid": valid,
        "warningCount": len(warnings),
        "warnings": {
            "missingAttachments": missing_attachments,
            "links": link_warnings,
            "missingProjects": missing_projects,
            "other": max(len(warnings) - categorized, 0),
        },
        "metrics": {
            "chats": int(counts.get("threads", 0)),
            "projects": int(counts.get("projects", 0)),
            "files": int(counts.get("hashedFiles", 0)),
            "bytes": int(package.get("payloadBytes", 0)),
        },
        "conversations": {
            "active": int(conversations.get("recent", 0)),
            "archived": int(conversations.get("archived", 0)),
            "pinned": int(conversations.get("pinned", 0)),
            "projectless": int(conversations.get("projectless", 0)),
        },
        "attachments": {
            "copied": int(counts.get("attachmentsCopied", 0)),
            "missing": missing_attachments,
        },
        "identities": {
            "logical": int(counts.get("logicalProjects", 0)),
            "roots": int(counts.get("projects", 0)),
        },
        "lineage": str(package.get("lineage", {}).get("relation") or "root"),
    }


class BackupResultDialog(tk.Toplevel):
    def __init__(self, parent: "TransferApp", model: dict, verified: bool):
        super().__init__(parent)
        self.parent_app = parent
        self.model = model
        self.title(parent.t("result_verify_title" if verified else "result_backup_title"))
        self.geometry("980x700")
        self.minsize(820, 620)
        self.configure(bg=parent.BG)
        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        title = parent.t("result_verify_title" if verified else "result_backup_title")
        ttk.Label(self, text=title, style="DialogTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=28, pady=(24, 2)
        )
        status_key = (
            "result_invalid"
            if not model["valid"]
            else "result_valid_warnings"
            if model["warningCount"]
            else "result_valid"
        )
        status_color = parent.SUCCESS if model["valid"] else "#B42318"
        tk.Label(
            self,
            text="●  " + parent.t(status_key),
            bg=parent.BG,
            fg=status_color,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=1, column=0, sticky="w", padx=28, pady=(0, 18))

        metrics = ttk.Frame(self, style="App.TFrame")
        metrics.grid(row=2, column=0, sticky="ew", padx=28)
        metric_values = (
            ("metric_chats", str(model["metrics"]["chats"])),
            ("metric_projects", str(model["metrics"]["projects"])),
            ("metric_files", str(model["metrics"]["files"])),
            ("metric_size", _format_bytes(model["metrics"]["bytes"])),
        )
        for column, (label_key, value) in enumerate(metric_values):
            metrics.columnconfigure(column, weight=1)
            card = tk.Frame(metrics, bg=parent.CARD, highlightbackground=parent.BORDER,
                            highlightthickness=1, padx=18, pady=14)
            card.grid(
                row=0, column=column, sticky="ew",
                padx=(0 if column == 0 else 6, 0 if column == 3 else 6),
            )
            tk.Label(
                card, text=value, bg=parent.CARD, fg=parent.NAVY,
                font=("Segoe UI", 18, "bold"),
            ).pack(anchor="w")
            tk.Label(
                card, text=parent.t(label_key), bg=parent.CARD, fg=parent.MUTED,
                font=("Segoe UI", 9),
            ).pack(anchor="w")

        content = ttk.Frame(self, style="App.TFrame")
        content.grid(row=3, column=0, sticky="ew", padx=28, pady=(20, 0))
        content.columnconfigure(0, weight=1)
        ttk.Label(content, text=parent.t("details"), style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        details = [
            parent.t("chat_details", **model["conversations"]),
            parent.t("attachment_details", **model["attachments"]),
            parent.t("identity_details", **model["identities"]),
            parent.t(
                "lineage_details",
                relation=parent.t(
                    "lineage_" + model["lineage"]
                    if model["lineage"] in {"root", "linear", "divergent"}
                    else "lineage_root"
                ),
            ),
            parent.t("assurance_hashes"),
            parent.t("assurance_database"),
            parent.t("assurance_auth"),
        ]
        ttk.Label(
            content,
            text="\n".join(f"✓  {item}" for item in details),
            style="Body.TLabel",
            justify="left",
        ).grid(row=1, column=0, sticky="w")

        notices = ttk.Frame(self, style="App.TFrame")
        notices.grid(row=4, column=0, sticky="nsew", padx=28, pady=(18, 8))
        notices.columnconfigure(0, weight=1)
        warning_lines: list[str] = []
        for key, translation in (
            ("missingAttachments", "warning_missing_attachments"),
            ("links", "warning_links"),
            ("missingProjects", "warning_missing_projects"),
            ("other", "warning_other"),
        ):
            count = int(model["warnings"].get(key, 0))
            if count:
                warning_lines.append("• " + parent.t(translation, count=count))
        if warning_lines:
            ttk.Label(
                notices, text=parent.t("warnings_summary"), style="Section.TLabel"
            ).grid(row=0, column=0, sticky="w", pady=(0, 6))
            ttk.Label(
                notices,
                text="\n".join(warning_lines),
                style="Body.TLabel",
                justify="left",
                wraplength=900,
            ).grid(row=1, column=0, sticky="nw")

        footer = ttk.Frame(self, padding=(28, 8, 28, 22), style="App.TFrame")
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            text=parent.t("result_location", path=model["package"])
            + "\n"
            + parent.t("full_report", path=model["report"]),
            style="Body.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text=parent.t("close"), command=self.destroy).grid(
            row=0, column=1, padx=(14, 0)
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)


class RecoveryDialog(tk.Toplevel):
    def __init__(self, parent: "TransferApp", model: dict):
        super().__init__(parent)
        self.parent_app = parent
        self.model = model
        self.title(parent.t("recovery_title"))
        self.geometry("1000x650")
        self.minsize(820, 560)
        self.configure(bg=parent.BG)
        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text=parent.t("recovery_title"), style="DialogTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=28, pady=(24, 2)
        )
        ttk.Label(
            self, text=parent.t("recovery_intro"), style="Body.TLabel",
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", padx=28, pady=(0, 16))
        cards = ttk.Frame(self, style="App.TFrame")
        cards.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 16))
        values = (
            ("recovery_valid", model.get("validPoints", 0)),
            ("recovery_invalid", model.get("invalidPoints", 0)),
            ("recovery_storage", _format_bytes(int(model.get("totalBytes", 0)))),
            ("recovery_policy", f"{model.get('keep', 2)} {parent.t('recovery_keep')}"),
        )
        for column, (key, value) in enumerate(values):
            cards.columnconfigure(column, weight=1)
            frame = tk.Frame(cards, bg=parent.CARD, highlightbackground=parent.BORDER,
                             highlightthickness=1, padx=15, pady=12)
            frame.grid(row=0, column=column, sticky="ew", padx=5)
            tk.Label(frame, text=str(value), bg=parent.CARD, fg=parent.NAVY,
                     font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(frame, text=parent.t(key), bg=parent.CARD, fg=parent.MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")
        table = ttk.Frame(self, style="App.TFrame")
        table.grid(row=3, column=0, sticky="nsew", padx=28)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            table,
            columns=("date", "status", "size", "location"),
            show="headings",
        )
        for column, key, width in (
            ("date", "recovery_date", 175),
            ("status", "recovery_status", 110),
            ("size", "recovery_size", 100),
            ("location", "recovery_location", 500),
        ):
            tree.heading(column, text=parent.t(key))
            tree.column(column, width=width, stretch=column == "location")
        points = model.get("points", [])
        for item in points:
            total = int(item.get("centralBytes", 0)) + int(
                item.get("projectRecoveryBytes", 0)
            )
            tree.insert(
                "", "end", values=(
                    str(item.get("completedAtUtc") or "")[:19].replace("T", " "),
                    parent.t("recovery_valid") if item.get("valid") else parent.t("recovery_invalid"),
                    _format_bytes(total),
                    item.get("path"),
                ),
            )
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        self.empty_state: tk.Frame | None = None
        if not points:
            self.empty_state = tk.Frame(
                table,
                bg=parent.CARD,
                highlightbackground=parent.BORDER,
                highlightthickness=1,
                padx=28,
                pady=20,
            )
            tk.Label(
                self.empty_state,
                text=parent.t("recovery_empty_title"),
                bg=parent.CARD,
                fg=parent.NAVY,
                font=("Segoe UI", 14, "bold"),
            ).pack()
            tk.Label(
                self.empty_state,
                text=parent.t("recovery_empty_help"),
                bg=parent.CARD,
                fg=parent.MUTED,
                font=("Segoe UI", 9),
                wraplength=560,
                justify="center",
            ).pack(pady=(6, 0))
            self.empty_state.place(relx=0.5, rely=0.5, anchor="center")
        actions = ttk.Frame(self, padding=(28, 16, 28, 22), style="App.TFrame")
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.clean_button = ttk.Button(
            actions,
            text=parent.t("recovery_clean"),
            command=lambda: parent._clean_recovery(self),
        )
        self.clean_button.grid(row=0, column=1)
        if int(model.get("validPoints", 0)) <= int(model.get("keep", 2)):
            self.clean_button.state(["disabled"])
        ttk.Button(actions, text=parent.t("close"), command=self.destroy).grid(
            row=0, column=2, padx=(10, 0)
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)


class RestorePlanDialog(tk.Toplevel):
    def __init__(self, parent: "TransferApp", plan: dict):
        super().__init__(parent)
        self.approved = False
        self.parent_app = parent
        self.plan = plan
        self.title(parent.t("plan_title"))
        self.geometry("1320x780")
        self.minsize(960, 620)
        self.configure(bg=parent.BG)
        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(
            self,
            text=parent.t("plan_title"),
            style="DialogTitle.TLabel",
        ).grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 4))
        self.status_label = ttk.Label(
            self,
            text="",
            style="Body.TLabel",
        )
        self.status_label.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))

        columns = ("kind", "state", "source", "target", "action", "size")
        tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        headings = {
            "kind": parent.t("plan_kind"),
            "state": parent.t("plan_state"),
            "source": parent.t("plan_source"),
            "target": parent.t("plan_target"),
            "action": parent.t("plan_action"),
            "size": parent.t("plan_size"),
        }
        widths = {"kind": 145, "state": 120, "source": 280, "target": 300, "action": 155, "size": 100}
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], minwidth=80, stretch=column in {"source", "target"})
        for item in self.plan.get("items", []):
            language = parent.language.get()
            tree.insert(
                "",
                "end",
                iid=str(item.get("key")),
                values=(
                    item.get("name") or item.get("kind"),
                    PLAN_VALUES[language].get(str(item.get("state")), item.get("state")),
                    item.get("source") or "—",
                    item.get("target") or "—",
                    PLAN_VALUES[language].get(
                        str(item.get("proposedAction")), item.get("proposedAction")
                    ),
                    _format_bytes(int(item.get("sourceBytes", 0))),
                ),
                tags=("blocked",) if item.get("blocking") else (),
            )
        tree.tag_configure("blocked", foreground="#B42318")
        tree.grid(row=2, column=0, sticky="nsew", padx=24)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns", padx=(0, 20))

        decisions = ttk.Frame(self, padding=(24, 10), style="App.TFrame")
        decisions.grid(row=3, column=0, sticky="ew")
        decisions.columnconfigure(0, weight=1)
        ttk.Label(
            decisions,
            text=parent.t("plan_decision_help"),
            style="Body.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self.decision_buttons: dict[str, ttk.Button] = {}
        for column, decision in enumerate(
            (
                "keep-source", "keep-target", "keep-both", "skip",
                "retain", "archive", "delete",
            ),
            start=1,
        ):
            button = ttk.Button(
                decisions,
                text=parent.t(decision.replace("-", "_")),
                command=lambda value=decision: self._apply_decision(value),
            )
            button.grid(row=0, column=column, padx=(8, 0))
            button.state(["disabled"])
            self.decision_buttons[decision] = button

        self.details_label = ttk.Label(
            self, text="", style="Body.TLabel", justify="left"
        )
        self.details_label.grid(row=4, column=0, sticky="ew", padx=24, pady=12)

        actions = ttk.Frame(self, padding=(24, 0, 24, 20), style="App.TFrame")
        actions.grid(row=5, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        ttk.Button(actions, text=parent.t("plan_close"), command=self.destroy).grid(
            row=0, column=1, padx=(8, 0)
        )
        approve = ttk.Button(
            actions,
            text=parent.t("plan_restore"),
            command=self._approve,
            style="Action.TButton",
        )
        approve.grid(row=0, column=2, padx=(8, 0))
        self.plan_tree = tree
        self.approve_button = approve
        tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self._refresh_summary()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _plan_item(self, key: str) -> dict | None:
        return next(
            (item for item in self.plan.get("items", []) if item.get("key") == key),
            None,
        )

    def _selection_changed(self, _event=None) -> None:
        selected = self.plan_tree.selection()
        item = self._plan_item(selected[0]) if selected else None
        available = set(item.get("availableDecisions", [])) if item else set()
        for decision, button in self.decision_buttons.items():
            if decision in available:
                button.state(["!disabled"])
            else:
                button.state(["disabled"])
        self._refresh_summary()

    def _git_explanation(self, item: dict) -> str:
        insight = item.get("gitInsight") or {}
        relation = str(insight.get("historyRelation") or "unknown")
        key = {
            "same-commit": (
                "plan_git_worktree"
                if insight.get("sourceDirty") or insight.get("targetDirty")
                else "plan_git_exact"
            ),
            "backup-ahead": "plan_git_backup_ahead",
            "computer-ahead": "plan_git_computer_ahead",
            "diverged": "plan_git_diverged",
            "unrelated": "plan_git_unrelated",
            "unrelated-or-unavailable": "plan_git_unrelated",
        }.get(relation, "plan_git_unavailable")
        explanation = self.parent_app.t(key)
        source_changes = insight.get("sourceChangedEntries")
        target_changes = insight.get("targetChangedEntries")
        if source_changes is not None or target_changes is not None:
            explanation += " " + self.parent_app.t(
                "plan_git_changes",
                source=source_changes if source_changes is not None else "?",
                target=target_changes if target_changes is not None else "?",
            )
        return explanation

    def _apply_decision(self, decision: str) -> None:
        selected = self.plan_tree.selection()
        if not selected:
            return
        key = selected[0]
        item = self._plan_item(key)
        if not item:
            return
        if item.get("kind") == "project" and decision == "delete":
            if not messagebox.askyesno(
                self.parent_app.t("warning"),
                self.parent_app.t(
                    "delete_project_confirm", path=item.get("target") or "—"
                ),
                parent=self,
            ):
                return
        try:
            if item.get("kind") == "project":
                self.plan = restore_plan.resolve_project_decision(
                    self.plan, key, decision
                )
            else:
                self.plan = restore_plan.resolve_conversation_decision(
                    self.plan, key, decision
                )
        except ValueError as exc:
            messagebox.showerror(
                self.parent_app.t("error"), str(exc), parent=self
            )
            return
        item = self._plan_item(key)
        if item:
            values = list(self.plan_tree.item(key, "values"))
            values[4] = PLAN_VALUES[self.parent_app.language.get()].get(
                str(item.get("proposedAction")), item.get("proposedAction")
            )
            self.plan_tree.item(
                key,
                values=values,
                tags=("blocked",) if item.get("blocking") else (),
            )
        self._selection_changed()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        ready = bool(self.plan.get("ready"))
        self.status_label.configure(
            text=self.parent_app.t("plan_ready" if ready else "plan_blocked")
        )
        details: list[str] = []
        for disk in self.plan.get("diskRequirements", []):
            details.append(
                f"{disk.get('volume')}: "
                + self.parent_app.t(
                    "plan_disk",
                    required=_format_bytes(int(disk.get("requiredBytes", 0))),
                    free=_format_bytes(int(disk.get("freeBytes", 0))),
                )
            )
        blockers = self.plan.get("blockingReasons", [])
        if blockers:
            details.append(
                self.parent_app.t(
                    "plan_blockers",
                    details="\n".join(f"• {value}" for value in blockers[:8]),
                )
            )
        selected = self.plan_tree.selection() if hasattr(self, "plan_tree") else ()
        selected_item = self._plan_item(selected[0]) if selected else None
        if selected_item:
            prefix = selected_item.get("prefixSync") or {}
            if prefix.get("automatic"):
                reason = self.parent_app.t(
                    "plan_prefix_sync",
                    existing=int(prefix.get("targetRecords", 0)),
                    incoming=int(prefix.get("additionalSourceRecords", 0)),
                )
            else:
                reason = str(
                    selected_item.get("originalReason")
                    or selected_item.get("reason")
                    or "—"
                )
            if selected_item.get("kind") == "project":
                details.insert(
                    0,
                    self.parent_app.t(
                        "plan_item_details",
                        reason=reason,
                        git=self._git_explanation(selected_item),
                    ),
                )
            else:
                details.insert(
                    0,
                    self.parent_app.t("plan_item_details_plain", reason=reason),
                )
        self.details_label.configure(text="\n".join(details))
        if ready:
            self.approve_button.state(["!disabled"])
        else:
            self.approve_button.state(["disabled"])

    def _approve(self) -> None:
        self.approved = True
        self.destroy()


class BackupSelectionDialog(tk.Toplevel):
    def __init__(self, parent: "TransferApp", preview: dict) -> None:
        super().__init__(parent)
        self.parent_app = parent
        self.preview = preview
        self.approved = False
        self.selected_paths = {
            str(item["path"])
            for item in preview.get("projects", [])
            if item.get("sourcePresent")
        }
        self.project_by_iid: dict[str, dict] = {}
        self.title(parent.t("selection_title"))
        screen_width = max(parent.winfo_screenwidth(), 1100)
        screen_height = max(parent.winfo_screenheight(), 720)
        width = min(1540, max(1180, int(screen_width * 0.88)))
        height = min(980, max(760, int(screen_height * 0.88)))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1080, 720)
        self.configure(bg=parent.BG)
        # Keep this independently restorable from the Windows taskbar. A
        # transient modal window can disappear behind its owner and then block
        # the owner's grouped taskbar button from restoring either window.
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build()
        self._refresh()
        self.after_idle(self._present)

    def _present(self) -> None:
        if not self.winfo_exists():
            return
        self.deiconify()
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        self.lift()
        self.focus_force()

    @property
    def excluded_paths(self) -> list[str]:
        return [
            str(item["path"])
            for item in self.preview.get("projects", [])
            if str(item["path"]) not in self.selected_paths
        ]

    @property
    def selected_summary(self) -> dict[str, int]:
        selected = [
            item
            for item in self.preview.get("projects", [])
            if str(item["path"]) in self.selected_paths
        ]
        codex = self.preview.get("codex", {})
        return {
            "projects": len(selected),
            "files": int(codex.get("fileCount", 0))
            + sum(int(item.get("fileCount", 0)) for item in selected),
            "bytes": int(codex.get("totalBytes", 0))
            + sum(int(item.get("totalBytes", 0)) for item in selected),
        }

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        header = tk.Frame(self, bg=self.parent_app.NAVY, padx=28, pady=20)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            header, text=self.parent_app.t("selection_title"),
            bg=self.parent_app.NAVY, fg="#FFFFFF",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header, text=self.parent_app.t("selection_intro"),
            bg=self.parent_app.NAVY, fg="#C9D8E8", font=("Segoe UI", 10),
            wraplength=1080, justify="left",
        ).pack(anchor="w", pady=(6, 0))

        metrics = tk.Frame(self, bg=self.parent_app.BG)
        metrics.grid(row=1, column=0, sticky="ew", padx=26, pady=14)
        for column in range(4):
            metrics.columnconfigure(column, weight=1, uniform="metric")
        self.metric_values: dict[str, tk.Label] = {}
        metric_specs = (
            ("codex", "selection_codex_card"),
            ("projects", "selection_projects_card"),
            ("files", "selection_files_card"),
            ("size", "selection_size_card"),
        )
        for column, (key, label_key) in enumerate(metric_specs):
            card = tk.Frame(
                metrics, bg=self.parent_app.CARD,
                highlightbackground=self.parent_app.BORDER, highlightthickness=1,
                padx=16, pady=10,
            )
            card.grid(
                row=0, column=column, sticky="ew",
                padx=(0 if column == 0 else 5, 0 if column == 3 else 5),
            )
            value = tk.Label(
                card, text="—", bg=self.parent_app.CARD,
                fg=self.parent_app.NAVY, font=("Segoe UI", 16, "bold"),
            )
            value.pack(anchor="w")
            tk.Label(
                card, text=self.parent_app.t(label_key), bg=self.parent_app.CARD,
                fg=self.parent_app.MUTED, font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(2, 0))
            self.metric_values[key] = value

        portability = self.preview.get("portabilityAudit") or {}
        portability_summary = portability.get("summary") or {}
        needs_review = int(portability_summary.get("needsReviewReferences", 0))
        review_fields = int(portability_summary.get("fieldsNeedingReview", 0))
        path_references = int(portability_summary.get("pathReferences", 0))
        if needs_review or portability_summary.get("scanErrors"):
            portability_text = self.parent_app.t(
                "selection_portability_attention",
                count=needs_review,
                fields=review_fields,
            )
            portability_color = "#8A5A00"
            portability_background = "#FFF5E6"
        else:
            portability_text = self.parent_app.t(
                "selection_portability_ready", count=path_references
            )
            portability_color = "#0B6B47"
            portability_background = "#EAF7F1"
        portability_bar = tk.Frame(metrics, bg=portability_background)
        portability_bar.grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0)
        )
        portability_bar.columnconfigure(0, weight=1)
        tk.Label(
            portability_bar,
            text=portability_text,
            bg=portability_background,
            fg=portability_color,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            justify="left",
            padx=13,
            pady=9,
            wraplength=1080,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            portability_bar,
            text=self.parent_app.t("portability_details"),
            command=lambda: PathPortabilityDialog(self, portability),
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(8, 12), pady=5)

        table_frame = tk.Frame(
            self, bg=self.parent_app.CARD,
            highlightbackground=self.parent_app.BORDER, highlightthickness=1,
            padx=1, pady=1,
        )
        table_frame.grid(row=2, column=0, sticky="nsew", padx=26)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("include", "name", "location", "files", "size")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse",
            height=20, style="Selection.Treeview"
        )
        self.tree.heading("include", text=self.parent_app.t("selection_include"))
        self.tree.heading("name", text=self.parent_app.t("selection_name"))
        self.tree.heading("location", text=self.parent_app.t("selection_location"))
        self.tree.heading("files", text=self.parent_app.t("metric_files"))
        self.tree.heading("size", text=self.parent_app.t("metric_size"))
        self.tree.column("include", width=100, minwidth=90, anchor="center", stretch=False)
        self.tree.column("name", width=190, minwidth=140, anchor="w")
        self.tree.column("location", width=570, minwidth=300, anchor="w")
        self.tree.column("files", width=105, minwidth=85, anchor="e", stretch=False)
        self.tree.column("size", width=115, minwidth=95, anchor="e", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.bind("<Button-1>", self._click)
        self.tree.bind("<Double-1>", self._double_click)
        self.tree.bind("<space>", self._toggle_selected_row)
        self.tree.bind("<<TreeviewSelect>>", self._show_details)
        self.tree.tag_configure("protected", background="#EAF7F1", foreground="#0B6B47")
        self.tree.tag_configure("included", background="#FFFFFF", foreground=self.parent_app.TEXT_COLOR)
        self.tree.tag_configure("excluded", background="#F4F6F8", foreground="#718096")
        self.tree.tag_configure("missing", background="#FFF5E6", foreground="#8A5A00")

        codex = self.preview.get("codex", {})
        self.tree.insert(
            "",
            "end",
            iid="codex",
            values=(
                self.parent_app.t("selection_locked"),
                codex.get("name", "Codex"),
                codex.get("path", ""),
                f"{int(codex.get('fileCount', 0)):,}",
                _format_bytes(int(codex.get("totalBytes", 0))),
            ),
            tags=("protected",),
        )
        for index, item in enumerate(self.preview.get("projects", [])):
            iid = f"project-{index}"
            self.project_by_iid[iid] = item
            self.tree.insert("", "end", iid=iid, values=("", "", "", "", ""))

        controls = ttk.Frame(self, style="App.TFrame")
        controls.grid(row=3, column=0, sticky="ew", padx=26, pady=(12, 0))
        ttk.Button(
            controls,
            text=self.parent_app.t("selection_all"),
            command=self._select_all,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            controls,
            text=self.parent_app.t("selection_none"),
            command=self._select_none,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))
        self.total_label = ttk.Label(controls, style="Body.TLabel")
        self.total_label.pack(side="right")

        details_card = tk.Frame(
            self, bg=self.parent_app.CARD,
            highlightbackground=self.parent_app.BORDER, highlightthickness=1,
            padx=14, pady=10,
        )
        details_card.grid(row=4, column=0, sticky="ew", padx=26, pady=(12, 8))
        self.details_label = tk.Label(
            details_card,
            text=self.parent_app.t("selection_details"),
            bg=self.parent_app.CARD, fg=self.parent_app.TEXT_COLOR,
            font=("Segoe UI", 9), wraplength=1100, justify="left",
        )
        self.details_label.pack(anchor="w")

        footer = ttk.Frame(self, style="App.TFrame")
        footer.grid(row=5, column=0, sticky="ew", padx=26, pady=(8, 22))
        ttk.Button(
            footer,
            text=self.parent_app.t("selection_cancel"),
            command=self.destroy,
            style="Secondary.TButton",
        ).pack(side="right")
        ttk.Button(
            footer,
            text=self.parent_app.t("selection_continue"),
            command=self._approve,
            style="Primary.TButton",
        ).pack(side="right", padx=(0, 10))

    def _click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if iid in self.project_by_iid and column == "#1":
            self._toggle_iid(iid)

    def _double_click(self, event) -> None:
        self._toggle_iid(self.tree.identify_row(event.y))

    def _toggle_selected_row(self, _event=None) -> str:
        selected = self.tree.selection()
        if selected:
            self._toggle_iid(selected[0])
        return "break"

    def _toggle_iid(self, iid: str) -> None:
        if iid not in self.project_by_iid:
            return
        item = self.project_by_iid[iid]
        if not item.get("sourcePresent"):
            return
        path = str(item["path"])
        if path in self.selected_paths:
            self.selected_paths.remove(path)
        else:
            self.selected_paths.add(path)
        self._refresh()

    def _select_all(self) -> None:
        self.selected_paths = {
            str(item["path"])
            for item in self.preview.get("projects", [])
            if item.get("sourcePresent")
        }
        self._refresh()

    def _select_none(self) -> None:
        self.selected_paths.clear()
        self._refresh()

    def _refresh(self) -> None:
        for iid, item in self.project_by_iid.items():
            path = str(item["path"])
            state = (
                self.parent_app.t("selection_missing")
                if not item.get("sourcePresent")
                else "✓ " + self.parent_app.t("selection_included")
                if path in self.selected_paths
                else "○ " + self.parent_app.t("selection_excluded")
            )
            tag = (
                "missing" if not item.get("sourcePresent")
                else "included" if path in self.selected_paths else "excluded"
            )
            self.tree.item(
                iid,
                values=(
                    state,
                    item.get("name") or Path(path).name,
                    path,
                    f"{int(item.get('fileCount', 0)):,}",
                    _format_bytes(int(item.get("totalBytes", 0))),
                ),
                tags=(tag,),
            )
        summary = self.selected_summary
        total_projects = len(self.preview.get("projects", []))
        codex = self.preview.get("codex", {})
        self.metric_values["codex"].configure(
            text=_format_bytes(int(codex.get("totalBytes", 0)))
        )
        self.metric_values["projects"].configure(
            text=f"{summary['projects']} / {total_projects}"
        )
        self.metric_values["files"].configure(text=f"{summary['files']:,}")
        self.metric_values["size"].configure(text=_format_bytes(summary["bytes"]))
        self.total_label.configure(
            text=self.parent_app.t(
                "selection_total",
                projects=summary["projects"],
                total=total_projects,
                files=f"{summary['files']:,}",
                size=_format_bytes(summary["bytes"]),
            )
        )

    def _show_details(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        iid = selected[0]
        item = self.preview.get("codex", {}) if iid == "codex" else self.project_by_iid.get(iid)
        if not item:
            return
        folders = item.get("largestFolders", [])
        if not folders:
            detail = self.parent_app.t("selection_details")
        else:
            lines = [self.parent_app.t("selection_folders") + ":"]
            lines.extend(
                f"• {folder['name']} — {_format_bytes(int(folder['totalBytes']))} — "
                f"{int(folder['fileCount']):,} {self.parent_app.t('metric_files').lower()}"
                for folder in folders[:6]
            )
            detail = "\n".join(lines)
        self.details_label.configure(text=detail)

    def _approve(self) -> None:
        excluded = len(self.excluded_paths)
        if excluded and not messagebox.askyesno(
            self.parent_app.t("warning"),
            self.parent_app.t("selection_exclusion_notice", count=excluded),
            parent=self,
        ):
            return
        self.approved = True
        self.destroy()


class PathPortabilityDialog(tk.Toplevel):
    """Explain path audit findings without leaking them into support reports."""

    def __init__(self, parent: tk.Misc, audit: dict) -> None:
        super().__init__(parent)
        self.parent_app = getattr(parent, "parent_app", parent)
        self.audit = audit
        self.findings = list(
            audit.get("_localFindings")
            or (audit.get("_localPortabilityAudit") or {}).get("findings")
            or audit.get("findings")
            or []
        )
        self.item_by_iid: dict[str, dict] = {}
        self.show_paths = tk.BooleanVar(value=False)
        self.title(self.parent_app.t("portability_title"))
        screen_width = max(self.winfo_screenwidth(), 1100)
        screen_height = max(self.winfo_screenheight(), 720)
        width = min(1320, max(1040, int(screen_width * 0.78)))
        height = min(860, max(680, int(screen_height * 0.78)))
        self.geometry(f"{width}x{height}")
        self.minsize(940, 620)
        self.configure(bg=self.parent_app.BG)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build()
        self.grab_set()

    def _label(self, prefix: str, value: str) -> str:
        middle = f"{prefix}_" if prefix else ""
        key = f"portability_{middle}{value.replace('-', '_')}"
        return self.parent_app.t(key)

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        header = tk.Frame(self, bg=self.parent_app.NAVY, padx=26, pady=18)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            header, text=self.parent_app.t("portability_title"),
            bg=self.parent_app.NAVY, fg="#FFFFFF",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header, text=self.parent_app.t("portability_intro"),
            bg=self.parent_app.NAVY, fg="#D5E3F0", font=("Segoe UI", 10),
            justify="left", wraplength=1100,
        ).pack(anchor="w", pady=(5, 0))

        summary = self.audit.get("summary") or (
            self.audit.get("_localPortabilityAudit") or {}
        ).get("summary") or {}
        covered = int(summary.get("translatedReferences", 0)) + int(
            summary.get("excludedMachineStateReferences", 0)
        )
        review = int(summary.get("needsReviewReferences", 0))
        summary_bar = tk.Frame(self, bg=self.parent_app.BG)
        summary_bar.grid(row=1, column=0, sticky="ew", padx=24, pady=12)
        for column, (value, label, color) in enumerate((
            (covered, self.parent_app.t("portability_covered"), self.parent_app.SUCCESS),
            (review, self.parent_app.t("portability_review"), "#C47A00"),
        )):
            card = tk.Frame(
                summary_bar, bg=self.parent_app.CARD,
                highlightbackground=self.parent_app.BORDER, highlightthickness=1,
                padx=16, pady=9,
            )
            card.grid(row=0, column=column, sticky="ew", padx=(0, 8))
            tk.Label(
                card, text=f"{value:,}", bg=self.parent_app.CARD, fg=color,
                font=("Segoe UI", 16, "bold"),
            ).pack(anchor="w")
            tk.Label(
                card, text=label, bg=self.parent_app.CARD,
                fg=self.parent_app.MUTED, font=("Segoe UI", 9),
            ).pack(anchor="w")

        table_frame = tk.Frame(
            self, bg=self.parent_app.CARD,
            highlightbackground=self.parent_app.BORDER, highlightthickness=1,
        )
        table_frame.grid(row=2, column=0, sticky="nsew", padx=24)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("impact", "field", "kind", "references", "exists", "handling")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Selection.Treeview", selectmode="browse",
        )
        headings = {
            "impact": "portability_impact",
            "field": "portability_field",
            "kind": "portability_kind",
            "references": "portability_references",
            "exists": "portability_exists",
            "handling": "portability_handling",
        }
        for column, key in headings.items():
            self.tree.heading(column, text=self.parent_app.t(key))
        self.tree.column("impact", width=150, minwidth=120, stretch=False)
        self.tree.column("field", width=250, minwidth=180)
        self.tree.column("kind", width=150, minwidth=120, stretch=False)
        self.tree.column("references", width=100, minwidth=85, anchor="e", stretch=False)
        self.tree.column("exists", width=125, minwidth=105, stretch=False)
        self.tree.column("handling", width=225, minwidth=180)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure("low", foreground="#0B6B47")
        self.tree.tag_configure("medium", foreground="#9A6200")
        self.tree.tag_configure("high", foreground="#B42318")
        for index, item in enumerate(self.findings):
            iid = f"finding-{index}"
            self.item_by_iid[iid] = item
            impact = str(item.get("impact") or "medium")
            self.tree.insert(
                "", "end", iid=iid,
                values=(
                    self.parent_app.t(f"portability_{impact}"),
                    item.get("schemaField", "—"),
                    self._label("", str(item.get("pathKind") or "external-or-unknown")),
                    f"{int(item.get('occurrences', 0)):,}",
                    self.parent_app.t(
                        "portability_present"
                        if item.get("pathStatus") == "present"
                        else "portability_missing"
                        if item.get("pathStatus") == "missing"
                        else "portability_not_checked"
                    ),
                    self._label("", str(item.get("backupHandling") or "preserved-unchanged")),
                ),
                tags=(impact,),
            )
        self.tree.bind("<<TreeviewSelect>>", self._show_details)

        detail_card = tk.Frame(
            self, bg=self.parent_app.CARD,
            highlightbackground=self.parent_app.BORDER, highlightthickness=1,
            padx=14, pady=10,
        )
        detail_card.grid(row=3, column=0, sticky="ew", padx=24, pady=(10, 0))
        self.detail_label = tk.Label(
            detail_card,
            text=self.parent_app.t("portability_no_details") if not self.findings else "",
            bg=self.parent_app.CARD, fg=self.parent_app.TEXT_COLOR,
            justify="left", anchor="w", wraplength=1100, font=("Segoe UI", 9),
        )
        self.detail_label.pack(fill="x")

        footer = ttk.Frame(self, style="App.TFrame")
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=14)
        ttk.Checkbutton(
            footer, text=self.parent_app.t("portability_show_paths"),
            variable=self.show_paths, command=self._show_details,
        ).pack(side="left")
        ttk.Label(
            footer, text=self.parent_app.t("portability_privacy"),
            style="Muted.TLabel",
        ).pack(side="left", padx=(14, 0))
        ttk.Button(
            footer, text=self.parent_app.t("close"), command=self.destroy,
            style="Secondary.TButton",
        ).pack(side="right")
        if self.findings:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._show_details()

    def _show_details(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item = self.item_by_iid.get(selection[0], {})
        local_paths = list(item.get("localPaths") or [])
        if self.show_paths.get() and local_paths:
            examples = "\n".join(f"• {path}" for path in local_paths)
        else:
            kind = str(item.get("pathKind") or "external-or-unknown")
            placeholder = {
                "profile-relative": "%USERPROFILE%\\…",
                "project-relative": "%PROJECT_ROOT%\\…",
                "external-or-unknown": "%EXTERNAL_OR_OLD_PATH%\\…",
                "old-source-location": "%OLD_COMPUTER_PATH%\\…",
            }.get(kind, "%LOCAL_PATH%\\…")
            examples = f"• {placeholder}"
        impact = str(item.get("impact") or "medium")
        self.detail_label.configure(
            text=self.parent_app.t(
                "portability_detail_text",
                field=item.get("schemaField", "—"),
                source=item.get("source", "—"),
                count=f"{int(item.get('occurrences', 0)):,}",
                included=self.parent_app.t("yes" if item.get("dataIncluded") else "no"),
                translated=self.parent_app.t("yes" if item.get("translationPlanned") else "no"),
                impact=self.parent_app.t(f"portability_{impact}"),
                paths=examples,
            )
        )


class DiagnosticsDialog(tk.Toplevel):
    STATUS_COLORS = {
        diagnostics.STATUS_PASS: "#18A66A",
        diagnostics.STATUS_NOTICE: "#C47A00",
        diagnostics.STATUS_FAIL: "#B42318",
    }

    def __init__(self, parent: "TransferApp", report: dict) -> None:
        super().__init__(parent)
        self.parent_app = parent
        self.report = report
        self.title(parent.t("diagnostics_title"))
        self.geometry("1040x720")
        self.minsize(820, 590)
        self.configure(background=parent.BG)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build()
        self.grab_set()

    def _card(self, parent: tk.Widget, column: int, value: int, label: str) -> None:
        card = tk.Frame(
            parent, bg=self.parent_app.CARD,
            highlightbackground=self.parent_app.BORDER,
            highlightthickness=1, padx=18, pady=12,
        )
        card.grid(
            row=0, column=column, sticky="ew",
            padx=(0 if column == 0 else 6, 0),
        )
        parent.columnconfigure(column, weight=1)
        tk.Label(
            card, text=str(value), bg=self.parent_app.CARD,
            fg=self.parent_app.NAVY, font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card, text=label, bg=self.parent_app.CARD,
            fg=self.parent_app.MUTED, font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

    def _localized_summary(self, item: dict) -> str:
        if self.parent_app.language.get() == "en":
            return str(item.get("summary") or "")
        facts = item.get("facts") or {}
        check_id = item.get("id")
        status = item.get("status")
        if check_id == "windows":
            return (
                f"Windows {facts.get('release', '?')} is geschikt."
                if status == diagnostics.STATUS_PASS
                else "Deze computer gebruikt geen ondersteunde Windows 10/11-omgeving."
            )
        if check_id == "launch_location":
            return (
                "Codex Lifeboat is vanuit een uitgepakte map gestart."
                if status == diagnostics.STATUS_PASS
                else "Codex Lifeboat lijkt rechtstreeks vanuit een ZIP-bestand te zijn gestart."
            )
        if check_id == "codex_data":
            return (
                "De Codex-map en statusdatabase zijn gevonden."
                if status == diagnostics.STATUS_PASS
                else "De Codex-map of statusdatabase ontbreekt."
            )
        if check_id == "codex_readable":
            return (
                "De Codex-map kan worden gelezen."
                if status == diagnostics.STATUS_PASS
                else "De Codex-map kan niet worden gelezen."
            )
        if check_id == "database":
            return (
                "De database is consistent en bevat "
                f"{facts.get('threadCount', 0)} chat(s) en "
                f"{facts.get('projectCount', 0)} geregistreerde project(en)."
                if status == diagnostics.STATUS_PASS
                else "De database kon niet veilig worden gecontroleerd."
            )
        if check_id == "portability_audit":
            return (
                f"{facts.get('coveredReferences', 0)} padverwijzing(en) zijn afgedekt; "
                f"{facts.get('needsReviewReferences', 0)} bewaarde verwijzing(en) in "
                f"{facts.get('fieldsNeedingReview', 0)} veld(en) vragen aandacht. "
                f"{facts.get('missingReviewReferences', 0)} wijzen naar paden die niet meer bestaan. "
                "Back-up en herstel kunnen doorgaan; er worden geen databasegegevens weggelaten."
                if facts.get("needsReviewReferences") or facts.get("scanErrors")
                else f"Alle {facts.get('pathReferences', 0)} gevonden padverwijzingen vallen onder bekende vertaal- of uitsluitingsregels."
            )
        if check_id == "codex_closed":
            return (
                "Codex draait nog; sluit het programma vóór back-up of herstel."
                if facts.get("running")
                else "Codex draait niet."
            )
        if check_id == "installation":
            return (
                f"Codex-installatie versie {facts.get('version', 'onbekend')} is gevonden."
                if facts.get("detected")
                else "De geïnstalleerde Codex-versie kon niet worden vastgesteld."
            )
        if check_id == "removable_storage":
            return (
                f"{facts.get('count', 0)} verwisselbaar opslagapparaat/apparaten gevonden."
                if facts.get("count")
                else "Geen verwisselbare opslag gevonden; u kunt nog steeds handmatig een map kiezen."
            )
        if check_id == "local_space":
            return (
                "Er is minimaal 5 GiB vrije ruimte op het gebruikersvolume."
                if status == diagnostics.STATUS_PASS
                else "Er is minder dan 5 GiB vrije ruimte op het gebruikersvolume."
            )
        if check_id == "recovery_points":
            return (
                f"{facts.get('validPoints', 0)} geldig(e) herstelpunt(en) en "
                f"{facts.get('extraRetainedPoints', 0)} extra bewaard(e) punt(en) gevonden."
            )
        if check_id == "local_state":
            return (
                "De lokale Lifeboat-statusmap is aanwezig."
                if facts.get("present")
                else "Er is nog geen lokale Lifeboat-statusmap; deze wordt aangemaakt wanneer nodig."
            )
        if check_id == "atomic_metadata":
            return (
                f"Alle {facts.get('hardenedStoreCount', 0)} kritieke metadatagroepen "
                "gebruiken gecontroleerde vervanging vanuit dezelfde map."
            )
        return str(item.get("summary") or "")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        body = ttk.Frame(self, padding=(28, 24, 28, 20), style="App.TFrame")
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)

        ttk.Label(
            body, text=self.parent_app.t("diagnostics_title"),
            style="DialogTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body, text=self.parent_app.t("diagnostics_intro"),
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 12))

        summary = self.report.get("summary") or {}
        overall = str(summary.get("overall") or "attention")
        status_key = {
            "ready": "diagnostics_ready",
            "attention": "diagnostics_attention",
            "blocked": "diagnostics_blocked",
        }.get(overall, "diagnostics_attention")
        tk.Label(
            body,
            text="●  " + self.parent_app.t(status_key),
            bg=self.parent_app.BG,
            fg={
                "ready": self.parent_app.SUCCESS,
                "attention": "#C47A00",
                "blocked": "#B42318",
            }.get(overall, "#C47A00"),
            font=("Segoe UI", 11, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(0, 12))

        cards = tk.Frame(body, bg=self.parent_app.BG)
        cards.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self._card(
            cards, 0, int(summary.get("passed", 0)),
            self.parent_app.t("diagnostics_passed"),
        )
        self._card(
            cards, 1, int(summary.get("notices", 0)),
            self.parent_app.t("diagnostics_notices"),
        )
        self._card(
            cards, 2, int(summary.get("failed", 0)),
            self.parent_app.t("diagnostics_failed"),
        )

        table = tk.Frame(
            body, bg=self.parent_app.CARD,
            highlightbackground=self.parent_app.BORDER, highlightthickness=1,
        )
        table.grid(row=4, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table, columns=("status", "check", "result"), show="headings",
            style="Selection.Treeview",
        )
        self.tree.heading("status", text=self.parent_app.t("diagnostics_status"))
        self.tree.heading("check", text=self.parent_app.t("diagnostics_check"))
        self.tree.heading("result", text=self.parent_app.t("diagnostics_result"))
        self.tree.column("status", width=115, minwidth=95, stretch=False)
        self.tree.column("check", width=210, minwidth=160, stretch=False)
        self.tree.column("result", width=620, minwidth=300, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        for status_name, color in self.STATUS_COLORS.items():
            self.tree.tag_configure(status_name, foreground=color)
        self.check_by_iid: dict[str, dict] = {}
        for item in self.report.get("checks", []):
            check_id = str(item.get("id") or "")
            item_status = str(item.get("status") or diagnostics.STATUS_NOTICE)
            iid = self.tree.insert(
                "", "end",
                values=(
                    "●  " + self.parent_app.t(f"diagnostics_{item_status}"),
                    self.parent_app.t(f"diagnostics_{check_id}"),
                    self._localized_summary(item),
                ),
                tags=(item_status,),
            )
            self.check_by_iid[iid] = item
        self.tree.bind("<Double-1>", self._open_selected_details)

        tk.Label(
            body,
            text="🔒  " + self.parent_app.t("diagnostics_privacy"),
            bg="#EAF2FD", fg=self.parent_app.NAVY,
            font=("Segoe UI", 9), anchor="w", justify="left",
            padx=14, pady=10, wraplength=920,
        ).grid(row=5, column=0, sticky="ew", pady=(12, 0))

        actions = ttk.Frame(body, style="App.TFrame")
        actions.grid(row=6, column=0, sticky="e", pady=(14, 0))
        ttk.Button(
            actions, text=self.parent_app.t("portability_details"),
            command=self._open_portability_details, style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            actions, text=self.parent_app.t("diagnostics_copy"),
            command=self._copy, style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(
            actions, text=self.parent_app.t("diagnostics_save"),
            command=self._save, style="Primary.TButton",
        ).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(
            actions, text=self.parent_app.t("close"), command=self.destroy,
            style="Secondary.TButton",
        ).grid(row=0, column=3)

    def _open_selected_details(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item = self.check_by_iid.get(selection[0], {})
        if item.get("id") == "portability_audit":
            self._open_portability_details()

    def _open_portability_details(self) -> None:
        audit = self.report.get("_localPortabilityAudit") or self.report.get(
            "portabilityAudit", {}
        )
        PathPortabilityDialog(self, audit)

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(diagnostics.report_json(self.report))
        self.update_idletasks()
        messagebox.showinfo(
            self.parent_app.t("diagnostics_title"),
            self.parent_app.t("diagnostics_copy_done"), parent=self,
        )

    def _save(self) -> None:
        stamp = str(self.report.get("createdAtUtc") or "")
        stamp = stamp.replace(":", "").replace("-", "").replace("+0000", "Z")
        stamp = stamp.replace("T", "-")[:15]
        destination = filedialog.asksaveasfilename(
            parent=self,
            title=self.parent_app.t("diagnostics_save_title"),
            defaultextension=".json",
            initialfile=f"Codex-Lifeboat-Diagnostics-{stamp or 'report'}.json",
            filetypes=(("JSON", "*.json"), ("All files", "*.*")),
        )
        if not destination:
            return
        path = Path(destination)
        try:
            diagnostics.save_report(path, self.report)
        except OSError as exc:
            messagebox.showerror(
                self.parent_app.t("error"),
                self.parent_app.t(
                    "diagnostics_save_failed", error=type(exc).__name__
                ),
                parent=self,
            )
            return
        messagebox.showinfo(
            self.parent_app.t("diagnostics_title"),
            self.parent_app.t("diagnostics_save_done", path=path), parent=self,
        )


class TransferApp(tk.Tk):
    BG = "#F3F6FA"
    CARD = "#FFFFFF"
    NAVY = "#102A43"
    BLUE = "#1769E0"
    AMBER = "#F4A62A"
    TEXT_COLOR = "#1B2733"
    MUTED = "#60758A"
    BORDER = "#D9E2EC"
    SUCCESS = "#18A66A"

    def __init__(self) -> None:
        super().__init__()
        self.language = tk.StringVar(value="en")
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.launch_blocked = windows.launched_from_compressed_folder()
        self.last_package: Path | None = None
        self.last_version_check: dict | None = None
        self.last_result_model: dict | None = None
        self.last_result_verified = False
        self.geometry("1180x800")
        self.minsize(980, 700)
        self.configure(background=self.BG)
        self._configure_styles()
        self._build()
        self._translate()
        self.bind("<Map>", self._restore_from_taskbar, add="+")
        self.after(100, self._drain_messages)
        self.after(1000, self._refresh_drives)
        if self.launch_blocked:
            for button in self.action_buttons:
                button.configure(state="disabled")
            self.after(250, self._show_extract_required)

    def _restore_from_taskbar(self, _event=None) -> None:
        """Make a restored frozen Tk window reliably return to the foreground."""
        if self.state() == "iconic":
            return
        self.after_idle(self.lift)

    def t(self, key: str, **values) -> str:
        return TEXT[self.language.get()][key].format(**values)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=self.BG)
        style.configure(
            "DialogTitle.TLabel", background=self.BG, foreground=self.NAVY,
            font=("Segoe UI", 20, "bold")
        )
        style.configure(
            "Body.TLabel", background=self.BG, foreground=self.TEXT_COLOR,
            font=("Segoe UI", 9)
        )
        style.configure("Header.TFrame", background=self.NAVY)
        style.configure(
            "Title.TLabel", background=self.NAVY, foreground="#FFFFFF",
            font=("Segoe UI", 24, "bold")
        )
        style.configure(
            "Subtitle.TLabel", background=self.NAVY, foreground="#C9D8E8",
            font=("Segoe UI", 10)
        )
        style.configure(
            "Header.TLabel", background=self.NAVY, foreground="#DCE8F4",
            font=("Segoe UI", 9)
        )
        style.configure(
            "Card.TLabelframe", background=self.CARD, bordercolor=self.BORDER,
            relief="solid", borderwidth=1
        )
        style.configure(
            "Card.TLabelframe.Label", background=self.BG, foreground=self.NAVY,
            font=("Segoe UI", 10, "bold")
        )
        style.configure(
            "Field.TLabel", background=self.CARD, foreground=self.MUTED,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Value.TLabel", background=self.CARD, foreground=self.TEXT_COLOR,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Action.TButton", background=self.CARD, foreground=self.TEXT_COLOR,
            bordercolor=self.BORDER, lightcolor=self.CARD, darkcolor=self.CARD,
            font=("Segoe UI", 10, "bold"), padding=(16, 15), relief="solid"
        )
        style.map(
            "Action.TButton",
            background=[("active", "#EAF2FD"), ("disabled", "#EEF2F6")],
            foreground=[("active", self.BLUE), ("disabled", "#91A1B2")],
            bordercolor=[("active", self.BLUE)],
        )
        style.configure(
            "Primary.TButton", background=self.BLUE, foreground="#FFFFFF",
            bordercolor=self.BLUE, font=("Segoe UI", 10, "bold"),
            padding=(18, 10), relief="solid"
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#0E57C7"), ("disabled", "#A9BED8")],
            foreground=[("active", "#FFFFFF"), ("disabled", "#EEF3F8")],
        )
        style.configure(
            "HeroPrimary.TButton", background=self.AMBER, foreground=self.NAVY,
            bordercolor=self.AMBER, font=("Segoe UI", 10, "bold"),
            padding=(18, 10), relief="solid"
        )
        style.map(
            "HeroPrimary.TButton",
            background=[("active", "#FFB83E"), ("disabled", "#E4D3AE")],
            foreground=[("active", self.NAVY), ("disabled", "#7E8791")],
        )
        style.configure(
            "CardAction.TButton", background=self.CARD, foreground=self.NAVY,
            bordercolor=self.BORDER, font=("Segoe UI", 10, "bold"),
            padding=(18, 10), relief="solid"
        )
        style.map(
            "CardAction.TButton",
            background=[("active", "#EAF2FD"), ("disabled", "#EEF2F6")],
            foreground=[("active", self.BLUE), ("disabled", "#91A1B2")],
            bordercolor=[("active", self.BLUE)],
        )
        style.configure(
            "Secondary.TButton", background=self.CARD, foreground=self.NAVY,
            bordercolor=self.BORDER, font=("Segoe UI", 9, "bold"),
            padding=(12, 8), relief="solid"
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#EAF2FD")],
            foreground=[("active", self.BLUE)],
            bordercolor=[("active", self.BLUE)],
        )
        style.configure(
            "Selection.Treeview", background=self.CARD,
            fieldbackground=self.CARD, foreground=self.TEXT_COLOR,
            bordercolor=self.BORDER, rowheight=34, font=("Segoe UI", 9)
        )
        style.map(
            "Selection.Treeview",
            background=[("selected", self.BLUE)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.configure(
            "Selection.Treeview.Heading", background="#EAF0F6",
            foreground=self.NAVY, bordercolor=self.BORDER,
            font=("Segoe UI", 9, "bold"), padding=(8, 9)
        )
        style.configure(
            "Status.TLabel", background=self.BG, foreground=self.TEXT_COLOR,
            font=("Segoe UI", 9, "bold")
        )
        style.configure(
            "Section.TLabel", background=self.BG, foreground=self.NAVY,
            font=("Segoe UI", 10, "bold")
        )
        style.configure(
            "Lifeboat.Horizontal.TProgressbar", background=self.SUCCESS,
            troughcolor="#DCE4EC", bordercolor="#DCE4EC", lightcolor=self.SUCCESS,
            darkcolor=self.SUCCESS, thickness=10
        )
        style.configure(
            "Language.TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF",
            foreground=self.TEXT_COLOR, arrowcolor=self.NAVY, padding=5
        )

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = tk.Frame(self, bg=self.NAVY, width=244)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)

        logo = tk.Canvas(
            sidebar, width=62, height=62, bg=self.NAVY,
            highlightthickness=0, borderwidth=0
        )
        logo.create_oval(5, 5, 57, 57, fill="#FFFFFF", outline="")
        logo.create_rectangle(25, 2, 37, 22, fill=self.AMBER, outline="")
        logo.create_rectangle(25, 40, 37, 60, fill=self.AMBER, outline="")
        logo.create_rectangle(2, 25, 22, 37, fill=self.AMBER, outline="")
        logo.create_rectangle(40, 25, 60, 37, fill=self.AMBER, outline="")
        logo.create_oval(20, 20, 42, 42, fill=self.NAVY, outline="")
        logo.grid(row=0, column=0, pady=(28, 10))
        self.title_label = tk.Label(
            sidebar, bg=self.NAVY, fg="#FFFFFF", font=("Segoe UI", 15, "bold"),
            anchor="center"
        )
        self.title_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 24))
        self.subtitle_label = tk.Label(sidebar, text="", bg=self.NAVY)

        def nav_button(row: int, command) -> tk.Button:
            button = tk.Button(
                sidebar, command=command, anchor="w", relief="flat", borderwidth=0,
                bg=self.NAVY, fg="#DCE8F4", activebackground="#1E4668",
                activeforeground="#FFFFFF", disabledforeground="#8297AA",
                font=("Segoe UI", 10, "bold"), padx=24, pady=12,
                cursor="hand2"
            )
            button.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
            return button

        self.overview_button = nav_button(2, lambda: self.main_panel.focus_set())
        self.nav_backup_button = nav_button(3, self._backup)
        self.nav_restore_button = nav_button(4, self._restore)
        self.nav_recovery_button = nav_button(5, self._manage_recovery)
        self.nav_diagnostics_button = nav_button(6, self._diagnostics)
        self.overview_button.configure(bg="#1E4668", fg="#FFFFFF")

        self.sidebar_note = tk.Label(
            sidebar, bg=self.NAVY, fg="#9FB4C8", justify="left", wraplength=196,
            font=("Segoe UI", 8)
        )
        self.sidebar_note.grid(row=7, column=0, sticky="sw", padx=24, pady=22)
        sidebar.rowconfigure(7, weight=1)

        self.main_panel = ttk.Frame(self, style="App.TFrame", padding=(28, 22, 28, 20))
        self.main_panel.grid(row=0, column=1, sticky="nsew")
        self.main_panel.columnconfigure(0, weight=1)
        self.main_panel.rowconfigure(7, weight=1)

        header = ttk.Frame(self.main_panel, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        self.overview_title = ttk.Label(
            header, style="DialogTitle.TLabel", font=("Segoe UI", 22, "bold")
        )
        self.overview_title.grid(row=0, column=0, sticky="w")
        self.overview_subtitle = ttk.Label(header, style="Body.TLabel")
        self.overview_subtitle.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.header_status = tk.Label(
            header, bg="#E8F7EF", fg="#128250", font=("Segoe UI", 9, "bold"),
            padx=12, pady=6
        )
        self.header_status.grid(row=0, column=1, rowspan=2, padx=(12, 16))
        self.language_label = ttk.Label(header, style="Body.TLabel")
        self.language_label.grid(row=0, column=2, rowspan=2, padx=(0, 6))
        self.language_box = ttk.Combobox(
            header, state="readonly", width=11,
            values=("English", "Nederlands"), style="Language.TCombobox"
        )
        self.language_box.current(0 if self.language.get() == "en" else 1)
        self.language_box.grid(row=0, column=3, rowspan=2)
        self.language_box.bind("<<ComboboxSelected>>", self._change_language)

        self.detection = ttk.LabelFrame(
            self.main_panel, padding=(16, 11), style="Card.TLabelframe"
        )
        self.detection.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.detection.columnconfigure(1, weight=1)
        self.detection.columnconfigure(3, weight=1)
        self.codex_label = ttk.Label(self.detection, style="Field.TLabel")
        self.codex_label.grid(row=0, column=0, sticky="w")
        self.codex_value = ttk.Label(
            self.detection, text=str(Path.home() / ".codex"), style="Value.TLabel"
        )
        self.codex_value.grid(row=0, column=1, sticky="w", padx=(10, 22))
        self.usb_label = ttk.Label(self.detection, style="Field.TLabel")
        self.usb_label.grid(row=0, column=2, sticky="w")
        drives = windows.removable_drives()
        self.usb_value = ttk.Label(
            self.detection, text=", ".join(map(str, drives)) or "—", style="Value.TLabel"
        )
        self.usb_value.grid(row=0, column=3, sticky="w", padx=(10, 0))

        actions = ttk.Frame(self.main_panel, style="App.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        backup_card = tk.Frame(
            actions, bg=self.NAVY, highlightbackground=self.NAVY,
            highlightthickness=1, padx=22, pady=18
        )
        backup_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.backup_heading = tk.Label(
            backup_card, bg=self.NAVY, fg="#FFFFFF", anchor="w",
            font=("Segoe UI", 15, "bold")
        )
        self.backup_heading.pack(fill="x")
        self.backup_description = tk.Label(
            backup_card, bg=self.NAVY, fg="#C9D8E8", anchor="w",
            font=("Segoe UI", 9), pady=5
        )
        self.backup_description.pack(fill="x")
        backup_actions = tk.Frame(backup_card, bg=self.NAVY)
        backup_actions.pack(fill="x", pady=(10, 0))
        self.backup_button = ttk.Button(
            backup_actions, command=self._backup, style="HeroPrimary.TButton"
        )
        self.backup_button.pack(side="left")
        self.verify_backup_button = tk.Button(
            backup_actions, command=self._verify_backup, relief="flat", borderwidth=0,
            bg=self.NAVY, fg="#FFFFFF", activebackground="#1E4668",
            activeforeground="#FFFFFF", disabledforeground="#8297AA",
            font=("Segoe UI", 9, "bold"), padx=14, pady=8, cursor="hand2"
        )
        self.verify_backup_button.pack(side="left", padx=(10, 0))

        restore_card = tk.Frame(
            actions, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, padx=22, pady=18
        )
        restore_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.restore_heading = tk.Label(
            restore_card, bg=self.CARD, fg=self.NAVY, anchor="w",
            font=("Segoe UI", 15, "bold")
        )
        self.restore_heading.pack(fill="x")
        self.restore_description = tk.Label(
            restore_card, bg=self.CARD, fg=self.MUTED, anchor="w",
            font=("Segoe UI", 9), pady=5
        )
        self.restore_description.pack(fill="x")
        restore_actions = tk.Frame(restore_card, bg=self.CARD)
        restore_actions.pack(fill="x", pady=(10, 0))
        self.restore_button = ttk.Button(
            restore_actions, command=self._restore, style="CardAction.TButton"
        )
        self.restore_button.pack(side="left")
        self.verify_restore_button = ttk.Button(
            restore_actions, command=self._verify_restore, style="Secondary.TButton"
        )
        self.verify_restore_button.pack(side="left", padx=(10, 0))

        metrics = ttk.Frame(self.main_panel, style="App.TFrame")
        metrics.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        for column in range(3):
            metrics.columnconfigure(column, weight=1)

        def metric_card(column: int):
            card = tk.Frame(
                metrics, bg=self.CARD, highlightbackground=self.BORDER,
                highlightthickness=1, padx=16, pady=12
            )
            card.grid(
                row=0, column=column, sticky="nsew",
                padx=(0 if column == 0 else 6, 0 if column == 2 else 6)
            )
            heading = tk.Label(
                card, bg=self.CARD, fg=self.MUTED, anchor="w",
                font=("Segoe UI", 8)
            )
            heading.pack(fill="x")
            value = tk.Label(
                card, bg=self.CARD, fg=self.NAVY, anchor="w",
                font=("Segoe UI", 12, "bold")
            )
            value.pack(fill="x", pady=(4, 0))
            return heading, value

        self.latest_heading, self.latest_value = metric_card(0)
        self.included_heading, self.included_value = metric_card(1)
        self.storage_heading, self.storage_value = metric_card(2)

        status_frame = ttk.Frame(self.main_panel, style="App.TFrame")
        status_frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        status_frame.columnconfigure(1, weight=1)
        self.status_dot = tk.Label(
            status_frame, text="●", bg=self.BG, fg=self.SUCCESS,
            font=("Segoe UI", 10), borderwidth=0
        )
        self.status_dot.grid(row=0, column=0, sticky="w")
        self.status_label = ttk.Label(status_frame, style="Status.TLabel")
        self.status_label.grid(row=0, column=1, sticky="w", padx=(5, 0))
        self.progress = ttk.Progressbar(
            status_frame, mode="indeterminate", style="Lifeboat.Horizontal.TProgressbar"
        )
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))

        self.result_frame = tk.Frame(
            self.main_panel,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            padx=18,
            pady=12,
        )
        self.result_frame.grid(row=5, column=0, sticky="ew", pady=(2, 8))
        self.result_frame.columnconfigure(1, weight=1)
        self.result_title = tk.Label(
            self.result_frame,
            bg=self.CARD,
            fg=self.NAVY,
            font=("Segoe UI", 10, "bold"),
        )
        self.result_title.grid(row=0, column=0, sticky="w")
        self.result_status = tk.Label(
            self.result_frame,
            bg=self.CARD,
            fg=self.SUCCESS,
            font=("Segoe UI", 9, "bold"),
        )
        self.result_status.grid(row=0, column=1, sticky="w", padx=(14, 0))
        self.result_metrics = tk.Label(
            self.result_frame,
            bg=self.CARD,
            fg=self.TEXT_COLOR,
            font=("Segoe UI", 9),
        )
        self.result_metrics.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        self.result_path = tk.Label(
            self.result_frame,
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.result_path.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.result_frame.grid_remove()

        log_frame = ttk.Frame(self.main_panel, style="App.TFrame")
        log_frame.grid(row=7, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        self.activity_label = ttk.Label(log_frame, style="Section.TLabel")
        self.activity_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.log = tk.Text(
            log_frame, height=7, wrap="word", state="disabled",
            font=("Cascadia Mono", 9), background="#14212E", foreground="#DCE7F2",
            insertbackground="#FFFFFF", selectbackground=self.BLUE,
            borderwidth=0, padx=13, pady=11
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.recovery_button = self.nav_recovery_button
        self.diagnostics_button = self.nav_diagnostics_button
        self.action_buttons = (
            self.backup_button,
            self.verify_backup_button,
            self.restore_button,
            self.verify_restore_button,
            self.nav_backup_button,
            self.nav_restore_button,
            self.nav_recovery_button,
            self.nav_diagnostics_button,
        )

    def _change_language(self, _event=None) -> None:
        self.language.set("en" if self.language_box.current() == 0 else "nl")
        self._translate()

    def _refresh_drives(self) -> None:
        try:
            drives = windows.removable_drives()
            self.usb_value.configure(text=", ".join(map(str, drives)) or "—")
        except Exception:
            pass
        finally:
            self.after(2000, self._refresh_drives)

    def _show_extract_required(self) -> None:
        messagebox.showerror(
            self.t("error"), self.t("extract_required"), parent=self
        )

    def _translate(self) -> None:
        self.title(self.t("title"))
        self.title_label.configure(text=self.t("title"))
        self.subtitle_label.configure(text=self.t("subtitle"))
        self.sidebar_note.configure(text=self.t("subtitle"))
        self.overview_title.configure(text=self.t("overview"))
        self.overview_subtitle.configure(text=self.t("overview_subtitle"))
        self.overview_button.configure(text="⌂   " + self.t("overview"))
        self.nav_backup_button.configure(text="↑   " + self.t("nav_backup"))
        self.nav_restore_button.configure(text="↓   " + self.t("nav_restore"))
        self.nav_recovery_button.configure(text="↶   " + self.t("recovery"))
        self.nav_diagnostics_button.configure(text="✓   " + self.t("diagnostics"))
        self.language_label.configure(text=self.t("language"))
        self.detection.configure(text=self.t("computer"))
        self.codex_label.configure(text=self.t("codex_home") + ":")
        self.usb_label.configure(text=self.t("usb") + ":")
        self.backup_button.configure(text=self.t("backup"))
        self.verify_backup_button.configure(text=self.t("verify_backup"))
        self.restore_button.configure(text=self.t("restore"))
        self.verify_restore_button.configure(text=self.t("verify_restore"))
        self.backup_heading.configure(text=self.t("backup"))
        self.restore_heading.configure(text=self.t("restore"))
        self.backup_description.configure(text=self.t("backup_description"))
        self.restore_description.configure(text=self.t("restore_description"))
        self.latest_heading.configure(text=self.t("latest_backup"))
        self.included_heading.configure(text=self.t("included"))
        self.storage_heading.configure(text=self.t("storage"))
        self.activity_label.configure(text=self.t("activity"))
        self._render_last_result()
        if self.launch_blocked:
            self.status_label.configure(text=self.t("extract_status"))
            self.header_status.configure(
                text="●  " + self.t("warning"), bg="#FFF4E5", fg="#A15C00"
            )
        else:
            self.status_label.configure(text=self.t("working") if self.busy else self.t("ready"))
            self.header_status.configure(
                text="●  " + (self.t("working") if self.busy else self.t("ready")),
                bg="#EAF2FD" if self.busy else "#E8F7EF",
                fg=self.BLUE if self.busy else "#128250",
            )

    def _render_last_result(self) -> None:
        model = self.last_result_model
        if not model:
            self.result_frame.grid_remove()
            self.latest_value.configure(text=self.t("no_backup_yet"))
            self.included_value.configure(text="—")
            self.storage_value.configure(text="—")
            return
        status_key = (
            "result_invalid"
            if not model["valid"]
            else "result_valid_warnings"
            if model["warningCount"]
            else "result_valid"
        )
        title_key = (
            "result_verify_title" if self.last_result_verified else "result_backup_title"
        )
        self.result_title.configure(text=self.t("last_result") + ": " + self.t(title_key))
        self.result_status.configure(
            text="●  " + self.t(status_key),
            fg=self.SUCCESS if model["valid"] else "#B42318",
        )
        metrics = model["metrics"]
        self.latest_value.configure(text=self.t(status_key))
        self.included_value.configure(
            text=(
                f"{metrics['projects']} {self.t('metric_projects').lower()} · "
                f"{metrics['chats']} {self.t('metric_chats').lower()}"
            )
        )
        self.storage_value.configure(text=_format_bytes(metrics["bytes"]))
        self.result_metrics.configure(
            text=(
                f"{self.t('metric_chats')}: {metrics['chats']}    "
                f"{self.t('metric_projects')}: {metrics['projects']}    "
                f"{self.t('metric_files')}: {metrics['files']}    "
                f"{self.t('metric_size')}: {_format_bytes(metrics['bytes'])}"
            )
        )
        self.result_path.configure(text=model["package"])
        self.result_frame.grid()

    def _show_backup_result(self, package: Path, validation: dict | None = None) -> None:
        self.last_package = package.resolve(strict=False)
        self.last_result_verified = validation is not None
        self.last_result_model = _backup_result_model(self.last_package, validation)
        self._render_last_result()
        BackupResultDialog(
            self, self.last_result_model, self.last_result_verified
        )

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_messages(self) -> None:
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(value))
            elif kind == "progress":
                current, total, message = value
                self.progress.stop()
                if int(total) <= 0:
                    self.progress.configure(mode="indeterminate", value=0)
                    self.progress.start(10)
                else:
                    self.progress.configure(
                        mode="determinate",
                        maximum=max(int(total), 1),
                        value=min(int(current), max(int(total), 1)),
                    )
                self.status_label.configure(text=str(message))
            elif kind == "done":
                self._set_busy(False)
                callback, result = value
                callback(result)
            elif kind == "error":
                self._set_busy(False)
                self._append_log(str(value))
                messagebox.showerror(self.t("error"), str(value), parent=self)
        self.after(100, self._drain_messages)

    def _set_busy(self, value: bool) -> None:
        self.busy = value
        self.status_dot.configure(fg=self.BLUE if value else self.SUCCESS)
        for button in self.action_buttons:
            button.configure(
                state="disabled" if value or self.launch_blocked else "normal"
            )
        if value:
            self.progress.configure(mode="indeterminate", value=0)
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.configure(mode="indeterminate", value=0)
        self._translate()

    def _run(self, function, done) -> None:
        if self.launch_blocked:
            self._show_extract_required()
            return
        if self.busy:
            return
        self._set_busy(True)

        def worker():
            try:
                result = function()
                self.messages.put(("done", (done, result)))
            except Exception as exc:
                self.messages.put(("log", traceback.format_exc()))
                self.messages.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _log_callback(self, message: str) -> None:
        self.messages.put(("log", message))

    def _status_callback(self, current: int, total: int, message: str) -> None:
        self.messages.put(("progress", (current, total, message)))

    def _version_permission(self) -> bool:
        installed = windows.installed_codex_version()
        latest = windows.latest_version_check(installed)
        self.last_version_check = {"installed": installed, "latest": latest}
        if latest.get("isLatest") is not False:
            self._append_log(str(latest.get("message") or "Version check unavailable"))
            return True
        return messagebox.askyesno(
            self.t("warning"),
            self.t(
                "version_warning",
                message=latest.get("message"),
                installed=installed.get("version") or "?",
                latest=latest.get("latestVersion") or "?",
            ),
            parent=self,
        )

    def _initial_destination(self) -> str:
        drives = windows.removable_drives()
        return str(drives[0]) if drives else str(Path.home() / "Documents")

    def _choose_package(self) -> Path | None:
        detected = windows.detect_backup_packages()
        if detected and messagebox.askyesno(
            self.t("verify_backup"),
            self.t("detected_backup", path=detected[0]),
            parent=self,
        ):
            return detected[0]
        initial = str(detected[0].parent if detected else Path.home())
        selected = filedialog.askdirectory(
            title=self.t("choose_backup"), initialdir=initial, parent=self
        )
        return Path(selected) if selected else None

    def _backup(self) -> None:
        if not self._version_permission():
            return
        backup.set_progress_callback(self._log_callback)
        backup.set_status_callback(self._status_callback)

        def preview_work():
            return backup.build_backup_preview()

        self._run(preview_work, self._continue_backup_from_preview)

    def _continue_backup_from_preview(self, preview: dict) -> None:
        # The selection window is intentionally non-modal so Windows can restore
        # it from the taskbar; keep the main actions inactive until it closes.
        for button in self.action_buttons:
            button.configure(state="disabled")
        dialog = BackupSelectionDialog(self, preview)
        self.wait_window(dialog)
        for button in self.action_buttons:
            button.configure(
                state="disabled" if self.launch_blocked else "normal"
            )
        if not dialog.approved:
            return
        drives = windows.removable_drives()
        if len(drives) == 1:
            selected = str(drives[0] / "Codex Backups")
        else:
            selected = filedialog.askdirectory(
                title=self.t("choose_destination"),
                initialdir=self._initial_destination(),
                parent=self,
            )
        if not selected:
            return
        summary = dialog.selected_summary
        if not messagebox.askyesno(
            self.t("backup"),
            self.t(
                "confirm_backup_selection",
                path=selected,
                projects=summary["projects"],
                files=f"{summary['files']:,}",
                size=_format_bytes(summary["bytes"]),
            ),
            parent=self,
        ):
            return

        def work():
            config_root = Path(tempfile.gettempdir()) / "Codex-Lifeboat"
            config_root.mkdir(parents=True, exist_ok=True)
            config_path = config_root / "backup-config.json"
            atomic_io.write_json(
                config_path,
                {
                    "configVersion": 1,
                    "destinationRoot": selected,
                    "includeAttachments": True,
                    "projects": [],
                    "excludedProjectPaths": dialog.excluded_paths,
                    "additionalPortablePaths": [],
                    "excludeDirectoryNames": [],
                    "versionCheck": self.last_version_check,
                    "knownFolders": windows.known_folders(),
                },
            )
            backup.set_progress_callback(self._log_callback)
            backup.set_status_callback(self._status_callback)
            args = argparse.Namespace(
                config=str(config_path),
                destination=selected,
                source_profile=None,
                source_codex_home=None,
                allow_running_test=False,
            )
            return backup.build_backup(args)

        def done(path):
            self._show_backup_result(Path(path))

        self._run(work, done)

    def _verify_backup(self) -> None:
        package = self._choose_package()
        if not package:
            return

        def done(result):
            if result["valid"]:
                self._show_backup_result(package, result)
            else:
                messagebox.showerror(
                    self.t("error"),
                    self.t("invalid_backup", errors="\n".join(result["errors"][:10])),
                    parent=self,
                )

        self._run(
            lambda: validate(
                package,
                False,
                progress=lambda current, total, message: self._status_callback(
                    current, total, message
                ),
            ),
            done,
        )

    def _manage_recovery(self) -> None:
        self._run(
            lambda: recovery.list_points(Path.home()),
            lambda result: RecoveryDialog(self, result),
        )

    def _diagnostics(self) -> None:
        self._append_log(self.t("diagnostics_running"))
        self._run(
            diagnostics.build_report,
            lambda result: DiagnosticsDialog(self, result),
        )

    def _clean_recovery(self, dialog: RecoveryDialog) -> None:
        if not messagebox.askyesno(
            self.t("recovery_title"), self.t("recovery_confirm"), parent=dialog
        ):
            return
        dialog.destroy()

        def done(result):
            messagebox.showinfo(
                self.t("recovery_title"),
                self.t(
                    "recovery_cleaned",
                    points=len(result.get("removedPoints", [])),
                    size=_format_bytes(int(result.get("bytesFreed", 0))),
                    retained=result.get("validPointsAfter", 0),
                ),
                parent=self,
            )
            self._manage_recovery()

        self._run(
            lambda: recovery.enforce_retention(
                Path.home(), progress=self._log_callback
            ),
            done,
        )

    def _map_project_locations(self, package: Path) -> dict[str, str] | None:
        mappings = backup.read_json(package / "manifest" / "path-mappings.json")
        if mappings.get("mappingVersion") != 2:
            return {}
        registry_path = windows.location_mapping_registry_path(Path.home())
        registry = location_mapper.load_registry(registry_path)
        selected = location_mapper.external_roots(registry)
        requirements: dict[str, dict] = {}
        for item in mappings.get("projects", []):
            location = item.get("location") or {}
            if location.get("kind") != "external-root" or not item.get(
                "sourcePresent", True
            ):
                continue
            root_id = str(location.get("rootId"))
            requirements.setdefault(
                root_id,
                {
                    "rootId": root_id,
                    "sourceRootHint": str(location.get("sourceRootHint") or ""),
                },
            )

        for root_id, requirement in requirements.items():
            remembered = selected.get(root_id)
            if remembered:
                remembered_errors = location_mapper.validate_external_root(
                    Path(remembered), Path.home(), package
                )
                if not remembered_errors:
                    continue
                selected.pop(root_id, None)
                messagebox.showwarning(
                    self.t("warning"),
                    self.t("map_external_invalid", errors="\n".join(remembered_errors)),
                    parent=self,
                )

            source_hint = requirement["sourceRootHint"]
            while root_id not in selected:
                answer = messagebox.askyesnocancel(
                    self.t("map_external_title"),
                    self.t("map_external_question", source=source_hint or "—"),
                    parent=self,
                )
                if answer is None:
                    messagebox.showinfo(
                        self.t("restore"), self.t("map_external_skipped"), parent=self
                    )
                    return None
                if answer:
                    candidate = Path(source_hint)
                else:
                    initial = Path(source_hint).parent if source_hint else Path.home()
                    if not initial.exists():
                        initial = Path.home()
                    chosen = filedialog.askdirectory(
                        title=self.t("map_external_choose"),
                        initialdir=str(initial),
                        mustexist=False,
                        parent=self,
                    )
                    if not chosen:
                        messagebox.showinfo(
                            self.t("restore"),
                            self.t("map_external_skipped"),
                            parent=self,
                        )
                        return None
                    candidate = Path(chosen)
                errors = location_mapper.validate_external_root(
                    candidate, Path.home(), package
                )
                if errors:
                    messagebox.showerror(
                        self.t("error"),
                        self.t("map_external_invalid", errors="\n".join(errors)),
                        parent=self,
                    )
                    continue
                selected[root_id] = str(candidate.resolve(strict=False))

        plan = restore.plan_restore_locations(package, Path.home(), selected)
        if not plan.get("ready"):
            errors = [item.get("error", "?") for item in plan.get("issues", [])]
            if plan.get("requiredExternalRoots"):
                errors.append("External project mapping is incomplete.")
            messagebox.showerror(
                self.t("error"),
                self.t("map_failed", errors="\n".join(errors)),
                parent=self,
            )
            return None
        if not requirements:
            return {}
        review = "\n".join(
            f"• {item.get('name')}: {item.get('targetPath')}"
            for item in plan.get("items", [])
        )
        if not messagebox.askyesno(
            self.t("map_external_title"),
            self.t("map_review", mappings=review or "—"),
            parent=self,
        ):
            return None
        chosen_external = {
            root_id: selected[root_id]
            for root_id in requirements
            if root_id in selected
        }
        location_mapper.remember_external_roots(
            registry, chosen_external, backup.utc_now()
        )
        location_mapper.save_registry(registry_path, registry)
        return chosen_external

    def _restore(self) -> None:
        messagebox.showinfo(self.t("restore"), self.t("restore_intro"), parent=self)
        if not self._version_permission():
            return
        package = self._choose_package()
        if not package:
            return
        external_roots = self._map_project_locations(package)
        if external_roots is None:
            return

        def preview_done(plan):
            dialog = RestorePlanDialog(self, plan)
            self.wait_window(dialog)
            if not dialog.approved:
                return
            self._execute_restore(package, external_roots, dialog.plan)

        self._run(
            lambda: restore_plan.build_restore_plan(
                package,
                Path.home(),
                external_roots,
                progress=lambda current, total, message: self._status_callback(
                    current, total, message
                ),
            ),
            preview_done,
        )

    def _execute_restore(
        self, package: Path, external_roots: dict[str, str], comparison_plan: dict
    ) -> None:

        def work():
            prepared = restore.prepare_restore(
                package,
                Path.home(),
                self._log_callback,
                allow_running_test=False,
                external_roots=external_roots,
                comparison_plan=comparison_plan,
            )
            confirmation = threading.Event()
            answer: list[bool] = []

            def ask():
                answer.append(
                    messagebox.askyesno(
                        self.t("restore"),
                        self.t(
                            "restore_confirm",
                            safety=prepared["safetyRoot"],
                            threads=prepared["targetThreadsBefore"],
                            projects=prepared["targetProjectsBefore"],
                        ),
                        parent=self,
                    )
                )
                confirmation.set()

            self.after(0, ask)
            confirmation.wait()
            if not answer or not answer[0]:
                return {"cancelled": True, **prepared}
            return restore.restore_backup(
                package,
                Path.home(),
                Path(prepared["safetyRoot"]),
                self._log_callback,
                external_roots=external_roots,
            )

        def done(result):
            if result.get("cancelled"):
                messagebox.showinfo(
                    self.t("restore"), self.t("restore_cancelled"), parent=self
                )
            else:
                self.last_package = package
                retention = result.get("recoveryRetention", {})
                messagebox.showinfo(
                    self.t("restore"),
                    self.t(
                        "restore_done_retention",
                        safety=result["safetyRoot"],
                        retained=retention.get("validPointsAfter", 1),
                        size=_format_bytes(int(retention.get("totalBytesAfter", 0))),
                    ),
                    parent=self,
                )

        self._run(work, done)

    def _verify_restore(self) -> None:
        package = self._choose_package()
        if not package:
            return

        def done(result):
            if result["valid"]:
                path_check = result["checks"].get("pathPortability", {})
                needs_review = int(path_check.get("needsReviewReferences", 0))
                messagebox.showinfo(
                    self.t("verify_restore"),
                    self.t(
                        "valid_restore_notice" if needs_review else "valid_restore",
                        threads=result["checks"].get("threads", 0),
                        projects=result["checks"].get("projects", 0),
                        paths=needs_review,
                        old=int(path_check.get("oldSourceReferences", 0)),
                    ),
                    parent=self,
                )
            else:
                messagebox.showerror(
                    self.t("error"), "\n".join(result["errors"][:10]), parent=self
                )

        self._run(lambda: restore.verify_restored(package, Path.home()), done)


def run_gui() -> None:
    app = TransferApp()
    app.mainloop()
