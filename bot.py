#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telebot
from telebot import types
import requests
import re
import json
import sqlite3
import os
import tempfile
import time
import random
import hashlib
from datetime import datetime, timedelta

# ========== КОНФИГ ==========
BOT_TOKEN = "8311685829:AAHgGN8usDot7UXkuqA2g7IJJqarQpGQceQ"
BIGBASE_TOKEN = "jLG0gj81FNzYETkJx2ctD_7PodUcE8xB"
BIGBASE_URL = "https://bigbase.top/api/search"
ADMIN_ID = 6747528307
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mirada.db")

PRICES = {
    "1day": 150,
    "3days": 250,
    "7days": 500,
    "30days": 1000,
    "forever": 1500
}

bot = telebot.TeleBot(BOT_TOKEN)
captcha_storage = {}

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Создание всех таблиц базы данных в папке со скриптом"""
    try:
        # Создаем папку если нужно
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Таблица пользователей
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            reg_date TEXT,
            subscription_end TEXT,
            total_requests INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            captcha_passed INTEGER DEFAULT 0
        )''')
        
        # Проверяем и добавляем недостающие колонки
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'total_requests' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN total_requests INTEGER DEFAULT 0")
        if 'referrer_id' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT 0")
        if 'captcha_passed' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN captcha_passed INTEGER DEFAULT 0")
        if 'subscription_end' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN subscription_end TEXT")
        
        # Таблица рефералов
        c.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            referrer_id INTEGER,
            date TEXT,
            verified INTEGER DEFAULT 0
        )''')
        
        # Таблица настроек цен
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        
        # Таблица бонусов
        c.execute('''CREATE TABLE IF NOT EXISTS bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            date TEXT
        )''')
        
        # Сохраняем цены
        for key, value in PRICES.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        
        conn.commit()
        conn.close()
        print(f"✅ База данных создана: {DB_PATH}")
        return True
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")
        return False

def load_prices():
    """Загрузка цен из базы"""
    global PRICES
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        for key, val in c.fetchall():
            if key in PRICES:
                PRICES[key] = int(val)
        conn.close()
    except:
        pass

def save_price(key, val):
    """Сохранение цены"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE settings SET value = ? WHERE key = ?", (str(val), key))
        conn.commit()
        conn.close()
        PRICES[key] = val
    except:
        pass

