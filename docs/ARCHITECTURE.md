# AI Living City — Arxitektura

Avtonom AI sivilizatsiyasi: 3D shaharcha, unda mustaqil AI odamlar yashaydi,
ishlaydi, oila quradi va qariydi. Shaharni bitta AI Prezident boshqaradi.
Simulyatsiya foydalanuvchi hech narsa qilmasa ham davom etadi.

## 1. Umumiy oqim

```
Frontend (React + R3F)
      │  WebSocket: dunyo holati (o'qish)
      │  REST: buyruqlar (yozish)
      ▼
FastAPI  ──────────────►  Simulation Engine (avtoritar)
                                │
                                ├── City Analysis
                                ├── President Decision Engine
                                ├── Citizen AI (LOD bo'yicha)
                                ├── Economy / Jobs / Construction
                                ├── Families / Children / Emotions
                                └── Events / Weather / Transport
                                │
                                ▼
                          Persistence (SQLAlchemy → SQLite/Postgres)
```

Muhim prinsip: **simulyatsiya yagona haqiqat manbai**. Frontend hech qachon
holatni o'zgartirmaydi, faqat ko'rsatadi va buyruq yuboradi. Shu sababli
brauzer yopilsa ham shahar yashashda davom etadi.

## 2. Texnologiya va tanlovlar

| Qatlam | Tanlov | Sabab |
|---|---|---|
| Backend | Python 3.11 + FastAPI | Simulyatsiya mantiqi Python'da, API bilan bir jarayonda |
| ORM | SQLAlchemy 2.0 (sinxron) | Simulyatsiya tsikli CPU'ga bog'liq va deterministik; async bu yerda foyda bermaydi |
| Migratsiya | Alembic | Sxema o'zgarishlari versiyalanadi |
| DB | SQLite (dev) → PostgreSQL (prod) | Quyida izohlangan |
| Frontend | React + TypeScript (strict) + Vite | |
| 3D | Three.js + React Three Fiber + drei | Deklarativ sahna, instancing bilan mingta agent |
| State | Zustand | Loyihada allaqachon sinovdan o'tgan yondashuv |
| Real-time | WebSocket | Server har tickda delta yuboradi |

### 2.1 Nega SQLite'dan boshlanadi

Mashinada PostgreSQL ham, Docker ham yo'q. Postgres'ni o'rnatish administrator
huquqi va sozlash vaqtini talab qiladi, bu esa loyihaning boshlanishini
kechiktiradi. Shuning uchun kod **Postgres'ga tayyor** qilib yozilgan:

- Barcha model faqat ikkala bazada mavjud tiplardan foydalanadi (`JSON`,
  `Integer`, `String`, `Float`, `Boolean`, `DateTime`).
- SQLite'ga xos hech narsa ishlatilmaydi.
- Ulanish faqat `DATABASE_URL` orqali beriladi.

Postgres'ga o'tish uchun bitta o'zgarish kifoya:

```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/ailivingcity
```

### 2.2 Nega Prezident LLM emas

Spetsifikatsiyaning 5 va 32-bo'limlari qaror jarayonini aniq tasvirlaydi:
kirish ko'rsatkichlari → tahlil → ustuvorlik → qaror → natija → xotira. Bu
determenistik dvigatel, LLM'ga hojat yo'q. Sababi uchta:

1. **Narx.** Simulyatsiya to'xtovsiz ishlaydi va 100x tezlikda kunlar
   sekundlarda o'tadi. Har qarorga API chaqiruvi hisobni tez yeydi.
2. **Determinizm.** Bir xil shahar holati bir xil qarorga olib kelishi kerak,
   aks holda xatoni takrorlash va testlash imkonsiz.
3. **Tezlik.** Tsikl ichida tarmoq kutish simulyatsiyani to'xtatadi.

LLM keyinchalik **faqat matn qatlami** sifatida qo'shiladi: qaror qabul
qilingandan keyin uni tabiiy tilda bayon qilish, agentlar suhbati, Prezident
nutqi. `sim/ai/narrator.py` shu uchun interfeys sifatida ajratilgan va
sukut bo'yicha o'chirilgan.

## 3. Papka tuzilishi

