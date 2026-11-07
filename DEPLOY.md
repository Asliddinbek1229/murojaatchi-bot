# Serverga joylash va doimiy ishga tushirish

Ubuntu 22.04 / 24.04 yoki Debian 12 uchun yozilgan. Boshqa Linux distributivida ham ishlaydi, lekin u yerda Python'ni qo'lda o'rnatish kerak bo'ladi.

Botga **webhook, domen yoki ochiq port kerak emas**: bot o'zi Telegram'ga ulanadi (long polling). Serverda internet bo'lsa yetarli.

Quyida loyiha papkasi `/opt/murojaat-bot` deb olingan. O'rnatish skriptlari loyiha qaysi papkada turganini o'zi aniqlaydi, shuning uchun boshqa papka ham bo'ladi. Faqat buyruqlardagi yo'lni o'zingiznikiga almashtiring.

---

## 1. Fayllarni serverga joylash

**A) Git orqali (tavsiya etiladi).** Keyin yangilash bitta buyruq bilan bo'ladi.

```bash
sudo apt update && sudo apt install -y git
sudo git clone https://github.com/Asliddinbek1229/murojaatchi-bot.git /opt/murojaat-bot
cd /opt/murojaat-bot
```

Repozitoriy yopiq (private) bo'lsa, git parol so'raganda GitHub'dagi *Personal access token* ni kiriting.

**B) Git'siz (WinSCP, FileZilla yoki scp).** Kompyuteringizdan loyiha papkasini serverga ko'chiring. Quyidagilarni **ko'chirmang**:

- `.venv/` — Windows'niki, Linux'da ishlamaydi; serverda yangisi yaratiladi;
- `__pycache__/`;
- `.idea/`.

```bash
# kompyuteringizdan (PowerShell yoki Git Bash):
scp -r bot deploy scripts main.py requirements.txt .env.example README.md DEPLOY.md user@SERVER_IP:/tmp/murojaat-bot/
# serverda:
sudo mkdir -p /opt/murojaat-bot && sudo cp -r /tmp/murojaat-bot/. /opt/murojaat-bot/
cd /opt/murojaat-bot
```

> **Mavjud bazani ko'chirmoqchi bo'lsangiz:** `data/bot.db` bilan birga `data/.secret.key` ni ham ko'chiring. Bu kalit bo'lim botlarining tokenlarini ochadi; kalitsiz baza bilan bo'lim botlari ishga tushmaydi. Yangidan boshlasangiz, `data/` ni umuman ko'chirmang.

## 2. Sozlamalar (.env)

```bash
sudo cp .env.example .env
sudo nano .env
```

Faqat ikki qatorni to'ldirish majburiy:

```
BOT_TOKEN=123456789:AA...        # asosiy bot tokeni
SUPERADMIN_IDS=111111111         # sizning Telegram ID ingiz (bir nechta bo'lsa: 111,222)
```

Qolgan sozlamalarning standart qiymatlari yaxshi ishlaydi. Har birining izohi `.env` ichida yozilgan: loglar, avto-backup soati, nechta nusxa saqlanishi va boshqalar.

> ⚠️ **Bitta token bir vaqtda faqat bitta joyda ishlay oladi.** Serverda ishga tushirishdan oldin kompyuteringizdagi botni to'xtating. Aks holda ikkalasi ham xabar ololmay qoladi (Telegram'dagi `Conflict` xatosi).

## 3. O'rnatish (bitta buyruq)

```bash
sudo bash deploy/install.sh
```

Skript quyidagilarni avtomatik bajaradi:

1. Python 3.10+ va `venv` ni tekshiradi, yo'q bo'lsa o'rnatadi.
2. Bot uchun alohida tizim foydalanuvchisi `murojaat` ni yaratadi. Bot root nomidan ishlamaydi, bu xavfsizroq.
3. `.venv` yaratadi va kutubxonalarni o'rnatadi.
4. Huquqlarni sozlaydi:
   - `.env` va `data/` ni faqat bot o'qiy oladi;
   - `.env` ga `chmod 600` qo'yiladi.
5. `.env` ni tekshiradi. Token yoki ID noto'g'ri bo'lsa, aniq xato bilan to'xtaydi.
6. **systemd xizmati** `murojaat-bot` ni o'rnatadi, yoqadi va ishga tushiradi.

Muvaffaqiyatli o'rnatilsa, Telegram'da sizga kelgan bo'lishi kerak:

- asosiy botdan «🟢 **Tizim ishga tushdi**» xabari;
- har bir bo'lim botidan «ishga tushdi» xabari.

## 4. Doimiy ishlash qanday ta'minlanadi

Botni **systemd** boshqaradi. Bu Linux'ning o'z xizmat menejeri:

| Holat | Nima bo'ladi |
|---|---|
| Server qayta yondi | Bot avtomatik ishga tushadi (`enable`) |
| Dastur xato bilan yiqildi | 5 soniyadan keyin qayta ishga tushadi (`Restart=always`) |
| Internet uzildi | Bot o'chmaydi, ulanish tiklanguncha qayta urinadi (1 → 2 → 4 … 60 s) |
| Server yonganda internet hali yo'q | To'xtovsiz qayta urinadi, taslim bo'lmaydi |
| SSH oynasini yopdingiz | Bot ishlashda davom etadi (terminalga bog'liq emas) |
| `systemctl stop` / `restart` | Boshlangan ishlar (javob yuborish va h.k.) 15 soniyagacha tugatiladi, superadminga «to'xtadi» xabari ketadi |

Bot to'xtab turgan paytda talabalar yozgan xabarlar **yo'qolmaydi**: Telegram ularni 24 soatgacha saqlaydi va bot qayta yonganda hammasi qayta ishlanadi.

Yarim yig'ilgan murojaatlar ham saqlanib qoladi: «Yuborish» bosilmagan murojaatlar yoki admin yozayotgan javob. Ular bazada turadi.

## 5. Kundalik boshqaruv

```bash
sudo systemctl status murojaat-bot      # ishlayaptimi?
sudo journalctl -u murojaat-bot -f      # jonli loglar (chiqish: Ctrl+C)
sudo journalctl -u murojaat-bot --since "1 hour ago"
sudo systemctl restart murojaat-bot     # qayta ishga tushirish
sudo systemctl stop murojaat-bot        # to'xtatish
sudo systemctl start murojaat-bot       # ishga tushirish
```

**Telegram'dan** (asosiy botda, faqat superadmin):

- `/status` — ishlash vaqti, nechta bot ishlayotgani, baza hajmi, avto-backup holati;
- `/backup` — bazaning nusxasini darhol olib, fayl qilib yuboradi.

Kutilmagan xato yuz bersa, asosiy bot sizga «⚠️ **Botda xato**» xabarini yuboradi. Bir xil xato 10 daqiqada ko'pi bilan bir marta keladi.

## 6. Yangilash

Kodni o'zgartirganingizda:

```bash
cd /opt/murojaat-bot
sudo bash deploy/update.sh
```

Skript ketma-ket bajaradi:

1. Git ishlatilsa, `git pull` qiladi.
2. **Baza nusxasini oladi.**
3. Kutubxonalarni yangilaydi.
4. Kodni tekshiradi. Xato bo'lsa, to'xtaydi va eski versiya ishlashda davom etadi.
5. Botni qayta ishga tushiradi.

Git'siz joylagan bo'lsangiz, yangi fayllarni ustidan ko'chiring va shu buyruqni bering. `.env` va `data/` ga tegmang.

## 7. Zaxira nusxalar (backup)

- **Avtomatik:** har kuni soat 03:00 da (`BACKUP_HOUR`) `data/backups/` ga olinadi. Oxirgi 14 tasi saqlanadi (`BACKUP_KEEP`). Nusxa bot ishlab turgan paytda ham xavfsiz olinadi, butunligi tekshiriladi va siqiladi (`.db.gz`).
- **Qo'lda:**

  ```bash
  cd /opt/murojaat-bot
  sudo -u murojaat .venv/bin/python scripts/backup.py           # nusxa olish
  sudo -u murojaat .venv/bin/python scripts/backup.py --list    # ro'yxat
  ```

- **Tiklash:**

  ```bash
  sudo systemctl stop murojaat-bot
  sudo -u murojaat .venv/bin/python scripts/backup.py --restore data/backups/bot-2026-11-07_03-00-00.db.gz
  sudo systemctl start murojaat-bot
  ```

  Tiklashdan oldingi baza `bot.db.before-restore-...` nomi bilan saqlab qo'yiladi.

> 🔑 **Eng muhimi:** `data/.secret.key` faylini (yoki `.env` dagi `SECRET_KEY` ni) server tashqarisida ham saqlang, masalan parol menejerida. Server diski butunlay ishdan chiqsa, `/backup` bilan Telegram'ga olingan nusxa va shu kalit bilan hammasini tiklash mumkin.

## 8. Muammolar

| Belgi | Sabab va yechim |
|---|---|
| `install.sh`: «.env da xato bor» | Xato matnida qaysi qator ekani yozilgan. `sudo nano .env` bilan tuzating va skriptni qayta ishga tushiring |
| Logda `Conflict` | Shu token boshqa joyda ham ishlayapti (kompyuteringizda?). U yerdagisini to'xtating |
| Bo'lim boti «token yaroqsiz» deb to'xtadi | BotFather'da token o'zgartirilgan. Asosiy bot → Bo'lim botlari → bot → «Tokenni almashtirish» |
| Bo'lim botlari ishga tushmayapti, logda `InvalidToken` / `Fernet` | `.secret.key` boshqa: baza bir serverdan, kalit boshqasidan. To'g'ri kalitni `data/` ga qo'ying |
| `Python 3.10+ kerak` | Ubuntu 20.04 kabi eski tizim: `sudo apt install python3.11 python3.11-venv`, so'ng `sudo PYTHON=python3.11 bash deploy/install.sh` |
| Xizmat qayta-qayta yiqilyapti | `sudo journalctl -u murojaat-bot -n 100 --no-pager` — oxirgi xato shu yerda |

Xizmatni butunlay olib tashlash uchun: `sudo bash deploy/uninstall.sh`. Fayllar va baza o'chirilmaydi.

---

## Qo'shimcha: qo'lda ishga tushirish (sinov uchun)

```bash
cd /opt/murojaat-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py      # Ctrl+C bilan to'xtatiladi
```

Bu usul faqat sinov uchun: terminal yopilsa, bot ham to'xtaydi. Doimiy ishlashi uchun 3-bo'limdagi `install.sh` dan foydalaning.
