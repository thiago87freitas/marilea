# app.py
# -*- coding: utf-8 -*-
"""
Sistema básico (MVP) para:
- Cadastro de clientes
- Observações por atendimento (anotações por cliente)
- Agenda de consultas (com data/hora, duração, status e notas)

Stack: Flask + SQLite (arquivo local), Bootstrap 5 via CDN.

Como executar:
1) pip install flask
2) python app.py
3) Acesse http://127.0.0.1:5000

Banco: arquivo 'crm.sqlite3' criado automaticamente no primeiro run.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import os
import sqlite3
from typing import List, Dict, Any

from flask import Flask, g, render_template_string, request, redirect, url_for, flash

APP_TITLE = "Bem Serviços - CRM Básico"
DB_PATH = os.path.join(os.path.dirname(__file__), "crm.sqlite3")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

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
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    starts_at TEXT NOT NULL,          -- ISO datetime (UTC local)
    duration_min INTEGER NOT NULL DEFAULT 60,
    status TEXT NOT NULL DEFAULT 'Agendado', -- Agendado, Confirmado, Concluído, Cancelado, Não compareceu
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_appointments_starts_at ON appointments(starts_at);
CREATE INDEX IF NOT EXISTS idx_notes_client_id ON notes(client_id);
"""

def init_db():
    db = get_db()
    db.executescript(SCHEMA_SQL)
    db.commit()

@app.before_request
def ensure_db():
    init_db()

# ------------------------- Utils -------------------------

def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M")

# ------------------------- Templates (Jinja inline) -------------------------

BASE_TMPL = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title or 'App' }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding-bottom: 64px; }
    .navbar-brand { font-weight: 600; }
    .card { border-radius: 14px; }
    .table thead th { white-space: nowrap; }
    .badge-status { font-size: 0.85rem; }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg bg-body-tertiary">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">{{ app_title }}</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item"><a class="nav-link" href="{{ url_for('clients') }}">Clientes</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('appointments') }}">Agenda</a></li>
      </ul>
    </div>
  </div>
</nav>
<div class="container mt-4">
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="alert alert-info">{{ messages|join('\n') }}</div>
    {% endif %}
  {% endwith %}
  {{ body|safe }}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ------------------------- Routes -------------------------

@app.route("/")
def index():
    db = get_db()
    now = datetime.now()
    until = now + timedelta(days=7)
    cur = db.execute(
        """
        SELECT a.id, a.starts_at, a.duration_min, a.status, a.notes,
               c.id as client_id, c.name as client_name, c.phone
        FROM appointments a
        JOIN clients c ON c.id = a.client_id
        WHERE a.starts_at >= ? AND a.starts_at < ?
        ORDER BY a.starts_at ASC
        """,
        (now.strftime("%Y-%m-%dT%H:%M"), until.strftime("%Y-%m-%dT%H:%M"))
    )
    appts = cur.fetchall()
    body = render_template_string("""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3 class="mb-0">Próximos 7 dias</h3>
      <a class="btn btn-primary" href="{{ url_for('new_appointment') }}">+ Nova consulta</a>
    </div>
    {% if appts %}
      <div class="list-group">
        {% for a in appts %}
          <a class="list-group-item list-group-item-action" href="{{ url_for('edit_appointment', appt_id=a['id']) }}">
            <div class="d-flex w-100 justify-content-between">
              <h6 class="mb-1">{{ a['client_name'] }} ({{ a['phone'] or 's/ telefone' }})</h6>
              <small>{{ a['starts_at']|replace('T',' ') }} • {{ a['duration_min'] }}min</small>
            </div>
            <small class="text-muted">Status: {{ a['status'] }}</small>
            {% if a['notes'] %}<div class="small text-body-secondary mt-1">{{ a['notes'] }}</div>{% endif %}
          </a>
        {% endfor %}
      </div>
    {% else %}
      <div class="alert alert-secondary">Nenhuma consulta nos próximos 7 dias.</div>
    {% endif %}
    """, appts=appts)
    return render_template_string(BASE_TMPL, title=APP_TITLE, app_title=APP_TITLE, body=body)

# ------------------------- Clientes -------------------------

