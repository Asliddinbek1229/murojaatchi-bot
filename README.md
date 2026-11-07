# Murojaat-bot — anonim murojaatlar tizimi (ko'p botli)

Talabalar bo'limlarga **anonim** murojaat yuboradigan Telegram botlar tizimi (aiogram 3 + SQLite).

```
                 ┌──────────────────────────┐
                 │   ASOSIY BOT (markaz)    │  ← superadmin paneli, bo'limlar katalogi
                 └────────────┬─────────────┘
                              │ bitta dastur, bitta baza
      ┌───────────────┬───────┴───────┬────────────────┐
  @dekanat_bot   @yotoqxona_bot  @stipendiya_bot   @...bot
  talaba + admin talaba + admin  talaba + admin
```

- **Asosiy bot** — faqat superadmin uchun. Boshqalar `/start` bosganda bot haqida qisqa ma'lumot oladi, xolos;
  boshqa xabar va tugmalarga javob berilmaydi.
- **Bo'lim boti** — har bir bo'limning o'z boti. Talaba shu botga murojaat yozadi, shu botning adminlari javob beradi.
  Bo'lim botlari tokeni asosiy botga kiritiladi va dastur qayta ishga tushirilmasdan darhol ishlay boshlaydi.

## Imkoniyatlar

**Talaba (bo'lim botida)**
- Murojaat: matn, rasm, video, hujjat, ovozli xabar, albom (10 tagacha). «Yuborish» bosilmaguncha hech narsa ketmaydi;
  har bir xabardan keyin nima qo'shilgani, ko'rib chiqish va oxirgisini o'chirish tugmalari ko'rsatiladi
- Holat o'zgarganda xabar oladi; «Mening murojaatlarim», «Qanday ishlaydi?» yo'riqnomasi
- Shaxsi (ism, username, ID) hech kimga ko'rsatilmaydi

**Admin (o'z bo'lim botida)**
- Murojaat hayot sikli: 🆕 Yangi → ✅ **Qabul qilish** (talabaga «qabul qilindi, tez orada javob beramiz») yoki
  ❌ **Rad etish** (sabab bilan yoki sababsiz) → ✍️ Javob yozish (matn/rasm/video/hujjat) → 🔒 Yopish; qayta ochish mumkin
- «Ochiq murojaatlar» — faqat yangi va qabul qilingan (javob kutayotgan) murojaatlar, eng eskisi birinchi.
  Javob berilgan, yopilgan va rad etilganlar ro'yxatda ko'rinmaydi
- Murojaat kartasi barcha adminlarda bir vaqtda yangilanadi (holat, mas'ul xodim, faqat mumkin bo'lgan tugmalar)
- Ikki admin bir vaqtda bossa — faqat bittasi o'tadi, ikkinchisiga kim bajargani aytiladi
- Shaxsiy statistika: ishdagi, javob berilgan, yopilgan, rad etilgan

**Superadmin (asosiy botda `/admin` yoki «🛠 Admin panel»)**
- 🤖 **Bo'lim botlari**: token bilan qo'shish (tekshiriladi, shifrlanadi, bot profili avtomatik sozlanadi),
  to'xtatish/ishga tushirish, nomini o'zgartirish, tokenni almashtirish, o'chirish
- 👮 **Adminlar** (har bir botga alohida): qo'shish (kontaktdan, ID, @username, forward), faol/nofaol, olib tashlash,
  taklif havolasi (`t.me/bot?start=admin`)
- 📊 Statistika — umumiy va har bir bot bo'yicha
- 📨 Murojaatlar — bot va holat bo'yicha filtr, raqam bo'yicha qidirish; asosiy botda matnli ko'rinish,
  «… da ochish» tugmasi murojaatni rasm/videolari bilan bo'lim botida ochadi
- 🚫 Bloklash — barcha botlarda amal qiladi, shaxs yashirin qoladi
- 📢 E'lon — hammaga (har kimga bir marta), faqat asosiy bot yoki bitta bo'lim boti foydalanuvchilariga
- ✨ Premium emojilar — 74 ta emojini premiumga almashtirish (matnda `<tg-emoji>`, tugmada ikonka)

Superadmin barcha bo'lim botlarida avtomatik admin. Bo'lim botida faol admin bo'lmasa, murojaat haqida
asosiy bot orqali superadminga xabar boradi.

## Bilish muhim

- **Fayllar har bir botga bog'liq.** Bir bot qabul qilgan rasm/videoni boshqa bot yubora olmaydi — shuning uchun
  murojaat media bilan faqat o'z bo'lim botida ochiladi. E'lonlarda fayl avtomatik qayta yuklanadi (20 MB gacha).
- **Bot faqat uni ochgan odamga yoza oladi.** Yangi admin bo'lim botini ochib «Start» bosishi kerak — asosiy bot
  unga havolani yuboradi; admin kartasida «botni ochgan / ochmagan» ko'rinadi.
- **Premium emoji** faqat egasida Telegram Premium bo'lgan botlarda ishlaydi — bo'lim botlarini ham Premium
  akkauntingizdan yarating.
- **Tokenlar** shifrlangan holda saqlanadi. `data/.secret.key` (yoki `.env` dagi `SECRET_KEY`) yo'qolsa, bo'lim
  botlari tokenlarini qayta kiritishga to'g'ri keladi. Token BotFather'da bekor qilinsa, bot avtomatik to'xtaydi va
  superadminga xabar boradi.

## Anonimlik rejimi (har bir bot uchun)

- Superadmin: bot kartasi → «Anonimlik: yoqilgan/o'chirilgan». Standart holatda **yoqilgan**.
- **Yoqilgan:** murojaatchi anonim, adminlar uning shaxsini ko'rmaydi.
- **O'chirilgan:** admin kartasida murojaatchining ismi (bosiladigan), username va Telegram ID'si ko'rinadi.
  Shuningdek «Murojaatchi bilan bog'lanish» tugmasi chiqadi. Talabaga bu bot boshida, yordamda va murojaat
  yozishda «murojaat anonim emas» deb aniq aytiladi. Bot tavsifi ham shunga moslanadi.
- Rejim har bir murojaatga yuborilgan paytda yoziladi:
  - eski anonim murojaatlar rejim o'zgarganda ham anonim qoladi;
  - talaba anonim rejimda yozishni boshlagan bo'lsa, murojaati anonim ketadi.
- Telegram bot'larga telefon raqamini bermaydi (foydalanuvchi o'zi ulashmasa). Username bo'lmasa va
  profil yopiq bo'lsa, bog'lanish tugmasi chiqmaydi, lekin ism va ID baribir ko'rinadi.