def get_user(user_id):
    """Получение пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row
    except:
        return None

def add_user(user_id, username, first_name, last_name, ref_id=0):
    """Добавление пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (user_id, username, first_name, last_name, reg_date, referrer_id) VALUES (?,?,?,?,?,?)",
                      (user_id, username or '', first_name or '', last_name or '', datetime.now().isoformat(), ref_id))
            if ref_id > 0 and ref_id != user_id:
                c.execute("INSERT INTO referrals (user_id, referrer_id, date) VALUES (?,?,?)",
                          (user_id, ref_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"add_user error: {e}")

def update_user(user_id, sub_end=None, requests_count=None, captcha=None):
    """Обновление пользователя"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if sub_end:
            c.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (sub_end, user_id))
        if requests_count is not None:
            c.execute("UPDATE users SET total_requests = total_requests + ? WHERE user_id = ?", (requests_count, user_id))
        if captcha is not None:
            c.execute("UPDATE users SET captcha_passed = ? WHERE user_id = ?", (captcha, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"update_user error: {e}")

def add_subscription(user_id, days):
    """Добавление подписки"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        current = datetime.fromisoformat(row[0]) if row and row[0] else datetime.now()
        new_end = current + timedelta(days=days)
        c.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (new_end.isoformat(), user_id))
        c.execute("INSERT INTO bonuses (user_id, type, amount, date) VALUES (?, ?, ?, ?)",
                  (user_id, 'subscription', days, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return new_end
    except:
        return None

def remove_subscription(user_id):
    """Удаление подписки"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET subscription_end = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except:
        pass

def add_requests(user_id, amount):
    """Добавление запросов"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET total_requests = total_requests + ? WHERE user_id = ?", (amount, user_id))
        c.execute("INSERT INTO bonuses (user_id, type, amount, date) VALUES (?, ?, ?, ?)",
                  (user_id, 'add_requests', amount, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def remove_requests(user_id, amount):
    """Удаление запросов"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET total_requests = total_requests - ? WHERE user_id = ?", (amount, user_id))
        c.execute("INSERT INTO bonuses (user_id, type, amount, date) VALUES (?, ?, ?, ?)",
                  (user_id, 'remove_requests', amount, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def check_subscription(user_id):
    """Проверка подписки"""
    user = get_user(user_id)
    if not user:
        return False
    try:
        sub_end = user[5]
        if not sub_end:
            return False
        return datetime.fromisoformat(sub_end) > datetime.now()
    except:
        return False

def verify_referral(user_id, referrer_id):
    """Верификация реферала"""
    if referrer_id == user_id or referrer_id == 0:
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT verified FROM referrals WHERE user_id = ? AND referrer_id = ?", (user_id, referrer_id))
        row = c.fetchone()
        if row and row[0] == 0:
            c.execute("UPDATE referrals SET verified = 1 WHERE user_id = ? AND referrer_id = ?", (user_id, referrer_id))
            c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND verified = 1", (referrer_id,))
            count = c.fetchone()[0]
            bonus = count // 3
            if bonus > 0:
                c.execute("UPDATE users SET total_requests = total_requests + ? WHERE user_id = ?", (bonus, referrer_id))
                c.execute("INSERT INTO bonuses (user_id, type, amount, date) VALUES (?, ?, ?, ?)",
                          (referrer_id, 'referral_bonus', bonus, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"verify_referral error: {e}")

def get_referral_count(user_id):
    """Количество рефералов"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND verified = 1", (user_id,))
        cnt = c.fetchone()[0]
        conn.close()
        return cnt
    except:
        return 0

def get_all_users():
    """Все пользователи"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
        conn.close()
        return users
    except:
        return []

def get_stats():
    """Статистика"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        active = c.fetchone()[0]
        c.execute("SELECT SUM(total_requests) FROM users")
        req = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM referrals WHERE verified = 1")
        refs = c.fetchone()[0]
        conn.close()
        return total, active, req, refs
    except:
        return 0, 0, 0, 0

# ========== КАПТЧА ==========
def generate_captcha():
    n1 = random.randint(1, 10)
    n2 = random.randint(1, 10)
    ans = str(n1 + n2)
    cid = hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:8]
    captcha_storage[cid] = ans
    return cid, f"{n1} + {n2}"

def check_captcha(cid, ans):
    if cid not in captcha_storage:
        return False
    correct = captcha_storage[cid]
    del captcha_storage[cid]
    return ans.strip() == correct

# ========== ПОИСК ==========
def format_phone(phone):
    digits = re.sub(r'\D', '', phone)
    formats = []
    if digits.startswith('7') and len(digits) == 11:
        formats = [f"+{digits}", digits, f"8{digits[1:]}", digits[1:]]
    elif digits.startswith('8') and len(digits) == 11:
        formats = [f"+7{digits[1:]}", f"7{digits[1:]}", digits, digits[1:]]
    elif len(digits) == 10:
        formats = [f"+7{digits}", f"7{digits}", f"8{digits}", digits]
    else:
        formats = [phone, digits]
    return list(set(formats))

def search_bigbase(query):
    try:
        headers = {"Authorization": BIGBASE_TOKEN, "Content-Type": "application/json"}
        data = {"search": query.strip(), "page": 1}
        resp = requests.post(BIGBASE_URL, json=data, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        print(f"BigBase ошибка: {e}")
        return None

def extract_all_info(data):
    """Извлечение ВСЕЙ информации из BigBase"""
    result = {
        'phone_info': {},
        'persons': [],
        'emails': [],
        'sources': [],
        'addresses': []
    }
    
    if not data:
        return result
    
    # Информация о телефоне из head
    if 'head' in data:
        head = data['head']
        result['phone_info'] = {
            'number': head.get('title', ''),
            'operator': head.get('phone_operator', ''),
            'operator_code': head.get('phone_code_operator', ''),
            'operator_inn': head.get('phone_operator_inn', ''),
            'region': head.get('phone_region', ''),
            'country': head.get('phone_country_info', ''),
            'code': head.get('phone_code_country', ''),
            'region_gar': head.get('phone_region_gar', '')
        }
    
    # Персоны из connections
    connections = data.get('connections', {})
    persons = connections.get('person', [])
    
    for person in persons:
        person_info = {
            'name': '',
            'first_name': '',
            'last_name': '',
            'middle_name': '',
            'birth_date': '',
            'passport_series': '',
            'passport_number': '',
            'passport_issued': '',
            'passport_code': '',
            'passport_date': '',
            'snils': '',
            'inn': '',
            'phones': [],
            'emails': [],
            'addresses': []
        }
        
        # ФИО из head
        person_head = person.get('head', {})
        if person_head.get('title'):
            full_name = person_head['title']
            person_info['name'] = full_name
            
            # Парсим ФИО
            name_parts = full_name.split()
            if len(name_parts) >= 3:
                person_info['last_name'] = name_parts[0]
                person_info['first_name'] = name_parts[1]
                person_info['middle_name'] = name_parts[2]
        
        # Дата рождения
        if person.get('birth_date'):
            person_info['birth_date'] = person['birth_date']
        elif 'birthday' in person:
            bd = person['birthday']
            if isinstance(bd, list) and bd:
                person_info['birth_date'] = bd[0].get('value', '')
        
        # Паспорт
        if 'passport' in person:
            passport = person['passport']
            if isinstance(passport, list) and passport:
                p = passport[0]
                if isinstance(p, dict):
                    person_info['passport_series'] = p.get('series', '')
                    person_info['passport_number'] = p.get('number', '')
                    person_info['passport_issued'] = p.get('issued', '')
                    person_info['passport_code'] = p.get('code', '')
                    person_info['passport_date'] = p.get('issued_date', '')
        
        # СНИЛС
        if 'snils' in person:
            snils = person['snils']
            if isinstance(snils, list) and snils:
                s = snils[0]
                if isinstance(s, dict):
                    person_info['snils'] = s.get('number', '')
                else:
                    person_info['snils'] = str(s)
        
        # ИНН
        if 'inn' in person:
            inn = person['inn']
            if isinstance(inn, list) and inn:
                i = inn[0]
                if isinstance(i, dict):
                    person_info['inn'] = i.get('number', '')
                else:
                    person_info['inn'] = str(i)
        
        # Телефоны
        if 'phone' in person:
            for p in person['phone']:
                if isinstance(p, dict) and p.get('value'):
                    person_info['phones'].append(p['value'])
                elif isinstance(p, str):
                    person_info['phones'].append(p)
        
        # Email
        if 'email' in person:
            for e in person['email']:
                if isinstance(e, dict) and e.get('value'):
                    person_info['emails'].append(e['value'])
                    if e['value'] not in result['emails']:
                        result['emails'].append(e['value'])
                elif isinstance(e, str):
                    person_info['emails'].append(e)
                    if e not in result['emails']:
                        result['emails'].append(e)
        
        # Адреса
        if 'address_place' in person:
            for a in person['address_place']:
                if isinstance(a, dict) and a.get('full'):
                    person_info['addresses'].append(a['full'])
                    result['addresses'].append(a['full'])
        elif 'address' in person:
            addr = person['address']
            if addr:
                person_info['addresses'].append(addr)
                result['addresses'].append(addr)
        
        result['persons'].append(person_info)
    
    # Источники
    records = data.get('records', [])
    for record in records:
        base_info = record.get('base_info', {})
        if base_info.get('name'):
            result['sources'].append({
                'name': base_info.get('name', ''),
                'date': base_info.get('date_relevance', '')
            })
    
    return result

def create_html_report(query, search_type, raw_data):
    info = extract_all_info(raw_data)
    
    sections = []
    
    # Информация о телефоне
    if info['phone_info'] and info['phone_info'].get('number'):
        phone_html = f'''
        <div class="section">
            <div class="section-title">📞 ИНФОРМАЦИЯ О НОМЕРЕ</div>
            <div class="info-grid">
                <div class="info-item"><span class="info-label">Номер:</span><span class="info-value">{info['phone_info'].get('number', '')}</span></div>
                <div class="info-item"><span class="info-label">Оператор:</span><span class="info-value">{info['phone_info'].get('operator', '')}</span></div>
                <div class="info-item"><span class="info-label">Код оператора:</span><span class="info-value">{info['phone_info'].get('operator_code', '')}</span></div>
                <div class="info-item"><span class="info-label">ИНН оператора:</span><span class="info-value">{info['phone_info'].get('operator_inn', '')}</span></div>
                <div class="info-item"><span class="info-label">Код страны:</span><span class="info-value">{info['phone_info'].get('code', '')}</span></div>
                <div class="info-item"><span class="info-label">Страна:</span><span class="info-value">{info['phone_info'].get('country', '')}</span></div>
                <div class="info-item"><span class="info-label">Регион:</span><span class="info-value">{info['phone_info'].get('region', '')}</span></div>
                <div class="info-item"><span class="info-label">Регион ГАР:</span><span class="info-value">{info['phone_info'].get('region_gar', '')}</span></div>
            </div>
        </div>'''
        sections.append(phone_html)
    
    # Персоны
    if info['persons']:
        for p in info['persons']:
            person_html = '<div class="section"><div class="section-title">👤 ПЕРСОНА</div><div class="person-card">'
            
            if p['name']:
                person_html += f'<div class="person-name">📛 {p["name"]}</div>'
            
            if p['birth_date']:
                person_html += f'<div class="person-field">🎂 Дата рождения: {p["birth_date"]}</div>'
            
            if p['inn']:
                person_html += f'<div class="person-field">📄 ИНН: {p["inn"]}</div>'
            
            if p['snils']:
                person_html += f'<div class="person-field">📋 СНИЛС: {p["snils"]}</div>'
            
            if p['passport_series'] or p['passport_number']:
                passport_str = f"{p['passport_series']} {p['passport_number']}".strip()
                person_html += f'<div class="person-field">🪪 Паспорт: {passport_str}</div>'
            
            if p['passport_issued']:
                person_html += f'<div class="person-field">🏛 Выдан: {p["passport_issued"]}</div>'
            
            if p['passport_code']:
                person_html += f'<div class="person-field">📮 Код подразделения: {p["passport_code"]}</div>'
            
            if p['phones']:
                person_html += f'<div class="person-field">📱 Телефоны: {", ".join(p["phones"])}</div>'
            
            if p['emails']:
                person_html += f'<div class="person-field">📧 Email: {", ".join(p["emails"])}</div>'
            
            if p['addresses']:
                person_html += f'<div class="person-field">🏠 Адреса: {", ".join(p["addresses"])}</div>'
            
            person_html += '</div></div>'
            sections.append(person_html)
    
    # Email
    if info['emails']:
        emails_html = f'''
        <div class="section">
            <div class="section-title">📧 EMAIL</div>
            <div class="tags-list">
                {"".join([f'<span class="tag">📧 {e}</span>' for e in info['emails'][:10]])}
            </div>
        </div>'''
        sections.append(emails_html)
    
    # Адреса
    if info['addresses']:
        addr_html = f'''
        <div class="section">
            <div class="section-title">🏠 АДРЕСА</div>
            <div class="tags-list">
                {"".join([f'<span class="tag">📍 {a}</span>' for a in info['addresses'][:5]])}
            </div>
        </div>'''
        sections.append(addr_html)
    
    # Источники
    if info['sources']:
        sources_html = '<div class="section"><div class="section-title">📚 ИСТОЧНИКИ</div><div class="tags-list">'
        for s in info['sources']:
            sources_html += f'<span class="tag source">📌 {s["name"]} ({s["date"]})</span>'
        sources_html += '</div></div>'
        sections.append(sources_html)
    
    # Всего источников
    total_sources = len(info['sources'])
    total_html = f'<div class="section"><div class="section-title">📊 СТАТИСТИКА</div><div class="total-sources">Всего источников: {total_sources}<br>Поиск занял: 0.002 сек.</div></div>'
    sections.append(total_html)
    
    html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mirada | {query}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: linear-gradient(135deg, #0a0a0f 0%, #0c0c14 100%);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .report {{
            background: rgba(18, 18, 28, 0.96);
            backdrop-filter: blur(12px);
            border-radius: 28px;
            border: 1px solid rgba(139, 92, 246, 0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #12121c, #0a0a12);
            padding: 28px 24px;
            text-align: center;
            border-bottom: 1px solid rgba(139, 92, 246, 0.2);
        }}
        .logo {{
            font-size: 36px;
            font-weight: 800;
            background: linear-gradient(135deg, #a855f7, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .badge {{
            background: rgba(139, 92, 246, 0.15);
            padding: 6px 16px;
            border-radius: 40px;
            display: inline-block;
            margin-top: 12px;
            font-size: 12px;
            color: #c084fc;
        }}
        .section {{
            padding: 20px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .section-title {{
            font-size: 14px;
            font-weight: 600;
            color: #c084fc;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 18px;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 12px;
        }}
        .info-item {{
            background: rgba(10, 10, 18, 0.5);
            border-radius: 14px;
            padding: 12px 14px;
            border-left: 3px solid #8b5cf6;
        }}
        .info-label {{
            font-size: 10px;
            color: #8b5cf6;
            text-transform: uppercase;
            display: block;
            margin-bottom: 4px;
        }}
        .info-value {{
            font-size: 13px;
            color: #e5e7eb;
            font-family: monospace;
            word-break: break-all;
        }}
        .person-card {{
            background: rgba(10, 10, 18, 0.5);
            border-radius: 20px;
            padding: 16px;
            margin-bottom: 14px;
            border: 1px solid rgba(139, 92, 246, 0.2);
        }}
        .person-name {{
            font-size: 16px;
            font-weight: 600;
            color: #c084fc;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(139, 92, 246, 0.3);
        }}
        .person-field {{
            font-size: 12px;
            color: #d1d5db;
            margin-bottom: 8px;
            line-height: 1.4;
            word-break: break-word;
        }}
        .tags-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .tag {{
            background: rgba(139, 92, 246, 0.1);
            border: 1px solid rgba(139, 92, 246, 0.3);
            border-radius: 30px;
            padding: 6px 14px;
            font-size: 11px;
            color: #c084fc;
        }}
        .source {{
            background: rgba(20, 20, 35, 0.8);
        }}
        .total-sources {{
            text-align: center;
            font-size: 13px;
            color: #a855f7;
            font-weight: 500;
            padding: 12px;
            background: rgba(139, 92, 246, 0.05);
            border-radius: 16px;
        }}
        .footer {{
            padding: 20px;
            text-align: center;
            background: #08080e;
            border-top: 1px solid rgba(139, 92, 246, 0.15);
        }}
        .time {{
            font-size: 10px;
            color: #5a5a6e;
            margin-bottom: 10px;
        }}
        .dev {{
            font-size: 11px;
            color: #8b5cf6;
        }}
        .copy-btn {{
            background: linear-gradient(135deg, #1a1a28, #0f0f1a);
            border: 1px solid rgba(139, 92, 246, 0.4);
            color: #c084fc;
            padding: 8px 22px;
            border-radius: 40px;
            font-size: 11px;
            cursor: pointer;
            margin-top: 12px;
        }}
        @media (max-width: 600px) {{
            .section {{ padding: 16px 18px; }}
            .info-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="report">
        <div class="header">
            <div class="logo">MIRADA</div>
            <div class="badge">🔍 {search_type.replace('search_', '').upper()} | {query}</div>
        </div>
        
        {"".join(sections)}
        
        <div class="footer">
            <div class="time">🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            <div class="dev">👨‍💻 developer: @nymps</div>
            <button class="copy-btn" onclick="copyReport()">📋 КОПИРОВАТЬ</button>
        </div>
    </div>
</div>
<script>
function copyReport() {{
    let text = `MIRADA OSINT REPORT
═══════════════════════════════════════
🔍 ЗАПРОС: {query}
🕐 ВРЕМЯ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
───────────────────────────────────────────
👨‍💻 developer: @nymps`;
    navigator.clipboard.writeText(text);
    alert('✅ Отчет скопирован');
}}
</script>
</body>
</html>'''
    return html

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔍 ПОИСК", callback_data="search"),
        types.InlineKeyboardButton("👥 РЕФЕРАЛЫ", callback_data="referral"),
        types.InlineKeyboardButton("💎 ПОДПИСКА", callback_data="subscription"),
        types.InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"),
        types.InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help")
    )
    return kb

def search_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("👤 ФИО", "search_fio"),
        ("📱 ТЕЛЕФОН", "search_phone"),
        ("📧 ПОЧТА", "search_email"),
        ("🚗 АВТО", "search_auto"),
        ("🏠 АДРЕС", "search_address"),
        ("⬅️ НАЗАД", "back")
    ]
    for txt, data in buttons:
        kb.add(types.InlineKeyboardButton(txt, callback_data=data))
    return kb

def subscription_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"1 день - {PRICES['1day']} ₽", callback_data="buy_1"),
        types.InlineKeyboardButton(f"3 дня - {PRICES['3days']} ₽", callback_data="buy_3"),
        types.InlineKeyboardButton(f"7 дней - {PRICES['7days']} ₽", callback_data="buy_7"),
        types.InlineKeyboardButton(f"30 дней - {PRICES['30days']} ₽", callback_data="buy_30"),
        types.InlineKeyboardButton(f"НАВСЕГДА - {PRICES['forever']} ₽", callback_data="buy_forever"),
        types.InlineKeyboardButton("⬅️ НАЗАД", callback_data="back")
    )
    return kb

def admin_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📢 РАССЫЛКА", callback_data="admin_mail"),
        types.InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats"),
        types.InlineKeyboardButton("💰 НАСТРОЙКА ЦЕН", callback_data="admin_prices"),
        types.InlineKeyboardButton("💎 ВЫДАТЬ ПОДПИСКУ", callback_data="admin_add_sub"),
        types.InlineKeyboardButton("➖ ЗАБРАТЬ ПОДПИСКУ", callback_data="admin_remove_sub"),
        types.InlineKeyboardButton("🔍 ВЫДАТЬ ЗАПРОСЫ", callback_data="admin_add_requests"),
        types.InlineKeyboardButton("➖ ЗАБРАТЬ ЗАПРОСЫ", callback_data="admin_remove_requests"),
        types.InlineKeyboardButton("📈 РЕФЕРАЛЬНАЯ СТАТИСТИКА", callback_data="admin_ref_stats"),
        types.InlineKeyboardButton("⬅️ НАЗАД", callback_data="back")
    )
    return kb

def prices_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"1 день: {PRICES['1day']} ₽", callback_data="price_1day"),
        types.InlineKeyboardButton(f"3 дня: {PRICES['3days']} ₽", callback_data="price_3days"),
        types.InlineKeyboardButton(f"7 дней: {PRICES['7days']} ₽", callback_data="price_7days"),
        types.InlineKeyboardButton(f"30 дней: {PRICES['30days']} ₽", callback_data="price_30days"),
        types.InlineKeyboardButton(f"Навсегда: {PRICES['forever']} ₽", callback_data="price_forever"),
        types.InlineKeyboardButton("⬅️ НАЗАД", callback_data="admin_panel")
    )
    return kb

def get_example(t):
    ex = {
        "search_fio": "Иванов Иван 01.01.1990",
        "search_phone": "+79120463865",
        "search_email": "mail@example.com",
        "search_auto": "А123АА777",
        "search_address": "Москва, ул. Ленина 1"
    }
    return ex.get(t, "текст")

# ========== ОБРАБОТЧИКИ ==========
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    uname = m.from_user.username or ""
    fname = m.from_user.first_name or ""
    lname = m.from_user.last_name or ""
    
    ref = 0
    if len(m.text.split()) > 1:
        try:
            ref = int(m.text.split()[1])
            if ref == uid:
                ref = 0
        except:
            pass
    
    add_user(uid, uname, fname, lname, ref)
    
    user = get_user(uid)
    if user and len(user) > 8 and user[8] == 0:
        cid, ex = generate_captcha()
        kb = types.InlineKeyboardMarkup(row_width=3)
        correct = str(int(ex.split()[0]) + int(ex.split()[2]))
        opts = [correct]
        while len(opts) < 3:
            w = str(int(correct) + random.randint(-2, 2))
            if w != correct and int(w) > 0 and w not in opts:
                opts.append(w)
        random.shuffle(opts)
        for o in opts:
            kb.add(types.InlineKeyboardButton(o, callback_data=f"captcha_{cid}_{o}"))
        bot.send_message(uid, f"🔐 ПРОВЕРКА\n\nРешите: {ex} = ?", reply_markup=kb)
        return
    
    welcome = """🌟 ДОБРО ПОЖАЛОВАТЬ В MIRADA 🌟

🔍 Поиск по 60 ТБ баз
💎 Подписка: @nymps
👨‍💻 @nymps

⚠️ Все персонажи вымышлены, совпадения случайны.
Мы не несем ответственность за ваши действия."""
    
    bot.send_message(uid, welcome, reply_markup=main_menu())

@bot.message_handler(commands=['admin'])
def admin(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, "⛔ Доступ запрещен")
        return
    bot.send_message(m.chat.id, "🔧 АДМИН ПАНЕЛЬ", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    uid = c.from_user.id
    
    if c.data.startswith("captcha_"):
        _, cid, ans = c.data.split("_", 2)
        if check_captcha(cid, ans):
            update_user(uid, captcha=1)
            bot.answer_callback_query(c.id, "✅ Каптча пройдена!")
            user = get_user(uid)
            if user and len(user) > 7 and user[7] and user[7] > 0:
                verify_referral(uid, user[7])
            welcome = """🌟 ДОБРО ПОЖАЛОВАТЬ В MIRADA 🌟

🔍 Поиск по 60 ТБ баз
💎 Подписка: @nymps
👨‍💻 @nymps

⚠️ Все персонажи вымышлены, совпадения случайны.
Мы не несем ответственность за ваши действия."""
            bot.edit_message_text(welcome, uid, c.message.message_id, reply_markup=main_menu())
        else:
            bot.answer_callback_query(c.id, "❌ Неправильно!", True)
            bot.delete_message(uid, c.message.message_id)
            start(c.message)
        return
    
    if c.data == "search":
        bot.edit_message_text("🔍 Выберите тип поиска:", uid, c.message.message_id, reply_markup=search_menu())
    
    elif c.data in ["search_fio", "search_phone", "search_email", "search_auto", "search_address"]:
        types_map = {"search_fio": "ФИО", "search_phone": "ТЕЛЕФОН", "search_email": "EMAIL", "search_auto": "АВТО", "search_address": "АДРЕС"}
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ НАЗАД", callback_data="search"))
        bot.edit_message_text(f"🔍 Введите {types_map[c.data]}\n\nПример: {get_example(c.data)}", uid, c.message.message_id, reply_markup=kb)
        with open(f"temp_{uid}.txt", "w") as f:
            f.write(c.data)
    
    elif c.data == "referral":
        cnt = get_referral_count(uid)
        un = bot.get_me().username
        link = f"https://t.me/{un}?start={uid}"
        bot.edit_message_text(f"👥 РЕФЕРАЛЫ\n\n🔗 {link}\n📊 Приглашено: {cnt}\n🎁 3 реферала = 1 запрос\n🤝 Бот: @HardyWork_bot", uid, c.message.message_id, reply_markup=main_menu())
    
    elif c.data == "subscription":
        user = get_user(uid)
        status = "✅ Активна" if check_subscription(uid) else "❌ Не активна"
        expiry = datetime.fromisoformat(user[5]).strftime('%d.%m.%Y') if user and user[5] else "—"
        bot.edit_message_text(f"💎 ПОДПИСКА\n\nСтатус: {status}\nДо: {expiry}", uid, c.message.message_id, reply_markup=subscription_menu())
    
    elif c.data in ["buy_1", "buy_3", "buy_7", "buy_30", "buy_forever"]:
        key = {"buy_1":"1day", "buy_3":"3days", "buy_7":"7days", "buy_30":"30days", "buy_forever":"forever"}[c.data]
        bot.answer_callback_query(c.id, f"💰 Оплата @nymps\n{PRICES[key]} ₽", True)
    
    elif c.data == "profile":
        user = get_user(uid)
        if user:
            sub = "✅" if check_subscription(uid) else "❌"
            end = datetime.fromisoformat(user[5]).strftime('%d.%m.%Y') if user[5] else "—"
            refs = get_referral_count(uid)
            bot.edit_message_text(f"👤 ПРОФИЛЬ\n\n🆔 ID: {uid}\n👤 Имя: {user[2]} {user[3] or ''}\n📊 Запросов: {user[6]}\n💎 Подписка: {sub}\n📅 До: {end}\n👥 Рефералов: {refs}", uid, c.message.message_id, reply_markup=main_menu())
    
    elif c.data == "help":
        bot.edit_message_text("❓ ПОМОЩЬ\n\n1. Нажмите ПОИСК\n2. Выберите тип\n3. Введите запрос\n\n📱 +79120463865\n👤 Иванов Иван 01.01.1990\n📧 mail@example.com\n🚗 А123АА777\n🏠 Москва, ул. Ленина 1\n\nПоддержка: @nymps", uid, c.message.message_id, reply_markup=main_menu())
    
    elif c.data == "back":
        bot.edit_message_text("🌟 Главное меню", uid, c.message.message_id, reply_markup=main_menu())
    
    # АДМИН
    elif uid == ADMIN_ID:
        if c.data == "admin_stats":
            total, active, req, refs = get_stats()
            bot.edit_message_text(f"📊 СТАТИСТИКА\n\n👥 Всего: {total}\n💎 Активных: {active}\n🔍 Запросов: {req}\n👥 Рефералов: {refs}", uid, c.message.message_id, reply_markup=admin_menu())
        
        elif c.data == "admin_prices":
            bot.edit_message_text(f"💰 ЦЕНЫ\n\n1 день: {PRICES['1day']} ₽\n3 дня: {PRICES['3days']} ₽\n7 дней: {PRICES['7days']} ₽\n30 дней: {PRICES['30days']} ₽\nНавсегда: {PRICES['forever']} ₽", uid, c.message.message_id, reply_markup=prices_menu())
        
        elif c.data == "admin_mail":
            bot.edit_message_text("📢 Введите сообщение для рассылки:", uid, c.message.message_id)
            with open(f"admin_state_{uid}.txt", "w") as f:
                f.write("mailing")
        
        elif c.data == "admin_add_sub":
            bot.edit_message_text("➕ Введите ID и количество дней:\nПример: 123456789 30", uid, c.message.message_id)
            with open(f"admin_state_{uid}.txt", "w") as f:
                f.write("add_sub")
        
        elif c.data == "admin_remove_sub":
            bot.edit_message_text("➖ Введите ID пользователя:", uid, c.message.message_id)
            with open(f"admin_state_{uid}.txt", "w") as f:
                f.write("remove_sub")
        
        elif c.data == "admin_add_requests":
            bot.edit_message_text("🔍 Введите ID и количество запросов:\nПример: 123456789 10", uid, c.message.message_id)
            with open(f"admin_state_{uid}.txt", "w") as f:
                f.write("add_requests")
        
        elif c.data == "admin_remove_requests":
            bot.edit_message_text("➖ Введите ID и количество запросов для удаления:\nПример: 123456789 5", uid, c.message.message_id)
            with open(f"admin_state_{uid}.txt", "w") as f:
                f.write("remove_requests")
        
        elif c.data == "admin_ref_stats":
            conn = sqlite3.connect(DB_PATH)
            c2 = conn.cursor()
            c2.execute("SELECT u.user_id, u.username, COUNT(r.id) FROM users u LEFT JOIN referrals r ON u.user_id = r.referrer_id AND r.verified=1 GROUP BY u.user_id ORDER BY COUNT(r.id) DESC LIMIT 10")
            rows = c2.fetchall()
            conn.close()
            text = "🏆 ТОП РЕФЕРАЛОВ\n\n"
            for i, (uid2, un, cnt) in enumerate(rows, 1):
                name = f"@{un}" if un else str(uid2)
                text += f"{i}. {name} — {cnt} рефералов\n"
            bot.edit_message_text(text, uid, c.message.message_id, reply_markup=admin_menu())
        
        elif c.data in ["price_1day", "price_3days", "price_7days", "price_30days", "price_forever"]:
            key = c.data.replace("price_", "")
            bot.edit_message_text(f"💰 Введите новую цену для {key}:", uid, c.message.message_id)
            with open(f"admin_state_{uid}.txt", "w") as f:
                f.write(f"price_{key}")
        
        elif c.data == "admin_panel":
            bot.edit_message_text("🔧 АДМИН ПАНЕЛЬ", uid, c.message.message_id, reply_markup=admin_menu())

@bot.message_handler(func=lambda m: True)
def handle_msg(m):
    uid = m.chat.id
    text = m.text.strip()
    
    # Админ действия
    state_file = f"admin_state_{uid}.txt"
    if os.path.exists(state_file) and uid == ADMIN_ID:
        with open(state_file, "r") as f:
            state = f.read().strip()
        os.remove(state_file)
        
        if state.startswith("price_"):
            try:
                val = int(text)
                if val > 0:
                    key = state.replace("price_", "")
                    save_price(key, val)
                    bot.send_message(uid, f"✅ Цена для {key} изменена на {val} ₽")
                else:
                    bot.send_message(uid, "❌ Цена должна быть > 0")
            except:
                bot.send_message(uid, "❌ Введите число")
            return
        
        elif state == "mailing":
            users = get_all_users()
            sent = 0
            for u in users:
                try:
                    bot.send_message(u, text)
                    sent += 1
                    time.sleep(0.05)
                except:
                    pass
            bot.send_message(uid, f"✅ Рассылка завершена!\nОтправлено: {sent} из {len(users)}")
            return
        
        elif state == "add_sub":
            try:
                parts = text.split()
                uid2 = int(parts[0])
                days = int(parts[1]) if len(parts) > 1 else 30
                new_end = add_subscription(uid2, days)
                bot.send_message(uid, f"✅ Подписка выдана!\nПользователь: {uid2}\nДней: {days}\nДо: {new_end.strftime('%d.%m.%Y')}")
            except:
                bot.send_message(uid, "❌ Ошибка! Формат: ID дни")
            return
        
        elif state == "remove_sub":
            try:
                uid2 = int(text)
                remove_subscription(uid2)
                bot.send_message(uid, f"✅ Подписка удалена у {uid2}")
            except:
                bot.send_message(uid, "❌ Ошибка! Введите ID")
            return
        
        elif state == "add_requests":
            try:
                parts = text.split()
                uid2 = int(parts[0])
                amount = int(parts[1]) if len(parts) > 1 else 1
                add_requests(uid2, amount)
                bot.send_message(uid, f"✅ Выдано {amount} запросов пользователю {uid2}")
            except:
                bot.send_message(uid, "❌ Ошибка! Формат: ID количество")
            return
        
        elif state == "remove_requests":
            try:
                parts = text.split()
                uid2 = int(parts[0])
                amount = int(parts[1]) if len(parts) > 1 else 1
                remove_requests(uid2, amount)
                bot.send_message(uid, f"✅ Удалено {amount} запросов у пользователя {uid2}")
            except:
                bot.send_message(uid, "❌ Ошибка! Формат: ID количество")
            return
    
    # Поиск
    search_file = f"temp_{uid}.txt"
    if not os.path.exists(search_file):
        bot.send_message(uid, "🔍 Сначала выберите тип поиска!", reply_markup=main_menu())
        return
    
    with open(search_file, "r") as f:
        search_type = f.read().strip()
    os.remove(search_file)
    
    user = get_user(uid)
    if not user:
        bot.send_message(uid, "❌ Ошибка! Перезапустите бота /start", reply_markup=main_menu())
        return
    
    if not check_subscription(uid) and (len(user) > 6 and user[6] <= 0):
        bot.send_message(uid, "❌ Нет активной подписки и запросов!\nОплатите: @nymps", reply_markup=main_menu())
        return
    
    status = bot.send_message(uid, "🔍 Поиск...")
    
    try:
        bigbase_data = None
        if search_type == "search_phone":
            for fmt in format_phone(text)[:2]:
                res = search_bigbase(fmt)
                if res:
                    bigbase_data = res
                    break
        else:
            bigbase_data = search_bigbase(text)
        
        if not bigbase_data:
            bot.edit_message_text("❌ Ничего не найдено", uid, status.message_id)
            return
        
        if len(user) > 6 and user[6] > 0:
            update_user(uid, requests_count=-1)
        html = create_html_report(text, search_type, bigbase_data)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp = f.name
        
        with open(tmp, 'rb') as f:
            bot.send_document(uid, f, caption=f"✅ Mirada Report\n👨‍💻 @nymps")
        
        os.unlink(tmp)
        bot.delete_message(uid, status.message_id)
        
    except Exception as e:
        bot.delete_message(uid, status.message_id)
        bot.send_message(uid, f"❌ Ошибка: {str(e)[:100]}")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    init_db()
    load_prices()
    print("\n" + "="*50)
    print("🤖 MIRADA OSINT BOT")
    print("="*50)
    print("✅ Бот запущен!")
    print("👨‍💻 Admin ID: " + str(ADMIN_ID))
    print("📁 База данных: " + DB_PATH)
    print("="*50 + "\n")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=30)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(3)