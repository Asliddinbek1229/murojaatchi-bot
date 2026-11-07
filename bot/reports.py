"""Excel hisobotlar (openpyxl): haftalik / oylik / yillik.

Varaqlar:
  1. «Umumiy»      — asosiy ko'rsatkichlar, holatlar, dinamika jadvali va diagrammalar
  2. «Bo'limlar»   — (faqat «barcha botlar» hisobotida) har bir bo'lim kesimida
  3. «Kategoriyalar» — (kategoriyalar bo'lsa) kategoriya kesimida holatlar, tezlik, dinamika, adminlar
  4. «Adminlar»    — har bir admin faoliyati
  5. «Murojaatlar» — har bir murojaat. Anonim murojaatlarda muallif haqida hech qanday ma'lumot yo'q;
                     anonimlik o'chirilgan botlarda — murojaatchi ismi, username va ID si.
"""
import asyncio
import html
import io
import re
from datetime import datetime, timedelta

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from bot.db import STATUSES, Database
from bot.ui import CONTENT_NAMES

FMT = "%Y-%m-%d %H:%M:%S"
MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust",
          "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
WEEKDAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]

NO_CATEGORY = "Kategoriyasiz"

# davr kodi -> (tugma matni)
PERIODS = {
    "w0": "Shu hafta", "w1": "O'tgan hafta",
    "m0": "Shu oy", "m1": "O'tgan oy",
    "y0": "Shu yil", "y1": "O'tgan yil",
}


