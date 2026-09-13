# MIGIELS — centralny katalog taryf stałych w Polsce

Publiczny, deklaratywny katalog zweryfikowanych taryf stałych dla aplikacji
MIGIELS for Home Assistant. Repozytorium nie zawiera kodu aplikacji, konfiguracji
Home Assistant, danych instalacji, danych użytkowników ani danych dostępowych.

## Publiczne adresy

- manifest: `https://raw.githubusercontent.com/SmartServicePL/migiels-tariffs-pl/main/manifest.json`
- status ostatniej poprawnej kontroli źródeł:
  `https://raw.githubusercontent.com/SmartServicePL/migiels-tariffs-pl/main/status.json`

Klient pobiera manifest i wskazane przez niego niezmienne obiekty anonimowo po
HTTPS. Manifest zawiera SHA-256 oraz rozmiar każdego obiektu. Poprzednie obiekty
nie są usuwane, dzięki czemu starszy poprawny manifest pozostający w cache nadal
może zostać odtworzony.

## Zakres publikacji 2026

Katalog obejmuje oficjalnie zatwierdzone na 2026 r. taryfy domowe czterech
sprzedawców z urzędu na obszarach ich operatorów: PGE Obrót / PGE Dystrybucja,
TAURON Sprzedaż / TAURON Dystrybucja, ENEA / ENEA Operator oraz ENERGA-OBRÓT /
ENERGA-OPERATOR. Obejmuje również oficjalną taryfę E.ON Polska, ustaloną przez
sprzedawcę dla odbiorców w sieci Stoen Operator. URE wskazuje, że na tym
obszarze sprzedawca z urzędu jest zwolniony z obowiązku przedstawiania taryfy
do zatwierdzenia regulatorowi. Publikowane wartości są cenami brutto energii
czynnej i nie obejmują dystrybucji ani dodatkowych opłat.

Obsługiwane profile:

- PGE: G11, G12, G12w, G12n;
- TAURON: G11, G12, G12w, G13;
- ENEA: G11, G12w;
- Energa: G11, G12, G12w, G12r;
- E.ON / Stoen: G11, G12, G12w, G12as.

ENEA G12 nie jest publikowana, ponieważ operator wyznacza konkretne godziny
dwóch części strefy nocnej dla danego układu pomiarowego. Brak tego rekordu jest
zamierzonym zachowaniem fail-closed, a nie ceną zerową ani podstawą do użycia
profilu innego operatora.

Źródła oficjalne:

- [Taryfa ENERGA-OBRÓT S.A. dla grup G od 1 stycznia 2026 r.](https://www.energa.pl/dam/jcr:1f730159-7aab-4815-8a17-e0f6f0a6a223/Taryfa%20ENERGA-OBR%C3%93T%20S.A.%20dla%20energii%20elektrycznej%20obowi%C4%85zuj%C4%85ca%20od%201.01.pdf)
- [Decyzje i taryfy URE opublikowane w 2025 r.](https://bip.ure.gov.pl/bip/taryfy-i-inne-decyzje-b/energia-elektryczna/4767,Taryfy-opublikowane-w-2025-r.html)
- [Taryfa E.ON Polska dla grup G w sieci Stoen Operator od 1 stycznia 2026 r.](https://eon.pl/-/media/eon/dokumenty/dla-domu/taryfa-energii-elektrycznej-eon-polska-sa-dla-grup-taryfowych-g--obowizuje-od-dnia-01_01_2026.ashx)

W taryfach wielostrefowych administrator musi potwierdzić, czy licznik pracuje
według automatycznej zmiany czasu lato/zima, czy według stałego czasu zimowego.
Katalog przechowuje oficjalny rozkład godzin, a aplikacja rozwiązuje go dopiero
po tej decyzji. Brak wyboru nie uruchamia profilu domyślnego.

## Aktualizacja i bezpieczeństwo

Workflow `update-catalog.yml` uruchamia się codziennie o 03:17 UTC oraz ręcznie.
Sprawdza wyłącznie jawnie dozwolone oficjalne źródła, ma limit czasu, ograniczone
ponowienia i nie publikuje danych, gdy źródło uległo niezweryfikowanej zmianie.
Nie zapisuje cen dynamicznych. Zmiana dokumentu źródłowego powoduje błąd gate'u
i wymaga ponownej ręcznej weryfikacji wartości.

`status.json` odróżnia ostatnią poprawną kontrolę źródeł od nowej wersji danych.
GitHub może opóźniać zadania harmonogramu, a harmonogram publicznego repozytorium
może zostać wyłączony po 60 dniach braku aktywności. Stan workflow oraz czas w
`status.json` muszą więc pozostać częścią diagnostyki operatora.

## Walidacja lokalna

```text
python -m unittest discover -s tests -v
python tools/check_sources.py
python tools/build_catalog.py --check
python tools/validate_catalog.py
```

Publikacja nowej wersji zawsze zachowuje kolejność: najpierw niezmienny obiekt,
następnie manifest, który do niego odsyła.
