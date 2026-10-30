import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from supabase import create_client, Client

# ========= CONFIG =========
logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Estados da conversa
CHAPA, EPI, FOTO, OBS = range(4)

# ========= FUNÇÃO PRINCIPAL: BUSCA FUNCIONÁRIO =========
def buscar_funcionario(chapa_digitada):
    """Busca em funcionarios de 3 jeitos diferentes pra achar 062289, 62289, 100012"""
    if not chapa_digitada:
        return None
    
    chapa_limpa = str(chapa_digitada).strip().replace(" ", "")
    if not chapa_limpa:
        return None

    # Lista de variações pra tentar
    tentativas = list(dict.fromkeys([  # dict.fromkeys remove duplicatas
        chapa_limpa,
        chapa_limpa.lstrip('0'),
        chapa_limpa.zfill(6),  # 62289 -> 062289
        chapa_limpa.zfill(5),
    ]))
    
    for c in tentativas:
        if not c:
            continue
        try:
            res = supabase.table("funcionarios").select("*").eq("chapa", c).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            logging.error(f"Erro busca chapa {c}: {e}")

    # Última tentativa: busca parcial (ex: usuário digitou 62289 e no banco tá 062289)
    try:
        res = supabase.table("funcionarios").select("*").ilike("chapa", f"%{chapa_limpa.lstrip('0')}").limit(1).execute()
        if res.data:
            return res.data[0]
    except:
        pass

    return None

# ========= COMANDOS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👷 *Bot Telemont - Inspeção de Segurança*\n\n"
        "Comandos:\n"
        "/inspecao - Iniciar nova inspeção\n"
        "/cancelar - Cancelar inspeção atual",
        parse_mode='Markdown'
    )

async def inspecao_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🔍 *Nova Inspeção*\n\n"
        "Digite a CHAPA do colaborador (ex: 062289, 100012):",
        parse_mode='Markdown'
    )
    return CHAPA

async def receber_chapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa_digitada = update.message.text
    await update.message.reply_text(f"⏳ Buscando chapa {chapa_digitada}...")

    func = buscar_funcionario(chapa_digitada)

    if func:
        context.user_data['chapa'] = func['chapa']
        context.user_data['nome'] = func['nome']
        context.user_data['cargo'] = func['cargo']
        context.user_data['supervisor'] = func.get('supervisor', 'DESCONHECIDO')
        context.user_data['coordenador'] = func.get('coordenador', 'DESCONHECIDO')
        context.user_data['situacao'] = func.get('situacao', '')

        await update.message.reply_text(
            f"✅ *Funcionário encontrado:*\n\n"
            f"🪪 Chapa: `{func['chapa']}`\n"
            f"👤 Nome: *{func['nome']}*\n"
            f"💼 Cargo: {func['cargo']}\n"
            f"👷 Supervisor: {func.get('supervisor','-')}\n"
            f"👔 Coordenador: {func.get('coordenador','-')}\n\n"
            f"Agora digite a *Não Conformidade / EPI faltante*:\n"
            f"Ex: SEM CAPACETE, SEM LUVA, SEM OCULOS",
            parse_mode='Markdown'
        )
        return EPI
    else:
        context.user_data['chapa'] = chapa_digitada
        context.user_data['nome'] = "NÃO CADASTRADO"
        context.user_data['cargo'] = "NÃO CADASTRADO"
        context.user_data['supervisor'] = "DESCONHECIDO"
        context.user_data['coordenador'] = "DESCONHECIDO"
        
        await update.message.reply_text(
            f"❌ Chapa *{chapa_digitada}* não encontrada na base de 8578 funcionários.\n\n"
            f"Vou continuar como NÃO CADASTRADO.\n"
            f"Digite o EPI / Não conformidade:",
            parse_mode='Markdown'
        )
        return EPI

async def receber_epi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['epi'] = update.message.text.upper()
    await update.message.reply_text(
        "📸 Envie a *foto* da inspeção ou digite /pular se não tiver foto:",
        parse_mode='Markdown'
    )
    return FOTO

async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        # Pega a maior resolução
        foto = update.message.photo[-1]
        context.user_data['foto_id'] = foto.file_id
        context.user_data['tem_foto'] = True
    else:
        context.user_data['tem_foto'] = False
        context.user_data['foto_id'] = None

    await update.message.reply_text("📝 Alguma observação? Digite ou /pular")
    return OBS

async def pular_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tem_foto'] = False
    context.user_data['foto_id'] = None
    await update.message.reply_text("📝 Alguma observação? Digite ou /pular")
    return OBS

async def receber_obs_e_salvar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    obs = "" if update.message.text == "/pular" else update.message.text
    context.user_data['obs'] = obs
    
    # Monta dados para salvar em inspecoes
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
        await update.message.reply_text(
            f"✅ *Inspeção salva com sucesso!*\n\n"
            f"🪪 {dados['chapa']} - {dados['nome']}\n"
            f"⚠️ {dados['epi_faltante']}\n\n"
            f"Digite /inspecao para nova inspeção.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Erro ao salvar: {e}")
        await update.message.reply_text(f"❌ Erro ao salvar: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Inspeção cancelada. /inspecao para começar nova.")
    return ConversationHandler.END

# ========= MAIN =========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("inspecao", inspecao_start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_chapa)],
            EPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_epi)],
            FOTO: [
                MessageHandler(filters.PHOTO, receber_foto),
                CommandHandler("pular", pular_foto)
            ],
            OBS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_obs_e_salvar),
                CommandHandler("pular", receber_obs_e_salvar)
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("cancelar", cancelar))

    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