# ---------------- davr ----------------
def period_range(code: str, today: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    """(boshlanish, tugash [kirmaydi], nomi, guruhlash: day|month)."""
    t = (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    kind, back = code[0], int(code[1])
    if kind == "w":
        start = t - timedelta(days=t.weekday()) - timedelta(weeks=back)
        end = start + timedelta(days=7)
        name = "Haftalik hisobot"
        group = "day"
    elif kind == "m":
        start = t.replace(day=1)
        for _ in range(back):
            start = (start - timedelta(days=1)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        name = f"Oylik hisobot — {MONTHS[start.month - 1]} {start.year}"
        group = "day"
    else:
        start = t.replace(month=1, day=1, year=t.year - back)
        end = start.replace(year=start.year + 1)
        name = f"Yillik hisobot — {start.year}"
        group = "month"
    return start, end, name, group


def fmt_date(d: datetime) -> str:
    return d.strftime("%d.%m.%Y")


# ---------------- ma'lumotni tayyorlash ----------------
_TAGS = re.compile(r"<[^>]+>")


def clean(text: str | None, limit: int = 32000) -> str:
    """HTML teglarini olib tashlaydi, Excel uchun ruxsat etilmagan belgilarni tozalaydi."""
    if not text:
        return ""
    t = html.unescape(_TAGS.sub("", text))
    return ILLEGAL_CHARACTERS_RE.sub("", t)[:limit]


def _dt(s: str | None) -> datetime | None:
    try:
        return datetime.strptime(s, FMT) if s else None
    except ValueError:
        return None


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    return round((b - a).total_seconds() / 3600, 1) if a and b else None


def _msg_line(m: dict) -> str:
    t = m["content_type"]
    body = clean(m.get("text"))
    if t == "text":
        return body
    return f"[{CONTENT_NAMES.get(t, t)}]" + (f" {body}" if body else "")


def _author(a: dict) -> str:
    """Murojaatchi — faqat anonim bo'lmagan murojaatda; aks holda «Anonim»."""
    if a.get("anonymous", 1) != 0:
        return "Anonim"
    parts = [clean(a.get("author_name")) or "Foydalanuvchi"]
    if a.get("author_username"):
        parts.append(f"@{a['author_username']}")
    parts.append(f"ID {a['user_id']}")
    return ", ".join(parts)


def prepare(data: dict) -> dict:
    """Xom ma'lumotdan hisobot qatorlari va ko'rsatkichlarni hisoblaydi."""
    by_appeal_msgs: dict[int, list] = {}
    for m in data["messages"]:
        by_appeal_msgs.setdefault(m["appeal_id"], []).append(m)
    by_appeal_ev: dict[int, list] = {}
    for ev in data["events"]:
        by_appeal_ev.setdefault(ev["appeal_id"], []).append(ev)
    names = data["names"]

    rows, admins = [], {}

    def adm(uid):
        return admins.setdefault(uid, {
            "name": names.get(uid) or str(uid), "accepted": 0, "rejected": 0, "closed": 0,
            "answered": set(), "replies": 0, "answer_hours": [],
        })

    for a in data["appeals"]:
        msgs = by_appeal_msgs.get(a["id"], [])
        evs = by_appeal_ev.get(a["id"], [])
        student = [m for m in msgs if m["sender"] == "student"]
        answers = [m for m in msgs if m["sender"] == "admin"]
        created = _dt(a["created_at"])
        first_action = next((_dt(e["at"]) for e in evs if e["action"] in ("in_progress", "rejected")), None)
        first_answer = _dt(answers[0]["created_at"]) if answers else None

        types: dict[str, int] = {}
        for m in student:
            types[m["content_type"]] = types.get(m["content_type"], 0) + 1
        content = ", ".join(f"{CONTENT_NAMES.get(t, t)}: {n}" for t, n in types.items())

        for e in evs:
            if e["admin_id"]:
                if e["action"] == "in_progress":
                    adm(e["admin_id"])["accepted"] += 1
                elif e["action"] == "rejected":
                    adm(e["admin_id"])["rejected"] += 1
                elif e["action"] == "closed":
                    adm(e["admin_id"])["closed"] += 1
        for m in answers:
            info = adm(m["sender_id"])
            info["answered"].add(a["id"])
            info["replies"] += 1
        if answers:
            adm(answers[0]["sender_id"])["answer_hours"].append(_hours(created, first_answer))

        rows.append({
            "id": a["id"],
            "created": created,
            "bot": a.get("bot_title") or "O'chirilgan bot",
            "category": a.get("category_title") or (NO_CATEGORY if a.get("category_id") is None else "O'chirilgan kategoriya"),
            "admin_id": answers[0]["sender_id"] if answers else None,
            "open_identity": a.get("anonymous", 1) == 0,
            "author": _author(a),
            "status": a["status"],
            "admin": a.get("admin_name") or "",
            "text": "\n".join(_msg_line(m) for m in student),
            "content": content,
            "answer": "\n".join(_msg_line(m) for m in answers),
            "reason": clean(a.get("reject_reason")),
            "react_h": _hours(created, first_action),
            "answer_h": _hours(created, first_answer),
            "has_answer": bool(answers),
        })
    cats = data.get("categories") or []
    has_cats = bool(cats) or any(r["category"] != NO_CATEGORY for r in rows)
    return {"rows": rows, "admins": admins, "categories": cats, "has_categories": has_cats}


# ---------------- uslublar ----------------
NAVY, BLUE, LIGHT, ZEBRA, GRID = "1F3864", "2F5597", "DCE6F2", "F5F8FC", "C9D3E3"
STATUS_FILL = {
    "new": "DDEBF7", "in_progress": "FFF2CC", "answered": "E2EFDA", "closed": "EDEDED", "rejected": "F8CBAD",
}
STATUS_NAME = {k: v[1] for k, v in STATUSES.items()}
THIN = Side(style="thin", color=GRID)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
HEAD_FILL = PatternFill("solid", fgColor=BLUE)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="top", wrap_text=True)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _title(ws, text: str, sub: list[str], width: int):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    c = ws.cell(row=1, column=1, value=text)
    c.font = Font(name="Calibri", bold=True, size=16, color="FFFFFF")
    c.fill = _fill(NAVY)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 34
    for i, line in enumerate(sub, start=2):
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=width)
        c = ws.cell(row=i, column=1, value=line)
        c.font = Font(name="Calibri", size=11, color=NAVY)
        c.fill = _fill(LIGHT)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[i].height = 20
    return len(sub) + 3  # keyingi bo'sh qatordan keyin


def _section(ws, row: int, text: str, width: int) -> int:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(name="Calibri", bold=True, size=12, color=NAVY)
    c.border = Border(bottom=Side(style="medium", color=BLUE))
    ws.row_dimensions[row].height = 22
    return row + 1


def _table(ws, row: int, headers: list[str], data: list[list], col: int = 1,
           aligns: list | None = None, status_col: int | None = None, statuses: list | None = None) -> int:
    for j, h in enumerate(headers):
        c = ws.cell(row=row, column=col + j, value=h)
        c.font, c.fill, c.alignment, c.border = HEAD_FONT, HEAD_FILL, CENTER, BORDER
    ws.row_dimensions[row].height = 30
    for i, values in enumerate(data, start=1):
        for j, v in enumerate(values):
            c = ws.cell(row=row + i, column=col + j, value=v)
            c.border = BORDER
            c.alignment = (aligns[j] if aligns else CENTER)
            if i % 2 == 0:
                c.fill = _fill(ZEBRA)
            if isinstance(v, float):
                c.number_format = "0.0"
        if status_col is not None and statuses:
            ws.cell(row=row + i, column=col + status_col).fill = _fill(STATUS_FILL.get(statuses[i - 1], "FFFFFF"))
    return row + len(data) + 1


def _avg(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _num(v: float | None):
    """0.0 ham son sifatida ko'rinsin; faqat qiymat yo'q bo'lsa «—»."""
    return "—" if v is None else v


def _pct(n: int, total: int) -> str:
    return f"{n / total * 100:.0f}%" if total else "—"


def _buckets(start: datetime, end: datetime, group: str) -> list[tuple[str, datetime, datetime]]:
    out = []
    if group == "day":
        d = start
        while d < end:
            out.append((f"{d.strftime('%d.%m')} ({WEEKDAYS[d.weekday()]})", d, d + timedelta(days=1)))
            d += timedelta(days=1)
    else:
        for m in range(1, 13):
            s = start.replace(month=m)
            e = s.replace(month=m + 1) if m < 12 else s.replace(year=s.year + 1, month=1)
            out.append((MONTHS[m - 1], s, e))
    return out


def _top_category(rows: list) -> tuple[str, int] | None:
    """Eng ko'p murojaat kelgan kategoriya («Kategoriyasiz» hisobga olinmaydi)."""
    counts: dict[str, int] = {}
    for x in rows:
        if x["category"] != NO_CATEGORY:
            counts[x["category"]] = counts.get(x["category"], 0) + 1
    return max(counts.items(), key=lambda kv: kv[1]) if counts else None


# ---------------- varaqlar ----------------
def _sheet_summary(ws, title: str, sub: list[str], rep: dict, start: datetime, end: datetime, group: str):
    rows = rep["rows"]
    total = len(rows)
    counts = {st: sum(1 for r in rows if r["status"] == st) for st in STATUSES}
    answered = sum(1 for r in rows if r["has_answer"])
    react = [r["react_h"] for r in rows]
    ans = [r["answer_h"] for r in rows if r["answer_h"] is not None]

    for col, w in zip("ABCDEFGHIJ", (34, 16, 12, 4, 16, 14, 14, 4, 12, 12)):
        ws.column_dimensions[col].width = w
    r = _title(ws, title, sub, 7)

    # --- asosiy ko'rsatkichlar ---
    r = _section(ws, r, "Asosiy ko'rsatkichlar", 3)
    kpi = [
        ["Jami murojaatlar", total, "100%" if total else "—"],
        ["Javob olgan murojaatlar", answered, _pct(answered, total)],
        ["Javob kutayotganlar (yangi + qabul qilingan)", counts["new"] + counts["in_progress"],
         _pct(counts["new"] + counts["in_progress"], total)],
        ["O'rtacha reaksiya vaqti (soat)", _avg(react) if _avg(react) is not None else "—", ""],
        ["O'rtacha javob muddati (soat)", _avg(ans) if ans else "—", ""],
        ["Eng tez javob (soat)", min(ans) if ans else "—", ""],
        ["Eng uzoq javob (soat)", max(ans) if ans else "—", ""],
    ]
    top = _top_category(rows) if rep["has_categories"] else None
    if top:
        top_name, top_n = top
        kpi.append(["Eng ko'p murojaat kelgan kategoriya", top_name, _pct(top_n, total)])
    kpi_start = r
    r = _table(ws, r, ["Ko'rsatkich", "Qiymat", "Ulushi"], kpi, aligns=[LEFT, CENTER, CENTER])
    for i in range(kpi_start + 1, kpi_start + 1 + len(kpi)):
        ws.cell(row=i, column=1).font = Font(bold=True, color=NAVY)
    r += 1

    # --- holatlar ---
    r = _section(ws, r, "Holatlar bo'yicha", 3)
    st_rows = [[STATUS_NAME[st], counts[st], _pct(counts[st], total)] for st in STATUSES]
    st_head = r
    r = _table(ws, r, ["Holat", "Soni", "Ulushi"], st_rows, aligns=[LEFT, CENTER, CENTER],
               status_col=0, statuses=list(STATUSES))
    if total:
        pie = PieChart()
        pie.title = "Holatlar ulushi"
        pie.add_data(Reference(ws, min_col=2, min_row=st_head, max_row=st_head + len(st_rows)), titles_from_data=True)
        pie.set_categories(Reference(ws, min_col=1, min_row=st_head + 1, max_row=st_head + len(st_rows)))
        pie.dataLabels = DataLabelList()
        pie.dataLabels.showPercent = True
        pie.height, pie.width = 7.5, 11
        ws.add_chart(pie, f"E{kpi_start}")
    r += 1

    # --- dinamika ---
    r = _section(ws, r, "Kunlar bo'yicha dinamika" if group == "day" else "Oylar bo'yicha dinamika", 3)
    buckets = _buckets(start, end, group)
    dyn = []
    for label, s, e in buckets:
        part = [x for x in rows if x["created"] and s <= x["created"] < e]
        dyn.append([label, len(part), sum(1 for x in part if x["has_answer"])])
    dyn_head = r
    r = _table(ws, r, ["Sana" if group == "day" else "Oy", "Kelgan", "Javob berilgan"], dyn,
               aligns=[LEFT, CENTER, CENTER])
    bar = BarChart()
    bar.type = "col"
    bar.title = "Murojaatlar dinamikasi"
    bar.y_axis.title = "Soni"
    bar.add_data(Reference(ws, min_col=2, max_col=3, min_row=dyn_head, max_row=dyn_head + len(dyn)), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=1, min_row=dyn_head + 1, max_row=dyn_head + len(dyn)))
    bar.height, bar.width = 8.5, 20
    ws.add_chart(bar, f"E{dyn_head}")
    ws.sheet_view.showGridLines = False


def _sheet_bots(ws, title: str, sub: list[str], rep: dict):
    rows = rep["rows"]
    bots: dict[str, list] = {}
    for x in rows:
        bots.setdefault(x["bot"], []).append(x)
    data = []
    for name, items in sorted(bots.items(), key=lambda kv: -len(kv[1])):
        c = {st: sum(1 for x in items if x["status"] == st) for st in STATUSES}
        data.append([
            name, len(items), c["new"], c["in_progress"], c["answered"], c["closed"], c["rejected"],
            _pct(sum(1 for x in items if x["has_answer"]), len(items)),
            _num(_avg([x["answer_h"] for x in items])),
        ])
    widths = (28, 10, 10, 14, 14, 12, 12, 14, 16)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = _title(ws, title, sub, len(widths))
    r = _section(ws, r, "Bo'limlar kesimida", len(widths))
    _table(ws, r, ["Bo'lim", "Jami", "Yangi", "Qabul qilingan", "Javob berilgan", "Yopilgan", "Rad etilgan",
                   "Javob ulushi", "O'rtacha javob (soat)"], data,
           aligns=[LEFT] + [CENTER] * 8)
    ws.sheet_view.showGridLines = False


def _cat_groups(rep: dict, all_bots: bool) -> list[tuple[tuple[str, str], list]]:
    """(bo'lim, kategoriya) -> murojaatlar. Davrda murojaati bo'lmagan kategoriyalar ham (bo'sh ro'yxat bilan)."""
    groups: dict[tuple[str, str], list] = {}
    for c in rep["categories"]:
        groups.setdefault((c["bot_title"] if all_bots else "", c["title"]), [])
    for x in rep["rows"]:
        groups.setdefault((x["bot"] if all_bots else "", x["category"]), []).append(x)
    order = list(groups)
    # tartib: bo'lim, so'ng murojaatlar soni (ko'pdan kamga); «Kategoriyasiz» — oxirida
    return sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] == NO_CATEGORY, -len(kv[1]), order.index(kv[0])))


