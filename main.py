import asyncio
import logging
import sys
from datetime import datetime
import openpyxl
import io

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
)
from apscheduler.schedulers.asyncio import AsyncScheduler
from aiohttp import web
from sqlalchemy import select, update

from config import settings
from database import async_session, init_db, User, Material, TestQuestion, TestResult, DailyReport, ContestDoc

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- FSM STATES ---
class RegState(StatesGroup):
    full_name = State()
    role = State()

class ReportState(StatesGroup):
    camp_name = State()
    report_date = State()
    event_name = State()
    participants_count = State()
    club_activity = State()
    results = State()
    problems = State()

class ContestState(StatesGroup):
    contest_name = State()
    description = State()
    file = State()

class AdminMaterialState(StatesGroup):
    section = State()
    title = State()
    content = State()
    file_id = State()

class AdminTestState(StatesGroup):
    question = State()
    opt_a = State()
    opt_b = State()
    opt_c = State()
    opt_d = State()
    correct = State()

# --- KEYBOARDS ---
def main_menu(is_admin: bool):
    kb = [
        [KeyboardButton(text="12 кунлик дастур"), KeyboardButton(text="Тўгарак ва клублар")],
        [KeyboardButton(text="Интерфаол ўйинлар"), KeyboardButton(text="Муаммоли вазиятлар")],
        [KeyboardButton(text="Оромгоҳ кундалиги"), KeyboardButton(text="Тест ва савол-жавобlar")], # Kirillda
        [KeyboardButton(text="Кунлик ҳисобот"), KeyboardButton(text="Методик қўлланмалар")],
        [KeyboardButton(text="Танлов ва рағбатлантириш"), KeyboardButton(text="Қидириш")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="⚙️ Администратор панели")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Бош меню"), KeyboardButton(text="Орқага"), KeyboardButton(text="Қидириш")]
        ],
        resize_keyboard=True
    )

# --- START & REGISTRATION ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("Ассалому алайкум! «ОРОМГОҲ МАСЛАҲАТЧИ – 2027» ботига хуш келибсиз.\n\nИлтимос, Исм ва Фамилияingizni киритинг:")
            await state.set_state(RegState.full_name)
        else:
            is_admin = (message.from_user.id == settings.ADMIN_ID or user.role == "Марказий администратор")
            await message.answer(f"Хush келибсиз, {user.full_name}!\nСизнинг ролингиз: <b>{user.role}</b>", reply_markup=main_menu(is_admin))

@dp.message(RegState.full_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    roles = [
        ["Оддий фойдаланувчи", "Тарбиячи"],
        ["Етакчи", "Тўгарак раҳбари"],
        ["Оромгоҳ масъули"]
    ]
    if message.from_user.id == settings.ADMIN_ID:
        roles.append(["Марказий администратор"])
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=r) for r in row] for row in roles], resize_keyboard=True)
    await message.answer("Лавозимингизни қуйидагилардан бирини танланг:", reply_markup=kb)
    await state.set_state(RegState.role)

@dp.message(RegState.role)
async def process_role(message: Message, state: FSMContext):
    data = await state.get_data()
    role = message.text
    full_name = data.get("full_name")
    
    if message.from_user.id != settings.ADMIN_ID and role == "Марказий администратор":
        role = "Оддий фойдаланувчи" # Xavfsizlik uchun

    async with async_session() as session:
        user = User(id=message.from_user.id, full_name=full_name, role=role)
        session.add(user)
        await session.commit()

    await state.clear()
    is_admin = (message.from_user.id == settings.ADMIN_ID or role == "Марказий администратор")
    await message.answer("Рўйхатдан муваффақиятли ўтдингиз!", reply_markup=main_menu(is_admin))

# --- COMMON NAVIGATION ---
@dp.message(F.text == "Бош меню")
async def go_home(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        res = await session.execute(select(User).where(User.id == message.from_user.id))
        user = res.scalar_one_or_none()
        is_admin = user and (message.from_user.id == settings.ADMIN_ID or user.role == "Марказий администратор")
        await message.answer("Бош меню:", reply_markup=main_menu(is_admin))

@dp.message(F.text == "Қидириш")
async def global_search_prompt(message: Message, state: FSMContext):
    await message.answer("Қидирмоқчи бўлган сўзингизни киритинг:", reply_markup=back_menu())

# --- 9 SECTIONS HANDLERS ---
@dp.message(F.text == "12 кунлик дастур")
async def sec_1(message: Message):
    async with async_session() as session:
        res = await session.execute(select(Material).where(Material.section == "12_kun"))
        items = res.scalars().all()
        text = "<b>1 кунлик тарбиявий-маърифий дастур ва бошқалар:</b>\n\n"
        if not items:
            text += "Ҳозирча материаллар қўшилмаган. Администратор томонидан қўшилиши кутилмоқда."
        for i in items:
            text += f"📌 <b>{i.title}</b>\n{i.content}\n\n"
        await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "Тўгарак ва клублар")