Spetsifikatsiyada sanab o'tilgan modullar Python paketlari sifatida
`backend/sim/` ichiga joylashtirilgan. Ular ildizda alohida papka emas, chunki
Python'da import qilinadigan bo'lishi kerak va ular bitta jarayonda ishlaydi.

```
ai-living-city/
├── docs/
│   └── ARCHITECTURE.md
├── backend/
│   ├── app/                    # HTTP/WS qatlami — simulyatsiya mantiqi yo'q
│   │   ├── main.py             # FastAPI ilovasi, lifespan, tsiklni ishga tushirish
│   │   ├── config.py           # Sozlamalar (env)
│   │   ├── runtime.py          # Simulyatsiya jarayoni bilan bog'lovchi
│   │   ├── api/                # REST va WebSocket yo'nalishlari
│   │   ├── db/                 # Engine, sessiya, modellar
│   │   └── schemas/            # Pydantic DTO'lar
│   ├── sim/                    # Simulyatsiya yadrosi — HTTP haqida bilmaydi
│   │   ├── engine.py           # Asosiy tsikl, tick tartibi
│   │   ├── clock.py            # Simulyatsiya vaqti, tezlik, pauza
│   │   ├── state.py            # Xotiradagi dunyo holati
│   │   ├── rng.py              # Urug'langan tasodifiylik (determinizm uchun)
│   │   ├── world/              # Grid, tile'lar, tumanlar, xarita generatsiyasi
│   │   ├── pathfinding/        # Grid ustida A*
│   │   ├── agents/             # Agent modeli, ehtiyojlar, jadval, xatti-harakat
│   │   ├── president/          # Qaror dvigateli, jadval, xotira
│   │   ├── ai/                 # Umumiy qaror utilitalari, narrator interfeysi
│   │   ├── economy/            # Byudjet, soliqlar, GDP
│   │   ├── city/               # Ehtiyoj tahlili, shahar darajasi, shikoyatlar
│   │   ├── buildings/          # Bino turlari, qurilish jarayoni
│   │   ├── roads/              # Yo'l tarmog'i
│   │   ├── transport/          # Transport va traffik
│   │   ├── jobs/               # Kasblar, ish o'rinlari, ishga olish
│   │   ├── families/           # Munosabatlar, nikoh, oila
│   │   ├── children/           # Yosh bosqichlari
│   │   ├── emotions/           # His-tuyg'ular
│   │   ├── memory/             # Xotira tizimi
│   │   ├── relationships/      # Do'stlik va ijtimoiy graf
│   │   ├── animals/            # Zoo
│   │   ├── weather/            # Ob-havo
│   │   └── events/             # Voqealar, favqulodda holat
│   ├── tests/
│   ├── alembic/
│   └── requirements.txt
└── frontend/
    └── src/
        ├── scene/              # 3D: terrain, binolar, agentlar, kamera
        ├── ui/                 # Dashboard, vaqt boshqaruvi, debug panel
        ├── net/                # WebSocket klienti
        ├── store/              # Zustand
        └── avatar/             # Avatar generatori (Ikki Miya'dan ko'chirilgan)
```

`app/` va `sim/` orasidagi chegara qat'iy: `sim/` hech qachon FastAPI yoki
SQLAlchemy'ni import qilmaydi. Bu simulyatsiyani HTTP'siz va bazasiz
testlash imkonini beradi.

## 4. Vaqt tizimi

Simulyatsiya vaqti real vaqtdan ajratilgan.

- Bitta **tick** = 1 simulyatsiya daqiqasi.
- Sukut bo'yicha 1x tezlikda 1 tick = 200 ms real vaqt.
- Tezlik: 1x, 2x, 5x, 10x, 50x, 100x. Pauza va davom ettirish.
- Yuqori tezlikda tsikl bir real qadamda bir necha tick bajaradi, lekin
  qadam hisoblash byudjetidan oshsa tick'larni tashlab ketadi (frontend
  qotib qolmasligi uchun).

Kun tartibi: 24 soat × 60 daqiqa = 1440 tick bir simulyatsiya kuni.

## 5. Tick tartibi

Tartib muhim: har bir bosqich o'zidan oldingisining natijasini ko'radi.

