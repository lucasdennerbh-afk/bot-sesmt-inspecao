import os
import threading
import logging
from datetime import datetime
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from supabase import create_client, Client

# CONFIG
logging.basicConfig(level=logging.INFO)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

CHAPA, EPI, FOTO, OBS = range(4)

# FLASK - PRA MOSTRAR O DASHBOARD NO RENDER
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app_flask.route('/dashboard.html')
def dash():
    return send_from_directory('.', 'dashboard.html')

# FUNÇÃO QUE ACHA A CHAPA (062289, 100012, etc)
def buscar_funcionario(chapa_digitada):
    if not chapa_digitada or not supabase:
        return None
    chapa_limpa = str(chapa_digitada).strip()
    tentativas = list(dict.fromkeys([
        chapa_limpa,
        chapa_limpa.lstrip('0'),
        chapa_limpa.zfill(6),
        chapa_limpa.zfill(5)
    ]))
    for c in tentativas:
        if not c: continue
        try:
            res = supabase.table("funcionarios").select("*").eq("chapa", c).execute()
            if res.data: return res.data[0]
        except Exception as e:
            logging.error(f"Erro busca {c}: {e}")
    return None

# COMANDOS TELEGRAM
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👷 *Bot SESMT - Inspeção*\n\n"
        "/inspecao - Nova inspeção\n"
        "/cancelar - Cancelar\n\n"
        "Dashboard: no link do Render",
        parse_mode='Markdown'
    )

async def inspecao_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔍 Digite a CHAPA (ex: 100012, 062289):")
    return CHAPA

async def receber_chapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa_digitada = update.message.text
    await update.message.reply_text(f"⏳ Buscando {chapa_digitada}...")
    func = buscar_funcionario(chapa_digitada)
    if func:
        context.user_data['chapa'] = func['chapa']
        context.user_data['nome'] = func['nome']
        context.user_data['cargo'] = func['cargo']
        context.user_data['supervisor'] = func.get('supervisor','DESCONHECIDO')
        context.user_data['coordenador'] = func.get('coordenador','DESCONHECIDO')
        await update.message.reply_text(
            f"✅ *Encontrado:*\n🪪 {func['chapa']}\n👤 {func['nome']}\n💼 {func['cargo']}\n👷 {func.get('supervisor','-')}\n\nDigite o EPI / Não Conformidade:",
            parse_mode='Markdown'
        )
        return EPI
    else:
        context.user_data['chapa'] = chapa_digitada
        context.user_data['nome'] = "NÃO CADASTRADO"
        context.user_data['cargo'] = "NÃO CADASTRADO"
        context.user_data['supervisor'] = "DESCONHECIDO"
        context.user_data['coordenador'] = "DESCONHECIDO"
        await update.message.reply_text(f"❌ Chapa {chapa_digitada} não encontrada. Digite o EPI:")
        return EPI

async def receber_epi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['epi'] = update.message.text.upper()
    await update.message.reply_text("📸 Envie a foto ou /pular:")
    return FOTO

async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['foto_id'] = update.message.photo[-1].file_id
    else:
        context.user_data['foto_id'] = None
    await update.message.reply_text("📝 Observação? Digite ou /pular")
    return OBS

async def pular_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['foto_id'] = None
    await update.message.reply_text("📝 Observação? Digite ou /pular")
    return OBS

async def salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    obs = "" if update.message.text == "/pular" else update.message.text
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
        if supabase:
            supabase.table("inspecoes").insert(dados).execute()
        await update.message.reply_text(f"✅ Salvo!\n🪪 {dados['chapa']} - {dados['nome']}\n⚠️ {dados['epi_faltante']}\n\n/inspecao para nova", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao salvar: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado. /inspecao para nova.")
    return ConversationHandler.END

def run_bot():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN não configurado!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("inspecao", inspecao_start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_chapa)],
            EPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_epi)],
            FOTO: [MessageHandler(filters.PHOTO, receber_foto), CommandHandler("pular", pular_foto)],
            OBS: [MessageHandler(filters.TEXT & ~filters.COMMAND, salvar), CommandHandler("pular", salvar)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("cancelar", cancelar))
    logging.info("Bot Telegram rodando...")
    app.run_polling()

if __name__ == "__main__":
    # Roda bot em thread separada
    threading.Thread(target=run_bot, daemon=True).start()
    # Roda Flask na porta do Render
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)
