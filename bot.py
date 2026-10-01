# -*- coding: utf-8 -*-
import json
import logging
import os
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cs-library-bot")

BASE_DIR = Path(__file__).parent
COURSES_FILE = BASE_DIR / "courses.json"
CONTENT_FILE = BASE_DIR / "content.json"
TREE_IMAGE = BASE_DIR / "assets" / "tree.jpg"

# ---------- الإعدادات ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
ABOUT_TEXT = (
    "🎓 *Computer Science Bot*\n\n"
    "مكتبة إلكترونية لطلبة قسم علوم الحاسوب: شيتات وملخصات وأسئلة ومراجع لكل مادة، "
    "مرتبة حسب الفصل الدراسي.\n\n"
    "لو عندك ملف تبي تضيفه، ابعته لمشرف المكتبة :."
    " @rayan04al ."
    " \n"
    " Made by Rayan Alhajni ."
)

SEM_NAMES = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن"]
KIND_LABEL = {
    "general": "🟢 مادة عامة",
    "major": "🔵 مادة تخصصية",
    "support": "🔴 مادة داعمة",
    "elective": "🟡 مادة اختيارية",
}
SECTIONS = [
    ("books", "📚 المراجع والكتب"),
    ("sheets", "📝 الشيتات"),
    ("exams", "📋 الأسئلة"),
]
SECTION_LABEL = dict(SECTIONS)

BTN_COURSES = "📚 المواد"
BTN_TREE = "🌳 شجرة المواد"
BTN_SEARCH = "🔍 البحث عن مادة"
BTN_ABOUT = "ℹ️ عن المكتبة"
BTN_ADMIN = "👑 لوحة الإدارة"
BTN_BACK = "🔙 رجوع"

ADMIN_ADD = "📤 إضافة محتوى"
ADMIN_DEL = "🗑️ حذف محتوى"
ADMIN_EDIT = "✏️ تعديل مادة"
ADMIN_TREE = "🌳 تحديث شجرة المواد"

# ---------- 1) البيانات ----------
def load_courses():
    return json.loads(COURSES_FILE.read_text(encoding="utf-8"))


def load_content():
    if CONTENT_FILE.exists():
        return json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
    return {}


def save_content(content):
    CONTENT_FILE.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


COURSES = load_courses()
COURSE_BY_ID = {c["id"]: c for c in COURSES}


# ---------- 2) دوال مساعدة (بدون تلغرام) ----------
def courses_in_sem(n):
    return [c for c in COURSES if c["sem"] == n]


def norm(s: str) -> str:
    s = s.lower().strip()
    for a, b in [("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ـ", "")]:
        s = s.replace(a, b)
    return s


def find_courses(query: str):
    q = norm(query)
    if not q:
        return []
    return [c for c in COURSES if q in norm(c["name"]) or q in norm(c["code"])]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def course_caption(c):
    p = "نظري وعملي" if c.get("p") else "نظري"
    return f"*{c['name']}*\n{KIND_LABEL[c['kind']]} · `{c['code']}` · {c['u']} وحدات · {p}"


def add_content_item(content, course_id, section, item):
    content.setdefault(course_id, {}).setdefault(section, []).append(item)
    save_content(content)


def delete_content_item(content, course_id, section, index):
    items = content.get(course_id, {}).get(section, [])
    if 0 <= index < len(items):
        removed = items.pop(index)
        save_content(content)
        return removed
    return None


