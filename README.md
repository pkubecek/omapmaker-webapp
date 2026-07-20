# OMapMaker

OMapMaker je webová aplikace, která z LiDARových dat automaticky vygeneruje orientační mapu — jako PNG obrázek i jako GPKG soubor pro import do OpenOrienteeringMapperu.

## Rychlý návod

1. Vyberte oblast na mapě
2. Nahrajte data (stáhněte přímo v appce, nebo nahrajte vlastní)
3. Nastavte parametry zpracování
4. Klikněte na „Generovat mapu"
5. Stáhněte výsledek

---

## 1. Výběr oblasti a získání dat

### Stažení dat přímo v aplikaci (doporučeno)

V mapovém okně použijte nástroj **„Výběr oblasti"** a tažením myší vyznačte, co chcete zmapovat. Nad mapou se objeví panel pro stažení dat.

Vyberte zdrojovou zemi:

- **🇨🇿 Česko** — data se stahují z ČÚZK. Stahování trvá typicky několik desítek sekund.
- **🇵🇱 Polsko** — data se stahují z GUGiK. U větších oblastí může stahování trvat déle.
- Ostatní země (Slovensko, Rakousko, Německo) zatím nejsou podporované — v seznamu jsou označené jako „připravujeme".

Klikněte na **„Stáhnout"**. Po dokončení se data automaticky vloží jako vstup pro zpracování — nic dalšího už není potřeba nastavovat.

### Nebo nahrání vlastních souborů

Pokud máte vlastní LiDAR data, přetáhněte je do levého panelu. Potřebujete dva soubory:

- **DMR** (digitální model terénu / reliéfu) — holá zem bez vegetace a budov
- **DMP** (digitální model povrchu) — terén včetně vegetace, budov apod.

Oba musí být ve formátu **.las** nebo **.laz**. Aplikace nepozná DTM a DSM automaticky, pokud máte data DMR a DMP v jednom souboru, požijte raději výběr oblasti a stažení dat.

---

## 2. Nastavení parametrů mapy

V levém panelu (Nastavení) můžete upravit:

| Parametr | Co dělá |
|---|---|
| **Souřadnicový systém** | Výstupní CRS mapy (výchozí EPSG:5514 pro ČR) |
| **Měřítko** | 1:10 000 nebo 1:15 000 |
| **Formát papíru** | A4/A3 na výšku/šířku, nebo „Extent dat" (mapa přesně podle stažené oblasti) |
| **Interval vrstevnic** | Základní rozestup vrstevnic v metrech (výchozí 5 m). Hlavní vrstevnice se kreslí po 5násobku, pomocné po polovině intervalu |
| **Vyhlazení vrstevnic** | Vyšší hodnota = hladší, ale méně detailní vrstevnice (doporučeno 3–6) |
| **Prohlubně / kupky** | Minimální a maximální průměr a hloubka/výška, aby se odfiltroval šum a zachytily jen skutečné terénní tvary |
| **Magnetická deklinace** | Úhel odklonu severek od severu mapy |
| **Vrstvy** | Zapnutí/vypnutí jednotlivých vrstev — vrstevnice, skály, voda, vegetace, cesty, budovy, ostatní objekty, magnetické severky |
| **ZABAGED®** | Zaškrtávací pole pro vykreslení dat ze ZABAGED® (dostupné jen pro ČR). Zatím se zapíná/vypíná jako celek, bez výběru jednotlivých podvrstev |

U každého parametru najdete nápovědu po najetí na ikonu **„?"**.

---

## 3. Generování mapy

Jakmile máte nahraná/stažená data DTM i DSM, klikněte v pravém panelu na **„▶ Generovat mapu"**.

Zpracování trvá:
- řádově **jednotky minut** pro menší oblasti (do cca 2×2 km)
- déle u větších oblastí — ty se automaticky rozdělí na dlaždice a zpracovávají postupně

Průběh sledujte v pravém panelu — progress bar a log ukazují, v jaké fázi zpracování zrovna je (interpolace terénu, vrstevnice, vegetace, skály, export...).

---

## 4. Stažení výsledků

Po dokončení se v pravém panelu zobrazí náhled mapy. Kliknutím na náhled ho zvětšíte přes celou obrazovku.

K dispozici jsou tři tlačítka ke stažení:

- **↓ Stáhnout mapu v PNG** — hotová mapa v tisknutelném rozlišení (1000 DPI), včetně world file (.pgw) pro georeferencování
- **↓ Exportovat GPKG** — vektorová data se stejnými ISOM symboly, které vidíte na PNG, připravená k importu do OpenOrienteering Mapperu
- **↓ Stáhnout CRT soubor** — přiřazovací tabulka symbolů pro OOM; potřebujete ji, abyste GPKG mohli v OOM správně naimportovat s odpovídajícími symboly

### Import do OpenOrienteering Mapperu

1. V OOM: **File → Import** → vyberte stažený GPKG soubor
2. Při importu vyberte stažený **.crt** soubor jako mapovací tabulku symbolů
3. Vrstvy z GPKG se automaticky přiřadí ke správným ISOM symbolům podle CRT tabulky

---
Ve skalách může výsledek vypadat nějak takto:
<img width="2078" height="1658" alt="Žižkův kopec" src="https://github.com/user-attachments/assets/ced5d0b4-41c7-4eaf-895e-4ee5f7aa6ef6" />
<img width="1111" height="1034" alt="Borný" src="https://github.com/user-attachments/assets/e5ee5dec-aa03-455a-b358-561c0efc9f8c" />

## Tipy

- Pro oblast 3×3 km počítejte s cca 8 minutami zpracování
- Data z ČÚZK jsou zdarma a pokrývají celé území ČR
- Pokud zpracování skončí chybou, zkontrolujte v logu, jestli nejde o příliš velkou oblast nebo chybějící DSM data
- Menší `interval vrstevnic` a vyšší `vyhlazení` obvykle dá hezčí výsledek pro členitější terén; pro rovinatější oblasti stačí hrubší interval
