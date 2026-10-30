import os
import threading
import logging
from datetime import datetime
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cimfbcbvvtdgplyxrvc.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase: Client = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Erro Supabase: {e}")

CHAPA, EPI, FOTO, OBS = range(4)

# FLASK - Isso faz o Render não dar Failed
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    if os.path.exists('dashboard.html'):
        return send_from_directory('.', 'dashboard.html')
    return "<h1>Bot SESMT Live</h1><p><a href='/dashboard.html'>Ver Dashboard</a></p>"

@app_flask.route('/dashboard.html')
def dash():
    return send_from_directory('.', 'dashboard.html')

@app_flask.route('/dashboard.htmlml')
def dash_ml():
    return send_from_directory('.', 'dashboard.htmlml')

@app_flask.route('/health')
def health():
    return "OK", 200

# BUSCA CHAPA QUE RESOLVE 062289, 100012
def buscar_funcionario(chapa_digitada):
    if not chapa_digitada:
        return None
    chapa_limpa = str(chapa_digitada).strip()
    tentativas = []
    tentativas.append(chapa_limpa)
    tentativas.append(chapa_limpa.lstrip('0'))
    if chapa_limpa.isdigit():
        tentativas.append(chapa_limpa.zfill(6))
        tentativas.append(chapa_limpa.zfill(5))
        tentativas.append(chapa_limpa.zfill(4))
    tentativas = list(dict.fromkeys([t for t in tentativas if t]))

    if not supabase:
        try:
            import pandas as pd
            if os.path.exists('funcionarios.csv'):
                df = pd.read_csv('funcionarios.csv', dtype=str)
                for t in tentativas:
                    found = df[df['chapa'].astype(str).str.strip() == t]
                    if not found.empty:
                        return found.iloc[0].to_dict()
        except Exception as e:
            print(e)
        return None

    for c in tentativas:
        try:
            res = supabase.table("funcionarios").select("*").eq("chapa", c).limit(1).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except:
            continue
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👷 *BOT SESMT - TELEMONT*\n\n"
        "/inspecao - Nova inspeção\n"
        "/dashboard - Link Dashboard\n"
        "/cancelar - Cancelar\n\n"
        "✅ Já busca 062289, 100012!",
        parse_mode='Markdown'
    )

async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = os.getenv("RENDER_EXTERNAL_URL", "https://bot-sesmt-inspecao.onrender.com")
    await update.message.reply_text(f"📊 Dashboard: {url}/")

async def inspecao_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔍 *Digite a CHAPA:*\nEx: 100012, 062289", parse_mode='Markdown')
    return CHAPA

async def receber_chapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa_digitada = update.message.text.strip()
    await update.message.reply_text(f"⏳ Buscando {chapa_digitada}...")
    func = buscar_funcionario(chapa_digitada)

    if func:
        nome = func.get('nome') or func.get('NOME') or "N/A"
        cargo = func.get('cargo') or "N/A"
        supervisor = func.get('supervisor') or "DESCONHECIDO"
        coordenador = func.get('coordenador') or "DESCONHECIDO"
        chapa_real = func.get('chapa') or chapa_digitada

        context.user_data['chapa'] = str(chapa_real)
        context.user_data['nome'] = str(nome)
        context.user_data['cargo'] = str(cargo)
        context.user_data['supervisor'] = str(supervisor)
        context.user_data['coordenador'] = str(coordenador)

        await update.message.reply_text(
            f"✅ *ENCONTRADO*\n\n🪪 {chapa_real}\n👤 {nome}\n💼 {cargo}\n👷 {supervisor}\n\n⚠️ Digite o EPI:",
            parse_mode='Markdown'
        )
        return EPI
    else:
        context.user_data['chapa'] = chapa_digitada
        context.user_data['nome'] = "NÃO CADASTRADO"
        context.user_data['cargo'] = "NÃO CADASTRADO"
        context.user_data['supervisor'] = "DESCONHECIDO"
        context.user_data['coordenador'] = "DESCONHECIDO"
        await update.message.reply_text(f"⚠️ Chapa {chapa_digitada} não encontrada. Digite o EPI:")
        return EPI

async def receber_epi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['epi'] = update.message.text.upper().strip()
    await update.message.reply_text("📸 Envie a FOTO ou /pular:")
    return FOTO

async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['foto_id'] = update.message.photo[-1].file_id
    await update.message.reply_text("📝 Observação? Digite ou /pular")
    return OBS

async def pular_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['foto_id'] = None
    await update.message.reply_text("📝 Observação? Digite ou /pular")
    return OBS

async def salvar_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    obs_text = "" if not update.message or update.message.text == "/pular" else update.message.text
    dados = {
        "chapa": context.user_data.get('chapa', '0'),
        "nome": context.user_data.get('nome', 'NÃO CADASTRADO'),
        "cargo": context.user_data.get('cargo', 'NÃO CADASTRADO'),
        "supervisor": context.user_data.get('supervisor', 'DESCONHECIDO'),
        "coordenador": context.user_data.get('coordenador', 'DESCONHECIDO'),
        "epi_faltante": context.user_data.get('epi', 'NÃO INFORMADO'),
        "observacao": obs_text,
        "foto_telegram_id": context.user_data.get('foto_id'),
        "data_inspecao": datetime.now().isoformat(),
        "inspetor_nome": update.effective_user.full_name if update.effective_user else "Desconhecido",
        "inspetor_id": str(update.effective_user.id) if update.effective_user else "0"
    }
    try:
        if supabase:
            supabase.table("inspecoes").insert(dados).execute()
        await update.message.reply_text(f"✅ SALVO! {dados['chapa']} - {dados['nome']} - {dados['epi_faltante']}\n\n/inspecao para nova", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado. /inspecao para nova.")
    return ConversationHandler.END

def run_bot():
    if not BOT_TOKEN:
        print("BOT_TOKEN não configurado!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("inspecao", inspecao_start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_chapa)],
            EPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_epi)],
            FOTO: [MessageHandler(filters.PHOTO, receber_foto), CommandHandler("pular", pular_foto)],
            OBS: [MessageHandler(filters.TEXT & ~filters.COMMAND, salvar_final), CommandHandler("pular", salvar_final)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(conv)
    app.add_handler(CommandHandler("cancelar", cancelar))
    print("Bot rodando...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)
