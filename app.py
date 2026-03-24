import os
import io
import csv
import uuid
import psycopg2
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'hs-diagnostico-secret-local')


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({'error': str(e)}), 500


# ── Database ──────────────────────────────────────────────

def get_db():
    url = os.environ.get('DATABASE_URL')
    if not url:
        return None
    # Render usa postgres://, psycopg2 precisa de postgresql://
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return psycopg2.connect(url)


def init_db():
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            mode VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()


def save_lead(email, mode):
    conn = get_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO leads (email, mode) VALUES (%s, %s)',
                (email, mode)
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
    else:
        # fallback CSV para desenvolvimento local
        filepath = 'emails.csv'
        file_exists = os.path.exists(filepath)
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['email', 'mode', 'timestamp'])
            writer.writerow([email, mode, datetime.now().isoformat()])

QUESTIONS_SHORT = [
    "Me conta o que você faz e como o seu negócio funciona no dia a dia.",
    "Quais são as tarefas que mais consomem tempo — seu e da sua equipe?",
    "Onde as coisas travam ou se perdem com mais frequência?"
]

QUESTIONS_FULL = QUESTIONS_SHORT + [
    "Como é o seu processo de vendas hoje — do primeiro contato até o cliente pagar?",
    "Você tem alguma forma de acompanhar o desempenho do negócio — números, metas, indicadores?",
    "Se eu te dissesse que daqui a 3 anos seus concorrentes vão operar com o dobro da eficiência usando IA, o que você faria diferente hoje?"
]

# In-memory store for diagnoses (local use only)
diagnoses_store = {}




@app.route('/')
def home():
    return render_template('home.html')


@app.route('/diagnostico')
def index():
    return render_template('index.html')


@app.route('/interview')
def interview():
    email = request.args.get('email', '').strip()
    mode = request.args.get('mode', 'quick')

    if not email:
        return redirect(url_for('index'))

    if mode not in ('quick', 'full'):
        mode = 'quick'

    questions = QUESTIONS_SHORT if mode == 'quick' else QUESTIONS_FULL
    save_lead(email, mode)

    return render_template('interview.html', questions=questions, mode=mode, email=email)


@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json(silent=True) or {}
        transcriptions = data.get('transcriptions', [])
        questions = data.get('questions', [])

        if not transcriptions or not questions:
            return jsonify({'error': 'Dados incompletos.'}), 400

        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return jsonify({'error': 'Chave da API não configurada.'}), 500

        qa_text = ""
        for i, (q, a) in enumerate(zip(questions, transcriptions), 1):
            qa_text += f"\nPergunta {i}: {q}\nResposta do empresário: {a}\n"

        prompt = """Você é um consultor sênior em IA para PMEs brasileiras. Conduziu uma entrevista diagnóstica com um empresário. Respostas:

__QA_TEXT__

Crie um diagnóstico objetivo e personalizado. Seja específico ao negócio — nunca genérico. Prosa corrida, sem bullet points, português brasileiro, voz ativa. Cada seção: no máximo 2 parágrafos curtos.

## Visão do Negócio
O que a empresa faz, como opera e seu posicionamento. O dono deve se reconhecer no texto.

## Mapa de Processos
Principais processos hoje, onde travam e qual o impacto real disso.

## Quick Wins com IA
Exatamente 2 oportunidades de curto prazo: o que seria feito, como funciona na prática e resultado esperado.

## Visão de Longo Prazo
Como o negócio operaria em 2 anos com agentes de IA. Um parágrafo, específico ao setor.

## Diagrama de Fluxo Operacional

```diagram-visual
{
  "steps": [
    {"icon": "📥", "label": "Nome do processo", "detail": "detalhe curto e específico"},
    {"icon": "⚙️", "label": "Nome do processo", "detail": "detalhe curto e específico"}
  ]
}
```
Entre 4 e 7 steps com emojis relevantes ao setor.

## Próximos Passos
3 parágrafos curtos — uma ação cada, com prazo estimado. Cada um começa com o nome da ação em negrito.

## A Janela de Oportunidade
Um parágrafo: tom direto e urgente. Quem não agir agora vai ficar para trás. Sem suavização.""".replace("__QA_TEXT__", qa_text)

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        diagnosis = response.text

        token = str(uuid.uuid4())
        diagnoses_store[token] = diagnosis

        return jsonify({'success': True, 'token': token})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/diagnosis')
def diagnosis_page():
    token = request.args.get('token', '')
    diag = diagnoses_store.get(token, '')
    if not diag:
        return redirect(url_for('index'))
    return render_template('diagnosis.html', diagnosis=diag)


