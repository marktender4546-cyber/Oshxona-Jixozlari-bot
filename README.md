# AQUA HOME — Telegram bot + Mini App

Hammom jihozlari do'koni uchun tayyor o'quv/ishga tushirish loyihasi. Bot va Mini App serveri asosiy `bot.py` faylida jamlangan.

## Tayyor funksiyalar

- Telegram ichida zamonaviy Mini App katalogi.
- Mahsulot qidiruvi, kategoriyalar, saralash, mahsulot tafsilotlari.
- Sevimlilar, savat, miqdor +/- va jami narx.
- Buyurtma formasi: ism-familiya, telefon, manzil va izoh. To'lov integratsiyasi yo'q.
- Buyurtma yuborilganda admin Telegram ID'siga xabar boradi.
- ` /myorders ` orqali mijoz o'z buyurtmalarini ko'rishi mumkin.
- Admin panel, yangi buyurtmalar/statistika, statusni yangilash tugmalari.
- `/addproduct` orqali yangi mahsulotni botning o'zida katalogga qo'shish.
- SQLite ma'lumotlar bazasi; dastlab 12 ta demo mahsulot bilan to'ldiriladi.
- Mahalliy kompyuterda `start.bat` orqali ishga tushirish, Render uchun `render.yaml`.

> **Muhim:** `.env` fayliga faqat tokeningizni va o'zingizning Telegram raqamli ID'ingizni yozing. BotFather tokenini GitHub'ga joylamang. Mahsulot nomlari/narxlari namunaviy; ishga tushirishdan oldin admin orqali haqiqiy mahsulotlarni qo'shing yoki `SEED_PRODUCTS` ro'yxatini almashtiring.

## 1. Kompyuterda (Windows) ishga tushirish

1. Python 3.11 yoki yangiroq versiyasini o'rnating: https://www.python.org/downloads/ . O'rnatish oynasida **Add Python to PATH** ni belgilang.
2. ZIP'ni alohida papkaga oching.
3. `.env` faylini Notepad orqali oching. `BOT_TOKEN` qiymatiga BotFather tokenini kiriting. `ADMIN_IDS` o'rniga shaxsiy Telegram raqamli ID'ingizni kiriting. ID'ni Telegram'dagi ishonchli ID botidan bilib olishingiz mumkin.
4. `start.bat` faylini ikki marta bosing. Birinchi ishga tushishda kerakli kutubxonalar avtomatik o'rnatiladi. Oynani yopmaguningizcha bot ishlaydi.
5. Telegram'da o'z botingizni ochib `/start` yuboring.

Mahalliy ishga tushganda oddiy bot buyruqlari ishlaydi. Telegram Mini App esa Telegram talabiga ko'ra ommaviy HTTPS manzilda ochilishi kerak; shu sabab Mini App'ni real Telegram ichida sinash uchun Render'ga joylash tavsiya qilinadi. Mahalliy test uchun HTTPS tunnel (masalan, ngrok) ochib `.env` ichidagi `WEBAPP_URL` qiymatiga tunnel manzilini kiriting, keyin botni qayta ishga tushiring.

## 2. GitHub + Render orqali doimiy ishga tushirish

1. GitHub'da yangi repository yarating.
2. `bot.py`, `requirements.txt`, `render.yaml`, `README.md`, `start.bat`, `.gitignore` fayllarini repository'ga yuklang. `.env` faylini GitHub'ga yuklamang — u maxfiy token uchun.
3. Render hisobingizda **New + → Blueprint** ni tanlab, repository'ni ulang. `render.yaml` orqali Web Service yaratiladi. Agar Blueprint tanlovi mavjud bo'lmasa, **New + → Web Service** tanlang, Build Command `pip install -r requirements.txt`, Start Command `python bot.py` deb kiriting.
4. Render service'ining **Environment** bo'limida quyidagilarni qo'shing:
   - `BOT_TOKEN` = BotFather bergan token
   - `ADMIN_IDS` = sizning Telegram raqamli ID'ingiz (bir nechta admin bo'lsa vergul bilan)
   - (ixtiyoriy) `APP_NAME` = do'kon nomi
5. Deploy tugagach Render bergan `https://....onrender.com` manzilni oching. `/health` sahifasi `{"ok":true,...}` qaytarsa server tirik.
6. Telegram'da botga `/start` yuboring. Render domeni HTTPS bo'lgani uchun kod `RENDER_EXTERNAL_HOSTNAME` asosida Mini App manzilini aniqlaydi va menyu tugmasini sozlaydi.

## 3. Admin buyruqlari

- `/admin` — admin panel.
- `/orders` — oxirgi buyurtmalar va status tugmalari.
- `/addproduct` — mahsulot qo'shish bosqichlari: nomi → kategoriya → narx (so'm) → tavsif → rasm URL yoki `skip`.
- `/cancel` — mahsulot qo'shishni bekor qilish.
- `/myorders` — mijozning o'z buyurtmalari.

Admin funksiyalari faqat `ADMIN_IDS` ichidagi Telegram raqamli ID'larga ochiq.

## 4. Ma'lumotlar bazasi va chegaralar

- Lokal ishga tushganda ma'lumotlar `aqua_home.db` faylida saqlanadi.
- Render'ning bepul servisidagi mahalliy fayllar doimiy saqlanishiga kafolat yo'q: qayta deploy/restart yoki servisning qayta yaratilishida SQLite ma'lumotlari yo'qolishi mumkin. Buyurtmalarni jiddiy savdo uchun saqlash kerak bo'lsa, persistent disk yoki boshqariladigan tashqi ma'lumotlar bazasi ulang. Disk ulanganida `DB_PATH=/var/data/aqua_home.db` kabi yo'lni servisga moslang.
- Render bepul servisi uzoq vaqt trafik bo'lmaganda uxlab qolishi mumkin; birinchi so'rov sekinroq javob berishi mumkin.
- Rasmlar tashqi Unsplash URL'laridan namuna sifatida olinadi; internet kerak. Haqiqiy mahsulot rasmlari va narxlarini admin orqali yangilang.
- Mini App'dagi buyurtma serverda Telegram `initData` imzosi tekshirilgandan so'ng qabul qilinadi. Tashqi oddiy brauzerda katalogni ko'rish mumkin, ammo buyurtma Telegram ichidan yuborilishi kerak.
- To'lov, yetkazib berish kuryer API'si, ombor integratsiyasi va SMS tasdiqlash qo'shilmagan.