def _sheet_categories(ws, title: str, sub: list[str], rep: dict, start: datetime, end: datetime,
                      group: str, all_bots: bool):
    rows = rep["rows"]
    total = len(rows)
    groups = _cat_groups(rep, all_bots)
    lead = ["Bo'lim", "Kategoriya"] if all_bots else ["Kategoriya"]
    lead_n = len(lead)
    heads = lead + ["Jami", "Ulushi", "Yangi", "Qabul qilingan", "Javob berilgan", "Yopilgan", "Rad etilgan",
                    "Javob ulushi", "O'rtacha reaksiya (soat)", "O'rtacha javob (soat)"]
    widths = ([22] if all_bots else []) + [30, 9, 9, 9, 12, 12, 11, 11, 11, 13, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = _title(ws, title, sub, len(heads))
    key = (lambda x: (x["bot"] if all_bots else "", x["category"]))
    label = (lambda k: f"{k[0]}: {k[1]}") if all_bots else (lambda k: k[1])

    # --- 1. kategoriyalar jadvali ---
    r = _section(ws, r, "Kategoriyalar kesimida", len(heads))
    data = []
    for (bot, cat), items in groups:
        c = {st: sum(1 for x in items if x["status"] == st) for st in STATUSES}
        n = len(items)
        data.append(([bot] if all_bots else []) + [
            cat, n, _pct(n, total), c["new"], c["in_progress"], c["answered"], c["closed"], c["rejected"],
            _pct(sum(1 for x in items if x["has_answer"]), n),
            _num(_avg([x["react_h"] for x in items])),
            _num(_avg([x["answer_h"] for x in items])),
        ])
    st_all = {st: sum(1 for x in rows if x["status"] == st) for st in STATUSES}
    data.append(([""] if all_bots else []) + [
        "JAMI", total, "100%" if total else "—", st_all["new"], st_all["in_progress"], st_all["answered"],
        st_all["closed"], st_all["rejected"], _pct(sum(1 for x in rows if x["has_answer"]), total),
        _num(_avg([x["react_h"] for x in rows])), _num(_avg([x["answer_h"] for x in rows])),
    ])
    head = r
    r = _table(ws, r, heads, data, aligns=[LEFT] * lead_n + [CENTER] * (len(heads) - lead_n))
    for j in range(1, len(heads) + 1):  # jami qatori
        c = ws.cell(row=r - 1, column=j)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _fill(NAVY)
    for j, st in enumerate(STATUSES):  # holat ustunlari sarlavhasi — holat rangida
        c = ws.cell(row=head, column=lead_n + 3 + j)
        c.fill = _fill(STATUS_FILL[st])
        c.font = Font(bold=True, color=NAVY)
    ws.freeze_panes = ws.cell(row=head + 1, column=lead_n + 1)
    r += 1

    n_cats = len(groups)
    if total and n_cats:
        bar = BarChart()
        bar.type = "bar"
        bar.title = "Kategoriyalar bo'yicha murojaatlar"
        bar.add_data(Reference(ws, min_col=lead_n + 1, min_row=head, max_row=head + n_cats), titles_from_data=True)
        bar.set_categories(Reference(ws, min_col=lead_n, min_row=head + 1, max_row=head + n_cats))
        bar.legend = None
        bar.height, bar.width = max(7.0, 0.7 * n_cats + 3), 16
        ws.add_chart(bar, f"A{r}")
        pie = PieChart()
        pie.title = "Kategoriyalar ulushi"
        pie.add_data(Reference(ws, min_col=lead_n + 1, min_row=head, max_row=head + n_cats), titles_from_data=True)
        pie.set_categories(Reference(ws, min_col=lead_n, min_row=head + 1, max_row=head + n_cats))
        pie.dataLabels = DataLabelList()
        pie.dataLabels.showPercent = True
        pie.height, pie.width = bar.height, 12
        ws.add_chart(pie, f"{get_column_letter(lead_n + 5)}{r}")
        r += int(bar.height * 2) + 3  # diagramma egallagan qatorlar (~0.5 sm qator)

    # --- 2. dinamika (davr × kategoriya) ---
    active = [k for k, items in groups if items]
    top = active[:12]  # ko'pi bilan 12 ta ustun, qolganlari — «Boshqalar»
    other = len(active) > len(top)
    if total and top:
        r = _section(ws, r, ("Kunlar" if group == "day" else "Oylar") + " bo'yicha kategoriyalar dinamikasi",
                     len(heads))
        dheads = ["Sana" if group == "day" else "Oy"] + [label(k) for k in top] + (["Boshqalar"] if other else []) + ["Jami"]
        ddata = []
        for lab, s, e in _buckets(start, end, group):
            part = [x for x in rows if x["created"] and s <= x["created"] < e]
            vals = [sum(1 for x in part if key(x) == k) for k in top]
            if other:
                vals.append(len(part) - sum(vals))
            ddata.append([lab] + vals + [len(part)])
        dhead = r
        r = _table(ws, r, dheads, ddata, aligns=[LEFT] + [CENTER] * (len(dheads) - 1))
        chart = BarChart()
        chart.type = "col"
        chart.grouping = "stacked"
        chart.overlap = 100
        chart.title = "Kategoriyalar dinamikasi"
        chart.y_axis.title = "Soni"
        chart.add_data(Reference(ws, min_col=2, max_col=len(dheads) - 1, min_row=dhead, max_row=dhead + len(ddata)),
                       titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=dhead + 1, max_row=dhead + len(ddata)))
        chart.height, chart.width = 9, 24
        ws.add_chart(chart, f"A{r + 1}")
        r += 22

    # --- 3. adminlar × kategoriyalar ---
    answered = [x for x in rows if x["admin_id"]]
    if answered and top:
        names = {uid: info["name"] for uid, info in rep["admins"].items()}
        r = _section(ws, r, "Adminlar javob bergan murojaatlar — kategoriyalar kesimida", len(heads))
        aheads = ["Admin"] + [label(k) for k in top] + (["Boshqalar"] if other else []) + ["Jami"]
        adata = []
        uids = sorted({x["admin_id"] for x in answered}, key=lambda u: -sum(1 for x in answered if x["admin_id"] == u))
        for uid in uids:
            mine = [x for x in answered if x["admin_id"] == uid]
            vals = [sum(1 for x in mine if key(x) == k) for k in top]
            if other:
                vals.append(len(mine) - sum(vals))
            adata.append([names.get(uid, str(uid))] + vals + [len(mine)])
        _table(ws, r, aheads, adata, aligns=[LEFT] + [CENTER] * (len(aheads) - 1))
    ws.sheet_view.showGridLines = False