async def sec_2(message: Message):
    async with async_session() as session:
        res = await session.execute(select(Material).where(Material.section == "togarak"))
        items = res.scalars().all()
        text = "<b>Клуб ва тўгараклар фаолияти (10 та клуб, 120 та машғулот):</b>\n\n"
        if not items:
            text += "Маълумотлар базадан топилмади."
        for i in items:
            text += f"🎯 <b>{i.title}</b>\n{i.content}\n\n"
        await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "Интерфаол ўйинлар")
async def sec_3(message: Message):
    async with async_session() as session:
        res = await session.execute(select(Material).where(Material.section == "oyin"))
        items = res.scalars().all()
        text = "<b>Интерфаол ва ҳаракатли ўйинлар (30+ та):</b>\n\n"
        if not items:
            text += "Ҳозирча ўйинлар киритилмаган."
        for i in items:
            text += f"🎮 <b>{i.title}</b>\n{i.content}\n\n"
        await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "Муаммоли вазиятлар")
async def sec_4(message: Message):
    async with async_session() as session:
        res = await session.execute(select(Material).where(Material.section == "vaziyat"))
        items = res.scalars().all()
        text = "<b>Муаммоли вазиятлар ва ечимлар (20 та):</b>\n\n"
        if not items:
            text += "Маълумотлар мавжуд эмас."
        for i in items:
            text += f"⚠️ <b>{i.title}</b>\n{i.content}\n\n"
        await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "Оромгоҳ кундалиги")
async def sec_5(message: Message):
    text = (
        "📖 <b>Оромгоҳ кундалиги (Болалар учун):</b>\n\n"
        "Бу бўлим оромгоҳдаги болалар ўзларининг 12 кунлик таassurotлари, "
        "энг яхши кунлари ва янги дўстлари ҳақида ёзиб боришлари учун мўлжалланган.\n\n"
        "Ҳар куни ўз кундалигингизни шахсий дафтарингизга ёзиб боринг!"
    )
    await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "Тест ва савол-жавобlar") # Kirill
async def sec_6(message: Message):
    async with async_session() as session:
        res = await session.execute(select(TestQuestion))
        q = res.scalars().first()
        if not q:
            await message.answer("Ҳозирча тест саволлари мавжуд эмас.", reply_markup=back_menu())
            return
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"A) {q.option_a}", callback_data=f"test_{q.id}_A")],
            [InlineKeyboardButton(text=f"B) {q.option_b}", callback_data=f"test_{q.id}_B")],
            [InlineKeyboardButton(text=f"C) {q.option_c}", callback_data=f"test_{q.id}_C")],
            [InlineKeyboardButton(text=f"D) {q.option_d}", callback_data=f"test_{q.id}_D")],
        ])
        await message.answer(f"<b>Савол:</b> {q.question}", reply_markup=kb)

@dp.callback_query(F.data.startswith("test_"))
async def process_test_cb(callback: CallbackQuery):
    _, q_id, ans = callback.data.split("_")
    async with async_session() as session:
        res = await session.execute(select(TestQuestion).where(TestQuestion.id == int(q_id)))
        q = res.scalar_one_or_none()
        if q:
            if q.correct == ans:
                await callback.answer("Тоғри жавоб! ✨", show_alert=True)
            else:
                await callback.answer(f"НАТОҒРИ! Тўғри жавоб: {q.correct}", show_alert=True)
    await callback.message.delete()

# --- DAILY REPORTS ---
@dp.message(F.text == "Кунлик ҳисобот")
async def sec_7(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Ҳисобот юбориш", callback_data="send_report")],
        [InlineKeyboardButton(text="📊 Менинг ҳисоботларим", callback_data="my_reports")]
    ])
    await message.answer("Кунлик ҳисобот ва мониторинг бўлими:", reply_markup=kb)

