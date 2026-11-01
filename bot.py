import asyncio
import json
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask
import threading

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai

# ================= SOZLAMALAR (TAYYOR ULANGAN) =================
BOT_TOKEN = "9089417873:AAHc_ert008V25uvLryIHpDJf9z8d9JGI8A"
GEMINI_API_KEY = "AQ.Ab8RN6KfcE40J82CEbs4vMmSk2DqYJih1mFIZ1xcufRPl3pIDA"

DATA_FILE = "yotoqxona_baza.json"
TIMEZONE = ZoneInfo("Asia/Tashkent")

TASK_CATALOG = {
    "cook": {
        "name": "🍳 Ovqat qilish",
        "prompt": "Videoda tayyor pishirilgan ovqat (qozonda, tovada yoki idishda) ko'rsatilgan bo'lishi kerak."
    },
    "friday_trash": {
        "name": "🗑 Ketishdan oldin axlat to'kish",
        "prompt": "Videoda xonadagi axlat chelak bo'shatilgani yoki axlat paketlari tashqariga/axlatxonaga olib chiqib to'kilgani ko'rinishi kerak."
    },
    "dishes": {
        "name": "🍽 Idish yuvish va dasturxon yig'ishtirish",
        "prompt": "Videoda toza yuvilgan idishlar, toza rakovina yoki yig'ishtirilgan toza stol/dasturxon ko'rinishi kerak."
    },
    "room_water": {
        "name": "🛏 Xonani yig'ishtirish va 💧 Suv olib kelish",
        "prompt": "Videoda tartibga keltirilgan yotoqxona (yig'ilgan ko'rpa-to'shak/joylar) VA to'ldirilgan suv idishlari (baklajka) ko'rinishi kerak."
    },
    "bath": {
        "name": "🧽 Hammom va hojatxona tozalash",
        "prompt": "Videoda tozalangan, yuvilgan vanna/rakovina va hojatxona (sanuzel) ko'rinishi kerak."
    },
    "sweep": {
        "name": "🧹 Uy supurish",
        "prompt": "Videoda xona poli toza qilib supurilgani (yoki changyutgich qilingani) ko'rinishi kerak."
    }
}
# ===============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Render port talabini qondirish uchun veb-server
app = Flask(__name__)

@app.route('/')
def home():
    return "Yotoqxona Boti 24/7 ishlamoqda!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "group_id": None,
            "users": {},
            "order": [],
            "last_daily": {},
            "last_weekly_index": 0,  # Haftalik qat'iy navbat uchun indeks
            "penalties": [],
            "today_tasks": {},
            "pending_videos": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "last_weekly_index" not in data:
            data["last_weekly_index"] = 0
        return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    data = load_data()

    if message.chat.type in ["group", "supergroup"]:
        data["group_id"] = message.chat.id
        save_data(data)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🙋‍♂️ Yotoqxona ro'yxatiga qo'shilish", callback_data="join_room")]
        ])
        await message.answer(
            "🏠 **Yotoqxona Nazorat Boti guruhga ulandi!**\n\n"
            "3 nafar xonadosh pastdagi tugmani bosib ro'yxatdan o'tsin.\n"
            "❗️ *Muhim: Tugmani bosgach, bot lichkasiga kirib ham /start bosib qo'ying (shaxsiy xabarlar borishi uchun).*",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    else:
        bot_username = (await bot.get_me()).username
        group_add_url = f"https://t.me/{bot_username}?startgroup=true"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Botni guruhga qo'shish", url=group_add_url)]
        ])

        uid = str(message.from_user.id)
        if uid in data["users"]:
            await message.answer(
                f"Salom, {data['users'][uid]['name']}! Siz ro'yxatdasiz.\n"
                f"Botni yotoqxona guruhiga ulash yoki boshqarish uchun quyidagi tugmani bosing:",
                reply_markup=kb,
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                "Salom! Yotoqxona nazorat botiga xush kelibsiz.\n"
                "Ishni boshlash uchun avval botni yotoqxona guruhingizga qo'shing:",
                reply_markup=kb,
                parse_mode="Markdown"
            )