@app.route("/clientes")
def clients():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        cur = db.execute("SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? ORDER BY created_at DESC", (f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cur = db.execute("SELECT * FROM clients ORDER BY created_at DESC")
    clients = cur.fetchall()
    body = render_template_string("""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3 class="mb-0">Clientes</h3>
      <div>
        <a class="btn btn-outline-secondary" href="{{ url_for('clients') }}">Limpar</a>
        <a class="btn btn-primary" href="{{ url_for('new_client') }}">+ Novo cliente</a>
      </div>
    </div>

    <form class="row row-cols-lg-auto g-2 align-items-center mb-3">
      <div class="col-12">
        <input type="text" class="form-control" name="q" placeholder="Buscar por nome, telefone, e-mail" value="{{ request.args.get('q','') }}">
      </div>
      <div class="col-12">
        <button class="btn btn-outline-primary" type="submit">Buscar</button>
      </div>
    </form>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead><tr><th>Nome</th><th>Telefone</th><th>E-mail</th><th>Criado em</th><th></th></tr></thead>
          <tbody>
          {% for c in clients %}
            <tr>
              <td>{{ c['name'] }}</td>
              <td>{{ c['phone'] or '-' }}</td>
              <td>{{ c['email'] or '-' }}</td>
              <td><small>{{ c['created_at']|replace('T',' ') }}</small></td>
              <td class="text-end"><a href="{{ url_for('client_detail', client_id=c['id']) }}" class="btn btn-sm btn-outline-secondary">Abrir</a></td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% if not clients %}<div class="text-muted mt-3">Nenhum cliente encontrado.</div>{% endif %}
    """, clients=clients)
    return render_template_string(BASE_TMPL, title=f"Clientes · {APP_TITLE}", app_title=APP_TITLE, body=body)

@app.route("/clientes/novo", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        if not name:
            flash("Nome é obrigatório.")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO clients (name, phone, email, created_at) VALUES (?,?,?,?)",
                (name, phone or None, email or None, datetime.now().strftime("%Y-%m-%dT%H:%M"))
            )
            db.commit()
            flash("Cliente criado com sucesso!")
            return redirect(url_for("clients"))
    body = render_template_string("""
    <h3>Novo cliente</h3>
    <form method="post" class="mt-3">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Nome *</label>
          <input name="name" class="form-control" required>
        </div>
        <div class="col-md-3">
          <label class="form-label">Telefone</label>
          <input name="phone" class="form-control">
        </div>
        <div class="col-md-3">
          <label class="form-label">E-mail</label>
          <input name="email" type="email" class="form-control">
        </div>
      </div>
      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Salvar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('clients') }}">Cancelar</a>
      </div>
    </form>
    """)
    return render_template_string(BASE_TMPL, title=f"Novo cliente · {APP_TITLE}", app_title=APP_TITLE, body=body)

@app.route("/clientes/<int:client_id>", methods=["GET", "POST"])
def client_detail(client_id: int):
    db = get_db()
    # Post de nova nota
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            db.execute(
                "INSERT INTO notes (client_id, content, created_at) VALUES (?,?,?)",
                (client_id, content, datetime.now().strftime("%Y-%m-%dT%H:%M"))
            )
            db.commit()
            flash("Observação adicionada!")
        return redirect(url_for("client_detail", client_id=client_id))

    cur = db.execute("SELECT * FROM clients WHERE id=?", (client_id,))
    client = cur.fetchone()
    if not client:
        flash("Cliente não encontrado.")
        return redirect(url_for("clients"))

    notes = db.execute("SELECT * FROM notes WHERE client_id=? ORDER BY created_at DESC", (client_id,)).fetchall()
    appts = db.execute(
        """
        SELECT * FROM appointments WHERE client_id=? ORDER BY starts_at DESC
        """,
        (client_id,)
    ).fetchall()

    body = render_template_string("""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <div>
        <h3 class="mb-1">{{ client['name'] }}</h3>
        <div class="text-muted"><small>{{ client['phone'] or '-' }} · {{ client['email'] or '-' }}</small></div>
      </div>
      <div class="d-flex gap-2">
        <a class="btn btn-outline-primary" href="{{ url_for('new_appointment', client_id=client['id']) }}">Agendar consulta</a>
        <a class="btn btn-outline-secondary" href="{{ url_for('clients') }}">Voltar</a>
      </div>
    </div>

    <div class="row g-4">
      <div class="col-lg-6">
        <div class="card p-3">
          <h5 class="mb-3">Observações</h5>
          <form method="post" class="mb-3">
            <div class="input-group">
              <textarea name="content" class="form-control" placeholder="Adicionar uma observação do atendimento..."></textarea>
              <button class="btn btn-primary" type="submit">Adicionar</button>
            </div>
          </form>
          {% if notes %}
            <ul class="list-group list-group-flush">
              {% for n in notes %}
                <li class="list-group-item">
                  <div class="small text-muted">{{ n['created_at']|replace('T',' ') }}</div>
                  <div>{{ n['content'] }}</div>
                </li>
              {% endfor %}
            </ul>
          {% else %}
            <div class="text-muted">Sem observações ainda.</div>
          {% endif %}
        </div>
      </div>
      <div class="col-lg-6">
        <div class="card p-3">
          <h5 class="mb-3">Consultas</h5>
          {% if appts %}
            <div class="table-responsive">
              <table class="table table-sm align-middle">
                <thead>
                  <tr><th>Data/Hora</th><th>Duração</th><th>Status</th><th>Notas</th><th></th></tr>
                </thead>
                <tbody>
                  {% for a in appts %}
                    <tr>
                      <td><small>{{ a['starts_at']|replace('T',' ') }}</small></td>
                      <td>{{ a['duration_min'] }}min</td>
                      <td>{{ a['status'] }}</td>
                      <td><small>{{ a['notes'] or '-' }}</small></td>
                      <td class="text-end"><a class="btn btn-sm btn-outline-secondary" href="{{ url_for('edit_appointment', appt_id=a['id']) }}">Editar</a></td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <div class="text-muted">Nenhuma consulta registrada.</div>
          {% endif %}
        </div>
      </div>
    </div>
    """, client=client, notes=notes, appts=appts)
    return render_template_string(BASE_TMPL, title=f"{client['name']} · {APP_TITLE}", app_title=APP_TITLE, body=body)

# ------------------------- Agenda -------------------------

@app.route("/agenda")
def appointments():
    db = get_db()
    date_from = request.args.get("de")
    date_to = request.args.get("ate")

    query = "SELECT a.*, c.name as client_name FROM appointments a JOIN clients c ON c.id=a.client_id"
    params: List[Any] = []
    clauses: List[str] = []

    if date_from:
        clauses.append("a.starts_at >= ?")
        params.append(f"{date_from}T00:00")
    if date_to:
        clauses.append("a.starts_at <= ?")
        params.append(f"{date_to}T23:59")

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY a.starts_at ASC"

    rows = get_db().execute(query, params).fetchall()

    body = render_template_string("""
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h3 class="mb-0">Agenda</h3>
      <a class="btn btn-primary" href="{{ url_for('new_appointment') }}">+ Nova consulta</a>
    </div>

    <form class="row gy-2 gx-2 align-items-end mb-3">
      <div class="col-auto">
        <label class="form-label">De</label>
        <input type="date" class="form-control" name="de" value="{{ request.args.get('de','') }}">
      </div>
      <div class="col-auto">
        <label class="form-label">Até</label>
        <input type="date" class="form-control" name="ate" value="{{ request.args.get('ate','') }}">
      </div>
      <div class="col-auto">
        <button class="btn btn-outline-primary" type="submit">Filtrar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('appointments') }}">Limpar</a>
      </div>
    </form>

    {% if rows %}
      <div class="table-responsive">
        <table class="table table-hover align-middle">
          <thead><tr><th>Data/Hora</th><th>Cliente</th><th>Duração</th><th>Status</th><th>Notas</th><th></th></tr></thead>
          <tbody>
            {% for r in rows %}
              <tr>
                <td><small>{{ r['starts_at']|replace('T',' ') }}</small></td>
                <td>{{ r['client_name'] }}</td>
                <td>{{ r['duration_min'] }}min</td>
                <td>
                  <span class="badge text-bg-secondary badge-status">{{ r['status'] }}</span>
                </td>
                <td><small>{{ r['notes'] or '-' }}</small></td>
                <td class="text-end"><a class="btn btn-sm btn-outline-secondary" href="{{ url_for('edit_appointment', appt_id=r['id']) }}">Editar</a></td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="alert alert-secondary">Sem consultas no período.</div>
    {% endif %}
    """, rows=rows)
    return render_template_string(BASE_TMPL, title=f"Agenda · {APP_TITLE}", app_title=APP_TITLE, body=body)

@app.route("/agenda/nova", methods=["GET", "POST"])
def new_appointment():
    db = get_db()
    # permite pré-selecionar cliente via querystring ?client_id=1
    client_id_qs = request.args.get("client_id")

    if request.method == "POST":
        client_id = request.form.get("client_id")
        starts_at = request.form.get("starts_at")
        duration_min = int(request.form.get("duration_min") or 60)
        status = request.form.get("status") or "Agendado"
        notes = request.form.get("notes") or None

        if not client_id or not starts_at:
            flash("Cliente e data/hora são obrigatórios.")
        else:
            db.execute(
                "INSERT INTO appointments (client_id, starts_at, duration_min, status, notes, created_at) VALUES (?,?,?,?,?,?)",
                (client_id, starts_at, duration_min, status, notes, datetime.now().strftime("%Y-%m-%dT%H:%M"))
            )
            db.commit()
            flash("Consulta criada!")
            return redirect(url_for("appointments"))

    clients = db.execute("SELECT id, name FROM clients ORDER BY name ASC").fetchall()

    body = render_template_string("""
    <h3>Nova consulta</h3>
    <form method="post" class="mt-3">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Cliente *</label>
          <select name="client_id" class="form-select" required>
            <option value="">Selecione...</option>
            {% for c in clients %}
              <option value="{{ c['id'] }}" {% if request.args.get('client_id') and request.args.get('client_id')|int == c['id'] %}selected{% endif %}>{{ c['name'] }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-label">Data/Hora *</label>
          <input name="starts_at" type="datetime-local" class="form-control" required>
        </div>
        <div class="col-md-3">
          <label class="form-label">Duração (min)</label>
          <input name="duration_min" type="number" min="15" step="15" value="60" class="form-control">
        </div>
        <div class="col-md-3">
          <label class="form-label">Status</label>
          <select name="status" class="form-select">
            <option>Agendado</option>
            <option>Confirmado</option>
            <option>Concluído</option>
            <option>Cancelado</option>
            <option>Não compareceu</option>
          </select>
        </div>
        <div class="col-md-9">
          <label class="form-label">Notas</label>
          <input name="notes" class="form-control" placeholder="Ex.: retorno, primeira avaliação, preferências...">
        </div>
      </div>
      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Salvar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('appointments') }}">Cancelar</a>
      </div>
    </form>
    """, clients=clients)
    return render_template_string(BASE_TMPL, title=f"Nova consulta · {APP_TITLE}", app_title=APP_TITLE, body=body)

@app.route("/agenda/<int:appt_id>/editar", methods=["GET", "POST"])
def edit_appointment(appt_id: int):
    db = get_db()
    cur = db.execute(
        "SELECT a.*, c.name as client_name FROM appointments a JOIN clients c ON c.id=a.client_id WHERE a.id=?",
        (appt_id,)
    )
    appt = cur.fetchone()
    if not appt:
        flash("Consulta não encontrada.")
        return redirect(url_for("appointments"))

    if request.method == "POST":
        starts_at = request.form.get("starts_at")
        duration_min = int(request.form.get("duration_min") or 60)
        status = request.form.get("status")
        notes = request.form.get("notes") or None
        db.execute(
            "UPDATE appointments SET starts_at=?, duration_min=?, status=?, notes=? WHERE id=?",
            (starts_at, duration_min, status, notes, appt_id)
        )
        db.commit()
        flash("Consulta atualizada!")
        return redirect(url_for("appointments"))

    body = render_template_string("""
    <h3>Editar consulta</h3>
    <div class="mb-2 text-muted">Cliente: <strong>{{ appt['client_name'] }}</strong></div>
    <form method="post" class="mt-2">
      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label">Data/Hora</label>
          <input name="starts_at" type="datetime-local" class="form-control" value="{{ appt['starts_at'] }}">
        </div>
        <div class="col-md-2">
          <label class="form-label">Duração (min)</label>
          <input name="duration_min" type="number" min="15" step="15" class="form-control" value="{{ appt['duration_min'] }}">
        </div>
        <div class="col-md-3">
          <label class="form-label">Status</label>
          <select name="status" class="form-select" value="{{ appt['status'] }}">
            {% for s in ['Agendado','Confirmado','Concluído','Cancelado','Não compareceu'] %}
              <option value="{{ s }}" {% if s == appt['status'] %}selected{% endif %}>{{ s }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-12">
          <label class="form-label">Notas</label>
          <input name="notes" class="form-control" value="{{ appt['notes'] or '' }}">
        </div>
      </div>
      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-primary" type="submit">Salvar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('appointments') }}">Cancelar</a>
      </div>
    </form>
    """, appt=appt)
    return render_template_string(BASE_TMPL, title=f"Editar consulta · {APP_TITLE}", app_title=APP_TITLE, body=body)

# ------------------------- Seed opcional (apenas se vazio) -------------------------

@app.cli.command("seed")
def seed():
    """Adicionar alguns dados de exemplo: `flask seed`"""
    db = get_db()
    now = datetime.now()
    # cria 3 clientes
    clients = [("Maria Silva", "1199999-0001", "maria@example.com"),
               ("João Souza", "2198888-0002", "joao@example.com"),
               ("Ana Paula", "3197777-0003", "ana@example.com")]
    for n, p, e in clients:
        db.execute("INSERT INTO clients (name, phone, email, created_at) VALUES (?,?,?,?)",
                   (n, p, e, now.strftime("%Y-%m-%dT%H:%M")))
    db.commit()

    # notas para o primeiro
    c1 = db.execute("SELECT id FROM clients WHERE name=?", ("Maria Silva",)).fetchone()[0]
    db.execute("INSERT INTO notes (client_id, content, created_at) VALUES (?,?,?)",
               (c1, "Primeiro atendimento - avaliação inicial.", now.strftime("%Y-%m-%dT%H:%M")))

    # consultas
    appts = [
        (c1, (now + timedelta(days=1)).strftime("%Y-%m-%dT10:00"), 60, "Confirmado", "Retorno"),
        (c1, (now + timedelta(days=3)).strftime("%Y-%m-%dT14:30"), 45, "Agendado", None),
    ]
    for cid, st, dur, stt, nt in appts:
        db.execute("INSERT INTO appointments (client_id, starts_at, duration_min, status, notes, created_at) VALUES (?,?,?,?,?,?)",
                   (cid, st, dur, stt, nt, now.strftime("%Y-%m-%dT%H:%M")))
    db.commit()
    print("Seed concluído.")

# ------------------------- Main -------------------------

if __name__ == "__main__":
    app.run(debug=True)


# ------------------------- Arquivos de Deploy (Koyeb) -------------------------

# requirements.txt
# salve este conteúdo em um arquivo separado chamado requirements.txt
# (versões fixadas para estabilidade)
"""
flask==3.0.3
gunicorn==21.2.0
"""

# Procfile
# Koyeb (via buildpack) detecta este arquivo para executar seu app
"""
web: gunicorn --bind :$PORT app:app
"""

# Dockerfile (opcional: use se quiser controlar a imagem)
# Se usar o Dockerfile, você pode escolher no Koyeb "Deploy from Dockerfile".
"""
FROM python:3.11-slim

# Evitar prompts interativos
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instalar dependências do sistema (se precisar adicionar build deps, inclua aqui)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requisitos e instalar
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copiar app
COPY . .

# Porta fornecida pelo Koyeb via $PORT; expomos 8000 como padrão local
ENV PORT=8000
EXPOSE 8000

# Comando de execução
CMD ["gunicorn", "--bind", ":$PORT", "app:app"]
"""

# README - Passo a passo de deploy no Koyeb (buildpack/Procfile)
"""
1) Faça login no GitHub e crie um repositório (ex.: crm-flask) contendo:
   - app.py (este arquivo)
   - requirements.txt (conteúdo acima)
   - Procfile (conteúdo acima)

2) Envie o código:
   git init
   git add .
   git commit -m "MVP CRM Flask"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/crm-flask.git
   git push -u origin main

3) No painel do Koyeb:
   - Create > Web Service > GitHub > selecione seu repo.
   - Build: escolha Buildpacks (sem Docker) OU Dockerfile se preferir o arquivo Docker.
   - Run Command (se usar buildpack): gunicorn --bind :$PORT app:app
   - Defina o nome do serviço (ex.: crm-flask) e deploy.

4) Após o deploy, acesse a URL gerada (ex.: https://crm-flask-xxxxx.koyeb.app).

Notas importantes (SQLite):
- Em plataformas com filesystem efêmero, o arquivo crm.sqlite3 pode ser perdido em reinícios/deploys.
- Para produção, considere migrar para Postgres e usar SQLAlchemy + DATABASE_URL.
"""
