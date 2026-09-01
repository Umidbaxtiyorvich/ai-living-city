# AI Living City

**GitHub:** https://github.com/Umidbaxtiyorvich/ai-living-city

Avtonom 3D shahar simulyatori. AI Prezident shaharni boshqaradi; fuqarolar ishlaydi, yuradi, oila quradi. Brauzer yopilsa ham simulyatsiya serverda davom etadi.

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