@dp.callback_query(F.data == "join_room")
async def join_room_cb(call: CallbackQuery):
    data = load_data()
    uid = str(call.from_user.id)
    name = call.from_user.first_name

    if uid in data["users"]:
        await call.answer("Siz allaqachon ro'yxatdan o'tgansiz!", show_alert=True)
        return

    if len(data["order"]) >= 3:
        await call.answer("Joy to'lgan! 3 kishi ro'yxatdan o'tib bo'ldi.", show_alert=True)
        return

    data["users"][uid] = {"name": name}
    data["order"].append(uid)
    save_data(data)

    count = len(data["order"])
    names = ", ".join([data["users"][u]["name"] for u in data["order"]])

    if count < 3:
        await call.message.edit_text(
            f"🏠 **Ro'yxatdan o'tganlar ({count}/3):** {names}\n\n"
            f"Qolgan {3 - count} kishi tugmani bossin:",
            reply_markup=call.message.reply_markup,
            parse_mode="Markdown"
        )
    else:
        await call.message.edit_text(
            f"🎉 **3 nafar xonadosh to'liq yig'ildi:** {names}!\n\n"
            f"⏰ Ishlar Dushanbadan Jumagacha har kuni ertalab **06:30 da** avtomatik taqsimlanadi.\n"
            f"🛁 Haftalik ishlar har hafta **Payshanba soat 23:00 gacha** topshiriladi.\n"
            f"*(Hoziroq sinab ko'rish uchun guruhda /taqsimla buyrug'ini bosing)*",
            parse_mode="Markdown"
        )
    await call.answer("Ro'yxatga qo'shildingiz!")


@dp.message(Command("vazifa"))
async def my_tasks(message: Message):
    data = load_data()
    uid = str(message.from_user.id)
    tasks = data["today_tasks"].get(uid, [])

    if not tasks:
        await message.answer("🎉 Bugun sizda hech qanday vazifa yo'q (Dam olish)!")
        return

    lines = ["📋 **Bugungi vazifalaringiz:**\n"]
    for t in tasks:
        holat = "✅ Topshirilgan" if t["done"] else "⏳ Video kutilmoqda"
        lines.append(f"• {t['name']} — *{holat}*")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("taqsimla"))
async def manual_assign(message: Message):
    data = load_data()
    if len(data["order"]) < 3:
        await message.answer(f"Hali 3 kishi yig'ilmadi! Hozir: {len(data['order'])}/3 kishi.")
        return
    await assign_daily_and_weekly_tasks(force_test=True)
    await message.answer("✅ Vazifalar taqsimlandi!")


def get_deranged_assignment(users, roles, last_daily):
    valid_perms = []
    for p in [
        [roles[0], roles[1], roles[2]],
        [roles[0], roles[2], roles[1]],
        [roles[1], roles[0], roles[2]],
        [roles[1], roles[2], roles[0]],
        [roles[2], roles[0], roles[1]],
        [roles[2], roles[1], roles[0]],
    ]:
        ok = True
        for u, r in zip(users, p):
            prev = last_daily.get(u)
            r_base = "cook" if r == "friday_trash" else r
            prev_base = "cook" if prev == "friday_trash" else prev
            if prev_base == r_base:
                ok = False
                break
        if ok:
            valid_perms.append(p)

    chosen = random.choice(valid_perms) if valid_perms else random.sample(roles, 3)
    return {u: r for u, r in zip(users, chosen)}