```
1.  CLOCK          vaqtni surish
2.  WEATHER        ob-havo
3.  PERCEPTION     agentlar atrofni o'qiydi
4.  CITY ANALYSIS  shahar ko'rsatkichlari hisoblanadi
5.  PRESIDENT      qaror (faqat kerak bo'lganda, har tickda emas)
6.  CITIZEN AI     LOD bo'yicha agent xatti-harakati
7.  MOVEMENT       yo'l bo'ylab harakat
8.  ECONOMY        maosh, soliq, xarajat
9.  JOBS           ishga olish va bo'shatish
10. CONSTRUCTION   qurilish jarayoni
11. FAMILIES       munosabat, nikoh, farzand
12. AGING          yosh bosqichlari
13. EMOTIONS       his-tuyg'ular
14. EVENTS         voqealar va favqulodda holat
15. MEMORY         xotiraga yozish
16. SNAPSHOT       davriy saqlash
```

## 6. Ishlash arxitekturasi (LOD)

1000+ agentni har tickda to'liq hisoblash mumkin emas. Uch daraja:

| Daraja | Shart | Nima hisoblanadi |
|---|---|---|
| `FULL` | Kamera yaqinida yoki kuzatilayotgan | To'liq: qaror, yo'l, animatsiya, his-tuyg'u |
| `REDUCED` | O'rta masofa | Qaror kamroq tez-tez, yo'l soddalashtirilgan |
| `STATISTICAL` | Uzoq yoki ko'rinmaydigan | Individual hisob yo'q; ish, pul, ehtiyoj agregat formulalar bilan suriladi |

Agent darajasi kamera holatiga qarab har sekundda qayta baholanadi.
`STATISTICAL` darajadan `FULL`ga o'tganda agent holati agregatdan
qayta tiklanadi, shuning uchun sakrash ko'rinmaydi.

## 7. Saqlash strategiyasi

Har tickda bazaga yozish juda sekin. Shuning uchun:

- Dunyo holati **xotirada** yashaydi (`sim/state.py`).
- Snapshot davriy ravishda (sukut bo'yicha har simulyatsiya kunida bir marta)
  va to'xtatishda yoziladi.
- Voqealar (tug'ilish, nikoh, qurilish, Prezident qarori) darhol
  append-only jurnalga yoziladi, chunki ular hikoya uchun qimmatli.

Qayta ishga tushirilganda oxirgi snapshot tiklanadi (`app/runtime.py` →
`Runtime.start`), snapshot bo'lmasa yangi shahar tashkil etiladi.

### 7.1. Sxema

Ma'lumotlar ikki xil shaklda saqlanadi, chunki ular ikki xil maqsad uchun
o'qiladi (`app/db/models.py`):

| Jadval | Nima | Nega shunday |
| --- | --- | --- |
| `worlds` | shahar va sarlavha ko'rsatkichlari | saqlash ro'yxatini snapshotni ochmasdan ko'rsatish |
| `world_snapshots` | to'liq dunyo, bitta JSON hujjat | atomar yozuv; yarim yozilgan shahar — buzilgan shahar |
| `world_events` | voqealar tarixi | jurnal bo'yicha filtr va qidiruv |
| `world_decisions` | Prezident qarorlari va natijalari | qaror tarixi, samaradorlik hisobi |
| `world_metrics` | kunlik ko'rsatkichlar | dashboard grafiklari |

Dunyo nega normalizatsiya qilinmadi: model hali o'zgarib turadi, har bir
ehtiyoj yoki his-tuyg'u uchun alohida ustun bo'lsa, har o'zgarishga
migratsiya kerak bo'lardi. Aksincha, so'rov qilinadigan tarix haqiqiy
ustunlarda — JSON ichida o'n yillik voqealarni filtrlash so'rov emas, to'liq
skanerlash.

### 7.2. Kodek

Deyarli barcha entitylar — annotatsiyalangan dataclasslar, shuning uchun
`sim/codec.py` tip bo'yicha ishlaydigan umumiy kodek: yangi maydon
avtomatik saqlanadi. Qo'lda yozilgan `to_dict` juftliklari modeldan
ortda qolar edi — va jimgina, saqlash shunchaki yangi qiymatni yo'qotardi.

Holatli obyektlar (grid, clock, economy, registrylar) o'z
`snapshot()`/`restore()` metodlariga ega. Grid xarita RLE bilan siqiladi:
500×500 = 250 000 tile, har biri alohida obyekt bo'lsa saqlash o'nlab
megabaytga chiqadi.

`sim/` ichida SQLAlchemy yo'q. Baza bilan gaplashadigan yagona joy —
`app/db/repository.py`. Shu sabab butun tsivilizatsiyani bazasiz test
qilish mumkin.

### 7.3. To'g'rilik mezoni

Save/load testining asosiy da'vosi — **divergensiya yo'q**: saqlangan,
tiklangan va davom ettirilgan shahar hech to'xtamagan shahar bilan bir xil
kelajakka ega bo'lishi kerak (`tests/test_persistence.py`). Shu sabab RNG
oqimlarining ichki holati ham saqlanadi — faqat urug'ni saqlash kifoya
emas, aks holda restart kelajakni jimgina o'zgartiradi.

## 7.4. Til qoidasi

Enum qiymatlari — identifikatorlar: ular API, baza va kod uchun ingliz tilida
qoladi (`power_plant`, `accountant`). Foydalanuvchi o'qiydigan har bir satr
esa o'zbek tilida bo'lishi shart.

Tarjima ikki chegarada turadi:

- Backend: `sim/buildings/catalog.py::LABELS` va
  `sim/jobs/professions.py::LABELS` — javoblar, voqealar jurnali, xotira
  yozuvlari.
- Frontend: `src/ui/labels.ts` — inspektor va panellar.

Ikkala katalogda `_sanity_check` yangi bino yoki kasb yorliqsiz qolishiga
yo'l qo'ymaydi. Sabab oddiy: o'yinchi "3 ta uy qur" deb yozib,
"3 ta house qurilishi boshlandi" javobini olgan edi.

## 7.5. O'yinchi va shahar darajasi

AI Prezident faqat qulfi ochilgan binolarni taklif qiladi, chunki qishloqda
metropolis shifoxonasini buyurish bajarilmaydigan qarorni tug'diradi.

O'yinchi esa — Prezidentning o'zi. Uning farmoni "hali erta" degan sabab bilan
rad etilmaydi: `EARLY_BUILD_PREMIUM` (2.5×) bo'yicha qimmatroq narxda
bajariladi, chunki shaharda yo'q tajribani tashqaridan olib kelish kerak.
Rivojlanish bosqichlari ma'nosini yo'qotmaydi — muddatidan oldin qurish
byudjetni og'ritadi.

Faqat pul va yer to'xtatadi. Ilgari `_ensure_player_build_funds` yetmagan
summani xazinaga jimgina qo'shib qo'yardi, natijada har qanday farmon
bajarilardi va byudjet bezakka aylanardi — 11-bo'lim aynan buning teskarisini
talab qiladi: noto'g'ri qaror shaharga pul jihatidan zarar keltirishi kerak.

## 8. Determinizm

Butun simulyatsiya bitta urug'dan (`WORLD_SEED`) kelib chiqadi. Har bir
quyi tizim o'z nomlangan RNG oqimidan foydalanadi (`sim/rng.py`), shuning
uchun keyinchalik yangi tizim qo'shilishi mavjud oqimlarni surib
yubormaydi. Bir xil urug' + bir xil buyruqlar ketma-ketligi = bir xil shahar.

Bu testlash uchun ham, xato hisobotini takrorlash uchun ham zarur.

## 9. Bosqichlar

Har bosqich oxirida loyiha build bo'ladi va ishlaydi.

1. **Tik kesim** — struktura, sxema, tsikl, 30 agent, Prezidentning uy
   qurish qarori, 3D ko'rinish, dashboard. *(joriy)*
2. Iqtisodiyot va soliq siyosati, shahar darajalari
3. Oila, farzandlar, avlodlar, qarish
4. His-tuyg'ular, xotira, munosabatlar grafi
5. Transport, traffik, yo'l tarmog'i generatsiyasi
6. Vazirlar mahkamasi va reportlar
7. Voqealar, favqulodda holat, politsiya va o't o'chirish
8. Zoo, park, hayvonlar, ob-havo effektlari
9. Admin va debug panellari
10. 1000+ agent uchun LOD optimizatsiyasi va profiling
11. Saylov tizimi
