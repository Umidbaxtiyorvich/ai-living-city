# AI Living City

**GitHub:** https://github.com/Umidbaxtiyorvich/ai-living-city

Tsivilizatsiya simulyatori. Bo'sh yerda **10 kishi**dan boshlanadi: odamlar o'zlari
meva teradi, o'tin kesadi, tosh qazadi, o'z uylarini quradi, turmush qurib farzand
ko'radi, kashfiyotlar qiladi (dehqonchilik, kulolchilik, toshtaroshlik, yozuv…).
Odamlar ko'paygach, bir guruh ko'chib, yangi qishloqqa asos soladi. Hech kim
boshqarmaydi: har bir odam nima qilishni o'zi hal qiladi. Brauzer yopilsa ham
simulyatsiya serverda davom etadi.

Eski "boshqariladigan shahar" rejimi ham saqlangan: `WORLD_MODE=city`.

## Tsivilizatsiya rejimi (sukut bo'yicha)

- `backend/civ/`: dunyo (orol, ko'llar, o'rmon, tosh, butalar), odamlar, binolar,
  texnologiyalar va dvigatel.
- Har bir odam ehtiyojlari (ochlik, kuch, muloqot, sog'liq), mahorati, xarakteri,
  orzulari, xotiralari va ichki fikriga ega. Qaysi ish yoqishini tajribadan o'rganadi.
- Uy turi oila bilimi va xarakteriga qarab tanlanadi: kulba → yog'och uy / paxsa uy
  → tosh uy → ikki qavatli uy → hovli-saroy.
- Odamlar ko'p yuradigan joyda so'qmoq paydo bo'ladi.
- Ekranda: yer bitta mesh bo'lib chiziladi, daraxtlar va odamlar "instancing" bilan
  chiziladi, shuning uchun sahna 30 ga yaqin draw call bilan tez ishlaydi.
- Tezlik: 1× da bir kun ≈ 48 soniya. 50× gacha tezlashtirish mumkin.
- **Vaqt haqiqiy**: 1× da o'yindagi soat Toshkent vaqti bilan bir xil yuradi, odamlar
  haqiqiy tezlikda (≈1.3 m/s) yuradi. O'yindagi 1 yil 12 kunga teng. Tezlashtirish
  tugmalari: 10×, 1 daq/s, 6 daq/s, 1 kun/min. Server uxlab qolsa, qayta yonganda
  o'tgan vaqtni (2 kungacha) tiklaydi.
- **Siz ham dunyodasiz**: Umid Ravshanov qahramoni. WASD yoki yerni bosib yurasiz.
  Meva terish, o'tin kesish, tosh qazish, qurish, ovqatlanish, uxlash. "Yaratish"
  menyusidan istalgan binoni tanlab, yerga qo'yasiz ("Darhol qurish" — resurssiz).
  Odamlar bilan gaplashib, yaqinlashgach turmush taklif qilasiz: oilangizda
  farzandlar tug'iladi. "Avto" qahramoningizni o'zi yashashga qo'yadi.
- **Siz — xalq rahbarisiz**: kimdir muammoga duch kelsa (o'tin/tosh tugadi, uy uchun
  joy yo'q, ochlik, kasallik, juft topolmayapti), u yoningizga keladi va so'raydi.
  "📜 Murojaat" tugmasini bosib, o'z so'zingiz bilan javob berasiz: «shimolga borib
  o'tin kes», «baliq tutinglar», «dehqonchilikni o'rgataman», «shu yerga uy quring»,
  «yangi joyga ko'chinglar». Tushunsa — «Tushundim!» deb bajaradi, tushunmasa —
  misollar bilan qayta so'raydi. Xalqqa bilim (texnologiya, mahorat) va odatlar
  («o'rmonni asranglar», «bolalarni o'qitinglar», «zaxira to'planglar», «hashar
  qilinglar») o'rgatasiz — ular shu bilan ishlaydi.
- **Hayvonlar va qushlar**: otlar podasi, tulkilar, laylak, flamingo va to'tiqushlar.
- **Haqiqiy odamlar**: kameraga yaqin 14 kishi realistik 3D tanada (yurish/turish
  animatsiyasi), uzoqdagilar yengil figura bo'ladi.
- Dunyo har daqiqada `backend/civ_world.json` (Docker'da `/data/civ_world.json`) fayliga
  saqlanadi. "Yangi dunyo" tugmasi 10 kishi bilan qaytadan boshlaydi.

## Internetga joylash (3 daqiqa)

1. [Render.com](https://render.com) ga kiring (GitHub bilan login)
2. **New +** → **Blueprint**
3. Repongizni tanlang: `Umidbaxtiyorvich/ai-living-city`
4. **Apply** — 3–5 daqiqadan keyin link: `https://ai-living-city-xxxx.onrender.com`

Bitta linkda hamma narsa: 3D shahar + API + WebSocket.

> **Tez ishlashi uchun:** Render'da **Starter** plan ($7/oy) — Free rejim uxlasa sekin ochiladi.

Docker (VPS):

```bash
docker build -t ai-living-city .
docker run -p 8000:8000 -v city-data:/data ai-living-city
```

---

## Ishga tushirish (lokal)

Ikkita terminal:

```powershell
cd "c:\Users\Dell\Desktop\ikki miya\ai-living-city\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
cd "c:\Users\Dell\Desktop\ikki miya\ai-living-city\frontend"
npm install
npm run dev
```

Brauzer: [http://localhost:5173/](http://localhost:5173/)

- Sichqoncha: aylantirish / yaqinlash
- Agent yoki binoni bosing — o‘ng panelda ma’lumot
- **Prezidentni kuzat** — kamera uni kuzatadi
- Tezlik: 0× pauza, **1×** haqiqiy vaqt (1 sim-daqiqa = 1 real soniya), 5×/10× tezroq

## Sun'iy ong va o'zini yangilaydigan shahar

Har bir fuqaroning **ongi** bor (`backend/sim/ai/mind.py`). U lokal ishlaydi, LLM
ishlatilmaydi, shuning uchun bepul, tez va deterministik:

- **Tajribadan o'rganadi.** Bo'sh vaqtda nima qilishni (sayr, do'stlar, xarid,
  o'qish) his-tuyg'u, o'rgangan narsasi va maqsadlariga qarab tanlaydi. Har bir
  tanlovdan keyin "bu meni baxtliroq qildimi?" deb baholaydi va keyingi safar shunga
  qarab tanlaydi.
- **Maqsad qo'yadi.** Ish, o'qish, pul, oila, do'stlar, uy, sog'liq va kasb
  mahorati kabi maqsadlarni shaxsiyati va ahvoliga qarab tanlaydi. Erishgach yangi
  maqsad qo'yadi.
- **O'zini takomillashtiradi.** Ishda ko'nikmasi oshadi. Ish topolmasa, o'qishga
  kirishadi va yetarli soat o'qisa, yangi ma'lumot darajasini oladi.
- **Har kuni mulohaza qiladi.** Kunini baholaydi, ong darajasi o'sadi, ichki
  fikrini aytadi ("💭") va shaharga talab bildiradi (park, uy, shifoxona…).

Fuqarolarning talablari **jamiyat ovozi**ga yig'iladi (`sim/ai/voice.py`).
Prezident uni o'z ko'rsatkichlari bilan birga hisobga oladi va shunga qarab
quradi. Prezident ham **o'z qarorlaridan o'rganadi**: ish bergan siyosatga
ishonchi oshadi, natija bermaganiga ishonchi pasayadi.

**Shahar o'zini yangilaydi** (`sim/urban/renewal.py`): binolar eskiradi. Har
hafta eng eskirgan bino ta'mirlanadi yoki zichroq binoga almashtiriladi (uy →
ko'p qavatli uy, klinika → shifoxona, do'kon → bozor).

HUD'da: chap panelda "Jamiyat ongi", fuqaroni bossangiz uning fikri, maqsadlari
va ong darajasi ko'rinadi.

## 3D odamlar (skeletli, animatsiyali)

```powershell
cd frontend
npm run fetch:humans
```

Bu buyruq `public/models/humans/` papkasiga skeletli odam modellarini yuklaydi
(three.js namunalari, Mixamo rig) va `manifest.json` yozadi. Kameraga eng yaqin
28 fuqaro shu modellarda yuradi, yuguradi va turadi. Qolganlari esa yengil
procedural figura bo'lib qoladi. Model bo'lmasa, ilova procedural figuralar bilan
ishlayveradi.

Realroq odamlar uchun Quaternius **Universal Base Characters** va **Universal
Animation Library** paketlarini oling. Ularning GLB fayllarini shu papkaga
tashlab, `manifest.json`ga qo'shing (`url`, `gender`, ixtiyoriy `clips`, `tint`,
`skin`, `clipSource`). Kod o'zgartirish shart emas. Paket litsenziyasini
itch.io'dagi sahifasida tekshiring.

## Saqlash (shahar restartdan keyin ham davom etadi)

Server ishga tushganda Alembic migratsiyalarini o‘zi bajaradi va oxirgi
saqlangan shaharni tiklaydi. Saqlangan shahar bo‘lmasa yangi shahar tashkil
etiladi.

- **Avtomatik**: har simulyatsiya kunida bir marta va server to‘xtaganda.
- **Qo‘lda**: HUD’dagi **Saqla** tugmasi yoki `POST /api/save`.
- **Tarix**: `GET /api/history` — kunlik ko‘rsatkichlar (aholi, byudjet,
  mamnunlik, reyting).

Sukut bo‘yicha baza — `backend/city.db` (SQLite). PostgreSQL uchun faqat
ulanish satrini o‘zgartirish kifoya:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://user:parol@localhost/city"
```

Boshqa sozlamalar (`.env` yoki muhit o‘zgaruvchisi): `WORLD_SEED`, `MAP_SIZE`,
`FOUNDING_POPULATION`, `AUTOSAVE_DAYS`, `SNAPSHOT_HISTORY`, `WORLD_NAME`.

Migratsiyalarni qo‘lda boshqarish:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "izoh"
```

## Testlar

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q -m "not slow"
```

Uzoq simulyatsiya testlari (`slow`) alohida ishlatiladi. Serversiz
tekshirish uchun: `python run_demo.py --days 90`.

## Holat

Ishlaydi: 3D xarita, yuruvchi va ishlaydigan agentlar, oila va avlodlar,
Prezident qaror dvigateli, iqtisodiyot va soliq siyosati, qurilish, voqealar,
ob-havo, o‘yinchi buyruqlari (o‘zbek tilida), vazirlar stollari, save/load.

Keyingi bosqichlar: transport va traffik, zoo hayvonlari, 1000+ agent uchun
optimizatsiya, saylov tizimi.


## 3D modellar va litsenziyalar

- Odamlar: Innerscene "Sam" va "Maya" (MakeHuman/MPFB asosida), **CC0**.
  `frontend/public/models/humans/sam.glb`, `maya.glb` — siqilgan (≈1.7 MB).
- Ot, laylak, flamingo, to'tiqush: three.js namunalari (`examples/models/gltf`).
- Tulki: Khronos glTF Sample Assets, **CC-BY 4.0** — PixelMannen (model),
  tomkranis (rig va animatsiya).
- Yer, bino va daraxt po'stlog'i teksturalari: Poly Haven, **CC0**
  (`frontend/public/textures/`). Suv normal xaritasi: three.js namunalari.

> Render'da dunyo saqlanib qolishi uchun xizmatda `/data` diski bo'lishi kerak
> (`render.yaml`dagi `disk`, Starter tarifi). Bepul tarifda disk yo'q: har deploy'da
> dunyo qaytadan boshlanadi.