async def assign_daily_and_weekly_tasks(force_test=False):
    data = load_data()
    if len(data["order"]) < 3:
        return

    now = datetime.now(TIMEZONE)
    weekday = now.weekday()

    if weekday in [5, 6] and not force_test:
        return

    users = data["order"]
    role1 = "friday_trash" if weekday == 4 else "cook"
    daily_roles = [role1, "dishes", "room_water"]

    penalties = data.get("penalties", [])
    data["today_tasks"] = {u: [] for u in users}

    if len(penalties) == 1:
        bad_u = penalties[0]
        good_users = [u for u in users if u != bad_u]
        vip_user = random.choice(good_users)
        worker_u = [u for u in good_users if u != vip_user][0]

        prev_w = data["last_daily"].get(worker_u)
        avail_for_worker = [r for r in daily_roles if ("cook" if r == "friday_trash" else r) != ("cook" if prev_w == "friday_trash" else prev_w)]
        w_role = random.choice(avail_for_worker)
        bad_roles = [r for r in daily_roles if r != w_role]

        for r in bad_roles:
            data["today_tasks"][bad_u].append({"key": r, "name": TASK_CATALOG[r]["name"], "done": False})
        data["today_tasks"][worker_u].append({"key": w_role, "name": TASK_CATALOG[w_role]["name"], "done": False})

        data["last_daily"][bad_u] = bad_roles[0]
        data["last_daily"][worker_u] = w_role
        data["last_daily"][vip_user] = None

    elif len(penalties) == 2:
        good_users = [u for u in users if u not in penalties]
        vip_user = good_users[0] if good_users else None
        b1, b2 = penalties[0], penalties[1]
        random.shuffle(daily_roles)

        data["today_tasks"][b1].append({"key": daily_roles[0], "name": TASK_CATALOG[daily_roles[0]]["name"], "done": False})
        data["today_tasks"][b1].append({"key": daily_roles[1], "name": TASK_CATALOG[daily_roles[1]]["name"], "done": False})
        data["today_tasks"][b2].append({"key": daily_roles[2], "name": TASK_CATALOG[daily_roles[2]]["name"], "done": False})

        data["last_daily"][b1] = daily_roles[0]
        data["last_daily"][b2] = daily_roles[2]
        if vip_user:
            data["last_daily"][vip_user] = None

    else:
        assigned = get_deranged_assignment(users, daily_roles, data.get("last_daily", {}))
        for u, r in assigned.items():
            data["today_tasks"][u].append({"key": r, "name": TASK_CATALOG[r]["name"], "done": False})
            data["last_daily"][u] = r

    data["penalties"] = []

    weekly_text = ""
    # HAFTALIK ISH (Payshanba kuni taqsimlanadi va navbatma-navbat aylanadi)
    if weekday == 3 or force_test:
        weekly_index = data.get("last_weekly_index", 0)
        bath_u = users[weekly_index % len(users)]
        
        # Keyingi safar boshqa xonadoshga tushishi uchun indeksni suramiz
        data["last_weekly_index"] = (weekly_index + 1) % len(users)

        # Qolgan ikkita xonadoshdan biri uy supurishga tushadi
        sweep_candidates = [u for u in users if u != bath_u]
        sweep_u = random.choice(sweep_candidates)
        free_weekly_u = [u for u in users if u not in [bath_u, sweep_u]][0]

        data["today_tasks"][bath_u].append({"key": "bath", "name": TASK_CATALOG["bath"]["name"], "done": False})
        data["today_tasks"][sweep_u].append({"key": "sweep", "name": TASK_CATALOG["sweep"]["name"], "done": False})

        weekly_text = (
            f"\n\n🧹 **PAYSHANBA — HAFTALIK KATTA TOZALIK (Dedlayn: 23:00):**\n"
            f"• **{data['users'][bath_u]['name']}:** {TASK_CATALOG['bath']['name']}\n"
            f"• **{data['users'][sweep_u]['name']}:** {TASK_CATALOG['sweep']['name']}\n"
            f"• **{data['users'][free_weekly_u]['name']}:** 😎 Haftalik ishdan ozod!"
        )

    save_data(data)

    deadline_str = "23:00"  # Barcha kunlar va haftalik ishlar uchun dedlayn 23:00
    group_lines = [f"🌅 **Xayrli tong! Bugungi vazifalar taqsimlandi (Dedlayn: {deadline_str} gacha):**\n"]

    for u in users:
        uname = data["users"][u]["name"]
        utasks = data["today_tasks"][u]

        if not utasks:
            group_lines.append(f"🎉 **{uname}:** BUGUN DAM OLISH (VIP)!")
            try:
                await bot.send_message(
                    u,
                    f"🎉 **Tabriklaymiz, {uname}!**\nKechagi intizomingiz sababli bugun sizga **DAM OLISH (VIP)** berildi! Vazifangizni jarima olgan xonadoshingiz bajaradi 😎",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            t_names = ", ".join([t["name"] for t in utasks])
            group_lines.append(f"👤 **{uname}:** {t_names}")

            personal_msg = (
                f"🌅 **Xayrli tong, {uname}!**\n\n"
                f"📋 **Bugungi vazifalaringiz:**\n" +
                "\n".join([f"• {t['name']}" for t in utasks]) +
                f"\n\n⏰ **Topshirish muddati:** Bugun soat **{deadline_str}** gacha!\n"
                f"🎥 *Ishni bajarib bo'lgach, shu yerga (lichkaga) DUMALOQ VIDEO (Video Note) yuboring!*"
            )
            try:
                await bot.send_message(u, personal_msg, parse_mode="Markdown")
            except Exception:
                pass

    if weekly_text:
        group_lines.append(weekly_text)

    if data.get("group_id"):
        try:
            await bot.send_message(data["group_id"], "\n".join(group_lines), parse_mode="Markdown")
        except Exception:
            pass


async def verify_video_with_ai(file_id: str, task_key: str) -> tuple[bool, str]:
    file_info = await bot.get_file(file_id)
    local_path = f"temp_{file_id}.mp4"
    await bot.download_file(file_info.file_path, local_path)

    try:
        uploaded = await asyncio.to_thread(ai_client.files.upload, file=local_path)
        for _ in range(15):
            file_state = await asyncio.to_thread(ai_client.files.get, name=uploaded.name)
            if file_state.state.name == "ACTIVE":
                break
            await asyncio.sleep(2)

        task_info = TASK_CATALOG[task_key]
        prompt = (
            f"Sen talabalar yotoqxonasidagi qattiqqo'l lekin adolatli nazoratchi botsan. "
            f"Talaba '{task_info['name']}' vazifasini bajargani haqida dumaloq video yubordi. "
            f"Talab: {task_info['prompt']} "
            f"Videoni (va undagi ovozni) diqqat bilan tahlil qil. Agar vazifa haqiqatan ham bajarilgani ko'rinsa, "
            f"faqatgina 'TASDIQLANDI: <qisqa 1 gaplik maqtov>' deb yoz. "
            f"Agar videoda qorong'ulik, shift, boshqa narsa ko'rinsa yoki ish oxirigacha qilinmagan bo'lsa, "
            f"'RAD_ETILDI: <nima kamchiligi borligini o'zbek tilida aniq ayt>' deb javob ber."
        )

        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[uploaded, prompt]
        )

        try:
            await asyncio.to_thread(ai_client.files.delete, name=uploaded.name)
        except Exception:
            pass

        res_text = response.text.strip()
        if "TASDIQLANDI" in res_text.upper():
            clean_msg = res_text.split(":", 1)[-1].strip() if ":" in res_text else "Vazifa a'lo darajada bajarilgan!"
            return True, clean_msg
        else:
            clean_msg = res_text.split(":", 1)[-1].strip() if ":" in res_text else res_text
            return False, clean_msg

    except Exception as e:
        return False, f"AI tahlil qilishda texnik xatolik yuz berdi: {e}"
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


