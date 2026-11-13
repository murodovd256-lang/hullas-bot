import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, Text, Boolean, DateTime, Float, ForeignKey
from datetime import datetime
from config import settings

# Render uchun postgresql:// ni postgresql+asyncpg:// ga o'zgartirish
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True) # Telegram ID
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(50), default="Оддий фойдаланувчи")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section: Mapped[str] = mapped_column(String(100)) # bo'lim nomi
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_id: Mapped[str] = mapped_column(String(255), nullable=True) # Telegram file_id

class TestQuestion(Base):
    __tablename__ = "test_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(String(255))
    option_b: Mapped[str] = mapped_column(String(255))
    option_c: Mapped[str] = mapped_column(String(255))
    option_d: Mapped[str] = mapped_column(String(255))
    correct: Mapped[str] = mapped_column(String(1)) # A, B, C, D

class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    passed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DailyReport(Base):
    __tablename__ = "daily_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    camp_name: Mapped[str] = mapped_column(String(150))
    report_date: Mapped[str] = mapped_column(String(50))
    event_name: Mapped[str] = mapped_column(String(255))
    participants_count: Mapped[int] = mapped_column(Integer)
    club_activity: Mapped[str] = mapped_column(Text)
    results: Mapped[str] = mapped_column(Text)
    problems: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="Кутилмоқда") # Кутилмоқда, Тасдиқланган, Рад этилган

class ContestDoc(Base):
    __tablename__ = "contest_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contest_name: Mapped[str] = mapped_column(String(150))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    description: Mapped[str] = mapped_column(Text)
    file_id: Mapped[str] = mapped_column(String(255), nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)