import os
import io
import csv
import uuid
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


def save_email(email, mode):
    filepath = 'emails.csv'
    file_exists = os.path.exists(filepath)
    with open(filepath, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['email', 'mode', 'timestamp'])
        writer.writerow([email, mode, datetime.now().isoformat()])


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
    save_email(email, mode)

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

    prompt = f"""Você é um consultor especialista em implementação de Inteligência Artificial em pequenas e médias empresas brasileiras. Você tem 15 anos de experiência e trabalha com empresas de diversos setores.

Você acabou de conduzir uma entrevista diagnóstica com um dono de negócio. Aqui estão as perguntas e respostas da entrevista:

{qa_text}

Com base nessas respostas, crie um documento de diagnóstico completo, personalizado e de alta qualidade. Siga exatamente esta estrutura:

## Visão do Negócio

Descreva em detalhes o que esta empresa faz, como opera e qual é o seu posicionamento. Use as informações específicas da entrevista — nunca escreva de forma genérica. O leitor deve reconhecer a própria empresa neste texto.

## Mapa de Processos

Identifique e descreva os principais processos operacionais desta empresa com base nas respostas. Explique como cada processo funciona hoje, onde são os gargalos e qual é o impacto disso na operação.

## Quick Wins com IA

Apresente exatamente 2 ou 3 oportunidades concretas de curto prazo onde a inteligência artificial pode gerar impacto imediato neste negócio específico. Para cada oportunidade, explique o que seria feito, como funcionaria na prática e qual seria o resultado esperado.

## Visão de Longo Prazo

Descreva como este negócio poderia operar em 2 a 3 anos com agentes de IA integrados à operação. Seja específico ao setor e ao que foi descrito na entrevista.

## Diagrama de Fluxo Operacional

Crie um diagrama visual do fluxo operacional deste negócio. Use EXATAMENTE este formato JSON dentro de um bloco de código com a linguagem "diagram-visual". Entre 4 e 7 steps. Escolha emojis relevantes ao setor e ao processo específico:

```diagram-visual
{
  "steps": [
    {"icon": "📥", "label": "Nome do processo", "detail": "detalhe curto e específico"},
    {"icon": "⚙️", "label": "Nome do processo", "detail": "detalhe curto e específico"}
  ]
}
```

## Próximos Passos

Escreva 3 parágrafos — um para cada ação concreta e sequenciada com prazo estimado. Cada parágrafo começa com o nome da ação em negrito. Sem listas numeradas, sem bullet points — apenas parágrafos corridos.

## A Janela de Oportunidade

Escreva um parágrafo final em tom de copy direto, urgente e persuasivo — completamente diferente do tom consultivo usado até aqui. Deixe claro que a orquestração de agentes de IA é o que vai separar as empresas que prosperam das que ficam para trás. Explique que tudo descrito neste diagnóstico só se materializa em escala real quando múltiplos agentes autônomos trabalham juntos. Crie senso de urgência genuíno. Convide o empresário a agir agora, não amanhã. Tom: direto, sem suavização, quase provocador — como quem sabe o que está vindo e quer que o outro também saiba.

---

Regras de estilo obrigatórias:
- Escreva em português brasileiro
- Tom consultivo, direto e premium — como um consultor sênior escreveria para um executivo
- Prosa corrida em parágrafos — sem bullet points, listas ou enumerações
- Voz ativa, frases diretas e objetivas
- Cada afirmação deve ser específica a este negócio — nunca genérica ou aplicável a qualquer empresa
- Não use jargões técnicos desnecessários
- Trate o leitor como um adulto inteligente que quer soluções práticas, não teoria"""

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


if __name__ == '__main__':
    app.run(debug=True, port=5000)