def _sheet_admins(ws, title: str, sub: list[str], rep: dict):
    data = []
    for info in sorted(rep["admins"].values(), key=lambda a: -len(a["answered"])):
        data.append([
            info["name"], info["accepted"], len(info["answered"]), info["replies"],
            info["closed"], info["rejected"], _num(_avg(info["answer_hours"])),
        ])
    widths = (30, 14, 16, 14, 12, 12, 18)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = _title(ws, title, sub, len(widths))
    r = _section(ws, r, "Adminlar faoliyati", len(widths))
    if not data:
        ws.cell(row=r, column=1, value="Bu davrda adminlar faoliyati qayd etilmagan.").font = Font(italic=True, color="808080")
    else:
        _table(ws, r, ["Admin", "Qabul qilgan", "Javob bergan (murojaat)", "Javob xabarlari", "Yopgan",
                       "Rad etgan", "O'rtacha javob muddati (soat)"], data, aligns=[LEFT] + [CENTER] * 6)
    ws.sheet_view.showGridLines = False


def _sheet_appeals(ws, title: str, sub: list[str], rep: dict, with_bot: bool):
    heads = ["№", "Sana", "Holati", "Mas'ul admin", "Murojaat matni", "Tarkibi", "Javob", "Rad etish sababi",
             "Reaksiya (soat)", "Javob muddati (soat)"]
    widths = [8, 17, 17, 22, 60, 18, 50, 28, 12, 14]
    with_cat = rep["has_categories"]
    with_author = any(x["open_identity"] for x in rep["rows"])
    if with_author:
        heads.insert(3, "Murojaatchi")
        widths.insert(3, 30)
    if with_cat:
        heads.insert(2, "Kategoriya")
        widths.insert(2, 22)
    if with_bot:
        heads.insert(2, "Bo'lim")
        widths.insert(2, 20)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    note = ("Anonim murojaatlarda muallif haqida hech qanday ma'lumot yo'q; «Murojaatchi» ustuni faqat "
            "anonimlik o'chirilgan botlarga yuborilgan murojaatlarda to'ldirilgan." if with_author else
            "Murojaatlar anonim: hisobotda murojaatchilar shaxsi haqida hech qanday ma'lumot yo'q.")
    r = _title(ws, title, sub + [note], len(heads))
    data, statuses = [], []
    for x in rep["rows"]:
        row = [
            x["id"], x["created"].strftime("%d.%m.%Y %H:%M") if x["created"] else "",
            STATUS_NAME.get(x["status"], x["status"]), x["admin"], x["text"], x["content"],
            x["answer"], x["reason"],
            x["react_h"] if x["react_h"] is not None else "—",
            x["answer_h"] if x["answer_h"] is not None else "—",
        ]
        if with_author:
            row.insert(3, x["author"])
        if with_cat:
            row.insert(2, x["category"])
        if with_bot:
            row.insert(2, x["bot"])
        data.append(row)
        statuses.append(x["status"])
    aligns = [CENTER, CENTER, CENTER, LEFT, LEFT, LEFT, LEFT, LEFT, CENTER, CENTER]
    if with_author:
        aligns.insert(3, LEFT)
    if with_cat:
        aligns.insert(2, LEFT)
    if with_bot:
        aligns.insert(2, LEFT)
    head_row = r
    if not data:
        ws.cell(row=r, column=1, value="Bu davrda murojaatlar bo'lmagan.").font = Font(italic=True, color="808080")
    else:
        _table(ws, r, heads, data, aligns=aligns, status_col=2 + int(with_bot) + int(with_cat), statuses=statuses)
        ws.auto_filter.ref = f"A{head_row}:{get_column_letter(len(heads))}{head_row + len(data)}"
        ws.freeze_panes = ws.cell(row=head_row + 1, column=3)
    ws.sheet_view.showGridLines = False