@dp.callback_query(F.data == "send_report")
async def start_report(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Оромгоҳ номини киритинг:", reply_markup=back_menu())
    await state.set_state(ReportState.camp_name)
    await callback.answer()

@dp.message(ReportState.camp_name)
async def rep_camp(message: Message, state: FSMContext):
    await state.update_data(camp_name=message.text)
    await message.answer("Санани киритинг (Масалан: 2027-06-01):")
    await state.set_state(ReportState.report_date)

@dp.message(ReportState.report_date)
async def rep_date(message: Message, state: FSMContext):
    await state.update_data(report_date=message.text)
    await message.answer("Тадбир номини киритинг:")
    await state.set_state(ReportState.event_name)

@dp.message(ReportState.event_name)
async def rep_event(message: Message, state: FSMContext):
    await state.update_data(event_name=message.text)
    await message.answer("Иштирокчилар сонини киритинг (фақат рақам):")
    await state.set_state(ReportState.participants_count)

@dp.message(ReportState.participants_count)
async def rep_part(message: Message, state: FSMContext):
    try:
        count = int(message.text)
    except ValueError:
        await message.answer("Фақат рақам киритинг!")
        return
    await state.update_data(participants_count=count)
    await message.answer("Клуб фаолияти ҳақида қисқача:")
    await state.set_state(ReportState.club_activity)

@dp.message(ReportState.club_activity)
async def rep_club(message: Message, state: FSMContext):
    await state.update_data(club_activity=message.text)
    await message.answer("Эришилган натижалар:")
    await state.set_state(ReportState.results)

@dp.message(ReportState.results)
async def rep_res(message: Message, state: FSMContext):
    await state.update_data(results=message.text)
    await message.answer("Дуч келинган муаммолар:")
    await state.set_state(ReportState.problems)

@dp.message(ReportState.problems)
async def rep_prob(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        rep = DailyReport(
            user_id=message.from_user.id,
            camp_name=data["camp_name"],
            report_date=data["report_date"],
            event_name=data["event_name"],
            participants_count=data["participants_count"],
            club_activity=data["club_activity"],
            results=data["results"],
            problems=message.text
        )
        session.add(rep)
        await session.commit()
    await state.clear()
    await message.answer("Ҳисоботингиз масъулга юборилди ва кўриб чиқилиш кутилмоқда!", reply_markup=main_menu(message.from_user.id == settings.ADMIN_ID))

# --- OTHER SECTIONS ---
@dp.message(F.text == "Методик қўлланмалар")
async def sec_8(message: Message):
    async with async_session() as session:
        res = await session.execute(select(Material).where(Material.section == "library"))
        items = res.scalars().all()
        text = "<b>Методик қўлланмалар ва электрон кутубхона:</b>\n\n"
        if not items:
            text += "Кутубхонада материаллар ҳозирча йўқ."
        for i in items:
            text += f"📚 <b>{i.title}</b>\n{i.content}\n"
            if i.file_id:
                text += f"📎 Файл бириктирилган\n"
            text += "\n"
        await message.answer(text, reply_markup=back_menu())

@dp.message(F.text == "Танлов ва рағбатлантириш")
async def sec_9(message: Message):
    text = (
        "🏆 <b>Танлов ва рағбатлантириш (5 та номинация):</b>\n"
        "1. Энг яхши оромгоҳ\n"
        "2. Энг яхши катта тарбиячи\n"
        "3. Энг яхши тарбиячи\n"
        "4. Энг яхши етакчи\n"
        "5. Энг яхши тўгарак раҳбари\n\n"
        "Баҳолаш мезонлари 100 баллик тизим асосида администратор томонидан юритилади."
    )
    await message.answer(text, reply_markup=back_menu())

# --- ADMIN PANEL ---
@dp.message(F.text == "⚙️ Администратор панели")
async def admin_panel(message: Message):
    if message.from_user.id != settings.ADMIN_ID:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Материал қўшиш", callback_data="adm_add_mat")],
        [InlineKeyboardButton(text="📝 Test савол қўшиш", callback_data="adm_add_test")],
        [InlineKeyboardButton(text="📋 Ҳисоботларни кўриш", callback_data="adm_reports")],
        [InlineKeyboardButton(text="📥 Excel экспорт", callback_data="adm_export")]
    ])
    await message.answer("Администратор панелига хуш келибсиз:", reply_markup=kb)

@dp.callback_query(F.data == "adm_export")
async def export_excel(callback: CallbackQuery):
    if callback.from_user.id != settings.ADMIN_ID:
        return
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobotlar"
    ws.append(["ID", "Oromgoh", "Sana", "Tadbir", "Ishtirokchilar", "Holati"])

    async with async_session() as session:
        res = await session.execute(select(DailyReport))
        reports = res.scalars().all()
        for r in reports:
            ws.append([r.id, r.camp_name, r.report_date, r.event_name, r.participants_count, r.status])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    
    await callback.message.answer_document(
        BufferedInputFile(bio.read(), filename="reports.xlsx"),
        caption="Барча ҳисоботлар Excel форматида."
    )
    await callback.answer()

# --- HEALTH CHECK SERVER & APSCHEDULER ---
async def handle_root(request):
    return web.Response(text="Oromgoh Maslahatchi 2027 Bot is running successfully!")

async def handle_health(request):
    try:
        async with async_session() as session:
            await session.execute(select(User))
        return web.json_response({"status": "healthy", "database": "connected"})
    except Exception as e:
        return web.json_response({"status": "unhealthy", "error": str(e)}, status=500)

async def monitoring_job():
    logger.info("APScheduler: 5 daqiqalik monitoring tekshiruvi bajarildi.")
    try:
        async with async_session() as session:
            await session.execute(select(User))
    except Exception as e:
        logger.error(f"Monitoring DB error: {e}")

async def main():
    await init_db()
    
    # Scheduler
    scheduler = AsyncScheduler()
    # APScheduler 3.x versiyasi uchun oddiy background interval
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    aps = AsyncIOScheduler()
    aps.add_job(monitoring_job, 'interval', minutes=5)
    aps.start()

    # Web App for Render
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/health', handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', settings.PORT)
    await site.start()
    logger.info(f"HTTP server started on port {settings.PORT}")

    # Start Bot Polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")