def move_course_semester(course_id, new_sem):
    c = COURSE_BY_ID.get(course_id)
    if not c or not (1 <= new_sem <= 8):
        return False
    c["sem"] = new_sem
    COURSES_FILE.write_text(json.dumps(COURSES, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# ---------- 3) لوحات الأزرار ----------
def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    rows = [[BTN_COURSES], [BTN_TREE, BTN_SEARCH], [BTN_ABOUT]]
    if is_admin(user_id):
        rows.append([BTN_ADMIN])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    rows = [[ADMIN_ADD, ADMIN_DEL], [ADMIN_EDIT, ADMIN_TREE], [BTN_BACK]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def kb_semesters(prefix="sem") -> InlineKeyboardMarkup:
    rows = []
    for y in range(1, 5):
        s1, s2 = y * 2 - 1, y * 2
        rows.append([
            InlineKeyboardButton(f"الفصل {SEM_NAMES[s1-1]}", callback_data=f"{prefix}:{s1}"),
            InlineKeyboardButton(f"الفصل {SEM_NAMES[s2-1]}", callback_data=f"{prefix}:{s2}"),
        ])
    return InlineKeyboardMarkup(rows)


def kb_semester_courses(n, prefix="course") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{c['name']}", callback_data=f"{prefix}:{c['id']}")] for c in courses_in_sem(n)]
    rows.append([InlineKeyboardButton("↩️ كل الفصول", callback_data="sems")])
    return InlineKeyboardMarkup(rows)


def kb_course(course_id, content) -> InlineKeyboardMarkup:
    files = content.get(course_id, {})
    rows = [[InlineKeyboardButton(f"{label} ({len(files.get(key, []))})", callback_data=f"sec:{course_id}:{key}")]
            for key, label in SECTIONS]
    c = COURSE_BY_ID[course_id]
    rows.append([InlineKeyboardButton("↩️ رجوع للفصل", callback_data=f"sem:{c['sem']}")])
    return InlineKeyboardMarkup(rows)


def kb_section_files(course_id, sec, items) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📎 {it['title']}", callback_data=f"file:{course_id}:{sec}:{i}")]
            for i, it in enumerate(items)]
    rows.append([InlineKeyboardButton("↩️ رجوع للمادة", callback_data=f"course:{course_id}")])
    return InlineKeyboardMarkup(rows)


# ---------- 4) هاندلرز الطالب ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "مرحباً بك في *مكتبة قسم علوم الحاسوب* 📚", reply_markup=main_menu(update.effective_user.id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"آي دي حسابك: `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)


async def show_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر الفصل الدراسي:", reply_markup=kb_semesters())


async def show_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if TREE_IMAGE.exists():
        await update.message.reply_photo(TREE_IMAGE.open("rb"), caption="🌳 شجرة مواد قسم علوم الحاسوب")
    else:
        await update.message.reply_text("ما فيه صورة شجرة مضافة بعد.")


async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT, parse_mode=ParseMode.MARKDOWN)


async def ask_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "searching"
    await update.message.reply_text("اكتب اسم المادة أو رمزها:")


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    hits = find_courses(query)
    if not hits:
        await update.message.reply_text("ما لقيت مادة بهذا الاسم. جرب كلمة ثانية.")
        return
    rows = [[InlineKeyboardButton(f"{c['name']} — الفصل {SEM_NAMES[c['sem']-1]}", callback_data=f"course:{c['id']}")]
            for c in hits]
    await update.message.reply_text("🔍 نتائج البحث:", reply_markup=InlineKeyboardMarkup(rows))


# ---------- 5) هاندلرز الأدمن ----------
async def open_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data.clear()
    await update.message.reply_text("👑 لوحة الإدارة", reply_markup=admin_menu())


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("القائمة الرئيسية:", reply_markup=main_menu(update.effective_user.id))


async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data["state"] = None
    await update.message.reply_text("💻 اختاري المادة:", reply_markup=kb_semesters(prefix="add_sem"))


async def admin_del_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🗑️ اختاري المادة:", reply_markup=kb_semesters(prefix="del_sem"))


async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("✏️ اختاري المادة اللي تبين تنقلينها لفصل ثاني:", reply_markup=kb_semesters(prefix="edit_sem"))


async def admin_update_tree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data["state"] = "awaiting_tree_image"
    await update.message.reply_text("ابعتي صورة الشجرة الجديدة الآن.")


# ---------- توجيه ضغطات الأزرار الشفافة (Inline) ----------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    content = load_content()
    user_id = q.from_user.id

    if data == "sems":
        await q.edit_message_text("اختر الفصل الدراسي:", reply_markup=kb_semesters())
        return

    if data.startswith("sem:"):
        n = int(data.split(":")[1])
        await q.edit_message_text(f"الفصل {SEM_NAMES[n-1]} — اختر مادة:", reply_markup=kb_semester_courses(n))
        return

    if data.startswith("course:"):
        cid = data.split(":")[1]
        c = COURSE_BY_ID.get(cid)
        if not c:
            await q.edit_message_text("المادة غير موجودة.")
            return
        await q.edit_message_text(course_caption(c), reply_markup=kb_course(cid, content), parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("sec:"):
        _, cid, sec = data.split(":")
        items = content.get(cid, {}).get(sec, [])
        c = COURSE_BY_ID[cid]
        title = f"{c['name']} — {SECTION_LABEL[sec]}"
        if not items:
            rows = [[InlineKeyboardButton("↩️ رجوع للمادة", callback_data=f"course:{cid}")]]
            await q.edit_message_text(f"{title}\n\nما فيه ملفات بعد.", reply_markup=InlineKeyboardMarkup(rows))
        else:
            await q.edit_message_text(title, reply_markup=kb_section_files(cid, sec, items))
        return

    if data.startswith("file:"):
        _, cid, sec, idx = data.split(":")
        items = content.get(cid, {}).get(sec, [])
        idx = int(idx)
        if idx >= len(items):
            await q.answer("الملف غير موجود.", show_alert=True)
            return
        item = items[idx]
        chat_id = q.message.chat_id
        if item.get("file_id"):
            await context.bot.send_document(chat_id, item["file_id"], caption=item["title"])
        elif item.get("url"):
            await context.bot.send_message(chat_id, f"{item['title']}\n{item['url']}")
        return

    # ---- تدفقات الأدمن ----
    if not is_admin(user_id):
        return

    if data.startswith("add_sem:"):
        n = int(data.split(":")[1])
        await q.edit_message_text(f"الفصل {SEM_NAMES[n-1]} — اختاري المادة:", reply_markup=kb_semester_courses(n, prefix="add_course"))
        return

    if data.startswith("add_course:"):
        cid = data.split(":")[1]
        context.user_data["add_course_id"] = cid
        rows = [[InlineKeyboardButton(label, callback_data=f"add_sec:{key}")] for key, label in SECTIONS]
        await q.edit_message_text("اختاري القسم:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("add_sec:"):
        sec = data.split(":")[1]
        context.user_data["add_section"] = sec
        context.user_data["state"] = "awaiting_file"
        await q.edit_message_text("📤 ابعتي الملف الآن (أو حوّليه Forward)، أو ابعتي رابط.")
        return

    if data.startswith("del_sem:"):
        n = int(data.split(":")[1])
        await q.edit_message_text(f"الفصل {SEM_NAMES[n-1]} — اختاري المادة:", reply_markup=kb_semester_courses(n, prefix="del_course"))
        return

    if data.startswith("del_course:"):
        cid = data.split(":")[1]
        rows = [[InlineKeyboardButton(label, callback_data=f"del_sec:{cid}:{key}")] for key, label in SECTIONS]
        await q.edit_message_text("اختاري القسم:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("del_sec:"):
        _, cid, sec = data.split(":")
        items = content.get(cid, {}).get(sec, [])
        if not items:
            await q.edit_message_text("ما فيه ملفات في هذا القسم.")
            return
        rows = [[InlineKeyboardButton(f"🗑️ {it['title']}", callback_data=f"del_file:{cid}:{sec}:{i}")]
                for i, it in enumerate(items)]
        await q.edit_message_text("اختاري الملف اللي تبين تحذفينه:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("del_file:"):
        _, cid, sec, idx = data.split(":")
        removed = delete_content_item(content, cid, sec, int(idx))
        if removed:
            await q.edit_message_text(f"تم حذف «{removed['title']}» ✅")
        else:
            await q.edit_message_text("تعذّر الحذف، الملف غير موجود.")
        return

    if data.startswith("edit_sem:"):
        n = int(data.split(":")[1])
        await q.edit_message_text(f"الفصل {SEM_NAMES[n-1]} — اختاري المادة:", reply_markup=kb_semester_courses(n, prefix="edit_course"))
        return

    if data.startswith("edit_course:"):
        cid = data.split(":")[1]
        context.user_data["edit_course_id"] = cid
        rows = [[InlineKeyboardButton(f"الفصل {name}", callback_data=f"edit_to:{i+1}")] for i, name in enumerate(SEM_NAMES)]
        await q.edit_message_text("انقليها إلى:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("edit_to:"):
        new_sem = int(data.split(":")[1])
        cid = context.user_data.get("edit_course_id")
        if cid and move_course_semester(cid, new_sem):
            await q.edit_message_text(f"تم نقل المادة إلى الفصل {SEM_NAMES[new_sem-1]} ✅")
        else:
            await q.edit_message_text("تعذّر التعديل.")
        return


# ---------- استقبال الملفات والروابط والرسائل النصية العامة ----------
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get("state")

    if state == "awaiting_tree_image" and is_admin(user_id):
        photo = update.message.document or (update.message.photo[-1] if update.message.photo else None)
        f = await photo.get_file()
        TREE_IMAGE.parent.mkdir(exist_ok=True)
        await f.download_to_drive(str(TREE_IMAGE))
        context.user_data["state"] = None
        await update.message.reply_text("تم تحديث شجرة المواد ✅", reply_markup=admin_menu())
        return

    if state == "awaiting_file" and is_admin(user_id):
        doc = update.message.document
        context.user_data["pending_item"] = {"file_id": doc.file_id, "title": doc.file_name or "ملف"}
        context.user_data["state"] = "awaiting_title"
        await update.message.reply_text("✏️ شن الاسم اللي تبين يظهر للطلبة؟ (أو ابعتي - لاستخدام اسم الملف)")
        return


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # يستخدم فقط لتحديث صورة شجرة المواد
    await on_document(update, context)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    state = context.user_data.get("state")

    # أزرار القائمة الرئيسية
    if text == BTN_COURSES:
        return await show_courses(update, context)
    if text == BTN_TREE:
        return await show_tree(update, context)
    if text == BTN_SEARCH:
        return await ask_search(update, context)
    if text == BTN_ABOUT:
        return await show_about(update, context)
    if text == BTN_ADMIN:
        return await open_admin_panel(update, context)
    if text == BTN_BACK:
        return await back_to_main(update, context)

    # أزرار لوحة الإدارة
    if text == ADMIN_ADD:
        return await admin_add_start(update, context)
    if text == ADMIN_DEL:
        return await admin_del_start(update, context)
    if text == ADMIN_EDIT:
        return await admin_edit_start(update, context)
    if text == ADMIN_TREE:
        return await admin_update_tree(update, context)

    # تدفقات حسب الحالة
    if state == "searching":
        context.user_data["state"] = None
        return await run_search(update, context, text)

    if state == "awaiting_file" and is_admin(user_id):
        if text.startswith("http"):
            context.user_data["pending_item"] = {"url": text, "title": text}
            context.user_data["state"] = "awaiting_title"
            await update.message.reply_text("✏️ شن الاسم اللي تبين يظهر للطلبة؟ (أو ابعتي - لاستخدام الرابط نفسه)")
            return
        await update.message.reply_text("ابعتي ملف أو رابط يبدأ بـ https://")
        return

    if state == "awaiting_title" and is_admin(user_id):
        pending = context.user_data.pop("pending_item", None)
        cid = context.user_data.pop("add_course_id", None)
        sec = context.user_data.pop("add_section", None)
        context.user_data["state"] = None
        if not pending or not cid or not sec:
            await update.message.reply_text("حدث خطأ، ابدئي من جديد بـ 📤 إضافة محتوى.", reply_markup=admin_menu())
            return
        if text != "-":
            pending["title"] = text
        content = load_content()
        add_content_item(content, cid, sec, pending)
        c = COURSE_BY_ID[cid]
        await update.message.reply_text(
            f"تمت الإضافة إلى «{c['name']} — {SECTION_LABEL[sec]}» ✅", reply_markup=admin_menu()
        )
        return

    # ولا شي من فوق: اعتبرها بحث سريع
    await run_search(update, context, text)


def main():
    if not BOT_TOKEN:
        raise SystemExit("حطّ توكن البوت في متغير البيئة BOT_TOKEN.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