## Bir nechta admin — sinxron ishlash

Murojaat bo'limning barcha faol adminlariga keladi:
- Holat atomik o'zgaradi: ikki admin bir vaqtda «Qabul qilish»ni bossa, faqat bittasi qabul qiladi.
  Ikkinchisiga «allaqachon qabul qilingan (Ism)» degan ogohlantirish chiqadi.
- Har qanday amaldan keyin (qabul, rad, javob, yopish, qayta ochish) barcha adminlardagi karta bir zumda yangilanadi.
  Kartada holat, mas'ul admin va o'sha holatga mos tugmalar ko'rinadi.
- Qabul qilingan murojaatga istalgan admin javob yoza oladi.

## Murojaat kategoriyalari (ixtiyoriy)

- Superadmin: Asosiy bot → Bo'lim botlari → bot → «Murojaat kategoriyalari» → «Kategoriya qo'shish».
  Bir nechtasini birdaniga qo'shish mumkin: har birini yangi qatorga yozasiz.
- Kategoriyani nomlash, tartibini o'zgartirish (yuqoriga/pastga), yashirish va o'chirish mumkin.
  Murojaatlari bor kategoriya o'chirilsa, eski murojaatlar va hisobotlarda nomi saqlanib qoladi.
- Har bir kategoriyaga ixtiyoriy **izoh** yozish mumkin (kategoriya kartasi → «Izoh qo'shish»). Talaba shu
  kategoriyani tanlagach, izoh «Murojaatingizni yozing» xabarida mavzu ostida ko'rinadi. Izohda formatlash
  va premium emoji ishlaydi. Saqlashdan oldin superadminga talaba ko'radigan ko'rinish yuboriladi.
- Botda faol kategoriya bo'lsa, talaba «Murojaat yuborish»ni bosgach avval **mavzuni tanlaydi**, keyin yozadi.
  Kategoriya bo'lmasa, bot avvalgidek ishlaydi.
- Kategoriya admin kartasida, ro'yxatlarda, talabaning «Mening murojaatlarim» bo'limida va statistikada ko'rinadi.
- Excel hisobotda alohida **Kategoriyalar** varag'i paydo bo'ladi:
  - har bir kategoriya bo'yicha: soni, ulushi, holatlar, javob ulushi, o'rtacha reaksiya va javob vaqti;
  - ikkita diagramma;
  - kunlar yoki oylar bo'yicha dinamika;
  - adminlar × kategoriyalar jadvali.
  
  «Murojaatlar» varag'iga «Kategoriya» ustuni qo'shiladi.

## Excel hisobotlar

- **Bo'lim botida** admin «📑 Hisobot» tugmasini bosadi → davrni tanlaydi → bot `.xlsx` faylni yuboradi.
- **Asosiy botda** superadmin: Admin panel → «Excel hisobotlar» → bo'lim (yoki «Barcha bo'limlar») → davr.
  Bot kartasida ham «Excel hisobot» tugmasi bor.
