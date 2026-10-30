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

supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Erro Supabase: {e}")

CHAPA, EPI, FOTO, OBS = range(4)

app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    if os.path.exists('dashboard.html'):
        return send_from_directory('.', 'dashboard.html')
    return "<h1>Bot SESMT Live</h1>"

@app_flask.route('/dashboard.html')
def dash():
    return send_from_directory('.', 'dashboard.html')

@app_flask.route('/health')
def health():
    return "OK", 200

def buscar_funcionario(chapa_digitada):
    if not chapa_digitada or not supabase:
        return None
    chapa_limpa = str(chapa_digitada).strip()
    tentativas = [chapa_limpa, chapa_limpa.lstrip('0'), chapa_limpa.zfill(6), chapa_limpa.zfill(5)]
    tentativas = list(dict.fromkeys([t for t in tentativas if t]))
    for c in tentativas:
        try:
            res = supabase.table("funcionarios").select("*").eq("chapa", c).limit(1).execute()
            if res.data:
                return res.data[0]
        except:
            continue
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👷 BOT SESMT - TELEMONT\n\n/inspecao - Nova inspeção\n/dashboard - Dashboard\n/cancelar - Cancelar", parse_mode='Markdown')

async def inspecao_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔍 Digite a CHAPA: Ex: 100012, 062289")
    return CHAPA

async def receber_chapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa_digitada = update.message.text.strip()
    await update.message.reply_text(f"⏳ Buscando {chapa_digitada}...")
    func = buscar_funcionario(chapa_digitada)
    if func:
        context.user_data['chapa'] = str(func.get('chapa'))
        context.user_data['nome'] = str(func.get('nome'))
        context.user_data['cargo'] = str(func.get('cargo'))
        context.user_data['supervisor'] = str(func.get('supervisor','DESCONHECIDO'))
        context.user_data['coordenador'] = str(func.get('coordenador','DESCONHECIDO'))
        await update.message.reply_text(f"✅ ENCONTRADO\n🪪 {func.get('chapa')}\n👤 {func.get('nome')}\n💼 {func.get('cargo')}\n👷 {func.get('supervisor')}\n\nDigite o EPI:", parse_mode='Markdown')
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
    context.user_data['epi'] = update.message.text.upper()
    await update.message.reply_text("📸 Envie a FOTO ou /pular")
    return FOTO

async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['foto_id'] = update.message.photo[-1].file_id
    await update.message.reply_text("📝 Observação? /pular")
    return OBS

async def pular_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['foto_id'] = None
    await update.message.reply_text("📝 Observação? /pular")
    return OBS

async def salvar_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    obs = "" if not update.message or update.message.text == "/pular" else update.message.text
    dados = {
        "chapa": context.user_data.get('chapa'),
        "nome": context.user_data.get('nome'),
        "cargo": context.user_data.get('cargo'),
        "supervisor": context.user_data.get('supervisor'),
        "coordenador": context.user_data.get('coordenador'),
        "epi_faltante": context.user_data.get('epi'),
        "observacao": obs,
        "foto_telegram_id": context.user_data.get('foto_id'),
        "data_inspecao": datetime.now().isoformat(),
        "inspetor_nome": update.effective_user.full_name,
        "inspetor_id": str(update.effective_user.id)
    }
    try:
        supabase.table("inspecoes").insert(dados).execute()
        await update.message.reply_text(f"✅ SALVO! {dados['chapa']} - {dados['nome']}\n/inspecao para nova")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado. /inspecao")
    return ConversationHandler.END

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def run_bot():
    if not BOT_TOKEN:
        print("BOT_TOKEN faltando!")
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
    app.add_handler(conv)
    app.add_handler(CommandHandler("cancelar", cancelar))
    print("Bot rodando em polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # CORREÇÃO: Flask na thread secundária, Bot na main thread
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
