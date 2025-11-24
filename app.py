# app.py
# -*- coding: utf-8 -*-
"""
NextCly – CRM básico com:
- Cadastro de clientes
- Observações por atendimento
- Agenda de consultas
- Autenticação (Flask-Login)
- Envio de confirmação por WhatsApp/SMS (Twilio – opcional)
- Exportação de agenda em ICS (importável no Google Calendar)
- Relatórios (por período, status) + exportação CSV


Stack: Flask + SQLite (arquivo local), Bootstrap 5 via CDN.


Como executar localmente:
1) python -m venv .venv && source .venv/bin/activate (no Windows: .venv\Scripts\activate)
2) pip install -r requirements.txt (ver arquivo abaixo)
3) python app.py
4) http://127.0.0.1:5000


Usuário inicial:
- Rode: `flask --app app.py create-user --email admin@example.com --password 123456 --name Admin`


Variáveis de ambiente (opcional):
- FLASK_SECRET_KEY: chave da sessão
- TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM (SMS) / TWILIO_WHATSAPP_FROM (whatsapp: +14155238886 por ex.)
- BASE_URL: URL pública do app (para links em mensagens)
"""
from __future__ import annotations
from datetime import datetime, timedelta
import csv
import io
import os
import sqlite3
from dataclasses import dataclass
from typing import List, Any, Optional


from flask import (
Flask, g, render_template_string, request, redirect, url_for, flash,
send_file
)
from flask_login import (
LoginManager, login_user, logout_user, login_required, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash


# ------------------------- Config -------------------------
APP_TITLE = "NextCly"
DB_PATH = os.path.join(os.path.dirname(__file__), "nextcly.sqlite3")


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")


login_manager = LoginManager(app)
login_manager.login_view = "login"


# ------------------------- DB Helpers -------------------------


def get_db():
db = getattr(g, "_db", None)
if db is None:
db = g._db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
return db


@app.teardown_appcontext
def close_db(exception):
db = getattr(g, "_db", None)
if db is not None:
db.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
email TEXT UNIQUE NOT NULL,
password_hash TEXT NOT NULL,
created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS clients (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT NOT NULL,
phone TEXT,
email TEXT,
created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS notes (
"""