def build_xlsx(data: dict, scope_name: str, period_name: str, start: datetime, end: datetime,
               group: str, all_bots: bool) -> tuple[bytes, dict]:
    rep = prepare(data)
    sub = [
        f"Bo'lim: {scope_name}",
        f"Davr: {fmt_date(start)} — {fmt_date(end - timedelta(days=1))}",
        f"Tuzilgan: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    _sheet_summary(ws, f"Murojaatlar hisoboti · {period_name}", sub, rep, start, end, group)
    if all_bots:
        _sheet_bots(wb.create_sheet("Bo'limlar"), "Bo'limlar kesimida", sub, rep)
    if rep["has_categories"]:
        _sheet_categories(wb.create_sheet("Kategoriyalar"), "Kategoriyalar bo'yicha statistika", sub, rep,
                          start, end, group, all_bots)
    _sheet_admins(wb.create_sheet("Adminlar"), "Adminlar faoliyati", sub, rep)
    _sheet_appeals(wb.create_sheet("Murojaatlar"), "Murojaatlar ro'yxati", sub, rep, all_bots)
    for sheet in wb.worksheets:
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
    wb.properties.title = f"Murojaatlar hisoboti — {scope_name}"
    wb.properties.creator = "Murojaat-bot"
    buf = io.BytesIO()
    wb.save(buf)

    rows = rep["rows"]
    summary = {
        "total": len(rows),
        "answered": sum(1 for x in rows if x["has_answer"]),
        "open": sum(1 for x in rows if x["status"] in ("new", "in_progress")),
        "rejected": sum(1 for x in rows if x["status"] == "rejected"),
        "avg_answer": _avg([x["answer_h"] for x in rows]),
        "top_category": _top_category(rows) if rep["has_categories"] else None,
    }
    return buf.getvalue(), summary


async def make_report(db: Database, code: str, bot_id: int | None, scope_name: str) -> tuple[bytes, str, dict, str]:
    """Hisobotni tayyorlaydi: (fayl baytlari, fayl nomi, qisqa xulosa, davr matni).
    Excel yasash og'ir ish — alohida oqimda bajariladi, bot boshqa foydalanuvchilarga javob berishda davom etadi."""
    start, end, name, group = period_range(code)
    data = await db.report_data(start.strftime(FMT), end.strftime(FMT), bot_id)
    content, summary = await asyncio.to_thread(
        build_xlsx, data, scope_name, name, start, end, group, bot_id is None
    )
    safe = re.sub(r"[^\w\-]+", "_", scope_name, flags=re.UNICODE).strip("_")[:40] or "hisobot"
    filename = f"Hisobot_{safe}_{code}_{start.strftime('%Y-%m-%d')}.xlsx"
    period_text = f"{name} ({PERIODS[code]}): {fmt_date(start)} — {fmt_date(end - timedelta(days=1))}"
    return content, filename, summary, period_text