@app.route('/download-pdf', methods=['POST'])
def download_pdf():
    data = request.get_json()
    diagnosis_text = data.get('diagnosis', '')

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.enums import TA_JUSTIFY

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=3 * cm, leftMargin=3 * cm,
        topMargin=3 * cm, bottomMargin=3 * cm
    )

    GOLD = HexColor('#C9A84C')
    BLACK = HexColor('#1A1A1A')
    GRAY = HexColor('#666666')

    logo_style = ParagraphStyle('Logo', fontName='Helvetica-Bold', fontSize=28, textColor=BLACK, spaceAfter=16, leading=34)
    logo_sub_style = ParagraphStyle('LogoSub', fontName='Helvetica', fontSize=10, textColor=GOLD, spaceAfter=20)
    date_style = ParagraphStyle('Date', fontName='Helvetica', fontSize=9, textColor=GRAY, spaceAfter=24)
    h2_style = ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=14, textColor=BLACK, spaceBefore=24, spaceAfter=10)
    body_style = ParagraphStyle('Body', fontName='Helvetica', fontSize=10, textColor=BLACK, leading=17, spaceAfter=10, alignment=TA_JUSTIFY)
    cta_style = ParagraphStyle('CTA', fontName='Helvetica-Bold', fontSize=11, textColor=BLACK, spaceBefore=20, spaceAfter=6)
    cta_email_style = ParagraphStyle('CTAEmail', fontName='Helvetica', fontSize=10, textColor=GOLD, spaceAfter=20)

    story = []
    story.append(Paragraph("HS.", logo_style))
    story.append(Paragraph("Diagnóstico IA · Henrique Schütz", logo_sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=16))
    story.append(Paragraph(f"Diagnóstico gerado em {datetime.now().strftime('%d/%m/%Y')}", date_style))

    note_style = ParagraphStyle('Note', fontName='Helvetica-Oblique', fontSize=9, textColor=GRAY, spaceAfter=10)
    in_code_block = False
    for line in diagnosis_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('```'):
            if not in_code_block:
                in_code_block = True
                if 'mermaid' in stripped or 'diagram-visual' in stripped:
                    story.append(Paragraph('[Diagrama disponível na versão web do diagnóstico]', note_style))
            else:
                in_code_block = False
            continue
        if in_code_block:
            continue
        if not stripped:
            story.append(Spacer(1, 0.2 * cm))
            continue
        if stripped.startswith('## '):
            story.append(Paragraph(stripped[3:], h2_style))
        elif stripped.startswith('# '):
            story.append(Paragraph(stripped[2:], h2_style))
        elif stripped == '---':
            story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceAfter=8))
        else:
            clean = stripped.replace('**', '').replace('*', '')
            if clean.strip():
                story.append(Paragraph(clean, body_style))

    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=16))
    story.append(Paragraph("Quer implementar isso? Fale com Henrique Schütz.", cta_style))
    story.append(Paragraph("henrique@henriqueschutz.com", cta_email_style))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'diagnostico-ia-{datetime.now().strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )


@app.route('/leads')
def leads():
    senha = request.args.get('key', '')
    if senha != os.environ.get('LEADS_KEY', ''):
        return 'Acesso negado.', 401

    conn = get_db()
    if not conn:
        return 'Banco de dados não configurado.', 500

    cur = conn.cursor()
    cur.execute('SELECT id, email, mode, created_at FROM leads ORDER BY created_at DESC')
    rows = cur.fetchall()
    cur.close()
    conn.close()

    html = '''<!DOCTYPE html><html><head>
    <meta charset="UTF-8">
    <title>Leads · HS.</title>
    <style>
        body { font-family: sans-serif; padding: 32px; background: #f9f9f9; color: #1a1a1a; }
        h1 { margin-bottom: 24px; font-size: 20px; }
        table { border-collapse: collapse; width: 100%; background: white; border-radius: 6px; overflow: hidden; }
        th { background: #1a1a1a; color: white; padding: 10px 16px; text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        td { padding: 10px 16px; border-bottom: 1px solid #eee; font-size: 14px; }
        tr:last-child td { border-bottom: none; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
        .quick { background: #e8f5e9; color: #2e7d32; }
        .full  { background: #e3f2fd; color: #1565c0; }
    </style></head><body>'''
    html += f'<h1>Leads ({len(rows)})</h1><table>'
    html += '<tr><th>#</th><th>Email</th><th>Modo</th><th>Data</th></tr>'
    for row in rows:
        mode_class = 'quick' if row[2] == 'quick' else 'full'
        mode_label = 'Rápido' if row[2] == 'quick' else 'Completo'
        dt = row[3].strftime('%d/%m/%Y %H:%M') if row[3] else '—'
        html += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td><span class="badge {mode_class}">{mode_label}</span></td><td>{dt}</td></tr>'
    html += '</table></body></html>'
    return html


init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
