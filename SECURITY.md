# Beveiliging

Back-uppakketten zijn niet versleuteld. Zij kunnen broncode, `.env`-bestanden,
API-sleutels en andere vertrouwelijke projectbestanden bevatten. Bewaar de USB-stick
veilig en deel back-uppakketten niet zonder de inhoud eerst te controleren.

De applicatie kopieert bewust geen `auth.json`, installatie-id's, sandboxgeheimen,
locks of actieve runtimebestanden naar een andere computer. Bij herstel blijven de
lokale identiteit en aanmelding van de doelcomputer behouden.

Publiceer geen werkelijk back-uppakket in deze Git-repository. Gebruik voor testen
alleen kunstmatige gegevens zoals de meegeleverde zelftest doet.
