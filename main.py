import os
import threading
import logging
import time
from datetime import datetime
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cimfbcbvvtdgplyxrvc.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logging.info(f"Supabase conectado: {SUPABASE_URL}")
    else:
        logging.error(f"SUPABASE_KEY ou URL faltando! URL={SUPABASE_URL} KEY_exists={bool(SUPABASE_KEY)}")
except Exception as e:
    logging.error(f"Erro Supabase: {e}")

CHAPA, EPI, FOTO, OBS = range(4)

app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    if os.path.exists('dashboard.html'):
        return send_from_directory('.', 'dashboard.html')
    return "<h1>Bot SESMT Live - OK</h1><a href='/health'>Health</a>"

@app_flask.route('/dashboard.html')
def dash():
    return send_from_directory('.', 'dashboard.html')

@app_flask.route('/health')
def health():
    return "OK", 200

def buscar_funcionario(chapa_digitada):
    if not chapa_digitada:
        return None
    if not supabase:
        logging.error("Supabase client é None!")
        return None
    
    chapa_limpa = str(chapa_digitada).strip()
    logging.info(f"BUSCANDO CHAPA: '{chapa_limpa}'")
    
    # Todas as variações possíveis
    tentativas = []
    tentativas.append(chapa_limpa)
    tentativas.append(chapa_limpa.lstrip('0'))
    tentativas.append(chapa_limpa.zfill(6))
    tentativas.append(chapa_limpa.zfill(5))
    # Remove duplicatas mantendo ordem
    tentativas = list(dict.fromkeys([t for t in tentativas if t]))
    
    for c in tentativas:
        try:
            logging.info(f"  Tentando eq chapa='{c}'")
            res = supabase.table("funcionarios").select("*").eq("chapa", c).limit(1).execute()
            if res.data:
                logging.info(f"  ACHOU com '{c}': {res.data[0].get('nome')}")
                return res.data[0]
        except Exception as e:
            logging.error(f"  Erro eq {c}: {e}")

        # Tenta buscar sem case sensitive (se a coluna tiver espaços)
        try:
            res = supabase.table("funcionarios").select("*").ilike("chapa", c).limit(1).execute()
            if res.data:
                logging.info(f"  ACHOU com ilike '{c}'")
                return res.data[0]
        except Exception as e:
            logging.error(f"  Erro ilike {c}: {e}")

    logging.warning(f"NENHUMA tentativa achou {chapa_digitada}")
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👷 BOT SESMT - TELEMONT\n\n/inspecao - Nova inspeção\n/cancelar - Cancelar")

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
        await update.message.reply_text(
            f"✅ ENCONTRADO\n"
            f"🪪 {func.get('chapa')}\n"
            f"👤 {func.get('nome')}\n"
            f"💼 {func.get('cargo')}\n"
            f"👷 {func.get('supervisor')}\n\n"
            f"Digite o EPI faltante:"
        )
        return EPI
    else:
        context.user_data['chapa'] = chapa_digitada
        context.user_data['nome'] = "NÃO CADASTRADO"
        context.user_data['cargo'] = "NÃO CADASTRADO"
        context.user_data['supervisor'] = "DESCONHECIDO"
        context.user_data['coordenador'] = "DESCONHECIDO"
        await update.message.reply_text(f"⚠️ Chapa {chapa_digitada} não encontrada no Supabase. Vou salvar como NÃO CADASTRADO.\nDigite o EPI:")
        return EPI

async def receber_epi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['epi'] = update.message.text.upper()
    await update.message.reply_text("📸 Envie a FOTO ou /pular")
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
        logging.error(f"Erro ao salvar inspeção: {e}")
        await update.message.reply_text(f"❌ Erro ao salvar: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado. /inspecao para nova")
    return ConversationHandler.END

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"Flask rodando na porta {port}")
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def run_bot():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN faltando no Environment!")
        return
    
    logging.info(f"SUPABASE_URL: {SUPABASE_URL}")
    logging.info(f"SUPABASE_KEY existe: {bool(SUPABASE_KEY)}")
    
    if supabase:
        try:
            teste = supabase.table("funcionarios").select("chapa", count="exact").limit(1).execute()
            logging.info(f"TESTE CONEXAO OK: {teste.count} funcionarios na base")
        except Exception as e:
            logging.error(f"ERRO TESTE CONEXAO: {e}")

    while True:
        try:
            logging.info("Iniciando bot polling...")
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
            app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logging.error(f"ERRO BOT (tentando reconectar em 5s): {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    run_bot()
