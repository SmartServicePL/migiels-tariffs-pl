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

## Zakres pierwszej publikacji

Pierwsza wersja zawiera wyłącznie taryfę ENERGA-OBRÓT S.A. G11 obowiązującą od
1 stycznia 2026 r. dla odbiorców objętych taryfą zatwierdzoną przez Prezesa URE i
przyłączonych do ENERGA-OPERATOR S.A. Cena `0,6172 PLN/kWh` jest ceną brutto
energii czynnej. Nie obejmuje dystrybucji ani dodatkowych opłat.

Źródło oficjalne:

- [Taryfa ENERGA-OBRÓT S.A. dla grup G od 1 stycznia 2026 r.](https://www.energa.pl/dam/jcr:1f730159-7aab-4815-8a17-e0f6f0a6a223/Taryfa%20ENERGA-OBR%C3%93T%20S.A.%20dla%20energii%20elektrycznej%20obowi%C4%85zuj%C4%85ca%20od%201.01.pdf)

Katalog nie twierdzi, że obejmuje cały polski rynek. Profile G12, G12w i G12r
nie są jeszcze publikowane: wymagają jawnego modelu sposobu prowadzenia zegara
taryfowego przy zmianie czasu. Brak profilu oznacza brak pokrycia, a nie cenę
zerową ani automatyczny wybór innej oferty.

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