- Davrlar: shu / o'tgan **hafta** (Du–Ya), shu / o'tgan **oy**, shu / o'tgan **yil** (oylar kesimida).
- Fayl varaqlari: **Umumiy** (ko'rsatkichlar, holatlar, dinamika, 2 ta diagramma), **Bo'limlar** (umumiy hisobotda),
  **Adminlar** (qabul qilgan, javob bergan, yopgan, rad etgan, o'rtacha javob muddati), **Murojaatlar**
  (har bir murojaat: matn, javob, holat rangli, filtr va qotirilgan sarlavha). Talabalar shaxsi hisobotda yo'q.
- Reaksiya vaqti (qabul/rad etilgunga qadar) shu versiyadan boshlab qayd etiladi; avvalgi murojaatlar uchun «—».

## Ishga tushish va to'xtash xabarlari

- Tizim ishga tushganda asosiy bot superadminga hisobot yuboradi: qaysi bo'lim botlari ishlayapti, qaysilari xato bilan
  ishga tushmadi, qaysilari o'chirib qo'yilgan. Har bir bo'lim boti ham o'z chatida «ishga tushdi» deb yozadi.
- To'g'ri to'xtatilganda (Ctrl+C, `systemctl stop`) har bir bo'lim boti va asosiy bot «to'xtadi» deb yozadi.
  Panel orqali bitta bot to'xtatilsa yoki o'chirilsa — o'sha bot sababini yozadi.
- Kutilmagan to'xtash (server o'chishi, jarayon majburan yopilishi) paytida xabar yuborishning iloji yo'q —
  shuning uchun keyingi ishga tushishda hisobotda «oldingi safar kutilmaganda to'xtagan» ogohlantirishi chiqadi.
- Bot to'xtab turgan paytda yozilgan xabarlar yo'qolmaydi: Telegram ularni saqlaydi (24 soatgacha) va bot qayta
  ishga tushganda qabul qilinadi.

## O'rnatish

**Serverga (production, doimiy ishlash):** batafsil qo'llanma — [DEPLOY.md](DEPLOY.md). Qisqasi:

```bash
sudo cp .env.example .env && sudo nano .env    # BOT_TOKEN, SUPERADMIN_IDS
sudo bash deploy/install.sh                    # venv, kutubxonalar, systemd xizmati
sudo bash deploy/update.sh                     # keyingi yangilashlar (avval backup oladi)
```

**Kompyuterda (ishlab chiqish):**

```bash
python -m venv .venv
.venv\Scripts\activate        # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
python main.py
```

Keyin asosiy botda: Admin panel → Bo'lim botlari → «Bo'lim boti qo'shish».

## Tuzilma

```
main.py                     — ishga tushirish, routerlar
bot/manager.py              — BotManager: botlarni yurgizish, token tekshirish/shifrlash
bot/config.py               — .env sozlamalari
bot/db.py                   — SQLite bazasi (bots, bot_admins, bot_users, appeals ...)
bot/middlewares.py          — kontekst: qaysi bot, rol, blok
bot/ui.py                   — emoji reyestri, premium emoji, rangli tugmalar
bot/keyboards.py, texts.py  — tugmalar va matnlar
bot/utils.py                — xabar yig'ish, murojaatni ko'rsatish/yetkazish
bot/handlers/common.py      — /start (deep link), /cancel, /id
bot/handlers/main_user.py   — asosiy bot: begonalar uchun to'siq (faqat qisqa ma'lumot)
bot/handlers/superadmin.py  — asosiy bot: superadmin paneli
bot/handlers/emoji.py       — asosiy bot: premium emojilar
bot/handlers/admin.py       — bo'lim boti: admin
bot/handlers/student.py     — bo'lim boti: talaba
bot/handlers/report.py      — Excel hisobotlar (bo'lim boti va asosiy bot)
bot/handlers/system.py      — asosiy bot: /status, /backup
bot/reports.py              — Excel fayl yasash
bot/storage.py              — FSM holati SQLite'da (qayta ishga tushganda yo'qolmaydi)
bot/backup.py, scripts/backup.py — zaxira nusxa olish/tiklash
bot/logs.py                 — logging (konsol + ixtiyoriy aylanuvchi fayl)
deploy/                     — systemd xizmati, install.sh, update.sh, uninstall.sh
```

FSM holati bazada saqlanadi — dastur qayta ishga tushsa ham yarim yozilgan murojaatlar va javoblar yo'qolmaydi.
