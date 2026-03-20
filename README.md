# Diagnóstico IA · HS.

Ferramenta de diagnóstico gratuita para donos de negócio. Entrevista por voz + diagnóstico gerado por IA.

## Pré-requisitos

- Python 3.9 ou superior
- Google Chrome (para a gravação por voz via Web Speech API)

## Instalação

**1. Clone ou abra a pasta do projeto no terminal**

**2. Crie e ative um ambiente virtual**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

**3. Instale as dependências**
```bash
pip install -r requirements.txt
```

**4. Configure as variáveis de ambiente**
```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Abra o .env e insira sua chave da Anthropic
# ANTHROPIC_API_KEY=sk-ant-SUA_CHAVE_AQUI
```

Obtenha sua chave em: https://console.anthropic.com

**5. Rode a aplicação**
```bash
python app.py
```

**6. Acesse no navegador**
```
http://localhost:5000
```

> Use obrigatoriamente o **Google Chrome** para que a gravação por voz funcione.

## Estrutura dos arquivos

```
Operations Agent/
├── app.py              # Servidor Flask
├── requirements.txt    # Dependências Python
├── .env               # Variáveis de ambiente (não versionar)
├── .env.example       # Exemplo de configuração
├── emails.csv         # Criado automaticamente ao primeiro uso
└── templates/
    ├── index.html     # Tela 1 — Landing
    ├── interview.html # Tela 2 — Entrevista por voz
    └── diagnosis.html # Tela 4 — Diagnóstico gerado
```

## Emails coletados

Os emails são salvos automaticamente em `emails.csv` com o modo escolhido e o timestamp.