@dp.message(F.chat.type == "private", F.video_note)
async def handle_video_note(message: Message):
    data = load_data()
    uid = str(message.from_user.id)

    if uid not in data["users"]:
        return

    undone_tasks = [t for t in data["today_tasks"].get(uid, []) if not t["done"]]
    if not undone_tasks:
        await message.answer("😎 Siz bugungi barcha vazifalaringizni topshirib bo'lgansiz!")
        return

    data["pending_videos"][uid] = {
        "file_id": message.video_note.file_id,
        "msg_id": message.message_id
    }
    save_data(data)

    buttons = []
    for t in undone_tasks:
        buttons.append([InlineKeyboardButton(text=t["name"], callback_data=f"verify_{t['key']}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "🎥 **Video qabul qilindi!**\nUshbu video qaysi vazifangiz uchun ekanligini tanlang (tugmani bosing):",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@dp.callback_query(F.data.startswith("verify_"))
async def verify_task_callback(call: CallbackQuery):
    data = load_data()
    uid = str(call.from_user.id)
    task_key = call.data.replace("verify_", "")

    pending = data.get("pending_videos", {}).get(uid)
    if not pending:
        await call.answer("Avval dumaloq video yuboring!", show_alert=True)
        return

    task_obj = None
    for t in data["today_tasks"].get(uid, []):
        if t["key"] == task_key and not t["done"]:
            task_obj = t
            break

    if not task_obj:
        await call.answer("Bu vazifa allaqachon bajarilgan!", show_alert=True)
        return

    await call.message.edit_text(
        f"🤖 **AI videoni tekshirmoqda...**\nVazifa: *{task_obj['name']}*\n⏳ Iltimos, 5-10 soniya kuting...",
        parse_mode="Markdown"
    )

    ok, ai_comment = await verify_video_with_ai(pending["file_id"], task_key)

    if ok:
        for t in data["today_tasks"][uid]:
            if t["key"] == task_key:
                t["done"] = True
        data["pending_videos"].pop(uid, None)
        save_data(data)

        remaining = [t for t in data["today_tasks"][uid] if not t["done"]]
        rem_text = (
            f"\n\n⚠️ Sizda hali **{len(remaining)} ta** bajarilmagan vazifa qoldi ({', '.join([r['name'] for r in remaining])}). Unga ham alohida dumaloq video tashlang!"
            if remaining else "\n\n🎉 **Bugungi barcha vazifalaringizdan to'liq qutuldingiz!**"
        )

        await call.message.edit_text(
            f"✅ **TASDIQLANDI!** ({task_obj['name']})\n🤖 **AI xulosasi:** {ai_comment}{rem_text}",
            parse_mode="Markdown"
        )

        if data.get("group_id"):
            uname = data["users"][uid]["name"]
            await bot.send_message(
                data["group_id"],
                f"✅ **{uname}** o'zining **{task_obj['name']}** vazifasini bajardi!\n🤖 *AI: {ai_comment}*\n👇 Mana video isboti:",
                parse_mode="Markdown"
            )
            await bot.send_video_note(data["group_id"], pending["file_id"])
    else:
        await call.message.edit_text(
            f"❌ **VAZIFA QABUL QILINMADI!** ({task_obj['name']})\n\n"
            f"🤖 **AI e'tirozi:** {ai_comment}\n\n"
            f"🎥 *Iltimos, ishni to'liq bajarib, aniq ko'rinadigan qilib yangi DUMALOQ VIDEO tashlang!*",
            parse_mode="Markdown"
        )


@dp.message(F.chat.type == "private")
async def reject_other_messages(message: Message):
    data = load_data()
    uid = str(message.from_user.id)
    if uid in data["users"]:
        undone = [t for t in data["today_tasks"].get(uid, []) if not t["done"]]
        if undone:
            await message.answer(
                "❌ **Oddiy video, rasm yoki matn o'tmaydi!**\n"
                "Telegramning o'zida hozir olingan **DUMALOQ VIDEO (Video Note)** yuborishingiz shart! 🎥",
                parse_mode="Markdown"
            )


async def send_reminder(hours_left_text: str):
    data = load_data()
    for uid in data["order"]:
        undone = [t["name"] for t in data["today_tasks"].get(uid, []) if not t["done"]]
        if undone:
            uname = data["users"][uid]["name"]
            try:
                await bot.send_message(
                    uid,
                    f"⏰ **ESLATMA, {uname}!**\nVaqt tugashiga **{hours_left_text}** qoldi, lekin siz hali quyidagi ishlarga dumaloq video tashlamadingiz:\n" +
                    "\n".join([f"• {n}" for n in undone]) +
                    "\n\n🚨 *Vaqtida topshirmasangiz, ertaga 2 barobar ish qilasiz!*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass


async def check_deadline():
    data = load_data()
    if len(data["order"]) < 3:
        return

    failed_users = []
    for uid in data["order"]:
        undone = [t for t in data["today_tasks"].get(uid, []) if not t["done"]]
        if undone:
            failed_users.append(uid)
            if uid not in data["penalties"]:
                data["penalties"].append(uid)

            uname = data["users"][uid]["name"]
            undone_names = ", ".join([t["name"] for t in undone])
            try:
                await bot.send_message(
                    uid,
                    f"🚨 **VAQT TUGADI, {uname}!**\nSiz **{undone_names}** vazifasini vaqtida topshirmadingiz!\n"
                    f"Jazo sifatida keyingi ish kunida sizga **2 TA ROL** yuklanadi! 😈",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    save_data(data)

    if data.get("group_id"):
        if failed_users:
            f_names = ", ".join([data["users"][u]["name"] for u in failed_users])
            await bot.send_message(
                data["group_id"],
                f"🚨 **DEDLAYN VAQTI TUGADI!**\n\n"
                f"❌ Bugun vazifasini bajarmaganlar: **{f_names}**.\n"
                f"⚖️ Qoidaga ko'ra, keyingi ish kunida ularga **2 TA ROL** tushadi, toza ishlagan xonadoshlardan biri esa **🎉 DAM OLISH (VIP)** beriladi!",
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                data["group_id"],
                "🎉 **BARAKALLA YIGITLAR!** Bugun hamma o'z vazifasini vaqtida topshirdi! Yotoqxona top-toza 😎",
                parse_mode="Markdown"
            )


async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Har kuni 06:30 da vazifa taqsimlash
    scheduler.add_job(assign_daily_and_weekly_tasks, 'cron', day_of_week='mon-fri', hour=6, minute=30)
    
    # Eslatmalar (Kechki 19:00 va 21:30 da)
    scheduler.add_job(send_reminder, 'cron', day_of_week='mon-fri', hour=19, minute=0, args=["4 soat"])
    scheduler.add_job(send_reminder, 'cron', day_of_week='mon-fri', hour=21, minute=30, args=["1.5 soat"])
    
    # Barcha kunlar uchun dedlayn soat 23:00 da (shu jumladan Payshanba haftalik ishlari uchun ham)
    scheduler.add_job(check_deadline, 'cron', day_of_week='mon-fri', hour=23, minute=0)

    scheduler.start()
    print("✅ Yotoqxona Nazorat Boti ishga tushdi!")
    
    # Veb-serverni alohida oqimda ishga tushiramiz
    threading.Thread(target=run_flask, daemon=True).start()
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
